"""
Integration tests for NotebookLM MCP server
"""

import pytest
import os
import json
from unittest.mock import patch

from notebooklm_mcp import NotebookLMClient, ServerConfig


@pytest.mark.integration
@pytest.mark.browser
class TestNotebookLMIntegration:
    """Integration tests requiring browser"""
    
    @pytest.fixture
    def config(self):
        """Test configuration for integration tests"""
        return ServerConfig(
            default_notebook_id=os.getenv("TEST_NOTEBOOK_ID", "test-notebook-id"),
            headless=True,
            debug=True,
            timeout=30
        )
    
    @pytest.mark.asyncio
    async def test_browser_startup_and_shutdown(self, config):
        """Test browser can start and stop successfully"""
        client = NotebookLMClient(config)
        
        try:
            await client.start()
            assert client.driver is not None
            
        finally:
            await client.close()
            assert client.driver is None
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_authentication_flow(self, config):
        """Test authentication flow (may require manual intervention)"""
        client = NotebookLMClient(config)
        
        try:
            await client.start()
            
            # Attempt authentication
            auth_result = await client.authenticate()
            
            # Note: This test may fail if no valid session exists
            # In CI, we expect this to fail gracefully
            assert isinstance(auth_result, bool)
            
        finally:
            await client.close()
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_notebook_navigation(self, config):
        """Test navigation to notebook"""
        client = NotebookLMClient(config)
        
        try:
            await client.start()
            
            # Navigate to notebook
            result_url = await client.navigate_to_notebook(config.default_notebook_id)
            
            assert "notebooklm.google.com" in result_url
            assert config.default_notebook_id in result_url
            
        finally:
            await client.close()
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("NOTEBOOKLM_INTEGRATION_TESTS"),
        reason="Full integration tests require NOTEBOOKLM_INTEGRATION_TESTS=1"
    )
    async def test_full_chat_flow(self, config):
        """Test complete chat flow (requires authenticated session)"""
        client = NotebookLMClient(config)
        
        try:
            await client.start()
            
            # Authenticate
            auth_success = await client.authenticate()
            if not auth_success:
                pytest.skip("Authentication required for full chat test")
            
            # Send message
            test_message = "Hello, can you provide a brief summary?"
            await client.send_message(test_message)
            
            # Get response
            response = await client.get_response(wait_for_completion=True, max_wait=30)
            
            assert isinstance(response, str)
            assert len(response) > 0
            assert response != "No response content found"
            
        finally:
            await client.close()


@pytest.mark.integration
class TestConfigurationIntegration:
    """Integration tests for configuration management"""
    
    def test_config_file_integration(self, tmp_path):
        """Test configuration file loading in realistic scenario"""
        config_file = tmp_path / "test_config.json"
        config_content = {
            "headless": True,
            "timeout": 45,
            "debug": True,
            "default_notebook_id": "integration-test-notebook",
            "auth": {
                "profile_dir": str(tmp_path / "chrome_profile"),
                "use_persistent_session": True
            }
        }
        
        config_file.write_text(json.dumps(config_content))
        
        from notebooklm_mcp.config import ServerConfig
        config = ServerConfig.from_file(str(config_file))
        
        assert config.headless is True
        assert config.timeout == 45
        assert config.debug is True
        assert config.default_notebook_id == "integration-test-notebook"
        assert config.auth.use_persistent_session is True
    
    def test_environment_integration(self):
        """Test environment variable configuration"""
        test_env = {
            "NOTEBOOKLM_HEADLESS": "true",
            "NOTEBOOKLM_TIMEOUT": "90",
            "NOTEBOOKLM_DEBUG": "false",
            "NOTEBOOKLM_NOTEBOOK_ID": "env-integration-test"
        }
        
        with patch.dict(os.environ, test_env):
            from notebooklm_mcp.config import ServerConfig
            config = ServerConfig.from_env()
            
            assert config.headless is True
            assert config.timeout == 90
            assert config.debug is False
            assert config.default_notebook_id == "env-integration-test"