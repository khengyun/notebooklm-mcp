"""Additional behavioural coverage for :mod:`notebooklm_mcp.client`."""

from unittest.mock import Mock, patch

import pytest
from selenium.common.exceptions import TimeoutException

from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.config import ServerConfig
from notebooklm_mcp.exceptions import ChatError, NavigationError


@pytest.fixture
def client_config() -> ServerConfig:
    """Configuration tuned for fast test execution."""

    return ServerConfig(
        default_notebook_id="test-notebook",
        headless=True,
        response_stability_checks=1,
    )


@pytest.fixture
def client_with_driver(client_config: ServerConfig) -> NotebookLMClient:
    """Client instance with a fully mocked Selenium driver."""

    client = NotebookLMClient(client_config)
    driver = Mock()
    driver.current_url = "https://notebooklm.google.com/notebook/test-notebook"
    driver.get = Mock()
    driver.find_elements = Mock(return_value=[])
    driver.quit = Mock()
    driver.close = Mock()
    driver.set_page_load_timeout = Mock()
    client.driver = driver
    client._is_authenticated = True
    return client


@pytest.mark.asyncio
async def test_get_response_quick_mode_handles_missing_elements(
    client_with_driver: NotebookLMClient,
):
    """When no elements are found the client should return the fallback message."""

    client_with_driver.driver.find_elements.return_value = []

    response = await client_with_driver.get_response(wait_for_completion=False)

    assert response == "No response content found"


@pytest.mark.asyncio
async def test_get_response_streaming_waits_for_stable_content(
    client_with_driver: NotebookLMClient, monkeypatch: pytest.MonkeyPatch
):
    """The streaming helper should wait until the response stops changing."""

    calls = {"count": 0}

    def fake_get_current_response() -> str:
        calls["count"] += 1
        if calls["count"] < 2:
            return "Partial response"
        return "Final response"

    monkeypatch.setattr(
        client_with_driver, "_get_current_response", fake_get_current_response
    )
    monkeypatch.setattr(
        client_with_driver, "_check_streaming_indicators", lambda: False
    )

    with patch("time.sleep"):
        response = await client_with_driver.get_response(
            wait_for_completion=True, max_wait=2
        )

    assert response == "Final response"


@pytest.mark.asyncio
async def test_send_message_raises_when_input_missing(
    client_with_driver: NotebookLMClient,
):
    """If no chat input can be located a :class:`ChatError` should be raised."""

    with patch("selenium.webdriver.support.ui.WebDriverWait") as mock_wait:
        mock_wait.return_value.until.side_effect = TimeoutException()

        with pytest.raises(ChatError, match="Could not find chat input"):
            await client_with_driver.send_message("hello")


@pytest.mark.asyncio
async def test_navigate_to_notebook_updates_state(
    client_with_driver: NotebookLMClient,
):
    """Notebook navigation should update the stored notebook id and URL."""

    with patch("selenium.webdriver.support.ui.WebDriverWait") as mock_wait:
        mock_wait.return_value.until.return_value = True

        result = await client_with_driver.navigate_to_notebook("new-notebook")

    expected_url = "https://notebooklm.google.com/notebook/new-notebook"
    client_with_driver.driver.get.assert_called_with(expected_url)
    assert client_with_driver.current_notebook_id == "new-notebook"
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_navigate_to_notebook_without_driver_raises(
    client_config: ServerConfig,
) -> None:
    """Calling navigate_to_notebook without a driver should raise an error."""

    client = NotebookLMClient(client_config)

    with pytest.raises(NavigationError, match="Browser not started"):
        await client.navigate_to_notebook("abc")


def test_clean_response_text_filters_ui_artifacts(client_config: ServerConfig) -> None:
    """The response cleaner should strip UI artefacts from the tail of strings."""

    client = NotebookLMClient(client_config)
    noisy_response = "Here is the answer\ncopy_all\nthumb_up"

    cleaned = client._clean_response_text(noisy_response)

    assert "copy_all" not in cleaned
    assert "thumb_up" not in cleaned
    assert "Here is the answer" in cleaned
