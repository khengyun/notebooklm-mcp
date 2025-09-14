"""
Comprehensive tests for NotebookLM client module
"""

import pytest
from unittest.mock import Mock, patch
from selenium.common.exceptions import TimeoutException, WebDriverException

from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.config import ServerConfig, AuthConfig
from notebooklm_mcp.exceptions import AuthenticationError, NavigationError, ChatError


class TestNotebookLMClientInitialization:
    """Test client initialization and configuration"""
    
    def test_client_initialization_default_config(self):
        """Test client initialization with default configuration"""
        config = ServerConfig()
        client = NotebookLMClient(config)
        
        assert client.config == config
        assert client.driver is None
        assert client.current_notebook_id is None
        assert client._is_authenticated is False
    
    def test_client_initialization_with_notebook_id(self):
        """Test client initialization with preset notebook ID"""
        config = ServerConfig(default_notebook_id="test-notebook-123")
        client = NotebookLMClient(config)
        
        assert client.current_notebook_id == "test-notebook-123"
    
    def test_client_initialization_custom_auth_config(self):
        """Test client initialization with custom auth configuration"""
        auth_config = AuthConfig(
            profile_dir="./custom_profile",
            use_persistent_session=False,
            auto_login=False
        )
        config = ServerConfig(auth=auth_config)
        client = NotebookLMClient(config)
        
        assert client.config.auth.profile_dir == "./custom_profile"
        assert client.config.auth.use_persistent_session is False


class TestNotebookLMClientBrowserManagement:
    """Test browser startup, configuration, and shutdown"""
    
    @pytest.fixture
    def mock_webdriver(self):
        """Mock webdriver for testing"""
        with patch('notebooklm_mcp.client.webdriver') as mock_wd:
            mock_driver = Mock()
            mock_wd.Chrome.return_value = mock_driver
            yield mock_driver
    
    @pytest.fixture
    def mock_undetected_chrome(self):
        """Mock undetected chrome driver"""
        with patch('notebooklm_mcp.client.uc') as mock_uc:
            mock_driver = Mock()
            mock_uc.Chrome.return_value = mock_driver
            yield mock_driver
    
    @pytest.mark.asyncio
    async def test_start_browser_undetected_chrome(self, mock_undetected_chrome):
        """Test browser startup with undetected chrome"""
        config = ServerConfig(headless=True)
        client = NotebookLMClient(config)
        
        with patch('notebooklm_mcp.client.USE_UNDETECTED', True):
            await client.start()
        
        assert client.driver is not None
        mock_undetected_chrome.set_page_load_timeout.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_browser_standard_chrome(self, mock_webdriver):
        """Test browser startup with standard chrome"""
        config = ServerConfig(headless=True)
        client = NotebookLMClient(config)
        
        with patch('notebooklm_mcp.client.USE_UNDETECTED', False):
            await client.start()
        
        assert client.driver is not None
        mock_webdriver.set_page_load_timeout.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_browser_with_persistent_session(self, mock_undetected_chrome):
        """Test browser startup with persistent session"""
        config = ServerConfig(
            auth=AuthConfig(
                use_persistent_session=True,
                profile_dir="./test_profile"
            )
        )
        client = NotebookLMClient(config)
        
        with patch('notebooklm_mcp.client.USE_UNDETECTED', True), \
             patch('pathlib.Path.mkdir') as mock_mkdir:
            await client.start()
        
        mock_mkdir.assert_called_once_with(exist_ok=True)
    
    @pytest.mark.asyncio
    async def test_start_browser_headless_mode(self, mock_undetected_chrome):
        """Test browser startup in headless mode"""
        config = ServerConfig(headless=True)
        client = NotebookLMClient(config)
        
        with patch('notebooklm_mcp.client.USE_UNDETECTED', True):
            await client.start()
        
        # Should configure headless options
        assert client.driver is not None
    
    @pytest.mark.asyncio
    async def test_close_browser(self, mock_undetected_chrome):
        """Test browser cleanup"""
        config = ServerConfig()
        client = NotebookLMClient(config)
        
        with patch('notebooklm_mcp.client.USE_UNDETECTED', True):
            await client.start()
            await client.close()
        
        mock_undetected_chrome.quit.assert_called_once()
        assert client.driver is None


class TestNotebookLMClientAuthentication:
    """Test authentication flows and session management"""
    
    @pytest.fixture
    def client_with_driver(self, mock_webdriver):
        """Client with mocked driver"""
        config = ServerConfig(base_url="https://notebooklm.google.com")
        client = NotebookLMClient(config)
        client.driver = mock_webdriver
        return client
    
    @pytest.mark.asyncio
    async def test_authenticate_success(self, client_with_driver):
        """Test successful authentication"""
        mock_driver = client_with_driver.driver
        mock_driver.current_url = "https://notebooklm.google.com/notebook/test"
        
        # Mock WebDriverWait and element finding
        with patch('selenium.webdriver.support.ui.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.return_value = True
            
            success = await client_with_driver.authenticate()
        
        assert success is True
        assert client_with_driver._is_authenticated is True
        mock_driver.get.assert_called_with("https://notebooklm.google.com")
    
    @pytest.mark.asyncio
    async def test_authenticate_timeout(self, client_with_driver):
        """Test authentication timeout"""
        
        with patch('selenium.webdriver.support.ui.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.side_effect = TimeoutException()
            
            with pytest.raises(AuthenticationError):
                await client_with_driver.authenticate()
    
    @pytest.mark.asyncio
    async def test_is_authenticated_true(self, client_with_driver):
        """Test authentication status check - authenticated"""
        client_with_driver._is_authenticated = True
        mock_driver = client_with_driver.driver
        mock_driver.current_url = "https://notebooklm.google.com/notebook/test"
        
        result = await client_with_driver.is_authenticated()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_is_authenticated_false(self, client_with_driver):
        """Test authentication status check - not authenticated"""
        client_with_driver._is_authenticated = False
        mock_driver = client_with_driver.driver
        mock_driver.current_url = "https://accounts.google.com/signin"
        
        result = await client_with_driver.is_authenticated()
        assert result is False


class TestNotebookLMClientNavigation:
    """Test notebook navigation and URL handling"""
    
    @pytest.fixture
    def authenticated_client(self, mock_webdriver):
        """Client with mocked driver and authentication"""
        config = ServerConfig(base_url="https://notebooklm.google.com")
        client = NotebookLMClient(config)
        client.driver = mock_webdriver
        client._is_authenticated = True
        return client
    
    @pytest.mark.asyncio
    async def test_navigate_to_notebook_success(self, authenticated_client):
        """Test successful notebook navigation"""
        mock_driver = authenticated_client.driver
        
        with patch('selenium.webdriver.support.ui.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.return_value = True
            
            await authenticated_client.navigate_to_notebook("test-notebook-123")
        
        expected_url = "https://notebooklm.google.com/notebook/test-notebook-123"
        mock_driver.get.assert_called_with(expected_url)
        assert authenticated_client.current_notebook_id == "test-notebook-123"
    
    @pytest.mark.asyncio
    async def test_navigate_to_notebook_timeout(self, authenticated_client):
        """Test notebook navigation timeout"""
        
        with patch('selenium.webdriver.support.ui.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.side_effect = TimeoutException()
            
            with pytest.raises(NavigationError):
                await authenticated_client.navigate_to_notebook("test-notebook-123")
    
    @pytest.mark.asyncio
    async def test_navigate_to_notebook_not_authenticated(self, mock_webdriver):
        """Test navigation fails when not authenticated"""
        config = ServerConfig()
        client = NotebookLMClient(config)
        client.driver = mock_webdriver
        client._is_authenticated = False
        
        with pytest.raises(AuthenticationError):
            await client.navigate_to_notebook("test-notebook-123")


class TestNotebookLMClientChatOperations:
    """Test chat message sending and response handling"""
    
    @pytest.fixture
    def ready_client(self, mock_webdriver):
        """Client ready for chat operations"""
        config = ServerConfig()
        client = NotebookLMClient(config)
        client.driver = mock_webdriver
        client._is_authenticated = True
        client.current_notebook_id = "test-notebook"
        return client
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, ready_client):
        """Test successful message sending"""
        mock_driver = ready_client.driver
        mock_textarea = Mock()
        mock_button = Mock()
        
        mock_driver.find_elements.side_effect = [
            [mock_textarea],  # Chat input
            [mock_button]     # Send button
        ]
        
        await ready_client.send_message("Hello, NotebookLM!")
        
        mock_textarea.clear.assert_called_once()
        mock_textarea.send_keys.assert_called_with("Hello, NotebookLM!")
        mock_button.click.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_message_no_input_found(self, ready_client):
        """Test message sending when input not found"""
        mock_driver = ready_client.driver
        mock_driver.find_elements.return_value = []  # No elements found
        
        with pytest.raises(ChatError):
            await ready_client.send_message("Hello!")
    
    @pytest.mark.asyncio
    async def test_get_response_success(self, ready_client):
        """Test successful response retrieval"""
        mock_driver = ready_client.driver
        mock_response = Mock()
        mock_response.text = "This is a response from NotebookLM"
        
        mock_driver.find_elements.return_value = [mock_response]
        
        response = await ready_client.get_response()
        assert response == "This is a response from NotebookLM"
    
    @pytest.mark.asyncio
    async def test_get_response_timeout(self, ready_client):
        """Test response retrieval timeout"""
        mock_driver = ready_client.driver
        
        with patch('asyncio.sleep') as mock_sleep:
            mock_driver.find_elements.return_value = []
            
            # Should timeout after checking multiple times
            response = await ready_client.get_response(timeout=1)
            assert response == ""
            assert mock_sleep.call_count > 0
    
    @pytest.mark.asyncio
    async def test_wait_for_response_completion(self, ready_client):
        """Test waiting for response to complete"""
        mock_driver = ready_client.driver
        
        # Mock response elements with changing states
        mock_response1 = Mock()
        mock_response1.text = "Thinking..."
        mock_response2 = Mock() 
        mock_response2.text = "Complete response"
        
        mock_driver.find_elements.side_effect = [
            [mock_response1],  # First check - incomplete
            [mock_response2],  # Second check - complete
            [mock_response2],  # Third check - still complete
        ]
        
        with patch('asyncio.sleep'):
            response = await ready_client.get_response()
        
        assert response == "Complete response"


class TestNotebookLMClientErrorHandling:
    """Test error handling and edge cases"""
    
    @pytest.mark.asyncio
    async def test_webdriver_exception_handling(self):
        """Test handling of webdriver exceptions"""
        config = ServerConfig()
        client = NotebookLMClient(config)
        
        with patch('notebooklm_mcp.client.uc.Chrome', side_effect=WebDriverException("Driver failed")):
            with patch('notebooklm_mcp.client.USE_UNDETECTED', True):
                with pytest.raises(Exception):
                    await client.start()
    
    @pytest.mark.asyncio
    async def test_driver_not_started_operations(self):
        """Test operations when driver not started"""
        config = ServerConfig()
        client = NotebookLMClient(config)
        
        # All operations should fail gracefully when driver is None
        with pytest.raises((AttributeError, AuthenticationError)):
            await client.authenticate()
    
    @pytest.mark.asyncio
    async def test_cleanup_with_failed_driver(self):
        """Test cleanup when driver is in failed state"""
        config = ServerConfig()
        client = NotebookLMClient(config)
        client.driver = Mock()
        client.driver.quit.side_effect = Exception("Driver already closed")
        
        # Should not raise exception during cleanup
        await client.close()
        assert client.driver is None


class TestNotebookLMClientIntegration:
    """Integration tests for complete workflows"""
    
    @pytest.mark.asyncio
    async def test_complete_chat_workflow(self):
        """Test complete workflow: start -> auth -> navigate -> chat"""
        config = ServerConfig(default_notebook_id="test-notebook")
        client = NotebookLMClient(config)
        
        mock_driver = Mock()
        mock_textarea = Mock()
        mock_button = Mock()
        mock_response = Mock()
        mock_response.text = "AI response"
        
        with patch('notebooklm_mcp.client.uc.Chrome', return_value=mock_driver), \
             patch('notebooklm_mcp.client.USE_UNDETECTED', True), \
             patch('selenium.webdriver.support.ui.WebDriverWait') as mock_wait:
            
            # Setup successful operations
            mock_wait.return_value.until.return_value = True
            mock_driver.current_url = "https://notebooklm.google.com/notebook/test"
            mock_driver.find_elements.side_effect = [
                [mock_textarea], [mock_button],  # send_message
                [mock_response]  # get_response
            ]
            
            # Execute workflow
            await client.start()
            await client.authenticate()
            await client.navigate_to_notebook("test-notebook")
            await client.send_message("Test message")
            response = await client.get_response()
            await client.close()
            
            # Verify workflow completion
            assert response == "AI response"
            assert client.current_notebook_id == "test-notebook"
            mock_driver.quit.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])