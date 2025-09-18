from notebooklm_mcp.exceptions import (
    AuthenticationError,
    ChatError,
    ConfigurationError,
    NavigationError,
    NotebookLMError,
    StreamingError,
)


def test_exception_hierarchy() -> None:
    error = NotebookLMError("base")
    assert str(error) == "base"

    for exc_cls in (AuthenticationError, ChatError, NavigationError, StreamingError):
        derived = exc_cls("problem")
        assert isinstance(derived, NotebookLMError)
        assert "problem" in str(derived)


def test_configuration_error_is_distinct() -> None:
    err = ConfigurationError("config issue")
    assert isinstance(err, NotebookLMError)
    assert "config" in str(err)
