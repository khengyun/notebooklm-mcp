import json
from pathlib import Path

import pytest

from notebooklm_mcp.config import AuthConfig, ServerConfig, load_config
from notebooklm_mcp.exceptions import ConfigurationError


def _write_config(path: Path, **overrides) -> None:
    data = {
        "headless": False,
        "timeout": 60,
        "debug": False,
        "default_notebook_id": "abc123",
        "base_url": "https://notebooklm.google.com",
        "server_name": "notebooklm-mcp",
        "stdio_mode": True,
        "streaming_timeout": 45,
        "response_stability_checks": 2,
        "retry_attempts": 1,
        "auth": {
            "cookies_path": None,
            "profile_dir": "./chrome_profile_notebooklm",
            "use_persistent_session": True,
            "auto_login": True,
        },
    }
    data.update(overrides)
    path.write_text(json.dumps(data, indent=2))


def test_server_config_from_file_round_trip(tmp_path):
    config_path = tmp_path / "config.json"
    _write_config(config_path, default_notebook_id="file-value", timeout=90)

    config = ServerConfig.from_file(str(config_path))

    assert config.default_notebook_id == "file-value"
    assert config.timeout == 90
    assert config.auth.profile_dir == "./chrome_profile_notebooklm"


def test_server_config_from_file_errors(tmp_path):
    missing_path = tmp_path / "missing.json"
    with pytest.raises(ConfigurationError, match="Config file not found"):
        ServerConfig.from_file(str(missing_path))

    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not-json}")
    with pytest.raises(ConfigurationError, match="Invalid JSON"):
        ServerConfig.from_file(str(bad_path))


def test_save_to_file_creates_directories(tmp_path):
    nested = tmp_path / "configs" / "server.json"
    config = ServerConfig(default_notebook_id="nested")

    config.save_to_file(str(nested))

    assert nested.exists()
    saved = json.loads(nested.read_text())
    assert saved["default_notebook_id"] == "nested"


def test_setup_profile_import_and_export(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "prefs.txt").write_text("data")

    destination = tmp_path / "profiles" / "primary"
    export_target = tmp_path / "exported"

    config = ServerConfig(
        auth=AuthConfig(
            profile_dir=str(destination),
            import_profile_from=str(source),
            export_profile_to=str(export_target),
        )
    )

    config.setup_profile()
    assert (destination / "prefs.txt").read_text() == "data"

    (destination / "cache").write_text("cached")

    config.export_profile()
    assert (export_target / "prefs.txt").read_text() == "data"
    assert (export_target / "cache").read_text() == "cached"


def test_export_profile_requires_existing_source(tmp_path):
    config = ServerConfig(
        auth=AuthConfig(
            profile_dir=str(tmp_path / "profile"),
            export_profile_to=str(tmp_path / "exported"),
        )
    )

    with pytest.raises(ConfigurationError, match="Source profile does not exist"):
        config.export_profile()


def test_load_config_prefers_local_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    default_path = tmp_path / "config.json"
    _write_config(default_path, default_notebook_id="local")

    config = load_config()

    assert config.default_notebook_id == "local"


def test_load_config_falls_back_to_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NOTEBOOKLM_PROFILE_DIR", raising=False)
    monkeypatch.setenv("NOTEBOOKLM_HEADLESS", "true")
    monkeypatch.setenv("NOTEBOOKLM_TIMEOUT", "30")
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_ID", "env")

    config = load_config()

    assert config.headless is True
    assert config.timeout == 30
    assert config.default_notebook_id == "env"
    assert config.auth.profile_dir == "./chrome_profile_notebooklm"
