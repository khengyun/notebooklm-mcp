"""
Test configuration and fixtures
"""

import pytest
import os
import asyncio
from pathlib import Path


def pytest_configure(config):
    """Configure pytest with custom markers"""
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
            "auto_login": True
        }
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