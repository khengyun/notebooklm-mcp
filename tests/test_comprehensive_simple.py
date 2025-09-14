"""
Simplified professional tests for NotebookLM modules
"""

import pytest
from unittest.mock import Mock, patch

from notebooklm_mcp.config import ServerConfig, AuthConfig
from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.exceptions import NotebookLMError


class TestConfigurationModule:
    """Comprehensive tests for configuration module"""
    
    def test_server_config_defaults(self):
        """Test default server configuration values"""
        config = ServerConfig()
        
        assert config.headless is False  # Default is False, not True
        assert config.timeout == 60
        assert config.debug is False
        assert config.default_notebook_id is None
        assert config.base_url == "https://notebooklm.google.com"
    
    def test_server_config_custom_values(self):
        """Test custom server configuration"""
        config = ServerConfig(
            headless=False,
            timeout=120,
            debug=True,
            default_notebook_id="custom-notebook",
            base_url="https://custom.url.com"
        )
        
        assert config.headless is False
        assert config.timeout == 120
        assert config.debug is True
        assert config.default_notebook_id == "custom-notebook"
        assert config.base_url == "https://custom.url.com"
    
    def test_auth_config_defaults(self):
        """Test default authentication configuration"""
        auth = AuthConfig()
        
        assert auth.profile_dir == "./chrome_profile_notebooklm"
        assert auth.use_persistent_session is True
        assert auth.auto_login is True
    
    def test_config_validation_success(self):
        """Test successful configuration validation"""
        config = ServerConfig(timeout=60, streaming_timeout=30)
        
        # Should not raise exception
        config.validate()
    
    def test_config_validation_negative_timeout(self):
        """Test validation fails with negative timeout"""
        from notebooklm_mcp.exceptions import ConfigurationError
        
        config = ServerConfig(timeout=-10)
        
        with pytest.raises(ConfigurationError, match="Timeout must be positive"):
            config.validate()
    
    def test_config_to_dict(self):
        """Test configuration serialization to dict"""
        config = ServerConfig(
            headless=True,
            timeout=90,
            debug=False,
            default_notebook_id="test-notebook"
        )
        
        data = config.to_dict()
        
        assert data["headless"] is True
        assert data["timeout"] == 90
        assert data["debug"] is False
        assert data["default_notebook_id"] == "test-notebook"
        assert "auth" in data
    
    def test_config_from_dict(self):
        """Test configuration creation from dict"""
        data = {
            "headless": False,
            "timeout": 120,
            "debug": True,
            "default_notebook_id": "dict-notebook",
            "auth": {
                "profile_dir": "./custom_profile",
                "use_persistent_session": False
            }
        }
        
        config = ServerConfig.from_dict(data)
        
        assert config.headless is False
        assert config.timeout == 120
        assert config.debug is True
        assert config.default_notebook_id == "dict-notebook"
        assert config.auth.profile_dir == "./custom_profile"
        assert config.auth.use_persistent_session is False


class TestClientModule:
    """Professional tests for client module"""
    
    def test_client_initialization(self):
        """Test client initialization"""
        config = ServerConfig(default_notebook_id="test-notebook")
        client = NotebookLMClient(config)
        
        assert client.config == config
        assert client.current_notebook_id == "test-notebook"
        assert client.driver is None
        assert client._is_authenticated is False
    
    def test_client_initialization_no_notebook(self):
        """Test client initialization without notebook ID"""
        config = ServerConfig()
        client = NotebookLMClient(config)
        
        assert client.current_notebook_id is None
    
    @patch('notebooklm_mcp.client.uc')
    def test_start_browser_mock(self, mock_uc):
        """Test browser startup with mocking"""
        mock_driver = Mock()
        mock_uc.Chrome.return_value = mock_driver
        
        config = ServerConfig(headless=True)
        client = NotebookLMClient(config)
        
        # Call the sync method directly for testing
        client._start_browser()
        
        assert client.driver == mock_driver
        mock_driver.set_page_load_timeout.assert_called_once()
    
    def test_browser_configuration_headless(self):
        """Test browser configuration for headless mode"""
        config = ServerConfig(headless=True)
        client = NotebookLMClient(config)
        
        # Test that config is properly set
        assert client.config.headless is True
    
    def test_browser_configuration_with_profile(self):
        """Test browser configuration with persistent profile"""
        auth_config = AuthConfig(
            profile_dir="./test_profile",
            use_persistent_session=True
        )
        config = ServerConfig(auth=auth_config)
        client = NotebookLMClient(config)
        
        assert client.config.auth.profile_dir == "./test_profile"
        assert client.config.auth.use_persistent_session is True


class TestExceptionsModule:
    """Test custom exceptions"""
    
    def test_notebooklm_error_creation(self):
        """Test NotebookLMError exception creation"""
        error = NotebookLMError("Test error message")
        
        assert str(error) == "Test error message"
        assert isinstance(error, Exception)
    
    def test_notebooklm_error_inheritance(self):
        """Test that custom exceptions inherit from NotebookLMError"""
        from notebooklm_mcp.exceptions import AuthenticationError, NavigationError, ChatError
        
        auth_error = AuthenticationError("Auth failed")
        nav_error = NavigationError("Navigation failed")
        chat_error = ChatError("Chat failed")
        
        assert isinstance(auth_error, NotebookLMError)
        assert isinstance(nav_error, NotebookLMError)
        assert isinstance(chat_error, NotebookLMError)


class TestIntegrationScenarios:
    """Integration test scenarios"""
    
    def test_complete_config_workflow(self):
        """Test complete configuration workflow"""
        # Create custom auth config
        auth_config = AuthConfig(
            profile_dir="./integration_profile",
            use_persistent_session=True,
            auto_login=False
        )
        
        # Create server config with auth
        server_config = ServerConfig(
            headless=True,
            timeout=90,
            debug=True,
            default_notebook_id="integration-notebook",
            auth=auth_config
        )
        
        # Validate configuration
        server_config.validate()
        
        # Create client with config
        client = NotebookLMClient(server_config)
        
        # Verify client has correct configuration
        assert client.config.headless is True
        assert client.config.timeout == 90
        assert client.config.debug is True
        assert client.current_notebook_id == "integration-notebook"
        assert client.config.auth.profile_dir == "./integration_profile"
    
    def test_config_serialization_roundtrip(self):
        """Test configuration serialization and deserialization"""
        original_config = ServerConfig(
            headless=False,
            timeout=120,
            debug=True,
            default_notebook_id="roundtrip-test",
            streaming_timeout=45,
            response_stability_checks=3
        )
        
        # Serialize to dict
        config_dict = original_config.to_dict()
        
        # Deserialize back to config
        restored_config = ServerConfig.from_dict(config_dict)
        
        # Verify all values match
        assert restored_config.headless == original_config.headless
        assert restored_config.timeout == original_config.timeout
        assert restored_config.debug == original_config.debug
        assert restored_config.default_notebook_id == original_config.default_notebook_id
        assert restored_config.streaming_timeout == original_config.streaming_timeout
        assert restored_config.response_stability_checks == original_config.response_stability_checks
    
    def test_error_handling_chain(self):
        """Test error handling in realistic scenarios"""
        from notebooklm_mcp.exceptions import ConfigurationError
        
        config = ServerConfig(timeout=-1)  # Invalid config
        
        # Should raise ConfigurationError (not ValueError)
        with pytest.raises(ConfigurationError):
            config.validate()
        
        # Test that client can handle invalid config gracefully
        client = NotebookLMClient(config)
        assert client.config.timeout == -1  # Config is stored as-is
    
    def test_multiple_client_instances(self):
        """Test multiple client instances with different configs"""
        config1 = ServerConfig(
            default_notebook_id="client1-notebook",
            headless=True
        )
        config2 = ServerConfig(
            default_notebook_id="client2-notebook",
            headless=False
        )
        
        client1 = NotebookLMClient(config1)
        client2 = NotebookLMClient(config2)
        
        # Verify clients are independent
        assert client1.current_notebook_id == "client1-notebook"
        assert client2.current_notebook_id == "client2-notebook"
        assert client1.config.headless is True
        assert client2.config.headless is False
        
        # Verify clients don't share state
        assert client1 is not client2
        assert client1.config is not client2.config


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_empty_notebook_id(self):
        """Test handling of empty notebook ID"""
        config = ServerConfig(default_notebook_id="")
        client = NotebookLMClient(config)
        
        assert client.current_notebook_id == ""
    
    def test_none_notebook_id(self):
        """Test handling of None notebook ID"""
        config = ServerConfig(default_notebook_id=None)
        client = NotebookLMClient(config)
        
        assert client.current_notebook_id is None
    
    def test_very_long_notebook_id(self):
        """Test handling of very long notebook ID"""
        long_id = "a" * 1000
        config = ServerConfig(default_notebook_id=long_id)
        client = NotebookLMClient(config)
        
        assert client.current_notebook_id == long_id
    
    def test_special_characters_in_notebook_id(self):
        """Test handling of special characters in notebook ID"""
        special_id = "notebook-with-special-chars-@#$%^&*()"
        config = ServerConfig(default_notebook_id=special_id)
        client = NotebookLMClient(config)
        
        assert client.current_notebook_id == special_id
    
    def test_extreme_timeout_values(self):
        """Test extreme timeout values"""
        from notebooklm_mcp.exceptions import ConfigurationError
        
        # Very small timeout
        config_small = ServerConfig(timeout=1)
        assert config_small.timeout == 1
        
        # Very large timeout
        config_large = ServerConfig(timeout=86400)  # 24 hours
        assert config_large.timeout == 86400
        
        # Zero timeout should be invalid
        config_zero = ServerConfig(timeout=0)
        with pytest.raises(ConfigurationError):
            config_zero.validate()


class TestPerformanceScenarios:
    """Performance-related test scenarios"""
    
    def test_config_creation_performance(self):
        """Test that config creation is fast"""
        import time
        
        start_time = time.time()
        
        # Create many config instances
        configs = []
        for i in range(1000):
            config = ServerConfig(
                default_notebook_id=f"notebook-{i}",
                timeout=60 + i
            )
            configs.append(config)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should create 1000 configs in less than 1 second
        assert duration < 1.0
        assert len(configs) == 1000
    
    def test_client_creation_performance(self):
        """Test that client creation is fast"""
        import time
        
        config = ServerConfig()
        start_time = time.time()
        
        # Create many client instances
        clients = []
        for i in range(100):
            client = NotebookLMClient(config)
            clients.append(client)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should create 100 clients very quickly
        assert duration < 0.5
        assert len(clients) == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])