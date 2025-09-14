"""
Configuration tests
"""

import json
import os
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, "src")

from notebooklm_mcp.config import AuthConfig, ServerConfig, load_config
from notebooklm_mcp.exceptions import ConfigurationError


@pytest.mark.unit
class TestServerConfig:
    """Test server configuration"""

    def test_default_config(self):
        """Test default configuration values"""
        config = ServerConfig()

        assert config.headless is False
        assert config.timeout == 60
        assert config.debug is False
        assert config.default_notebook_id is None
        assert config.base_url == "https://notebooklm.google.com"
        assert isinstance(config.auth, AuthConfig)

    def test_config_validation_success(self):
        """Test successful configuration validation"""
        config = ServerConfig(
            timeout=30,
            streaming_timeout=45,
            response_stability_checks=3,
            retry_attempts=2,
        )

        # Should not raise
        config.validate()

    def test_config_validation_negative_timeout(self):
        """Test validation fails for negative timeout"""
        config = ServerConfig(timeout=-1)

        with pytest.raises(ConfigurationError, match="Timeout must be positive"):
            config.validate()

    def test_config_validation_negative_streaming_timeout(self):
        """Test validation fails for negative streaming timeout"""
        config = ServerConfig(streaming_timeout=-1)

        with pytest.raises(
            ConfigurationError, match="Streaming timeout must be positive"
        ):
            config.validate()

    def test_config_to_dict(self):
        """Test configuration serialization"""
        config = ServerConfig(
            headless=True, timeout=30, debug=True, default_notebook_id="test-id"
        )

        config_dict = config.to_dict()

        assert config_dict["headless"] is True
        assert config_dict["timeout"] == 30
        assert config_dict["debug"] is True
        assert config_dict["default_notebook_id"] == "test-id"
        assert "auth" in config_dict

    def test_config_from_dict(self):
        """Test configuration deserialization"""
        config_data = {
            "headless": True,
            "timeout": 30,
            "debug": True,
            "default_notebook_id": "test-id",
            "auth": {"profile_dir": "./test_profile", "use_persistent_session": False},
        }

        config = ServerConfig.from_dict(config_data)

        assert config.headless is True
        assert config.timeout == 30
        assert config.debug is True
        assert config.default_notebook_id == "test-id"
        assert config.auth.profile_dir == "./test_profile"
        assert config.auth.use_persistent_session is False

    def test_config_save_and_load(self):
        """Test configuration file save and load"""
        config = ServerConfig(
            headless=True, timeout=45, debug=True, default_notebook_id="test-notebook"
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_path = f.name

        try:
            # Save configuration
            config.save_to_file(config_path)

            # Load configuration
            loaded_config = ServerConfig.from_file(config_path)

            assert loaded_config.headless == config.headless
            assert loaded_config.timeout == config.timeout
            assert loaded_config.debug == config.debug
            assert loaded_config.default_notebook_id == config.default_notebook_id

        finally:
            os.unlink(config_path)

    def test_config_from_env(self):
        """Test configuration from environment variables"""
        env_vars = {
            "NOTEBOOKLM_HEADLESS": "true",
            "NOTEBOOKLM_TIMEOUT": "45",
            "NOTEBOOKLM_DEBUG": "true",
            "NOTEBOOKLM_NOTEBOOK_ID": "env-notebook-id",
            "NOTEBOOKLM_PROFILE_DIR": "./env_profile",
        }

        with patch.dict(os.environ, env_vars):
            config = ServerConfig.from_env()

            assert config.headless is True
            assert config.timeout == 45
            assert config.debug is True
            assert config.default_notebook_id == "env-notebook-id"
            assert config.auth.profile_dir == "./env_profile"


@pytest.mark.unit
class TestAuthConfig:
    """Test authentication configuration"""

    def test_default_auth_config(self):
        """Test default auth configuration"""
        auth = AuthConfig()

        assert auth.cookies_path is None
        assert auth.profile_dir == "./chrome_profile_notebooklm"
        assert auth.use_persistent_session is True
        assert auth.auto_login is True


@pytest.mark.unit
class TestLoadConfig:
    """Test configuration loading functions"""

    def test_load_config_from_file(self):
        """Test loading configuration from file"""
        config_data = {
            "headless": True,
            "timeout": 30,
            "debug": False,
            "default_notebook_id": "file-notebook-id",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            config = load_config(config_path)

            assert config.headless is True
            assert config.timeout == 30
            assert config.default_notebook_id == "file-notebook-id"

        finally:
            os.unlink(config_path)

    def test_load_config_nonexistent_file(self):
        """Test loading config from non-existent file falls back to env"""
        with patch("notebooklm_mcp.config.ServerConfig.from_env") as mock_from_env:
            mock_from_env.return_value = ServerConfig(debug=True)

            config = load_config("/nonexistent/config.json")

            mock_from_env.assert_called_once()
            assert config.debug is True

    def test_load_config_no_args(self):
        """Test loading config without arguments"""
        with (
            patch("os.path.exists", return_value=False),
            patch("notebooklm_mcp.config.ServerConfig.from_env") as mock_from_env,
        ):
            mock_from_env.return_value = ServerConfig(headless=True)

            config = load_config()

            mock_from_env.assert_called_once()
            assert config.headless is True
