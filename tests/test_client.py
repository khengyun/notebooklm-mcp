"""
Unit tests for NotebookLM MCP client
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from notebooklm_mcp import NotebookLMClient, ServerConfig
from notebooklm_mcp.exceptions import AuthenticationError, ChatError


@pytest.fixture
def config():
    """Test configuration"""
    return ServerConfig(
        default_notebook_id="test-notebook-id",
        headless=True,
        debug=True
    )


@pytest.fixture
def mock_driver():
    """Mock Selenium WebDriver"""
    driver = Mock()
    driver.current_url = "https://notebooklm.google.com/notebook/test-notebook-id"
    driver.get = Mock()
    driver.find_elements = Mock(return_value=[])
    driver.quit = Mock()
    return driver


@pytest.mark.unit
class TestNotebookLMClient:
    """Test NotebookLM client functionality"""
    
    def test_client_initialization(self, config):
        """Test client initialization"""
        client = NotebookLMClient(config)
        assert client.config == config
        assert client.driver is None
        assert client.current_notebook_id == config.default_notebook_id
        assert not client._is_authenticated
    
    @pytest.mark.asyncio
    async def test_start_browser(self, config, mock_driver):
        """Test browser startup"""
        client = NotebookLMClient(config)
        
        with patch('notebooklm_mcp.client.uc.Chrome', return_value=mock_driver):
            await client.start()
            
        assert client.driver is not None
        mock_driver.set_page_load_timeout.assert_called_once_with(config.timeout)
    
    @pytest.mark.asyncio
    async def test_authentication_success(self, config, mock_driver):
        """Test successful authentication"""
        client = NotebookLMClient(config)
        client.driver = mock_driver
        
        # Mock successful authentication
        mock_driver.current_url = "https://notebooklm.google.com/notebook/test-notebook-id"
        
        with patch('selenium.webdriver.support.ui.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.return_value = True
            
            result = await client.authenticate()
            
        assert result is True
        assert client._is_authenticated is True
    
    @pytest.mark.asyncio
    async def test_authentication_failure(self, config, mock_driver):
        """Test authentication failure"""
        client = NotebookLMClient(config)
        client.driver = mock_driver
        
        # Mock authentication failure (redirect to login)
        mock_driver.current_url = "https://accounts.google.com/signin"
        
        with patch('selenium.webdriver.support.ui.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.return_value = True
            
            result = await client.authenticate()
            
        assert result is False
        assert client._is_authenticated is False
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, config, mock_driver):
        """Test successful message sending"""
        client = NotebookLMClient(config)
        client.driver = mock_driver
        client._is_authenticated = True
        
        # Mock chat input element
        mock_input = Mock()
        mock_input.clear = Mock()
        mock_input.send_keys = Mock()
        
        with patch('selenium.webdriver.support.ui.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.return_value = mock_input
            
            await client.send_message("Test message")
            
        mock_input.clear.assert_called_once()
        mock_input.send_keys.assert_called()
    
    @pytest.mark.asyncio
    async def test_send_message_not_authenticated(self, config):
        """Test message sending when not authenticated"""
        client = NotebookLMClient(config)
        client._is_authenticated = False
        
        with pytest.raises(ChatError):
            await client.send_message("Test message")
    
    @pytest.mark.asyncio
    async def test_get_response_quick(self, config, mock_driver):
        """Test quick response retrieval"""
        client = NotebookLMClient(config)
        client.driver = mock_driver
        
        # Mock response element
        mock_element = Mock()
        mock_element.text = "Test response"
        mock_driver.find_elements.return_value = [mock_element]
        
        response = await client.get_response(wait_for_completion=False)
        assert response == "Test response"
    
    @pytest.mark.asyncio
    async def test_get_response_streaming(self, config, mock_driver):
        """Test streaming response retrieval"""
        client = NotebookLMClient(config)
        client.driver = mock_driver
        
        # Mock stable response after streaming
        mock_element = Mock()
        mock_element.text = "Complete response"
        mock_driver.find_elements.return_value = [mock_element]
        
        with patch('time.sleep'):  # Speed up test
            response = await client.get_response(wait_for_completion=True, max_wait=5)
            
        assert response == "Complete response"
    
    @pytest.mark.asyncio
    async def test_navigate_to_notebook(self, config, mock_driver):
        """Test notebook navigation"""
        client = NotebookLMClient(config)
        client.driver = mock_driver
        
        with patch('selenium.webdriver.support.ui.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.return_value = True
            
            result = await client.navigate_to_notebook("new-notebook-id")
            
        assert client.current_notebook_id == "new-notebook-id"
        mock_driver.get.assert_called_with("https://notebooklm.google.com/notebook/new-notebook-id")
    
    @pytest.mark.asyncio
    async def test_close(self, config, mock_driver):
        """Test client cleanup"""
        client = NotebookLMClient(config)
        client.driver = mock_driver
        client._is_authenticated = True
        
        await client.close()
        
        assert client.driver is None
        assert client._is_authenticated is False
        mock_driver.quit.assert_called_once()