from notebooklm_mcp import __all__


def test_package_exports() -> None:
    expected = {
        "NotebookLMFastMCP",
        "NotebookLMClient",
        "ServerConfig",
        "AuthConfig",
        "NotebookLMError",
        "AuthenticationError",
        "StreamingError",
    }

    assert expected.issubset(set(__all__))
