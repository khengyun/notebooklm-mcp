"""Test configuration and lightweight dependency stubs."""

from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path
from typing import Callable, Iterator

import pytest
from click.testing import CliRunner


def _install_loguru_stub() -> None:
    if "loguru" in sys.modules:
        return

    module = types.ModuleType("loguru")

    class _Logger:
        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

        def add(self, *args, **kwargs):
            return 0

        def remove(self, *args, **kwargs):
            pass

    module.logger = _Logger()
    sys.modules["loguru"] = module


def _install_rich_stub() -> None:
    if "rich" in sys.modules:
        return

    rich_module = types.ModuleType("rich")

    class Console:
        def __init__(self) -> None:
            self.printed: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def print(self, *args, **kwargs) -> None:
            self.printed.append((args, kwargs))

    console_module = types.ModuleType("rich.console")
    console_module.Console = Console

    class Panel:
        def __init__(self, renderable, title: str | None = None) -> None:
            self.renderable = renderable
            self.title = title

        @classmethod
        def fit(cls, renderable, title: str | None = None) -> "Panel":
            return cls(renderable, title=title)

    panel_module = types.ModuleType("rich.panel")
    panel_module.Panel = Panel

    class Table:
        def __init__(self, title: str | None = None) -> None:
            self.title = title
            self.columns: list[tuple[str, str | None]] = []
            self.rows: list[tuple[object, ...]] = []

        def add_column(self, header: str, style: str | None = None) -> None:
            self.columns.append((header, style))

        def add_row(self, *values: object) -> None:
            self.rows.append(values)

    table_module = types.ModuleType("rich.table")
    table_module.Table = Table

    rich_module.console = console_module
    rich_module.panel = panel_module
    rich_module.table = table_module

    sys.modules["rich"] = rich_module
    sys.modules["rich.console"] = console_module
    sys.modules["rich.panel"] = panel_module
    sys.modules["rich.table"] = table_module


def _install_psutil_stub() -> None:
    if "psutil" in sys.modules:
        return

    psutil_module = types.ModuleType("psutil")

    class _Memory:
        def __init__(self, percent: float = 12.5, used: int = 1024) -> None:
            self.percent = percent
            self.used = used

    def virtual_memory():  # type: ignore[override]
        return _Memory()

    def cpu_percent(interval: float | None = None) -> float:
        return 15.0

    psutil_module.virtual_memory = virtual_memory  # type: ignore[attr-defined]
    psutil_module.cpu_percent = cpu_percent  # type: ignore[attr-defined]

    sys.modules["psutil"] = psutil_module


def _install_fastmcp_stub() -> None:
    if "fastmcp" in sys.modules:
        return

    fastmcp_module = types.ModuleType("fastmcp")

    class _ToolManager:
        def __init__(self) -> None:
            self._tools: dict[str, types.SimpleNamespace] = {}

    class FastMCP:
        def __init__(self, name: str) -> None:
            self.name = name
            self._tool_manager = _ToolManager()

        def tool(self, name: str | None = None):
            def decorator(fn):
                tool_name = name or fn.__name__
                self._tool_manager._tools[tool_name] = types.SimpleNamespace(fn=fn)
                return fn

            return decorator

        async def run_async(self, **kwargs) -> None:
            self.last_run_kwargs = kwargs

    fastmcp_module.FastMCP = FastMCP
    sys.modules["fastmcp"] = fastmcp_module


def _install_selenium_stub() -> None:
    if "selenium" in sys.modules:
        return

    selenium = types.ModuleType("selenium")
    sys.modules["selenium"] = selenium

    # Exceptions
    exceptions_module = types.ModuleType("selenium.common.exceptions")

    class TimeoutException(Exception):
        pass

    class WebDriverException(Exception):
        pass

    exceptions_module.TimeoutException = TimeoutException
    exceptions_module.WebDriverException = WebDriverException

    common_module = types.ModuleType("selenium.common")
    common_module.exceptions = exceptions_module

    selenium.common = common_module

    sys.modules["selenium.common"] = common_module
    sys.modules["selenium.common.exceptions"] = exceptions_module

    # Web element stub
    webelement_module = types.ModuleType("selenium.webdriver.remote.webelement")

    class WebElement:
        def __init__(self, text: str = "", displayed: bool = True) -> None:
            self.text = text
            self._displayed = displayed
            self._enabled = True

        def is_displayed(self) -> bool:
            return self._displayed

        def is_enabled(self) -> bool:
            return self._enabled

        def clear(self) -> None:
            self.text = ""

        def send_keys(self, value: str) -> None:
            self.text += value

        def click(self) -> None:
            pass

    webelement_module.WebElement = WebElement

    remote_module = types.ModuleType("selenium.webdriver.remote")
    remote_module.webelement = webelement_module

    sys.modules["selenium.webdriver.remote"] = remote_module
    sys.modules["selenium.webdriver.remote.webelement"] = webelement_module

    # WebDriver
    webdriver_module = types.ModuleType("selenium.webdriver")
    selenium.webdriver = webdriver_module

    class Chrome:
        def __init__(self, *_, **kwargs) -> None:
            self.options = kwargs.get("options")
            self.current_url = "https://notebooklm.google.com/notebook/test"
            self.visited: list[str] = []

        def set_page_load_timeout(self, value: int) -> None:
            self.page_load_timeout = value

        def execute_script(self, script: str) -> None:
            self.last_script = script

        def get(self, url: str) -> None:
            self.visited.append(url)
            self.current_url = url

        def find_elements(self, _by: str, _value: str):
            return []

        def quit(self) -> None:
            self.closed = True

    webdriver_module.Chrome = Chrome

    class Options:
        def __init__(self) -> None:
            self.arguments: list[str] = []
            self.experimental_options: dict[str, object] = {}

        def add_argument(self, argument: str) -> None:
            self.arguments.append(argument)

        def add_experimental_option(self, key: str, value: object) -> None:
            self.experimental_options[key] = value

    webdriver_module.ChromeOptions = Options

    chrome_module = types.ModuleType("selenium.webdriver.chrome")
    chrome_options_module = types.ModuleType("selenium.webdriver.chrome.options")
    chrome_options_module.Options = Options
    chrome_module.options = chrome_options_module

    sys.modules["selenium.webdriver"] = webdriver_module
    sys.modules["selenium.webdriver.chrome"] = chrome_module
    sys.modules["selenium.webdriver.chrome.options"] = chrome_options_module

    # Common By and Keys
    by_module = types.ModuleType("selenium.webdriver.common.by")

    class By:
        CSS_SELECTOR = "css selector"
        TAG_NAME = "tag name"

    by_module.By = By

    keys_module = types.ModuleType("selenium.webdriver.common.keys")

    class Keys:
        RETURN = "\n"

    keys_module.Keys = Keys

    common_module = types.ModuleType("selenium.webdriver.common")
    common_module.by = by_module

    sys.modules["selenium.webdriver.common"] = common_module
    sys.modules["selenium.webdriver.common.by"] = by_module
    sys.modules["selenium.webdriver.common.keys"] = keys_module

    # Expected conditions & WebDriverWait
    expected_conditions_module = types.ModuleType(
        "selenium.webdriver.support.expected_conditions"
    )

    def presence_of_element_located(locator):
        def _predicate(driver):
            by, value = locator
            elements = driver.find_elements(by, value)
            return elements and elements[-1]

        return _predicate

    def element_to_be_clickable(locator):
        def _predicate(driver):
            by, value = locator
            elements = driver.find_elements(by, value)
            for element in elements:
                displayed = getattr(element, "is_displayed", lambda: True)()
                enabled = getattr(element, "is_enabled", lambda: True)()
                if displayed and enabled:
                    return element
            return False

        return _predicate

    expected_conditions_module.presence_of_element_located = presence_of_element_located
    expected_conditions_module.element_to_be_clickable = element_to_be_clickable

    ui_module = types.ModuleType("selenium.webdriver.support.ui")

    class WebDriverWait:
        def __init__(self, driver, timeout: int) -> None:
            self.driver = driver
            self.timeout = timeout

        def until(self, predicate):
            result = predicate(self.driver)
            if not result:
                raise TimeoutException("condition not met")
            return result

    ui_module.WebDriverWait = WebDriverWait

    support_module = types.ModuleType("selenium.webdriver.support")
    support_module.expected_conditions = expected_conditions_module
    support_module.ui = ui_module

    sys.modules["selenium.webdriver.support"] = support_module
    sys.modules["selenium.webdriver.support.expected_conditions"] = (
        expected_conditions_module
    )
    sys.modules["selenium.webdriver.support.ui"] = ui_module

    webdriver_module.support = support_module
    webdriver_module.chrome = chrome_module


for installer in (
    _install_loguru_stub,
    _install_rich_stub,
    _install_psutil_stub,
    _install_fastmcp_stub,
    _install_selenium_stub,
):
    installer()


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Provide a dedicated event loop for asyncio-based tests."""

    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture
def cli_runner() -> CliRunner:
    """Convenience Click runner used across CLI tests."""

    return CliRunner()


@pytest.fixture
def config_file_factory(tmp_path: Path) -> Callable[[dict], Path]:
    """Create temporary JSON configuration files on demand."""

    def _factory(data: dict) -> Path:
        path = tmp_path / "config.json"
        path.write_text(json.dumps(data))
        return path

    return _factory
