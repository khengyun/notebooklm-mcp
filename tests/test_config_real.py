"""
Real unit tests for NotebookLM MCP - sử dụng pytest
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from notebooklm_mcp.config import AuthConfig, ServerConfig
from notebooklm_mcp.exceptions import ConfigurationError


class TestServerConfig:
    """Test ServerConfig class với pytest"""

    def test_default_values(self):
        """Test default configuration values"""
        config = ServerConfig()

        assert config.headless is False
        assert config.timeout == 60
        assert config.debug is False
        assert config.default_notebook_id is None
        assert config.base_url == "https://notebooklm.google.com"
        assert isinstance(config.auth, AuthConfig)

    def test_custom_values(self):
        """Test custom configuration values"""
        config = ServerConfig(
            headless=True, timeout=30, debug=True, default_notebook_id="test-id"
        )

        assert config.headless is True
        assert config.timeout == 30
        assert config.debug is True
        assert config.default_notebook_id == "test-id"

    def test_validation_success(self):
        """Test successful validation"""
        config = ServerConfig(timeout=30, streaming_timeout=45)
        config.validate()  # Should not raise

    def test_validation_negative_timeout(self):
        """Test validation fails for negative timeout"""
        config = ServerConfig(timeout=-1)

        with pytest.raises(ConfigurationError, match="Timeout must be positive"):
            config.validate()

    def test_validation_negative_streaming_timeout(self):
        """Test validation fails for negative streaming timeout"""
        config = ServerConfig(streaming_timeout=-1)

        with pytest.raises(
            ConfigurationError, match="Streaming timeout must be positive"
        ):
            config.validate()

    def test_to_dict(self):
        """Test configuration serialization"""
        config = ServerConfig(headless=True, timeout=30)
        data = config.to_dict()

        assert isinstance(data, dict)
        assert data["headless"] is True
        assert data["timeout"] == 30
        assert "auth" in data

    def test_from_dict(self):
        """Test configuration deserialization"""
        data = {
            "headless": True,
            "timeout": 45,
            "debug": True,
            "default_notebook_id": "test-notebook",
        }

        config = ServerConfig.from_dict(data)

        assert config.headless is True
        assert config.timeout == 45
        assert config.debug is True
        assert config.default_notebook_id == "test-notebook"

    def test_from_env_variables(self):
        """Test configuration from environment variables"""
        env_vars = {
            "NOTEBOOKLM_HEADLESS": "true",
            "NOTEBOOKLM_TIMEOUT": "90",
            "NOTEBOOKLM_DEBUG": "false",
            "NOTEBOOKLM_NOTEBOOK_ID": "env-notebook",
        }

        with patch.dict("os.environ", env_vars):
            config = ServerConfig.from_env()

            assert config.headless is True
            assert config.timeout == 90
            assert config.debug is False
            assert config.default_notebook_id == "env-notebook"


class TestAuthConfig:
    """Test AuthConfig class"""

    def test_default_auth_config(self):
        """Test default auth configuration"""
        auth = AuthConfig()

        assert auth.cookies_path is None
        assert auth.profile_dir == "./chrome_profile_notebooklm"
        assert auth.use_persistent_session is True
        assert auth.auto_login is True


if __name__ == "__main__":
    # Run tests if called directly
    pytest.main([__file__, "-v"])
