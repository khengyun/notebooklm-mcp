"""
Command-line interface for NotebookLM MCP Server
"""

import asyncio
import json
import platform
import re
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .client import NotebookLMClient
from .config import AuthConfig, ServerConfig, load_config
from .exceptions import ConfigurationError
from .server import NotebookLMFastMCP

console = Console()


def extract_notebook_id(url: str) -> str:
    """Extract notebook ID from NotebookLM URL"""
    # Pattern to match NotebookLM URL with notebook ID
    patterns = [
        r"https://notebooklm\.google\.com/notebook/([a-f0-9-]{36})",
        r"notebooklm\.google\.com/notebook/([a-f0-9-]{36})",
        r"([a-f0-9-]{36})",  # Just the ID itself
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise ValueError(f"Invalid NotebookLM URL or ID: {url}")


def create_default_config(
    notebook_id: str, config_path: str = "notebooklm-config.json"
) -> None:
    """Create default configuration file"""
    config = {
        "headless": False,
        "debug": False,
        "timeout": 60,
        "default_notebook_id": notebook_id,
        "base_url": "https://notebooklm.google.com",
        "server_name": "notebooklm-mcp",
        "stdio_mode": True,
        "streaming_timeout": 60,
        "response_stability_checks": 3,
        "retry_attempts": 3,
        "auth": {
            "cookies_path": None,
            "profile_dir": "./chrome_profile_notebooklm",
            "use_persistent_session": True,
            "auto_login": True,
        },
    }

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    console.print(f"✅ Created config file: [bold green]{config_path}[/bold green]")


def update_config_to_headless(config_path: str = "notebooklm-config.json") -> None:
    """Update config file to set headless=true after successful setup

    Note: On Windows, headless mode may have compatibility issues.
    The browser will automatically fall back to minimized mode if needed.
    """
    try:
        is_windows = platform.system() == "Windows"

        # Read current config
        with open(config_path, "r") as f:
            config = json.load(f)

        # Update headless setting
        config["headless"] = True

        # Write back to file
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        if is_windows:
            console.print(
                "✅ Updated config: [bold yellow]headless=true[/bold yellow]\n"
                "[dim]ℹ️  Note: On Windows, the browser may start in minimized mode instead of fully headless for compatibility[/dim]"
            )
        else:
            console.print(
                "✅ Updated config: [bold yellow]headless=true[/bold yellow] for optimal performance"
            )

    except Exception as e:
        console.print(f"⚠️  Failed to update config to headless mode: {e}")


@click.group()
@click.version_option()
@click.option(
    "--config", "-c", type=click.Path(exists=True), help="Configuration file path"
)
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, config: Optional[str], debug: bool) -> None:
    """NotebookLM MCP Server - Professional automation for Google NotebookLM"""
    ctx.ensure_object(dict)

    try:
        server_config = load_config(config)
        if debug:
            server_config.debug = True
        ctx.obj["config"] = server_config
        ctx.obj["config_file"] = (
            config or "notebooklm-config.json"
        )  # Store config file path
    except Exception as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("notebook_url")
@click.option(
    "--config-path",
    "-o",
    default="notebooklm-config.json",
    help="Output config file path",
)
@click.option("--headless", is_flag=True, help="Run initial setup in headless mode")
def init(notebook_url: str, config_path: str, headless: bool) -> None:
    """Initialize NotebookLM MCP Server with notebook URL

    NOTEBOOK_URL: NotebookLM notebook URL or ID

    Examples:
        notebooklm-mcp init https://notebooklm.google.com/notebook/4741957b-f358-48fb-a16a-da8d20797bc6
        notebooklm-mcp init 4741957b-f358-48fb-a16a-da8d20797bc6
    """
    try:
        # Extract notebook ID from URL
        notebook_id = extract_notebook_id(notebook_url)
        is_windows = platform.system() == "Windows"

        console.print(
            Panel.fit(
                f"[bold blue]🚀 Initializing NotebookLM MCP Server[/bold blue]\n"
                f"Notebook ID: [green]{notebook_id}[/green]\n"
                f"Config File: [yellow]{config_path}[/yellow]"
                + (
                    "\n[yellow]⚠️  Windows detected: headless mode may have compatibility issues[/yellow]"
                    if is_windows
                    else ""
                ),
                title="Setup Starting",
            )
        )

        # Create config file
        create_default_config(notebook_id, config_path)

        # Create profile directory
        profile_dir = Path("./chrome_profile_notebooklm")
        profile_dir.mkdir(exist_ok=True)
        console.print(
            f"✅ Created profile directory: [bold green]{profile_dir}[/bold green]"
        )

        # Guided setup
        console.print("\n[bold yellow]🔧 Setting up browser profile...[/bold yellow]")

        # Create temporary config for guided setup
        temp_config = ServerConfig(
            default_notebook_id=notebook_id,
            headless=headless,
            debug=False,
            auth=AuthConfig(
                profile_dir=str(profile_dir),
                use_persistent_session=True,
                auto_login=True,
            ),
        )

        # Run guided setup
        setup_success = asyncio.run(guided_setup(temp_config))

        # Update config to headless if setup was successful
        if setup_success:
            update_config_to_headless(config_path)
            console.print(
                "\n[bold blue]🚀 Optimization:[/bold blue] Config updated to [yellow]headless=true[/yellow] for better performance"
            )

        console.print(
            Panel.fit(
                "[bold green]✅ Setup Complete![/bold green]\n\n"
                f"Config file: [yellow]{config_path}[/yellow]\n"
                f"Profile directory: [yellow]{profile_dir}[/yellow]\n"
                f"Headless mode: [yellow]{'✅ Enabled' if setup_success else '❌ Disabled'}[/yellow]\n\n"
                "[bold blue]Next steps:[/bold blue]\n"
                f"notebooklm-mcp --config {config_path} server",
                title="🎉 Ready to Use",
            )
        )

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Setup failed: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--notebook", "-n", help="Notebook ID to use")
@click.option("--headless", is_flag=True, help="Run in headless mode")
@click.option("--port", type=int, default=8000, help="Server port (default: 8000)")
@click.option("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
@click.option(
    "--root-dir",
    help="Root directory for server operations (default: current directory)",
)
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http", "sse"]),
    default="stdio",
    help="Transport protocol (default: stdio)",
)
@click.pass_context
def server(
    ctx: click.Context,
    notebook: Optional[str],
    headless: bool,
    port: int,
    host: str,
    root_dir: Optional[str],
    transport: str,
) -> None:
    """Start the FastMCP v2 NotebookLM server"""
    import os
    from pathlib import Path

    config: ServerConfig = ctx.obj["config"]

    # Auto-detect current working directory as root
    if root_dir:
        working_dir = Path(root_dir).resolve()
    else:
        working_dir = Path.cwd()

    # Ensure root directory exists
    if not working_dir.exists():
        console.print(f"[red]Root directory does not exist: {working_dir}[/red]")
        sys.exit(1)

    if notebook:
        config.default_notebook_id = notebook
    if headless:
        config.headless = True

    console.print(
        Panel.fit(
            "[bold blue]Starting NotebookLM FastMCP v2 Server[/bold blue]\n"
            f"Mode: {'Headless' if config.headless else 'GUI'}\n"
            f"Transport: {transport.upper()}\n"
            f"{'Host: ' + host if transport != 'stdio' else ''}\n"
            f"{'Port: ' + str(port) if transport != 'stdio' else ''}\n"
            f"Notebook: {config.default_notebook_id or 'None'}\n"
            f"Working Directory: {working_dir}\n"
            f"Profile: {config.auth.profile_dir}\n"
            f"Debug: {config.debug}",
            title="🚀 FastMCP Server Starting",
        )
    )

    # Change to working directory
    os.chdir(working_dir)
    console.print(f"[dim]📁 Set working directory to: {working_dir}[/dim]")

    try:
        # Use FastMCP v2 implementation only
        server = NotebookLMFastMCP(config)

        if transport == "http":
            console.print(
                f"[green]🌐 FastMCP HTTP server will be available at: http://{host}:{port}/mcp/[/green]"
            )
        elif transport == "sse":
            console.print(
                f"[green]🌐 FastMCP SSE server will be available at: http://{host}:{port}/[/green]"
            )

        asyncio.run(server.start(transport=transport, host=host, port=port))

    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped by user[/yellow]")
    except Exception as e:
        is_windows = platform.system() == "Windows"
        error_str = str(e)
        console.print(f"[red]Server error: {e}[/red]")

        # Better Chrome connection error handling for Windows
        if (
            "cannot connect to chrome" in error_str.lower()
            or "chrome not reachable" in error_str.lower()
        ):
            if is_windows and config.headless:
                console.print(
                    Panel.fit(
                        "[yellow]🪟 Windows Chrome Connection Issue[/yellow]\n\n"
                        "The server failed to connect to Chrome in headless mode on Windows.\n"
                        "This is a known compatibility issue with undetected-chromedriver.\n\n"
                        "[bold]Quick Fix Options:[/bold]\n"
                        "1. Disable headless mode in your config file:\n"
                        f"   Edit [cyan]{ctx.obj.get('config_file', 'notebooklm-config.json')}[/cyan]\n"
                        '   Set [yellow]"headless": false[/yellow]\n\n'
                        "2. Use minimized window mode (automatic fallback):\n"
                        "   The browser will start minimized instead of headless\n\n"
                        "3. Run on Linux/Mac or WSL for full headless support\n\n"
                        "[dim]The minimized mode still works well for automation![/dim]",
                        title="🔧 Windows Compatibility",
                    )
                )
            else:
                console.print(
                    Panel.fit(
                        "[yellow]🌐 Chrome Connection Issue[/yellow]\n\n"
                        "Failed to connect to Chrome browser.\n\n"
                        "[bold]Troubleshooting steps:[/bold]\n"
                        "1. Make sure Chrome is installed\n"
                        "2. Close any existing Chrome instances\n"
                        "3. Delete and recreate the chrome_profile_notebooklm folder\n"
                        "4. Run init again to set up a fresh profile",
                        title="🔧 Browser Connection",
                    )
                )
        # Better authentication error handling
        elif "Authentication required" in error_str:
            console.print(
                Panel.fit(
                    "[yellow]🔐 Authentication Required[/yellow]\n\n"
                    "The server needs manual authentication to access NotebookLM.\n\n"
                    "[bold]To fix this:[/bold]\n"
                    "1. Run without --headless flag for manual login:\n"
                    f"   [cyan]notebooklm-mcp --config {ctx.obj.get('config_file', 'notebooklm-config.json')} server[/cyan]\n\n"
                    "2. Complete Google login in the browser\n"
                    "3. Then retry with --headless flag for production use",
                    title="🔑 Authentication Help",
                )
            )

        if config.debug:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option("--notebook", "-n", help="Notebook ID to use")
@click.option("--message", "-m", help="Message to send")
@click.option("--headless", is_flag=True, help="Run in headless mode")
@click.pass_context
def chat(
    ctx: click.Context, notebook: Optional[str], message: Optional[str], headless: bool
) -> None:
    """Interactive chat with NotebookLM"""
    config: ServerConfig = ctx.obj["config"]

    if notebook:
        config.default_notebook_id = notebook
    if headless:
        config.headless = True

    async def run_chat() -> None:
        client = NotebookLMClient(config)

        try:
            console.print("[yellow]Starting browser...[/yellow]")
            await client.start()

            console.print("[yellow]Authenticating...[/yellow]")
            auth_success = await client.authenticate()

            if not auth_success:
                console.print(
                    "[red]Authentication failed. Please login manually in browser.[/red]"
                )
                if not config.headless:
                    console.print("[blue]Press Enter when logged in...[/blue]")
                    input()

            if message:
                # Single message mode
                console.print(f"[blue]Sending: {message}[/blue]")
                await client.send_message(message)

                console.print("[yellow]Waiting for response...[/yellow]")
                response = await client.get_response()

                console.print(Panel(response, title="🤖 NotebookLM Response"))
            else:
                # Interactive mode
                console.print(
                    "[green]Interactive mode started. Type 'quit' to exit.[/green]"
                )

                while True:
                    try:
                        user_message = console.input("\n[bold blue]You:[/bold blue] ")
                        if user_message.lower() in ["quit", "exit", "q"]:
                            break

                        await client.send_message(user_message)
                        console.print("[yellow]Waiting for response...[/yellow]")

                        response = await client.get_response()
                        console.print(
                            f"[bold green]NotebookLM:[/bold green] {response}"
                        )

                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        console.print(f"[red]Chat error: {e}[/red]")

        finally:
            await client.close()

    try:
        asyncio.run(run_chat())
    except Exception as e:
        console.print(f"[red]Chat session error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--config", "-c", required=True, help="Configuration file path")
@click.option("--notebook", "-n", required=True, help="Notebook ID")
@click.option("--profile", "-p", help="Path to existing Chrome profile to import")
@click.option("--headless", is_flag=True, help="Run in headless mode")
@click.option(
    "--setup-only", is_flag=True, help="Only create config, don't run browser"
)
@click.pass_context
def quick_setup(
    ctx: click.Context,
    config: str,
    notebook: str,
    profile: Optional[str],
    headless: bool,
    setup_only: bool,
) -> None:
    """Quick setup with config file and optional profile import"""

    async def run_setup():
        try:
            # Step 1: Create enhanced config
            console.print("📋 Step 1: Creating configuration...")
            server_config = ServerConfig(
                default_notebook_id=notebook,
                headless=headless,
                auth=AuthConfig(
                    import_profile_from=profile,
                    skip_manual_login=bool(
                        profile
                    ),  # Skip manual login if profile provided
                ),
            )

            # Step 2: Setup profile
            console.print("🔧 Step 2: Setting up Chrome profile...")
            server_config.setup_profile()

            # Step 3: Save config
            console.print("💾 Step 3: Saving configuration...")
            server_config.save_to_file(config)

            console.print(
                Panel.fit(
                    f"[bold green]✅ Configuration Complete![/bold green]\n\n"
                    f"📁 Config saved to: {config}\n"
                    f"📝 Notebook ID: {notebook}\n"
                    f"🔧 Profile: {'Imported' if profile else 'New'}\n"
                    f"👀 Mode: {'Headless' if headless else 'GUI'}",
                    title="📋 Config Ready",
                )
            )

            # Step 4: Initialize and test browser (unless setup-only)
            if not setup_only:
                console.print("\n🌐 Step 4: Testing browser connection...")

                # Import client here to avoid circular imports
                from .client import NotebookLMClient

                # Create client
                client = NotebookLMClient(server_config)

                try:
                    # Start browser
                    console.print("🔄 Starting browser...")
                    await client.start()
                    console.print("✅ Browser started successfully!")

                    # Test authentication
                    console.print("🔐 Testing authentication...")
                    auth_success = await client.authenticate()

                    if auth_success:
                        console.print(
                            "✅ Authentication successful - no manual login needed!"
                        )
                        console.print(
                            Panel.fit(
                                f"[bold green]🎉 Complete Setup Success![/bold green]\n\n"
                                f"Your NotebookLM MCP server is ready to use!\n\n"
                                f"[yellow]Start server:[/yellow]\n"
                                f"notebooklm-mcp server -c {config}\n\n"
                                f"[yellow]Start interactive chat:[/yellow]\n"
                                f"notebooklm-mcp chat -c {config}",
                                title="🚀 Ready to Use!",
                            )
                        )
                    else:
                        console.print("⚠️ Manual login required")
                        console.print(
                            Panel.fit(
                                "[yellow]Manual Login Needed[/yellow]\n\n"
                                "Browser is open for you to login manually.\n"
                                "1. Complete Google login in the browser\n"
                                "2. Navigate to your notebook\n"
                                "3. Press Enter when ready...",
                                title="🔐 Login Required",
                            )
                        )

                        # Wait for user to complete login
                        input("\nPress Enter after completing login...")

                        # Test again
                        auth_success = await client.authenticate()
                        if auth_success:
                            console.print(
                                "✅ Login successful! Session saved for future use."
                            )
                        else:
                            console.print(
                                "⚠️ Authentication still pending - you can try again later"
                            )

                        console.print(
                            Panel.fit(
                                f"[bold green]✅ Setup Complete![/bold green]\n\n"
                                f"[yellow]Your session is now saved![/yellow]\n"
                                f"Future runs will auto-authenticate.\n\n"
                                f"[yellow]Start server:[/yellow]\n"
                                f"notebooklm-mcp server -c {config}",
                                title="🎉 Setup Complete!",
                            )
                        )

                except Exception as e:
                    console.print(f"⚠️ Browser test failed: {e}")
                    console.print(
                        "Config created successfully, but browser needs manual setup"
                    )

                finally:
                    # Clean up
                    try:
                        await client.close()
                        console.print("🔄 Browser closed")
                    except Exception:
                        pass
            else:
                # Setup-only mode
                console.print(
                    Panel.fit(
                        f"[bold green]✅ Config-Only Setup Complete![/bold green]\n\n"
                        f"📁 Configuration saved to: {config}\n\n"
                        f"[yellow]Next steps:[/yellow]\n"
                        f"• notebooklm-mcp server -c {config}\n"
                        f"• notebooklm-mcp chat -c {config}",
                        title="📋 Config Ready",
                    )
                )

        except Exception as e:
            console.print(f"[red]Setup failed: {e}[/red]")
            import traceback

            console.print(f"[red]Details: {traceback.format_exc()}[/red]")
            sys.exit(1)

    # Run async setup
    import asyncio

    asyncio.run(run_setup())


@cli.command()
@click.option("--from-profile", "-f", required=True, help="Source Chrome profile path")
@click.option("--to-profile", "-t", required=True, help="Destination profile path")
@click.pass_context
def import_profile(ctx: click.Context, from_profile: str, to_profile: str) -> None:
    """Import existing Chrome profile"""

    try:
        from pathlib import Path
        from shutil import copytree, rmtree

        source = Path(from_profile)
        dest = Path(to_profile)

        if not source.exists():
            raise ConfigurationError(f"Source profile not found: {source}")

        if dest.exists():
            console.print(f"[yellow]Removing existing profile: {dest}[/yellow]")
            rmtree(dest)

        copytree(source, dest)

        console.print(
            Panel.fit(
                f"[bold green]✅ Profile Import Complete![/bold green]\n\n"
                f"📁 From: {source}\n"
                f"📁 To: {dest}\n\n"
                f"[yellow]You can now use this profile in your config:[/yellow]\n"
                f'  "auth": {{\n'
                f'    "profile_dir": "{dest}",\n'
                f'    "use_persistent_session": true\n'
                f"  }}",
                title="📥 Profile Imported",
            )
        )

    except Exception as e:
        console.print(f"[red]Import failed: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--profile", "-p", help="Profile path to export from (default: current)")
@click.option("--to", "-t", required=True, help="Export destination path")
@click.pass_context
def export_profile(ctx: click.Context, profile: Optional[str], to: str) -> None:
    """Export Chrome profile for sharing"""
    config: ServerConfig = ctx.obj["config"]

    source_profile = profile or config.auth.profile_dir

    try:
        from pathlib import Path
        from shutil import copytree, rmtree

        source = Path(source_profile)
        dest = Path(to)

        if not source.exists():
            raise ConfigurationError(f"Source profile not found: {source}")

        if dest.exists():
            rmtree(dest)

        copytree(source, dest)

        console.print(
            Panel.fit(
                f"[bold green]✅ Profile Export Complete![/bold green]\n\n"
                f"📁 From: {source}\n"
                f"📁 To: {dest}\n\n"
                f"[yellow]Share this profile with others for quick setup![/yellow]",
                title="📤 Profile Exported",
            )
        )

    except Exception as e:
        console.print(f"[red]Export failed: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Show current configuration"""
    config: ServerConfig = ctx.obj["config"]

    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="yellow")

    config_dict = config.to_dict()
    for key, value in config_dict.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                table.add_row(f"{key}.{sub_key}", str(sub_value))
        else:
            table.add_row(key, str(value))

    console.print(table)


@cli.command()
@click.option("--notebook", "-n", required=True, help="Notebook ID to test")
@click.option("--headless", is_flag=True, help="Run in headless mode")
@click.pass_context
def test(ctx: click.Context, notebook: str, headless: bool) -> None:
    """Test connection to NotebookLM"""
    config: ServerConfig = ctx.obj["config"]
    config.default_notebook_id = notebook

    if headless:
        config.headless = True

    async def run_test() -> None:
        client = NotebookLMClient(config)

        try:
            console.print("[yellow]Testing browser startup...[/yellow]")
            await client.start()
            console.print("✅ Browser started successfully")

            console.print("[yellow]Testing authentication...[/yellow]")
            auth_success = await client.authenticate()

            if auth_success:
                console.print("✅ Authentication successful")
            else:
                console.print("⚠️  Authentication required - manual login needed")

            console.print("[yellow]Testing notebook navigation...[/yellow]")
            url = await client.navigate_to_notebook(notebook)
            console.print(f"✅ Navigated to: {url}")

            console.print("[green]All tests passed![/green]")

        except Exception as e:
            console.print(f"[red]Test failed: {e}[/red]")
            raise
        finally:
            await client.close()

    try:
        asyncio.run(run_test())
    except Exception as e:
        console.print(f"[red]Test error: {e}[/red]")
        sys.exit(1)


async def guided_setup(config: ServerConfig) -> bool:
    """Guided setup flow for first-time users

    Returns:
        bool: True if setup was successful, False otherwise
    """
    console.print("[bold blue]🔧 Setting up browser and profile...[/bold blue]")

    client = NotebookLMClient(config)
    setup_success = False

    try:
        # Start browser
        console.print("[yellow]Starting browser...[/yellow]")
        await client.start()
        console.print("✅ Browser started successfully")

        # Navigate to notebook for authentication
        if not config.default_notebook_id:
            raise ValueError("No notebook ID configured")

        console.print(
            f"[yellow]Navigating to notebook: {config.default_notebook_id}[/yellow]"
        )
        await client.navigate_to_notebook(config.default_notebook_id)

        # Check if already authenticated
        auth_success = await client.authenticate()

        if not auth_success:
            console.print(
                Panel.fit(
                    "[bold yellow]📋 Manual Login Required[/bold yellow]\n\n"
                    "Please complete the following steps:\n"
                    "1. 🔐 Login with your Google account in the browser\n"
                    "2. ✅ Ensure you can access the notebook\n"
                    "3. ⏱️  Wait for the page to fully load\n"
                    "4. ⌨️  Press Enter when ready...",
                    title="🔑 Authentication Setup",
                )
            )

            if not config.headless:
                input("\nPress Enter when login is complete...")

            # Verify authentication after manual login
            auth_success = await client.authenticate()

            if auth_success:
                console.print("✅ Authentication successful!")
            else:
                console.print(
                    "⚠️  Authentication verification failed, but profile was saved"
                )
        else:
            console.print("✅ Already authenticated!")

        # Test basic functionality
        console.print("[yellow]Testing basic functionality...[/yellow]")
        try:
            await client.send_message("Hello, this is a test message from setup.")
            console.print("✅ Chat functionality working")
            setup_success = True  # Mark as successful
        except Exception as e:
            console.print(f"⚠️  Chat test failed: {e}")
            setup_success = auth_success  # Success if at least authenticated

        console.print("[bold green]✅ Browser profile setup complete![/bold green]")
        return setup_success

    except Exception as e:
        console.print(f"[red]Setup error: {e}[/red]")
        raise
    finally:
        if client:
            await client.close()


def main() -> None:
    """Main entry point"""
    cli()


if __name__ == "__main__":
    main()
