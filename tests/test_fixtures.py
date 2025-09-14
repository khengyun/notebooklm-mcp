"""
Professional test fixtures and utilities for NotebookLM MCP testing
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from typing import Dict, Any, Generator
from contextlib import asynccontextmanager

from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import TimeoutException, WebDriverException

from notebooklm_mcp.config import ServerConfig, AuthConfig
from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.server import NotebookLMServer


# ====================
# Configuration Fixtures
# ====================

@pytest.fixture
def default_config() -> ServerConfig:
    """Default server configuration for testing"""
    return ServerConfig(
        headless=True,
        timeout=30,
        debug=True,
        default_notebook_id="test-notebook-default"
    )


@pytest.fixture
def custom_config() -> ServerConfig:
    """Custom server configuration with specific settings"""
    auth_config = AuthConfig(
        profile_dir="./test_profile",
        use_persistent_session=True,
        auto_login=True
    )
    
    return ServerConfig(
        headless=False,
        timeout=60,
        debug=False,
        default_notebook_id="custom-test-notebook",
        auth=auth_config,
        streaming_timeout=45,
        response_stability_checks=5,
        retry_attempts=2
    )


@pytest.fixture
def config_file(tmp_path: Path) -> Generator[Path, None, None]:
    """Temporary configuration file for testing"""
    config_data = {
        "headless": True,
        "timeout": 120,
        "debug": True,
        "default_notebook_id": "file-test-notebook",
        "auth": {
            "profile_dir": "./file_test_profile",
            "use_persistent_session": False,
            "auto_login": False
        },
        "streaming_timeout": 90,
        "response_stability_checks": 3
    }
    
    config_file = tmp_path / "test_config.json"
    with open(config_file, 'w') as f:
        json.dump(config_data, f, indent=2)
    
    yield config_file
    
    # Cleanup
    if config_file.exists():
        config_file.unlink()


# ====================
# Mock WebDriver Fixtures
# ====================

@pytest.fixture
def mock_webelement() -> Mock:
    """Mock WebElement for testing"""
    element = Mock(spec=WebElement)
    element.text = "Mock element text"
    element.is_displayed.return_value = True
    element.is_enabled.return_value = True
    element.clear.return_value = None
    element.click.return_value = None
    element.send_keys.return_value = None
    element.get_attribute.return_value = "mock-attribute"
    return element


@pytest.fixture
def mock_webdriver() -> Mock:
    """Mock WebDriver for testing browser operations"""
    driver = Mock()
    driver.current_url = "https://notebooklm.google.com/notebook/test"
    driver.title = "NotebookLM - Test Notebook"
    driver.page_source = "<html><body>Test page</body></html>"
    
    # Mock navigation methods
    driver.get.return_value = None
    driver.refresh.return_value = None
    driver.back.return_value = None
    driver.forward.return_value = None
    
    # Mock element finding methods
    driver.find_element.return_value = mock_webelement()
    driver.find_elements.return_value = [mock_webelement()]
    
    # Mock window management
    driver.maximize_window.return_value = None
    driver.minimize_window.return_value = None
    driver.set_window_size.return_value = None
    driver.get_window_size.return_value = {"width": 1920, "height": 1080}
    
    # Mock session management
    driver.quit.return_value = None
    driver.close.return_value = None
    driver.set_page_load_timeout.return_value = None
    driver.implicitly_wait.return_value = None
    
    # Mock JavaScript execution
    driver.execute_script.return_value = None
    
    # Mock screenshot
    driver.save_screenshot.return_value = True
    driver.get_screenshot_as_png.return_value = b"fake_screenshot_data"
    
    return driver


@pytest.fixture
def mock_webdriver_wait() -> Mock:
    """Mock WebDriverWait for testing waiting conditions"""
    wait = Mock()
    wait.until.return_value = mock_webelement()
    wait.until_not.return_value = True
    return wait


# ====================
# Client Fixtures
# ====================

@pytest.fixture
def mock_client() -> Mock:
    """Mock NotebookLM client for testing"""
    client = AsyncMock(spec=NotebookLMClient)
    
    # Mock basic properties
    client.config = default_config()
    client.driver = None
    client.current_notebook_id = "test-notebook"
    client._is_authenticated = False
    
    # Mock async methods
    client.start.return_value = None
    client.close.return_value = None
    client.authenticate.return_value = True
    client.is_authenticated.return_value = True
    client.navigate_to_notebook.return_value = None
    client.send_message.return_value = None
    client.get_response.return_value = "Mock AI response"
    client.wait_for_response_completion.return_value = True
    
    return client


@pytest.fixture
def client_with_driver(mock_webdriver: Mock, default_config: ServerConfig) -> NotebookLMClient:
    """NotebookLM client with mocked driver attached"""
    client = NotebookLMClient(default_config)
    client.driver = mock_webdriver
    client._is_authenticated = True
    return client


@pytest.fixture
def authenticated_client(mock_webdriver: Mock, default_config: ServerConfig) -> NotebookLMClient:
    """Authenticated NotebookLM client ready for operations"""
    client = NotebookLMClient(default_config)
    client.driver = mock_webdriver
    client._is_authenticated = True
    client.current_notebook_id = "authenticated-test-notebook"
    return client


# ====================
# Server Fixtures
# ====================

@pytest.fixture
def mock_server() -> Mock:
    """Mock NotebookLM server for testing"""
    server = AsyncMock(spec=NotebookLMServer)
    server.config = default_config()
    server.client = None
    
    # Mock tool operations
    server.list_tools.return_value = [
        {"name": "healthcheck", "description": "Check server health"},
        {"name": "send_chat_message", "description": "Send a message"},
        {"name": "get_chat_response", "description": "Get AI response"}
    ]
    
    server.call_tool.return_value = {
        "content": [{"type": "text", "text": "Mock tool response"}]
    }
    
    # Mock lifecycle methods
    server.cleanup.return_value = None
    
    return server


@pytest.fixture
def server_with_client(default_config: ServerConfig, mock_client: Mock) -> NotebookLMServer:
    """NotebookLM server with mocked client attached"""
    server = NotebookLMServer(default_config)
    server.client = mock_client
    return server


# ====================
# Browser Automation Fixtures
# ====================

@pytest.fixture
def mock_chat_elements() -> Dict[str, Mock]:
    """Mock chat interface elements"""
    chat_input = Mock(spec=WebElement)
    chat_input.text = ""
    chat_input.is_displayed.return_value = True
    
    send_button = Mock(spec=WebElement)
    send_button.is_enabled.return_value = True
    
    response_area = Mock(spec=WebElement)
    response_area.text = "AI response text"
    
    return {
        "input": chat_input,
        "send_button": send_button,
        "response": response_area
    }


@pytest.fixture
def mock_notebook_elements() -> Dict[str, Mock]:
    """Mock notebook interface elements"""
    notebook_title = Mock(spec=WebElement)
    notebook_title.text = "Test Notebook"
    
    document_list = Mock(spec=WebElement)
    document_list.find_elements.return_value = []
    
    return {
        "title": notebook_title,
        "documents": document_list
    }


# ====================
# Test Data Fixtures
# ====================

@pytest.fixture
def sample_messages() -> Dict[str, str]:
    """Sample chat messages for testing"""
    return {
        "simple": "Hello, NotebookLM!",
        "complex": "Can you analyze the uploaded document and provide a summary?",
        "long": "This is a very long message that tests the handling of extended text input. " * 10,
        "special_chars": "Test with special characters: @#$%^&*()[]{}|\\:;\"'<>?,./",
        "unicode": "Test with unicode: 🤖 Hello world! 你好世界 مرحبا بالعالم"
    }


@pytest.fixture
def sample_responses() -> Dict[str, str]:
    """Sample AI responses for testing"""
    return {
        "short": "Brief response",
        "medium": "This is a medium-length response with some detailed information.",
        "long": "This is a comprehensive response that includes multiple paragraphs and detailed analysis. " * 5,
        "thinking": "Let me think about this...",
        "complete": "Based on the document, here's my analysis: [detailed response]",
        "error": "I encountered an error while processing your request."
    }


@pytest.fixture
def sample_notebook_ids() -> Dict[str, str]:
    """Sample notebook IDs for testing"""
    return {
        "valid": "notebook-12345678-abcd-efgh-ijkl-1234567890ab",
        "short": "short-id",
        "invalid": "invalid-notebook-id-format",
        "empty": "",
        "special": "notebook-with-special-chars@#$%"
    }


# ====================
# Environment Fixtures
# ====================

@pytest.fixture
def clean_environment() -> Generator[None, None, None]:
    """Clean test environment with isolated temp directories"""
    import os
    import shutil
    
    original_cwd = os.getcwd()
    temp_dir = tempfile.mkdtemp(prefix="notebooklm_test_")
    
    try:
        os.chdir(temp_dir)
        yield
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_chrome_profile(tmp_path: Path) -> Path:
    """Mock Chrome profile directory for testing"""
    profile_dir = tmp_path / "chrome_profile_test"
    profile_dir.mkdir(exist_ok=True)
    
    # Create some fake profile files
    (profile_dir / "Default").mkdir(exist_ok=True)
    (profile_dir / "Default" / "Cookies").write_text("fake cookie data")
    (profile_dir / "Default" / "Preferences").write_text('{"test": "data"}')
    
    return profile_dir


# ====================
# Async Test Utilities
# ====================

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@asynccontextmanager
async def async_timeout(seconds: float):
    """Async context manager for test timeouts"""
    try:
        async with asyncio.timeout(seconds):
            yield
    except asyncio.TimeoutError:
        pytest.fail(f"Test timed out after {seconds} seconds")


# ====================
# Test Helpers and Utilities
# ====================

class MockResponseStream:
    """Mock streaming response for testing"""
    
    def __init__(self, responses: list[str], delay: float = 0.1):
        self.responses = responses
        self.delay = delay
        self.index = 0
    
    async def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.index >= len(self.responses):
            raise StopAsyncIteration
        
        response = self.responses[self.index]
        self.index += 1
        
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        
        return response


def assert_config_equals(config1: ServerConfig, config2: ServerConfig) -> None:
    """Assert that two configurations are equal"""
    assert config1.headless == config2.headless
    assert config1.timeout == config2.timeout
    assert config1.debug == config2.debug
    assert config1.default_notebook_id == config2.default_notebook_id
    assert config1.base_url == config2.base_url
    assert config1.streaming_timeout == config2.streaming_timeout
    assert config1.response_stability_checks == config2.response_stability_checks
    assert config1.retry_attempts == config2.retry_attempts
    
    # Compare auth config
    assert config1.auth.profile_dir == config2.auth.profile_dir
    assert config1.auth.use_persistent_session == config2.auth.use_persistent_session
    assert config1.auth.auto_login == config2.auth.auto_login


def create_mock_tool_response(content: str, success: bool = True) -> Dict[str, Any]:
    """Create a mock tool response in MCP format"""
    return {
        "content": [
            {
                "type": "text",
                "text": content
            }
        ],
        "isError": not success
    }


def mock_selenium_elements(driver_mock: Mock, element_configs: Dict[str, Dict[str, Any]]) -> None:
    """Configure mock selenium driver with specific elements"""
    def find_elements_side_effect(by, value):
        for selector, config in element_configs.items():
            if value == selector:
                elements = []
                for _ in range(config.get("count", 1)):
                    element = Mock(spec=WebElement)
                    element.text = config.get("text", "")
                    element.is_displayed.return_value = config.get("displayed", True)
                    element.is_enabled.return_value = config.get("enabled", True)
                    elements.append(element)
                return elements
        return []
    
    driver_mock.find_elements.side_effect = find_elements_side_effect


# ====================
# Parameterized Test Data
# ====================

@pytest.fixture(params=[
    {"headless": True, "timeout": 30},
    {"headless": False, "timeout": 60},
    {"headless": True, "timeout": 120, "debug": True}
])
def config_variations(request) -> ServerConfig:
    """Different configuration variations for parameterized tests"""
    return ServerConfig(**request.param)


@pytest.fixture(params=[
    "simple message",
    "message with special chars: @#$%",
    "very long message " * 20,
    ""  # empty message
])
def message_variations(request) -> str:
    """Different message variations for parameterized tests"""
    return request.param


@pytest.fixture(params=[
    TimeoutException("Element not found"),
    WebDriverException("Driver error"),
    Exception("Generic error")
])
def exception_variations(request) -> Exception:
    """Different exception types for error testing"""
    return request.param


# ====================
# Integration Test Fixtures
# ====================

@pytest.fixture
def integration_config() -> ServerConfig:
    """Configuration optimized for integration tests"""
    return ServerConfig(
        headless=True,
        timeout=10,  # Shorter timeout for faster tests
        debug=True,
        default_notebook_id="integration-test-notebook",
        streaming_timeout=15,
        response_stability_checks=2,
        retry_attempts=1
    )


@pytest.fixture
def performance_config() -> ServerConfig:
    """Configuration optimized for performance tests"""
    return ServerConfig(
        headless=True,
        timeout=5,  # Very short timeout
        debug=False,  # No debug logging for performance
        streaming_timeout=5,
        response_stability_checks=1,
        retry_attempts=1
    )


# ====================
# Cleanup Fixtures
# ====================

@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Automatic cleanup after each test"""
    yield
    # Cleanup any leftover resources
    asyncio.set_event_loop_policy(None)


if __name__ == "__main__":
    # This file contains fixtures and should not be run directly
    print("This file contains pytest fixtures and should not be run directly.")
    print("Run tests with: pytest tests/")