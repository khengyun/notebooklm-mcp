from notebooklm_mcp import exceptions


def test_exceptions_inherit_base():
    error = exceptions.AuthenticationError("auth")
    assert isinstance(error, exceptions.NotebookLMError)
    assert str(error) == "auth"

    for exc_cls in [
        exceptions.StreamingError,
        exceptions.NavigationError,
        exceptions.ChatError,
        exceptions.ConfigurationError,
    ]:
        exc = exc_cls("boom")
        assert isinstance(exc, exceptions.NotebookLMError)
        assert "boom" in str(exc)
