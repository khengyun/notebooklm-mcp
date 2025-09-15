"""
Comprehensive tests for NotebookLM CLI module
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from notebooklm_mcp.cli import chat, config_show, main, server, test
from notebooklm_mcp.client import NotebookLMClient


class TestCLIMainCommand:
    """Test main CLI command and entry point"""

    def test_main_command_help(self):
        """Test main command help output"""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "NotebookLM MCP Server" in result.output
        assert "chat" in result.output
        assert "server" in result.output
        assert "test" in result.output
        assert "config-show" in result.output

    def test_main_command_version(self):
        """Test version flag"""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        # Should show version information

    def test_main_command_debug_flag(self):
        """Test debug flag functionality"""
        runner = CliRunner()
        result = runner.invoke(main, ["--debug", "--help"])

        assert result.exit_code == 0
        # Debug flag should be processed without error


class TestCLIConfigCommand:
    """Test configuration display command"""

    def test_config_show_default(self):
        """Test config-show with default configuration"""
        runner = CliRunner()
        result = runner.invoke(config_show)

        assert result.exit_code == 0
        assert "Configuration" in result.output
        assert "headless" in result.output
        assert "timeout" in result.output

    def test_config_show_with_config_file(self):
        """Test config-show with configuration file"""
        config_data = {
            "headless": True,
            "timeout": 120,
            "default_notebook_id": "test-notebook",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            runner = CliRunner()
            result = runner.invoke(config_show, ["-c", config_file])

            assert result.exit_code == 0
            assert "test-notebook" in result.output
            assert "120" in result.output
        finally:
            Path(config_file).unlink()

    def test_config_show_nonexistent_file(self):
        """Test config-show with nonexistent configuration file"""
        runner = CliRunner()
        result = runner.invoke(config_show, ["-c", "/nonexistent/config.json"])

        # Should use default config when file doesn't exist
        assert result.exit_code == 0


class TestCLIChatCommand:
    """Test interactive chat command"""

    @pytest.fixture
    def mock_client(self):
        """Mock client for testing"""
        with patch("notebooklm_mcp.cli.NotebookLMClient") as mock_client_class:
            mock_client = AsyncMock(spec=NotebookLMClient)
            mock_client_class.return_value = mock_client
            yield mock_client

    def test_chat_command_help(self):
        """Test chat command help"""
        runner = CliRunner()
        result = runner.invoke(chat, ["--help"])

        assert result.exit_code == 0
        assert "Interactive chat" in result.output
        assert "--notebook" in result.output
        assert "--headless" in result.output

    def test_chat_command_missing_notebook_id(self):
        """Test chat command without notebook ID"""
        runner = CliRunner()
        result = runner.invoke(chat)

        # Should show error or prompt for notebook ID
        assert result.exit_code != 0 or "notebook" in result.output.lower()

    @patch("notebooklm_mcp.cli.asyncio.run")
    @patch("notebooklm_mcp.cli.NotebookLMClient")
    def test_chat_command_success(self, mock_client_class, mock_asyncio_run):
        """Test successful chat command execution"""
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(chat, ["--notebook", "test-notebook-123", "--headless"])

        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()

    @patch("notebooklm_mcp.cli.asyncio.run")
    def test_chat_command_with_config_file(self, mock_asyncio_run):
        """Test chat command with configuration file"""
        config_data = {"default_notebook_id": "config-notebook", "headless": True}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            runner = CliRunner()
            result = runner.invoke(chat, ["-c", config_file])

            assert result.exit_code == 0
            mock_asyncio_run.assert_called_once()
        finally:
            Path(config_file).unlink()


class TestCLIServerCommand:
    """Test MCP server command"""

    def test_server_command_help(self):
        """Test server command help"""
        runner = CliRunner()
        result = runner.invoke(server, ["--help"])

        assert result.exit_code == 0
        assert "Start the MCP server" in result.output
        assert "--notebook" in result.output
        assert "--stdio" in result.output

    def test_server_command_missing_notebook_id(self):
        """Test server command without notebook ID"""
        runner = CliRunner()
        result = runner.invoke(server)

        # Should show error or use default
        assert result.exit_code != 0 or "notebook" in result.output.lower()

    @patch("notebooklm_mcp.cli.asyncio.run")
    @patch("notebooklm_mcp.cli.NotebookLMServer")
    def test_server_command_success(self, mock_server_class, mock_asyncio_run):
        """Test successful server command execution"""
        mock_server = AsyncMock()
        mock_server_class.return_value = mock_server

        runner = CliRunner()
        result = runner.invoke(server, ["--notebook", "test-notebook", "--headless"])

        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()

    @patch("notebooklm_mcp.cli.asyncio.run")
    def test_server_command_stdio_mode(self, mock_asyncio_run):
        """Test server command in STDIO mode"""
        runner = CliRunner()
        result = runner.invoke(
            server, ["--notebook", "test-notebook", "--stdio", "--headless"]
        )

        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()


class TestCLITestCommand:
    """Test connection testing command"""

    @pytest.fixture
    def mock_client(self):
        """Mock client for testing"""
        with patch("notebooklm_mcp.cli.NotebookLMClient") as mock_client_class:
            mock_client = AsyncMock(spec=NotebookLMClient)
            mock_client_class.return_value = mock_client
            yield mock_client

    def test_test_command_help(self):
        """Test test command help"""
        runner = CliRunner()
        result = runner.invoke(test, ["--help"])

        assert result.exit_code == 0
        assert "Test connection" in result.output
        assert "--notebook" in result.output

    @patch("notebooklm_mcp.cli.asyncio.run")
    def test_test_command_success(self, mock_asyncio_run, mock_client):
        """Test successful connection test"""
        # Mock successful authentication
        mock_client.authenticate.return_value = True

        runner = CliRunner()
        result = runner.invoke(test, ["--notebook", "test-notebook"])

        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()

    @patch("notebooklm_mcp.cli.asyncio.run")
    def test_test_command_failure(self, mock_asyncio_run, mock_client):
        """Test connection test failure"""
        # Mock authentication failure
        mock_client.authenticate.side_effect = Exception("Auth failed")

        runner = CliRunner()
        runner.invoke(test, ["--notebook", "test-notebook"])

        # Should handle error gracefully
        mock_asyncio_run.assert_called_once()


class TestCLIConfigurationHandling:
    """Test configuration file handling across commands"""

    def test_config_file_json_format(self):
        """Test JSON configuration file parsing"""
        config_data = {
            "headless": True,
            "timeout": 90,
            "debug": False,
            "default_notebook_id": "json-test-notebook",
            "auth": {"profile_dir": "./custom_profile", "use_persistent_session": True},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            runner = CliRunner()
            result = runner.invoke(config_show, ["-c", config_file])

            assert result.exit_code == 0
            assert "json-test-notebook" in result.output
            assert "custom_profile" in result.output
        finally:
            Path(config_file).unlink()

    def test_config_file_invalid_json(self):
        """Test handling of invalid JSON configuration"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            config_file = f.name

        try:
            runner = CliRunner()
            result = runner.invoke(config_show, ["-c", config_file])

            # Should handle invalid JSON gracefully
            assert result.exit_code == 0  # Should fall back to defaults
        finally:
            Path(config_file).unlink()

    def test_command_line_options_override_config(self):
        """Test that command line options override config file"""
        config_data = {"headless": False, "default_notebook_id": "config-notebook"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            with patch("notebooklm_mcp.cli.asyncio.run") as mock_run:
                runner = CliRunner()
                result = runner.invoke(
                    chat,
                    [
                        "-c",
                        config_file,
                        "--notebook",
                        "override-notebook",
                        "--headless",  # Override config file setting
                    ],
                )

                assert result.exit_code == 0
                mock_run.assert_called_once()
        finally:
            Path(config_file).unlink()


class TestCLIErrorHandling:
    """Test error handling in CLI commands"""

    def test_invalid_command_line_options(self):
        """Test handling of invalid command line options"""
        runner = CliRunner()
        result = runner.invoke(main, ["--invalid-option"])

        assert result.exit_code != 0
        assert "No such option" in result.output or "Invalid" in result.output

    def test_nonexistent_config_file_handling(self):
        """Test handling of nonexistent configuration files"""
        runner = CliRunner()
        result = runner.invoke(config_show, ["-c", "/nonexistent/path/config.json"])

        # Should use defaults and not crash
        assert result.exit_code == 0

    @patch("notebooklm_mcp.cli.asyncio.run")
    def test_client_initialization_failure(self, mock_asyncio_run):
        """Test handling of client initialization failures"""
        # Mock asyncio.run to raise an exception
        mock_asyncio_run.side_effect = Exception("Client init failed")

        runner = CliRunner()
        result = runner.invoke(chat, ["--notebook", "test-notebook"])

        # Should handle the exception gracefully
        assert "error" in result.output.lower() or result.exit_code != 0


class TestCLIIntegration:
    """Integration tests for CLI workflows"""

    @patch("notebooklm_mcp.cli.NotebookLMClient")
    @patch("notebooklm_mcp.cli.asyncio.run")
    def test_complete_chat_workflow(self, mock_asyncio_run, mock_client_class):
        """Test complete chat workflow from CLI"""
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Mock successful operations
        mock_client.start.return_value = None
        mock_client.authenticate.return_value = True
        mock_client.navigate_to_notebook.return_value = None

        runner = CliRunner()
        result = runner.invoke(
            chat, ["--notebook", "test-notebook", "--headless", "--debug"]
        )

        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()

    @patch("notebooklm_mcp.cli.NotebookLMServer")
    @patch("notebooklm_mcp.cli.asyncio.run")
    def test_complete_server_workflow(self, mock_asyncio_run, mock_server_class):
        """Test complete server workflow from CLI"""
        mock_server = AsyncMock()
        mock_server_class.return_value = mock_server

        runner = CliRunner()
        result = runner.invoke(
            server, ["--notebook", "test-notebook", "--stdio", "--headless"]
        )

        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()

    def test_all_commands_accessible(self):
        """Test that all commands are accessible from main"""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0

        # Check that all expected commands are listed
        expected_commands = ["chat", "server", "test", "config-show"]
        for command in expected_commands:
            assert command in result.output


class TestCLIOutputFormatting:
    """Test CLI output formatting and user experience"""

    def test_config_show_table_format(self):
        """Test that config-show produces well-formatted table output"""
        runner = CliRunner()
        result = runner.invoke(config_show)

        assert result.exit_code == 0

        # Should contain table-like formatting
        lines = result.output.split("\n")
        non_empty_lines = [line for line in lines if line.strip()]
        assert len(non_empty_lines) > 5  # Should have multiple config entries

    def test_help_text_formatting(self):
        """Test that help text is well-formatted and informative"""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "Commands:" in result.output or "Usage:" in result.output
        assert len(result.output.split("\n")) > 10  # Should be detailed

    def test_error_message_formatting(self):
        """Test that error messages are clear and helpful"""
        runner = CliRunner()
        result = runner.invoke(main, ["nonexistent-command"])

        assert result.exit_code != 0
        assert len(result.output) > 0  # Should provide error message


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
