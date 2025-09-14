"""
Command-line interface for NotebookLM MCP Server
"""

import asyncio
import sys
from typing import Optional
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .config import load_config, ServerConfig
from .server import NotebookLMServer
from .client import NotebookLMClient

console = Console()


@click.group()
@click.version_option()
@click.option('--config', '-c', type=click.Path(exists=True), help='Configuration file path')
@click.option('--debug', is_flag=True, help='Enable debug logging')
@click.pass_context
def cli(ctx: click.Context, config: Optional[str], debug: bool) -> None:
    """NotebookLM MCP Server - Professional automation for Google NotebookLM"""
    ctx.ensure_object(dict)
    
    try:
        server_config = load_config(config)
        if debug:
            server_config.debug = True
        ctx.obj['config'] = server_config
    except Exception as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option('--notebook', '-n', help='Notebook ID to use')
@click.option('--headless', is_flag=True, help='Run in headless mode')
@click.option('--port', type=int, help='Server port (if not using STDIO)')
@click.pass_context
def server(ctx: click.Context, notebook: Optional[str], headless: bool, port: Optional[int]) -> None:
    """Start the MCP server"""
    config: ServerConfig = ctx.obj['config']
    
    if notebook:
        config.default_notebook_id = notebook
    if headless:
        config.headless = True
    
    console.print(Panel.fit(
        "[bold blue]Starting NotebookLM MCP Server[/bold blue]\n"
        f"Mode: {'Headless' if config.headless else 'GUI'}\n"
        f"Notebook: {config.default_notebook_id or 'None'}\n"
        f"Debug: {config.debug}",
        title="🚀 Server Starting"
    ))
    
    try:
        server = NotebookLMServer(config)
        asyncio.run(server.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Server error: {e}[/red]")
        if config.debug:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option('--notebook', '-n', help='Notebook ID to use')
@click.option('--message', '-m', help='Message to send')
@click.option('--headless', is_flag=True, help='Run in headless mode')
@click.pass_context
def chat(ctx: click.Context, notebook: Optional[str], message: Optional[str], headless: bool) -> None:
    """Interactive chat with NotebookLM"""
    config: ServerConfig = ctx.obj['config']
    
    if notebook:
        config.default_notebook_id = notebook
    if headless:
        config.headless = True
    
    async def run_chat():
        client = NotebookLMClient(config)
        
        try:
            console.print("[yellow]Starting browser...[/yellow]")
            await client.start()
            
            console.print("[yellow]Authenticating...[/yellow]")
            auth_success = await client.authenticate()
            
            if not auth_success:
                console.print("[red]Authentication failed. Please login manually in browser.[/red]")
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
                console.print("[green]Interactive mode started. Type 'quit' to exit.[/green]")
                
                while True:
                    try:
                        user_message = console.input("\n[bold blue]You:[/bold blue] ")
                        if user_message.lower() in ['quit', 'exit', 'q']:
                            break
                        
                        await client.send_message(user_message)
                        console.print("[yellow]Waiting for response...[/yellow]")
                        
                        response = await client.get_response()
                        console.print(f"[bold green]NotebookLM:[/bold green] {response}")
                        
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
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Show current configuration"""
    config: ServerConfig = ctx.obj['config']
    
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
@click.option('--notebook', '-n', required=True, help='Notebook ID to test')
@click.option('--headless', is_flag=True, help='Run in headless mode')
@click.pass_context
def test(ctx: click.Context, notebook: str, headless: bool) -> None:
    """Test connection to NotebookLM"""
    config: ServerConfig = ctx.obj['config']
    config.default_notebook_id = notebook
    
    if headless:
        config.headless = True
    
    async def run_test():
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


def main() -> None:
    """Main entry point"""
    cli()


if __name__ == '__main__':
    main()