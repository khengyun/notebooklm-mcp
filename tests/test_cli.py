"""Tests for the CLI entry point (``notebooklm_mcp.cli``).

These tests drive the REAL Click command bodies, option parsing, config
loading, console output, and control flow. The only thing faked is the RPC
client (``NotebookLMRPCClient``) and the FastMCP server (``NotebookLMFastMCP``),
patched at the import boundary so no real session or network is touched. Pure
helpers (``extract_notebook_id``, ``create_default_config``,
``update_config_to_headless``) are exercised directly with real temp files.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from notebooklm_mcp import cli as cli_module
from notebooklm_mcp.config import ServerConfig

# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #


def make_config_file(tmp_path: Path) -> Path:
    """Create a real on-disk config file (the group's --config needs exists=True)."""
    path = tmp_path / "config.json"
    path.write_text("{}")
    return path


def setup_cli(monkeypatch, tmp_path, config=None):
    """Patch ``load_config`` so the group yields a controlled ServerConfig.

    Console output is left intact so we can assert on ``result.output``.
    """
    config = config or ServerConfig(default_notebook_id="abc")
    monkeypatch.setattr(cli_module, "load_config", lambda path: config)
    return config


class FakeClient:
    """Async-capable fake of ``NotebookLMRPCClient``.

    Records ordered calls so tests can assert the command actually invoked the
    boundary (e.g. ``send_message`` with the user's message). Behaviour is
    configurable per-instance via the class attrs set by the factory below.
    """

    instances = []

    auth_result = True
    start_error = None
    navigate_result = "https://notebooklm.google.com/notebook/abc"
    response_text = "a response"

    def __init__(self, config):
        self.config = config
        self.calls = []
        type(self).instances.append(self)

    async def start(self):
        self.calls.append("start")
        if type(self).start_error is not None:
            raise type(self).start_error

    async def authenticate(self):
        self.calls.append("authenticate")
        return type(self).auth_result

    async def send_message(self, message):
        self.calls.append(("send_message", message))

    async def get_response(self, *args, **kwargs):
        self.calls.append("get_response")
        return type(self).response_text

    async def navigate_to_notebook(self, notebook_id):
        self.calls.append(("navigate", notebook_id))
        return type(self).navigate_result

    async def close(self):
        self.calls.append("close")


@pytest.fixture
def fake_client(monkeypatch):
    """Patch the RPC client symbol the CLI uses (``chat`` and ``test``)."""
    FakeClient.instances = []
    FakeClient.auth_result = True
    FakeClient.start_error = None
    FakeClient.navigate_result = "https://notebooklm.google.com/notebook/abc"
    FakeClient.response_text = "a response"

    monkeypatch.setattr(cli_module, "NotebookLMRPCClient", FakeClient)
    return FakeClient


# --------------------------------------------------------------------------- #
# extract_notebook_id  (pure logic)
# --------------------------------------------------------------------------- #

VALID_UUID = "123e4567-e89b-12d3-a456-426614174000"


def test_extract_notebook_id_full_url():
    url = f"https://notebooklm.google.com/notebook/{VALID_UUID}"
    assert cli_module.extract_notebook_id(url) == VALID_UUID


def test_extract_notebook_id_no_scheme():
    url = f"notebooklm.google.com/notebook/{VALID_UUID}"
    assert cli_module.extract_notebook_id(url) == VALID_UUID


def test_extract_notebook_id_bare_uuid():
    assert cli_module.extract_notebook_id(VALID_UUID) == VALID_UUID


def test_extract_notebook_id_uppercase_uuid_accepted():
    upper = VALID_UUID.upper()
    assert cli_module.extract_notebook_id(upper) == upper


def test_extract_notebook_id_with_query_string():
    url = f"https://notebooklm.google.com/notebook/{VALID_UUID}?foo=bar&baz=1"
    assert cli_module.extract_notebook_id(url) == VALID_UUID


def test_extract_notebook_id_whitespace_trimmed():
    assert cli_module.extract_notebook_id(f"  {VALID_UUID}  ") == VALID_UUID


def test_extract_notebook_id_junk_rejected():
    with pytest.raises(ValueError, match="Invalid NotebookLM URL or ID"):
        cli_module.extract_notebook_id("https://example.com/not-a-notebook")


def test_extract_notebook_id_embedded_in_longer_string_rejected():
    # A bare UUID embedded in a longer hyphenated token must NOT yield a
    # truncated/garbage 36-char window — the bare form is anchored (^...$).
    embedded = f"prefix-{VALID_UUID}-suffix"
    with pytest.raises(ValueError):
        cli_module.extract_notebook_id(embedded)


def test_extract_notebook_id_too_short_rejected():
    with pytest.raises(ValueError):
        cli_module.extract_notebook_id("123e4567-e89b-12d3-a456")


# --------------------------------------------------------------------------- #
# create_default_config  (pure logic, real temp file)
# --------------------------------------------------------------------------- #


def test_create_default_config_writes_valid_json(tmp_path):
    path = tmp_path / "out.json"
    cli_module.create_default_config(VALID_UUID, str(path))

    assert path.exists()
    data = json.loads(path.read_text())
    # Spot-check the keys the rest of the system depends on.
    assert data["default_notebook_id"] == VALID_UUID
    assert data["headless"] is False
    assert data["auth"]["profile_dir"] == "./chrome_profile_notebooklm"
    # Must round-trip into a real ServerConfig.
    cfg = ServerConfig.from_dict(json.loads(path.read_text()))
    assert cfg.default_notebook_id == VALID_UUID
    assert cfg.auth.profile_dir == "./chrome_profile_notebooklm"


# --------------------------------------------------------------------------- #
# cli group wiring
# --------------------------------------------------------------------------- #


def test_cli_help(monkeypatch, tmp_path):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["--config", str(config_path), "--help"])

    assert result.exit_code == 0
    assert "NotebookLM MCP" in result.output


def test_cli_config_error_exits_1(monkeypatch, tmp_path):
    config_path = make_config_file(tmp_path)

    def boom(_path):
        raise RuntimeError("bad config")

    monkeypatch.setattr(cli_module, "load_config", boom)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli, ["--config", str(config_path), "config-show"]
    )
    assert result.exit_code == 1
    assert "Configuration error" in result.output


def test_cli_debug_flag_sets_debug(monkeypatch, tmp_path):
    config = ServerConfig(default_notebook_id="abc", debug=False)
    setup_cli(monkeypatch, tmp_path, config=config)
    config_path = make_config_file(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli, ["--config", str(config_path), "--debug", "config-show"]
    )
    assert result.exit_code == 0
    assert config.debug is True


# --------------------------------------------------------------------------- #
# init command
# --------------------------------------------------------------------------- #


def test_init_creates_config_and_profile_and_prints_login_steps(
    monkeypatch, fake_client
):
    setup_cli(monkeypatch, Path("."))

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli_module.cli, ["init", VALID_UUID])

        assert result.exit_code == 0, result.output
        # Config + profile dir created (no browser involved).
        assert Path("notebooklm-config.json").exists()
        assert Path("chrome_profile_notebooklm").is_dir()

        cfg = json.loads(Path("notebooklm-config.json").read_text())
        assert cfg["default_notebook_id"] == VALID_UUID

    # init no longer launches a client at all.
    assert fake_client.instances == []
    assert "Setup Complete!" in result.output
    # The user is directed to create a session with notebooklm login.
    assert "notebooklm login" in result.output


def test_init_invalid_url_exits_1(monkeypatch, fake_client):
    setup_cli(monkeypatch, Path("."))
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli_module.cli, ["init", "not-a-valid-id"])
    assert result.exit_code == 1
    assert "Error:" in result.output
    # No client was ever constructed for an invalid URL.
    assert fake_client.instances == []


# --------------------------------------------------------------------------- #
# server command
# --------------------------------------------------------------------------- #


def _patch_fake_server(monkeypatch, calls, start_error=None):
    class DummyServer:
        def __init__(self, cfg):
            calls["config"] = cfg

        async def start(self, transport="stdio", host="127.0.0.1", port=8000):
            calls["params"] = (transport, host, port)
            if start_error is not None:
                raise start_error

    monkeypatch.setattr(cli_module, "NotebookLMFastMCP", DummyServer)
    return DummyServer


def test_server_builds_fastmcp_and_honors_options(monkeypatch, tmp_path):
    config = setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    calls = {}
    _patch_fake_server(monkeypatch, calls)

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
            "http",
            "--notebook",
            "nb-123",
            "--headless",
            "--host",
            "0.0.0.0",
            "--port",
            "9001",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls["config"] is config
    # --notebook / --headless flowed into the config object.
    assert config.default_notebook_id == "nb-123"
    assert config.headless is True
    # --transport / --host / --port flowed into server.start.
    assert calls["params"] == ("http", "0.0.0.0", 9001)
    assert "FastMCP HTTP server will be available" in result.output


def test_server_changes_working_dir(monkeypatch, tmp_path):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)
    calls = {}
    _patch_fake_server(monkeypatch, calls)

    target = tmp_path / "workroot"
    target.mkdir()
    original = Path.cwd()

    runner = CliRunner()
    try:
        result = runner.invoke(
            cli_module.cli,
            ["--config", str(config_path), "server", "--root-dir", str(target)],
        )
        assert result.exit_code == 0, result.output
        # os.chdir actually ran against the resolved root.
        assert Path.cwd() == target.resolve()
    finally:
        import os

        os.chdir(original)


def test_server_missing_root_dir_exits_1(monkeypatch, tmp_path):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)
    calls = {}
    _patch_fake_server(monkeypatch, calls)

    missing = tmp_path / "nope"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--config", str(config_path), "server", "--root-dir", str(missing)],
    )
    assert result.exit_code == 1
    assert "Root directory does not exist" in result.output


def test_server_auth_error_shows_help_panel(monkeypatch, tmp_path):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)
    calls = {}
    _patch_fake_server(
        monkeypatch, calls, start_error=RuntimeError("Authentication required: login")
    )

    original = Path.cwd()
    runner = CliRunner()
    try:
        result = runner.invoke(
            cli_module.cli,
            ["--config", str(config_path), "server", "--root-dir", str(tmp_path)],
        )
    finally:
        import os

        os.chdir(original)

    assert result.exit_code == 1
    assert "Server error" in result.output
    assert "Authentication Required" in result.output


# --------------------------------------------------------------------------- #
# chat command
# --------------------------------------------------------------------------- #


def test_chat_single_message_path(monkeypatch, tmp_path, fake_client):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--config", str(config_path), "chat", "--message", "hello there"],
    )

    assert result.exit_code == 0, result.output
    client = fake_client.instances[0]
    assert ("send_message", "hello there") in client.calls
    assert "get_response" in client.calls
    assert "close" in client.calls
    assert "a response" in result.output


def test_chat_auth_failed_branch(monkeypatch, tmp_path, fake_client):
    # auth fails; the command prints a login hint and still sends the message.
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)
    fake_client.auth_result = False

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        [
            "--config",
            str(config_path),
            "chat",
            "--message",
            "hi",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Authentication failed" in result.output
    client = fake_client.instances[0]
    assert ("send_message", "hi") in client.calls


def test_chat_notebook_option_overrides_config(monkeypatch, tmp_path, fake_client):
    config = setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        [
            "--config",
            str(config_path),
            "chat",
            "--notebook",
            "nb-override",
            "--message",
            "x",
        ],
    )
    assert result.exit_code == 0, result.output
    assert config.default_notebook_id == "nb-override"


def test_chat_interactive_mode_loops_until_quit(monkeypatch, tmp_path, fake_client):
    # No --message -> interactive loop. We feed two lines then "quit".
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--config", str(config_path), "chat"],
        input="first question\nsecond question\nquit\n",
    )

    assert result.exit_code == 0, result.output
    client = fake_client.instances[0]
    sent = [c for c in client.calls if isinstance(c, tuple) and c[0] == "send_message"]
    assert ("send_message", "first question") in sent
    assert ("send_message", "second question") in sent
    # "quit" must NOT be sent as a message.
    assert ("send_message", "quit") not in sent
    assert "close" in client.calls


def test_chat_session_error_wrapper_exits_1(monkeypatch, tmp_path, fake_client):
    # client.close() raising inside run_chat's finally bubbles out of
    # asyncio.run -> caught by the outer wrapper -> exit 1.
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    class ExplodingClose(FakeClient):
        async def close(self):
            self.calls.append("close")
            raise RuntimeError("close boom")

    monkeypatch.setattr(cli_module, "NotebookLMRPCClient", ExplodingClose)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--config", str(config_path), "chat", "--message", "hi"],
    )
    assert result.exit_code == 1
    assert "Chat session error" in result.output


# --------------------------------------------------------------------------- #
# quick_setup command
# --------------------------------------------------------------------------- #


def test_quick_setup_creates_config_and_prints_login_steps(monkeypatch, fake_client):
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli_module.cli,
            [
                "quick-setup",
                "--config",
                "qs-config.json",
                "--notebook",
                "nb-qs",
            ],
        )
        assert result.exit_code == 0, result.output
        # Config written by the real ServerConfig.save_to_file.
        assert Path("qs-config.json").exists()
        data = json.loads(Path("qs-config.json").read_text())
        assert data["default_notebook_id"] == "nb-qs"

    # quick-setup must NOT touch any client.
    assert fake_client.instances == []
    assert "Config Ready" in result.output
    assert "notebooklm login" in result.output


def test_quick_setup_imports_profile(monkeypatch, fake_client, tmp_path):
    # A provided --profile is imported into the new profile dir via setup_profile.
    src = tmp_path / "src_profile"
    src.mkdir()
    (src / "marker.txt").write_text("x")

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli_module.cli,
            [
                "quick-setup",
                "--config",
                "qs.json",
                "--notebook",
                "nb-2",
                "--profile",
                str(src),
            ],
        )
        assert result.exit_code == 0, result.output
        assert Path("qs.json").exists()
        # The imported profile landed in the default profile dir.
        assert Path("chrome_profile_notebooklm/marker.txt").read_text() == "x"

    assert fake_client.instances == []
    assert "Imported" in result.output


def test_quick_setup_failure_exits_1(monkeypatch, fake_client):
    # Make ServerConfig.save_to_file blow up -> except -> exit 1.
    import notebooklm_mcp.cli as climod

    def boom(self, path):
        raise RuntimeError("disk full")

    monkeypatch.setattr(climod.ServerConfig, "save_to_file", boom)

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli_module.cli,
            [
                "quick-setup",
                "--config",
                "qs.json",
                "--notebook",
                "nb-4",
            ],
        )
    assert result.exit_code == 1
    assert "Setup failed" in result.output


# --------------------------------------------------------------------------- #
# import_profile / export_profile commands (real temp dirs, real copytree)
# --------------------------------------------------------------------------- #


def test_import_profile_copies_tree(monkeypatch, tmp_path):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    src = tmp_path / "src_profile"
    src.mkdir()
    (src / "marker.txt").write_text("hello")
    dest = tmp_path / "dest_profile"

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        [
            "--config",
            str(config_path),
            "import-profile",
            "--from-profile",
            str(src),
            "--to-profile",
            str(dest),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (dest / "marker.txt").read_text() == "hello"
    assert "Profile Import Complete" in result.output


def test_import_profile_overwrites_existing_dest(monkeypatch, tmp_path):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    src = tmp_path / "src_profile"
    src.mkdir()
    (src / "new.txt").write_text("new")
    dest = tmp_path / "dest_profile"
    dest.mkdir()
    (dest / "stale.txt").write_text("stale")

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        [
            "--config",
            str(config_path),
            "import-profile",
            "--from-profile",
            str(src),
            "--to-profile",
            str(dest),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (dest / "new.txt").exists()
    assert not (dest / "stale.txt").exists()  # old tree was removed first


def test_import_profile_missing_source_exits_1(monkeypatch, tmp_path):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        [
            "--config",
            str(config_path),
            "import-profile",
            "--from-profile",
            str(tmp_path / "missing"),
            "--to-profile",
            str(tmp_path / "dest"),
        ],
    )
    assert result.exit_code == 1
    assert "Import failed" in result.output


def test_export_profile_copies_tree(monkeypatch, tmp_path):
    src = tmp_path / "live_profile"
    src.mkdir()
    (src / "cookie.txt").write_text("yum")
    config = ServerConfig(default_notebook_id="abc")
    config.auth.profile_dir = str(src)
    setup_cli(monkeypatch, tmp_path, config=config)
    config_path = make_config_file(tmp_path)

    dest = tmp_path / "exported"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--config", str(config_path), "export-profile", "--to", str(dest)],
    )
    assert result.exit_code == 0, result.output
    assert (dest / "cookie.txt").read_text() == "yum"
    assert "Profile Export Complete" in result.output


def test_export_profile_missing_source_exits_1(monkeypatch, tmp_path):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        [
            "--config",
            str(config_path),
            "export-profile",
            "--profile",
            str(tmp_path / "missing_src"),
            "--to",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 1
    assert "Export failed" in result.output


# --------------------------------------------------------------------------- #
# config_show command
# --------------------------------------------------------------------------- #


def test_config_show_renders_table(monkeypatch, tmp_path):
    config = ServerConfig(default_notebook_id="shown-nb")
    setup_cli(monkeypatch, tmp_path, config=config)
    config_path = make_config_file(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli, ["--config", str(config_path), "config-show"]
    )

    assert result.exit_code == 0, result.output
    assert "Configuration" in result.output
    assert "shown-nb" in result.output
    # Nested auth keys rendered as "auth.<key>".
    assert "auth.profile_dir" in result.output


# --------------------------------------------------------------------------- #
# test command
# --------------------------------------------------------------------------- #


def test_test_command_happy_path(monkeypatch, tmp_path, fake_client):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--config", str(config_path), "test", "--notebook", "nb-test"],
    )
    assert result.exit_code == 0, result.output
    client = fake_client.instances[0]
    assert "start" in client.calls
    assert ("navigate", "nb-test") in client.calls
    assert "close" in client.calls
    assert "All tests passed" in result.output


def test_test_command_failure_exits_1(monkeypatch, tmp_path, fake_client):
    setup_cli(monkeypatch, tmp_path)
    config_path = make_config_file(tmp_path)
    fake_client.start_error = RuntimeError("startup boom")

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--config", str(config_path), "test", "--notebook", "nb-test"],
    )
    assert result.exit_code == 1
    assert "Test" in result.output and "boom" in result.output
    # close still called in the finally.
    client = fake_client.instances[0]
    assert "close" in client.calls
