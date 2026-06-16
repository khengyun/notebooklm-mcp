"""
Command-line interface for NotebookLM MCP Server
"""

import asyncio
import json
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .client_rpc import NotebookLMRPCClient
from .config import AuthConfig, ServerConfig, _copy_tree, load_config
from .exceptions import ConfigurationError
from .server import NotebookLMFastMCP

console = Console()


@asynccontextmanager
async def _client_session(
    config: ServerConfig,
) -> AsyncIterator[NotebookLMRPCClient]:
    """Start an RPC client and always close it (shared by chat/test)."""
    client = NotebookLMRPCClient(config)
    try:
        await client.start()
        yield client
    finally:
        await client.close()


def _validated_copy(source: Path, dest: Path) -> None:
    """Copy a profile dir after checking the source exists (import/export)."""
    if not source.exists():
        raise ConfigurationError(f"Source profile not found: {source}")
    _copy_tree(source, dest)


def extract_notebook_id(url: str) -> str:
    """Extract a notebook ID (UUID) from a NotebookLM URL or a bare ID.

    Accepts upper- or lower-case UUIDs and anchors the bare-ID form so a longer
    hyphenated string can't yield a truncated/garbage 36-char window.
    """
    uuid = (
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )
    patterns = [
        rf"notebooklm\.google\.com/notebook/({uuid})",
        rf"^({uuid})$",  # Just the ID itself (anchored)
    ]

    for pattern in patterns:
        match = re.search(pattern, url.strip())
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
        "auth": {
            "profile_dir": "./chrome_profile_notebooklm",
        },
    }

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    console.print(f"✅ Created config file: [bold green]{config_path}[/bold green]")


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
def init(notebook_url: str, config_path: str) -> None:
    """Initialize NotebookLM MCP Server with notebook URL

    NOTEBOOK_URL: NotebookLM notebook URL or ID

    Examples:
        notebooklm-mcp init https://notebooklm.google.com/notebook/4741957b-f358-48fb-a16a-da8d20797bc6
        notebooklm-mcp init 4741957b-f358-48fb-a16a-da8d20797bc6
    """
    try:
        # Extract notebook ID from URL
        notebook_id = extract_notebook_id(notebook_url)

        console.print(
            Panel.fit(
                f"[bold blue]🚀 Initializing NotebookLM MCP Server[/bold blue]\n"
                f"Notebook ID: [green]{notebook_id}[/green]\n"
                f"Config File: [yellow]{config_path}[/yellow]",
                title="Setup Starting",
            )
        )

        # Create config file
        create_default_config(notebook_id, config_path)

        # Create profile directory (holds storage_state.json after login)
        profile_dir = Path("./chrome_profile_notebooklm")
        profile_dir.mkdir(exist_ok=True)
        console.print(
            f"✅ Created profile directory: [bold green]{profile_dir}[/bold green]"
        )

        console.print(
            Panel.fit(
                "[bold green]✅ Setup Complete![/bold green]\n\n"
                f"Config file: [yellow]{config_path}[/yellow]\n"
                f"Profile directory: [yellow]{profile_dir}[/yellow]\n\n"
                "[bold blue]Next steps:[/bold blue]\n"
                "1. Create a NotebookLM session (opens a browser to log in):\n"
                "   [cyan]uv run notebooklm login[/cyan]\n"
                "2. Start the MCP server:\n"
                f"   [cyan]notebooklm-mcp --config {config_path} server[/cyan]",
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
        console.print(f"[red]Server error: {e}[/red]")

        # Better authentication error handling
        if "Authentication required" in str(e):
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
@click.pass_context
def chat(ctx: click.Context, notebook: Optional[str], message: Optional[str]) -> None:
    """Interactive chat with NotebookLM"""
    config: ServerConfig = ctx.obj["config"]

    if notebook:
        config.default_notebook_id = notebook

    async def run_chat() -> None:
        async with _client_session(config) as client:
            console.print("[yellow]Authenticating...[/yellow]")
            if not await client.authenticate():
                console.print(
                    "[red]Authentication failed. Run `uv run notebooklm login` "
                    "to create a session.[/red]"
                )

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

    try:
        asyncio.run(run_chat())
    except Exception as e:
        console.print(f"[red]Chat session error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--config", "-c", required=True, help="Configuration file path")
@click.option("--notebook", "-n", required=True, help="Notebook ID")
@click.option("--profile", "-p", help="Path to existing Chrome profile to import")
@click.pass_context
def quick_setup(
    ctx: click.Context,
    config: str,
    notebook: str,
    profile: Optional[str],
) -> None:
    """Quick setup: create config + profile dir, then guide you to log in."""
    try:
        # Step 1: Create config
        console.print("📋 Step 1: Creating configuration...")
        server_config = ServerConfig(
            default_notebook_id=notebook,
            auth=AuthConfig(
                import_profile_from=profile,
                skip_manual_login=bool(profile),
            ),
        )

        # Step 2: Setup profile directory (holds storage_state.json after login)
        console.print("🔧 Step 2: Setting up profile directory...")
        server_config.setup_profile()

        # Step 3: Save config
        console.print("💾 Step 3: Saving configuration...")
        server_config.save_to_file(config)

        console.print(
            Panel.fit(
                f"[bold green]✅ Configuration Complete![/bold green]\n\n"
                f"📁 Config saved to: {config}\n"
                f"📝 Notebook ID: {notebook}\n"
                f"🔧 Profile: {'Imported' if profile else 'New'}\n\n"
                f"[bold blue]Next steps:[/bold blue]\n"
                f"1. Create a NotebookLM session (opens a browser to log in):\n"
                f"   [cyan]uv run notebooklm login[/cyan]\n"
                f"2. Start the server:\n"
                f"   [cyan]notebooklm-mcp server -c {config}[/cyan]\n"
                f"3. Or start an interactive chat:\n"
                f"   [cyan]notebooklm-mcp chat -c {config}[/cyan]",
                title="📋 Config Ready",
            )
        )

    except Exception as e:
        console.print(f"[red]Setup failed: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--from-profile", "-f", required=True, help="Source Chrome profile path")
@click.option("--to-profile", "-t", required=True, help="Destination profile path")
@click.pass_context
def import_profile(ctx: click.Context, from_profile: str, to_profile: str) -> None:
    """Import existing Chrome profile"""

    try:
        source = Path(from_profile)
        dest = Path(to_profile)
        _validated_copy(source, dest)

        console.print(
            Panel.fit(
                f"[bold green]✅ Profile Import Complete![/bold green]\n\n"
                f"📁 From: {source}\n"
                f"📁 To: {dest}\n\n"
                f"[yellow]You can now use this profile in your config:[/yellow]\n"
                f'  "auth": {{\n'
                f'    "profile_dir": "{dest}"\n'
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
        source = Path(source_profile)
        dest = Path(to)
        _validated_copy(source, dest)

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
@click.pass_context
def test(ctx: click.Context, notebook: str) -> None:
    """Test connection to NotebookLM"""
    config: ServerConfig = ctx.obj["config"]
    config.default_notebook_id = notebook

    async def run_test() -> None:
        async with _client_session(config) as client:
            try:
                console.print("✅ Connected successfully")

                console.print("[yellow]Testing authentication...[/yellow]")
                if await client.authenticate():
                    console.print("✅ Authentication successful")
                else:
                    console.print(
                        "⚠️  Authentication required - run `uv run notebooklm login`"
                    )

                console.print("[yellow]Testing notebook navigation...[/yellow]")
                url = await client.navigate_to_notebook(notebook)
                console.print(f"✅ Navigated to: {url}")

                console.print("[green]All tests passed![/green]")
            except Exception as e:
                console.print(f"[red]Test failed: {e}[/red]")
                raise

    try:
        asyncio.run(run_test())
    except Exception as e:
        console.print(f"[red]Test error: {e}[/red]")
        sys.exit(1)


def main() -> None:
    """Main entry point"""
    cli()


if __name__ == "__main__":
    main()
