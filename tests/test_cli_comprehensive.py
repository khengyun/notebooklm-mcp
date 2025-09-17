"""Integration-oriented tests for the NotebookLM CLI entry points."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from notebooklm_mcp.cli import cli


@pytest.fixture
def sample_config(config_file_factory) -> Path:
    """Create a minimal configuration file for CLI invocations."""

    return config_file_factory(
        {
            "default_notebook_id": "notebook-1234",
            "headless": True,
            "debug": False,
            "auth": {"profile_dir": "./profile", "use_persistent_session": True},
        }
    )


def test_cli_help_displays_available_commands(cli_runner):
    """The top-level help output should list the core commands."""

    result = cli_runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "config-show" in result.output
    assert "chat" in result.output
    assert "server" in result.output


def test_config_show_renders_table(cli_runner, sample_config):
    """`config-show` should load the provided config file and render values."""

    result = cli_runner.invoke(
        cli,
        ["--config", str(sample_config), "config-show"],
    )

    assert result.exit_code == 0
    assert "notebook-1234" in result.output
    assert "headless" in result.output


def test_chat_command_runs_async_workflow(cli_runner, sample_config):
    """Invoking the chat command should delegate to the async workflow."""

    with (
        patch("notebooklm_mcp.cli.NotebookLMClient") as mock_client_cls,
        patch("notebooklm_mcp.cli.asyncio.run") as mock_run,
    ):
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_run.return_value = None

        result = cli_runner.invoke(
            cli,
            [
                "--config",
                str(sample_config),
                "chat",
                "--notebook",
                "override-id",
                "--message",
                "Hello there!",
            ],
        )

    assert result.exit_code == 0
    mock_run.assert_called_once()
    (run_arg,) = mock_run.call_args.args
    assert asyncio.iscoroutine(run_arg)
    run_arg.close()


def test_server_command_initialises_fastmcp(cli_runner, sample_config, monkeypatch):
    """Starting the server should construct the FastMCP instance and run it."""

    fake_server = Mock()
    fake_server.start = AsyncMock()
    monkeypatch.setattr("os.chdir", lambda path: None)

    with (
        patch("notebooklm_mcp.cli.NotebookLMFastMCP", return_value=fake_server) as mock_server,
        patch("notebooklm_mcp.cli.asyncio.run") as mock_run,
    ):
        mock_run.return_value = None

        result = cli_runner.invoke(
            cli,
            [
                "--config",
                str(sample_config),
                "server",
                "--notebook",
                "override-id",
                "--transport",
                "stdio",
            ],
        )

    assert result.exit_code == 0
    mock_server.assert_called_once()
    mock_run.assert_called_once()
    (run_arg,) = mock_run.call_args.args
    assert asyncio.iscoroutine(run_arg)
    run_arg.close()


def test_test_command_executes_async_sequence(cli_runner, sample_config):
    """The test command should execute its async runner via asyncio.run."""

    with (
        patch("notebooklm_mcp.cli.NotebookLMClient") as mock_client_cls,
        patch("notebooklm_mcp.cli.asyncio.run") as mock_run,
    ):
        mock_client_cls.return_value = AsyncMock()
        mock_run.return_value = None

        result = cli_runner.invoke(
            cli,
            [
                "--config",
                str(sample_config),
                "test",
                "--notebook",
                "notebook-1234",
            ],
        )

    assert result.exit_code == 0
    mock_run.assert_called_once()
    (run_arg,) = mock_run.call_args.args
    assert asyncio.iscoroutine(run_arg)
    run_arg.close()
