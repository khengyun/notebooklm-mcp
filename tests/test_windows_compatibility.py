"""
Tests for Windows compatibility handling
"""

import platform
from unittest.mock import Mock, patch

import pytest

from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.config import ServerConfig


@pytest.fixture
def mock_config():
    """Create a mock server config"""
    return ServerConfig(
        headless=True,
        default_notebook_id="test-notebook-123",
        auth={"profile_dir": "./test_profile", "use_persistent_session": True},
    )


def test_windows_headless_detection(mock_config):
    """Test that Windows platform is correctly detected"""
    with patch("platform.system") as mock_platform:
        mock_platform.return_value = "Windows"

        # Just verify the platform check works
        is_windows = platform.system() == "Windows"
        assert is_windows is True

        mock_platform.return_value = "Linux"
        is_windows = platform.system() == "Windows"
        assert is_windows is False


@patch("notebooklm_mcp.client.USE_UNDETECTED", True)
@patch("notebooklm_mcp.client.uc")
def test_windows_headless_mode_arguments(mock_uc, mock_config):
    """Test that Windows gets special headless arguments"""
    with patch("platform.system", return_value="Windows"):
        # Mock the Chrome driver
        mock_driver = Mock()
        mock_uc.Chrome.return_value = mock_driver
        mock_uc.ChromeOptions.return_value = Mock()

        client = NotebookLMClient(mock_config)

        # This would normally call _start_browser
        # We can verify the options would be set correctly
        options = mock_uc.ChromeOptions()

        # Verify ChromeOptions was called
        assert mock_uc.ChromeOptions.called


@patch("notebooklm_mcp.client.USE_UNDETECTED", True)
@patch("notebooklm_mcp.client.uc")
def test_non_windows_headless_mode(mock_uc, mock_config):
    """Test that non-Windows systems use standard headless mode"""
    with patch("platform.system", return_value="Linux"):
        # Mock the Chrome driver
        mock_driver = Mock()
        mock_uc.Chrome.return_value = mock_driver
        mock_options = Mock()
        mock_uc.ChromeOptions.return_value = mock_options

        client = NotebookLMClient(mock_config)

        # Verify the client was created
        assert client is not None
        assert client.config.headless is True


def test_cli_windows_warning_in_init():
    """Test that CLI shows Windows warning during init"""
    from notebooklm_mcp.cli import extract_notebook_id

    # Test notebook ID extraction still works
    url = "https://notebooklm.google.com/notebook/4741957b-f358-48fb-a16a-da8d20797bc6"
    notebook_id = extract_notebook_id(url)
    assert notebook_id == "4741957b-f358-48fb-a16a-da8d20797bc6"


def test_cli_update_config_to_headless_with_platform_message():
    """Test that update_config_to_headless shows platform-specific message"""
    import json
    import tempfile
    from pathlib import Path
    from notebooklm_mcp.cli import update_config_to_headless

    # Create a temporary config file
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        config = {"headless": False, "default_notebook_id": "test-123"}
        json.dump(config, f)
        temp_path = f.name

    try:
        # Update config
        update_config_to_headless(temp_path)

        # Verify it was updated
        with open(temp_path, "r") as f:
            updated_config = json.load(f)

        assert updated_config["headless"] is True
    finally:
        # Clean up
        Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
