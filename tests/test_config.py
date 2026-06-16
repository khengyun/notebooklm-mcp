import json

import pytest

from notebooklm_mcp.config import AuthConfig, ServerConfig, load_config
from notebooklm_mcp.exceptions import ConfigurationError


def test_server_config_round_trip(tmp_path):
    profile_dir = tmp_path / "profiles" / "primary"
    profile_dir.parent.mkdir()

    config = ServerConfig(
        headless=True,
        timeout=45,
        debug=True,
        default_notebook_id="abc",
        auth=AuthConfig(
            profile_dir=str(profile_dir),
            import_profile_from=None,
        ),
    )

    data = config.to_dict()
    restored = ServerConfig.from_dict(json.loads(json.dumps(data)))

    assert restored.headless is True
    assert restored.timeout == 45
    assert restored.debug is True
    assert restored.default_notebook_id == "abc"
    assert restored.auth.profile_dir == str(profile_dir)


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"timeout": 0}, "Timeout must be positive"),
        ({"timeout": -5}, "Timeout must be positive"),
    ],
)
def test_server_config_validate_errors(tmp_path, overrides, expected):
    base = {
        "auth": AuthConfig(profile_dir=str(tmp_path / "profiles" / "a")),
    }
    config = ServerConfig(**base, **overrides)

    with pytest.raises(ConfigurationError, match=expected):
        config.validate()


def test_server_config_validate_profile_checks(tmp_path):
    config = ServerConfig(
        auth=AuthConfig(profile_dir=str(tmp_path / "missing" / "profile"))
    )

    with pytest.raises(
        ConfigurationError, match="Profile directory parent does not exist"
    ):
        config.validate()

    target_dir = tmp_path / "profiles" / "target"
    target_dir.parent.mkdir()
    config = ServerConfig(
        auth=AuthConfig(
            profile_dir=str(target_dir),
            import_profile_from=str(tmp_path / "unknown"),
        )
    )

    with pytest.raises(ConfigurationError, match="Import profile path does not exist"):
        config.validate()


def test_from_dict_ignores_unknown_keys():
    """A config dict carrying removed/unknown keys (top-level and under
    ``auth``) must load cleanly and silently drop the unknown keys."""
    data = {
        "headless": True,
        "timeout": 45,
        "default_notebook_id": "abc",
        # Removed/legacy top-level keys that older config files may still carry.
        "engine": "patchright",
        "chrome_channel": "chrome",
        "chrome_binary": "/usr/bin/google-chrome",
        "stdio_mode": False,
        "auth": {
            "profile_dir": "/tmp/p",
            # Removed/legacy auth keys.
            "cookies_path": "cookies.json",
            "auto_login": True,
            "totally_unknown": 123,
        },
    }

    config = ServerConfig.from_dict(data)

    # Known keys applied.
    assert config.headless is True
    assert config.timeout == 45
    assert config.default_notebook_id == "abc"
    assert config.auth.profile_dir == "/tmp/p"
    # Unknown keys ignored (not attached as attributes).
    assert not hasattr(config, "engine")
    assert not hasattr(config, "chrome_channel")
    assert not hasattr(config, "stdio_mode")
    assert not hasattr(config.auth, "cookies_path")
    assert not hasattr(config.auth, "totally_unknown")


def test_from_dict_without_auth_key():
    """from_dict must work when the ``auth`` key is missing entirely."""
    config = ServerConfig.from_dict({"default_notebook_id": "x"})
    assert config.default_notebook_id == "x"
    assert isinstance(config.auth, AuthConfig)


def test_server_config_save_and_load(tmp_path):
    config = ServerConfig(default_notebook_id="abc")
    path = tmp_path / "config.json"

    config.save_to_file(str(path))
    loaded = ServerConfig.from_file(str(path))

    assert loaded.default_notebook_id == "abc"


def test_server_config_from_file_errors(tmp_path):
    """from_file surfaces a ConfigurationError for a missing file and for
    malformed JSON (both error branches in from_file)."""
    missing_path = tmp_path / "missing.json"
    with pytest.raises(ConfigurationError, match="Config file not found"):
        ServerConfig.from_file(str(missing_path))

    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not-json}")
    with pytest.raises(ConfigurationError, match="Invalid JSON"):
        ServerConfig.from_file(str(bad_path))


def test_save_to_file_creates_directories(tmp_path):
    """save_to_file must create missing parent directories before writing."""
    nested = tmp_path / "configs" / "server.json"
    config = ServerConfig(default_notebook_id="nested")

    config.save_to_file(str(nested))

    assert nested.exists()
    saved = json.loads(nested.read_text())
    assert saved["default_notebook_id"] == "nested"


def test_load_config_prefers_local_default_file(tmp_path, monkeypatch):
    """With no explicit path, load_config picks up ./config.json in the cwd."""
    monkeypatch.chdir(tmp_path)
    default_path = tmp_path / "config.json"
    default_path.write_text(json.dumps({"default_notebook_id": "local"}))

    config = load_config()

    assert config.default_notebook_id == "local"


def test_setup_profile_imports_existing_profile(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "profile"
    source.mkdir()
    (source / "prefs.txt").write_text("data")

    config = ServerConfig(
        auth=AuthConfig(
            profile_dir=str(dest),
            import_profile_from=str(source),
        )
    )

    config.setup_profile()
    assert dest.exists()
    assert (dest / "prefs.txt").read_text() == "data"


def test_setup_profile_creates_new_directory_when_no_import(tmp_path):
    """Without import_profile_from, setup_profile must create the profile dir
    (covers the create-new-directory branch, config.py 170-172)."""
    profile_dir = tmp_path / "fresh" / "profile"
    config = ServerConfig(
        auth=AuthConfig(profile_dir=str(profile_dir), import_profile_from=None)
    )

    assert not profile_dir.exists()
    config.setup_profile()
    assert profile_dir.is_dir()

    # Idempotent: a second call with an existing dir must not raise and must
    # leave the directory intact.
    config.setup_profile()
    assert profile_dir.is_dir()


def test_setup_profile_import_replaces_existing_destination(tmp_path):
    """When the destination already exists, import must wipe it first and copy
    the source over it (covers the rmtree-on-import branch, config.py 164)."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "new.txt").write_text("new")

    dest = tmp_path / "dest"
    dest.mkdir()
    # Stale file that must NOT survive the re-import.
    (dest / "stale.txt").write_text("stale")

    config = ServerConfig(
        auth=AuthConfig(profile_dir=str(dest), import_profile_from=str(source))
    )
    config.setup_profile()

    assert (dest / "new.txt").read_text() == "new"
    assert not (dest / "stale.txt").exists()


def test_setup_profile_blank_import_path_treated_as_none(tmp_path):
    """A whitespace-only import path must be ignored (not treated as a real
    path), so setup_profile falls through to the create-directory branch."""
    profile_dir = tmp_path / "blank" / "profile"
    config = ServerConfig(
        auth=AuthConfig(profile_dir=str(profile_dir), import_profile_from="   ")
    )

    config.setup_profile()
    assert profile_dir.is_dir()


def test_storage_state_path_defaults_to_none():
    """``auth.storage_state_path`` defaults to None (no session configured)."""
    config = ServerConfig()
    assert config.auth.storage_state_path is None


def test_storage_state_round_trip(tmp_path):
    """``auth.storage_state_path`` must survive a full
    to_dict -> from_dict -> save_to_file -> from_file round trip."""
    profile_dir = tmp_path / "profiles" / "p"
    profile_dir.parent.mkdir()

    config = ServerConfig(
        auth=AuthConfig(
            profile_dir=str(profile_dir),
            storage_state_path="/tmp/state/storage_state.json",
        ),
    )

    # to_dict surfaces the field.
    data = config.to_dict()
    assert data["auth"]["storage_state_path"] == "/tmp/state/storage_state.json"

    # from_dict restores it (through a JSON round trip to catch serialization
    # surprises).
    restored = ServerConfig.from_dict(json.loads(json.dumps(data)))
    assert restored.auth.storage_state_path == "/tmp/state/storage_state.json"

    # And it survives a file save/load round trip.
    path = tmp_path / "cfg.json"
    config.save_to_file(str(path))
    from_file = ServerConfig.from_file(str(path))
    assert from_file.auth.storage_state_path == "/tmp/state/storage_state.json"


def test_storage_state_round_trips_default_none(tmp_path):
    """The default storage_state_path=None also round-trips (so a default config
    written to disk loads back identically)."""
    config = ServerConfig(default_notebook_id="abc")
    path = tmp_path / "default_cfg.json"
    config.save_to_file(str(path))

    from_file = ServerConfig.from_file(str(path))
    assert from_file.auth.storage_state_path is None


def test_load_config_prefers_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"default_notebook_id": "file-id"}))

    monkeypatch.chdir(tmp_path)
    config = load_config(str(path))

    assert config.default_notebook_id == "file-id"


def test_load_config_falls_back_to_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NOTEBOOKLM_HEADLESS", "true")
    monkeypatch.setenv("NOTEBOOKLM_TIMEOUT", "42")
    monkeypatch.setenv("NOTEBOOKLM_DEBUG", "true")
    monkeypatch.setenv("NOTEBOOKLM_NOTEBOOK_ID", "env-id")
    monkeypatch.setenv("NOTEBOOKLM_PROFILE_DIR", str(tmp_path / "profiles"))

    config = load_config()

    assert config.headless is True
    assert config.timeout == 42
    assert config.default_notebook_id == "env-id"
    assert config.auth.profile_dir == str(tmp_path / "profiles")
