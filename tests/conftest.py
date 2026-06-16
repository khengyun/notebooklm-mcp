"""
Test configuration and fixtures
"""

import asyncio
import os

# Disable napari plugins to avoid conflicts
import sys

import patchright.async_api as pw
import pytest

from notebooklm_mcp.client import NotebookLMClient
from notebooklm_mcp.config import ServerConfig

if "napari" in sys.modules:
    del sys.modules["napari"]

# Real Playwright error classes used by the faithful fakes so the production
# ``except PlaywrightError/PlaywrightTimeoutError`` branches catch them.
# (TimeoutError subclasses Error, mirroring patchright.)
PWError = pw.Error
PWTimeoutError = pw.TimeoutError


# --------------------------------------------------------------------------- #
# Faithful async fakes for the Patchright (async Playwright) client.
#
# The real client talks to ``page`` / ``context`` / ``locator`` objects whose
# methods are all coroutines. These doubles model enough of the *real*
# Playwright async API that the production helpers in ``client.py``
# (``_find_first``, ``_read_latest_response``, ``_is_thinking``,
# ``_wait_until_idle``) execute their actual DOM-walking logic against them --
# no browser, no network, no sleeping.
#
# Fidelity rules that matter for the helpers under test:
#
# * ``page.locator(sel)`` returns DIFFERENT results per selector string. Each
#   selector maps to a list of "element" specs; the returned ``FakeLocator``
#   is scoped to *that* selector's element list. This lets the real selector
#   fallback loops actually discriminate between selectors.
# * ``locator.count()`` is the number of elements matched by the selector.
# * ``locator.nth(i)`` indexes into that element list (like Playwright). An
#   out-of-range index yields a locator whose ``inner_text``/``is_visible``
#   raise a real Playwright error -- mirroring "no node for given index".
# * ``locator.first`` is ``nth(0)``.
# * ``locator.wait_for(state="visible", timeout=...)`` raises the real
#   ``patchright.async_api.TimeoutError`` when no matched element is visible
#   (i.e. the selector has no visible node within the timeout).
# * ``locator.is_visible()`` reflects the matched element's visibility (False
#   when the selector matched nothing, like Playwright).
#
# Element specs may carry *sequences* for ``text``/``visible`` so a value can
# advance on each poll (used to model a streaming response that changes then
# stabilizes, and a thinking indicator that flips visible -> hidden).
# --------------------------------------------------------------------------- #


def _advance(value, index):
    """Resolve a possibly-sequenced spec value for poll number ``index``.

    A plain scalar is returned as-is. A list/tuple is treated as a per-poll
    timeline whose last entry sticks once exhausted (so a response "stabilizes"
    instead of falling off the end).
    """
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        return value[min(index, len(value) - 1)]
    return value


class FakeElement:
    """One DOM node matched by a selector.

    ``text`` and ``visible`` may each be a scalar or a per-poll timeline list.
    A shared ``counter`` (a one-element list) is incremented by the owning page
    on every ``page.locator()`` call so that ``text``/``visible`` timelines
    advance together across the whole page, modelling sequential polls.
    """

    def __init__(self, *, text="", visible=False, raise_on=None, counter=None):
        self._text = text
        self._visible = visible
        self._raise_on = raise_on or {}
        self._counter = counter if counter is not None else [0]

    def _poll(self):
        return self._counter[0]

    def _maybe_raise(self, name):
        if name in self._raise_on:
            raise self._raise_on[name]

    @property
    def text(self):
        return _advance(self._text, self._poll())

    @property
    def visible(self):
        return bool(_advance(self._visible, self._poll()))

    def raises(self, name):
        return name in self._raise_on


class FakeLocator:
    """Stand-in for a Playwright ``Locator`` scoped to one selector match set.

    * ``elements`` is the ordered list of :class:`FakeElement` the selector
      matched (empty list => selector matched nothing).
    * Records ordered method calls in ``self.calls`` so tests can assert the
      ``click -> fill -> press`` sequence used by ``send_message``.
    * ``count()`` returns ``len(elements)``.
    * ``nth(i)`` returns a locator scoped to that single element; out-of-range
      yields a locator that raises a real Playwright error on read, like the
      engine's "given index is out of range" failure.
    * ``first`` is ``nth(0)``.
    * ``wait_for(state="visible")`` raises the real ``TimeoutError`` when no
      element in this set is visible.

    The legacy keyword form (``text=``, ``visible=``, ``count=``, ``raise_on=``)
    is still accepted for the ``send_message`` composer doubles and is mapped to
    a single synthetic element so existing assertion-style tests keep working.
    """

    def __init__(
        self,
        *,
        elements=None,
        index=None,
        text=None,
        visible=None,
        count=None,
        raise_on=None,
        _calls=None,
    ):
        if elements is None:
            # Legacy single-element form (composer / direct unit doubles).
            n = count if count is not None else 1
            counter = [0]
            elements = [
                FakeElement(
                    text=text or "",
                    visible=bool(visible),
                    raise_on=raise_on,
                    counter=counter,
                )
                for _ in range(max(n, 1))
            ]
            if count == 0:
                elements = []
        self._elements = list(elements)
        self._index = index
        # ``first`` / ``nth`` clones share their parent's ``calls`` list so the
        # full interaction (``locator -> .first -> wait_for -> click -> ...``)
        # is recorded on one object, mirroring how the client holds a single
        # ``Locator`` reference through the whole send sequence.
        self.calls = _calls if _calls is not None else []

    # -- helpers -------------------------------------------------------- #
    def _scoped_element(self):
        """The single element this (possibly ``nth``/``first``) locator points
        at, or ``None`` for an out-of-range / empty match.
        """
        idx = 0 if self._index is None else self._index
        if 0 <= idx < len(self._elements):
            return self._elements[idx]
        return None

    @property
    def first(self):
        return self.nth(0)

    def nth(self, index):
        return FakeLocator(elements=self._elements, index=index, _calls=self.calls)

    # -- async surface -------------------------------------------------- #
    async def count(self):
        return len(self._elements)

    async def wait_for(self, *, state="visible", timeout=None, **_kwargs):
        self.calls.append("wait_for")
        element = self._scoped_element()
        # A configured ``raise_on['wait_for']`` models a non-timeout engine
        # failure (e.g. execution context destroyed) -> a generic Playwright
        # ``Error`` rather than a ``TimeoutError``.
        if element is not None:
            element._maybe_raise("wait_for")
        # Mirror Playwright: succeed only if an element satisfies the state.
        if state == "visible":
            if element is not None and element.visible:
                return None
            raise PWTimeoutError(
                f"Timeout {timeout}ms exceeded waiting for visible element"
            )
        return None

    async def inner_text(self, **_kwargs):
        element = self._scoped_element()
        if element is None:
            raise PWError("Error: failed to find element matching given index")
        element._maybe_raise("inner_text")
        return element.text

    async def is_visible(self, **_kwargs):
        element = self._scoped_element()
        if element is None:
            return False
        element._maybe_raise("is_visible")
        return element.visible

    async def click(self, **_kwargs):
        self.calls.append("click")
        element = self._scoped_element()
        if element is not None:
            element._maybe_raise("click")

    async def fill(self, value, **_kwargs):
        self.calls.append(("fill", value))
        element = self._scoped_element()
        if element is not None:
            element._maybe_raise("fill")

    async def press(self, key, **_kwargs):
        self.calls.append(("press", key))
        element = self._scoped_element()
        if element is not None:
            element._maybe_raise("press")


class FakePage:
    """Stand-in for a Playwright ``Page``.

    ``locator(sel)`` returns a fresh :class:`FakeLocator` scoped to the element
    specs registered for that exact selector string (default: an empty match).
    Each call also advances a shared poll counter so sequenced
    ``text``/``visible`` timelines on the elements move forward across polls.

    ``goto`` updates ``self.url`` to ``goto_url`` (when set) or to the requested
    target, or raises ``goto_error`` when configured.
    """

    def __init__(
        self,
        *,
        url="https://notebooklm.google.com/notebook/abc",
        locators=None,
        selectors=None,
        goto_url=None,
        goto_error=None,
    ):
        self.url = url
        # ``locators``: selector -> pre-built FakeLocator (legacy/explicit).
        self._locators = locators or {}
        # ``selectors``: selector -> list of FakeElement (preferred faithful
        # form; lets one shared poll counter drive all elements together).
        self._poll_counter = [0]
        self._selectors = {}
        for sel, elements in (selectors or {}).items():
            built = []
            for el in elements:
                el._counter = self._poll_counter
                built.append(el)
            self._selectors[sel] = built
        self._goto_url = goto_url
        self._goto_error = goto_error
        self.goto_calls = []
        self.locator_calls = []
        self.default_timeout = None
        self.closed = False

    def set_default_timeout(self, timeout):
        self.default_timeout = timeout

    async def goto(self, url, **_kwargs):
        self.goto_calls.append(url)
        if self._goto_error is not None:
            raise self._goto_error
        self.url = self._goto_url if self._goto_url is not None else url
        return None

    def locator(self, selector):
        self.locator_calls.append(selector)
        # Advance the poll clock once per locator() call so timelines move.
        self._poll_counter[0] += 1
        if selector in self._locators:
            return self._locators[selector]
        if selector in self._selectors:
            return FakeLocator(elements=self._selectors[selector])
        return FakeLocator(elements=[])

    async def close(self):
        self.closed = True


class FakeContext:
    """Stand-in for a Playwright ``BrowserContext``."""

    def __init__(self, pages=None):
        self.pages = list(pages) if pages else []
        self.new_pages = []
        self.closed = False

    async def new_page(self):
        page = FakePage()
        self.new_pages.append(page)
        self.pages.append(page)
        return page

    async def close(self):
        self.closed = True


class FakePlaywright:
    """Stand-in for the object returned by ``async_playwright().start()``."""

    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True


def make_async_playwright(playwright):
    """Build a drop-in replacement for ``client.async_playwright``.

    ``async_playwright()`` returns an object whose ``.start()`` coroutine yields
    the Playwright instance, so the fake mirrors that two-step shape.
    """

    class _Factory:
        def start(self):  # returns the awaitable below
            return _AStart()

    class _AStart:
        def __await__(self):
            async def _coro():
                return playwright

            return _coro().__await__()

    return lambda: _Factory()


def pytest_configure(config):
    """Configure pytest with custom markers"""
    # Disable napari plugins
    config.option.plugins = [
        p
        for p in (config.option.plugins or [])
        if not any(napari in p for napari in ["napari", "npe2"])
    ]

    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "browser: Tests requiring browser")
    config.addinivalue_line("markers", "slow: Slow tests")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test location"""
    for item in items:
        # Add unit marker to all tests in test_*.py files
        if "test_" in item.nodeid and not any(
            marker in item.nodeid for marker in ["integration", "browser"]
        ):
            item.add_marker(pytest.mark.unit)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for session scope"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir(tmp_path):
    """Provide temporary directory for tests"""
    return tmp_path


@pytest.fixture
def client_factory():
    """Build a ``NotebookLMClient`` with an optional fake page injected.

    Usage::

        client = client_factory(page=FakePage(...), notebook_id="abc")

    When ``page`` is provided the client is treated as "browser started"; pass
    ``authenticated=True`` to also flip the auth flag for messaging tests.
    """

    def _make(page=None, notebook_id=None, authenticated=False, config=None):
        cfg = config or ServerConfig(default_notebook_id=notebook_id)
        client = NotebookLMClient(cfg)
        if notebook_id is not None:
            client.current_notebook_id = notebook_id
        if page is not None:
            client.page = page
        client._is_authenticated = authenticated
        return client

    return _make


@pytest.fixture
def test_config_data():
    """Provide test configuration data"""
    return {
        "headless": True,
        "timeout": 30,
        "debug": True,
        "default_notebook_id": "test-notebook-id",
        "base_url": "https://notebooklm.google.com",
        "streaming_timeout": 30,
        "response_stability_checks": 2,
        "retry_attempts": 2,
        "auth": {
            "profile_dir": "./test_chrome_profile",
            "use_persistent_session": True,
            "auto_login": True,
        },
    }


# Skip integration tests if no browser available
def pytest_runtest_setup(item):
    """Setup function to skip tests based on markers and environment"""

    # Skip browser tests if no display available
    if item.get_closest_marker("browser"):
        if not os.getenv("DISPLAY") and not os.getenv("GITHUB_ACTIONS"):
            pytest.skip("No display available for browser tests")

    # Skip integration tests if explicitly disabled
    if item.get_closest_marker("integration"):
        if os.getenv("SKIP_INTEGRATION_TESTS"):
            pytest.skip("Integration tests disabled")

    # Skip slow tests if running quick tests
    if item.get_closest_marker("slow"):
        if os.getenv("QUICK_TESTS"):
            pytest.skip("Slow tests disabled for quick run")
