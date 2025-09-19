import asyncio
from pathlib import Path

from click.testing import CliRunner

from notebooklm_mcp import cli as cli_module
from notebooklm_mcp.config import ServerConfig


def make_config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.json"
    path.write_text("{}")
    return path


def setup_cli(monkeypatch, tmp_path):
    config = ServerConfig(default_notebook_id="abc")
    config.auth.profile_dir = str(tmp_path / "profile")
    monkeypatch.setattr(cli_module, "load_config", lambda path: config)
    monkeypatch.setattr(cli_module.console, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli_module, "setup_logging", lambda *args, **kwargs: None)
    return config


def run_asyncio(coro):
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


def test_cli_help(monkeypatch, tmp_path):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["--config", str(config_path), "--help"])

    assert result.exit_code == 0
    assert "NotebookLM MCP" in result.output


def test_server_command_invokes_start(monkeypatch, tmp_path):
    config = setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    calls = {}

    class DummyServer:
        def __init__(self, cfg):
            calls["config"] = cfg

        async def start(self, transport="stdio", host="127.0.0.1", port=8000):
            calls["params"] = (transport, host, port)

    monkeypatch.setattr(cli_module, "NotebookLMFastMCP", DummyServer)
    monkeypatch.setattr(cli_module.asyncio, "run", run_asyncio)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        [
            "--config",
            str(config_path),
            "server",
            "--root-dir",
            str(tmp_path),
            "--transport",
            "stdio",
        ],
    )

    assert result.exit_code == 0
    assert calls["config"] is config
    assert calls["params"] == ("stdio", "127.0.0.1", 8000)


def test_server_command_allow_remote(monkeypatch, tmp_path):
    config = setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    class DummyServer:
        def __init__(self, cfg):
            self.config = cfg

        async def start(self, transport="stdio", host="127.0.0.1", port=8000):
            return None

    monkeypatch.setattr(cli_module, "NotebookLMFastMCP", DummyServer)
    monkeypatch.setattr(cli_module.asyncio, "run", run_asyncio)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        [
            "--config",
            str(config_path),
            "server",
            "--root-dir",
            str(tmp_path),
            "--allow-remote",
        ],
    )

    assert result.exit_code == 0
    assert config.allow_remote_access is True


def test_server_command_security_flags(monkeypatch, tmp_path):
    config = setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    class DummyServer:
        def __init__(self, cfg):
            self.config = cfg

        async def start(self, transport="stdio", host="127.0.0.1", port=8000):
            return None

    monkeypatch.setattr(cli_module, "NotebookLMFastMCP", DummyServer)
    monkeypatch.setattr(cli_module.asyncio, "run", run_asyncio)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        [
            "--config",
            str(config_path),
            "server",
            "--root-dir",
            str(tmp_path),
            "--require-api-key",
            "--api-key",
            "secret",  # first key
            "--api-key",
            "second",  # second key
            "--api-key-header",
            "X-Test-Key",
            "--disable-bearer-tokens",
        ],
    )

    assert result.exit_code == 0
    assert config.require_api_key is True
    assert config.api_keys == ["secret", "second"]
    assert config.api_key_header == "X-Test-Key"
    assert config.allow_bearer_tokens is False


def test_server_command_requires_api_key_values(monkeypatch, tmp_path):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        [
            "--config",
            str(config_path),
            "server",
            "--root-dir",
            str(tmp_path),
            "--require-api-key",
        ],
    )

    assert result.exit_code != 0


def test_chat_command_sends_message(monkeypatch, tmp_path):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    created = {}

    class DummyClient:
        def __init__(self, cfg):
            self.config = cfg
            self.calls = []
            created["client"] = self

        async def start(self):
            self.calls.append("start")

        async def authenticate(self):
            self.calls.append("authenticate")
            return True

        async def send_message(self, message):
            self.calls.append(("send", message))

        async def get_response(self):
            self.calls.append("response")
            return "ok"

        async def close(self):
            self.calls.append("close")

    monkeypatch.setattr(cli_module, "NotebookLMClient", DummyClient)
    monkeypatch.setattr(cli_module.asyncio, "run", run_asyncio)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--config", str(config_path), "chat", "--message", "hello"],
    )

    assert result.exit_code == 0
    client = created["client"]
    assert ("send", "hello") in client.calls
    assert "close" in client.calls


def test_extract_notebook_id_parses_url():
    notebook_id = "123e4567-e89b-12d3-a456-426614174000"
    assert (
        cli_module.extract_notebook_id(
            f"https://notebooklm.google.com/notebook/{notebook_id}"
        )
        == notebook_id
    )


def test_extract_notebook_id_invalid():
    try:
        cli_module.extract_notebook_id("https://example.com")
    except ValueError as exc:
        assert "Invalid NotebookLM URL" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for invalid URL")
