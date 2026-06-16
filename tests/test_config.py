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
        server_name="custom",
        stdio_mode=False,
        streaming_timeout=30,
        response_stability_checks=2,
        retry_attempts=1,
        auth=AuthConfig(
            cookies_path="cookies.json",
            profile_dir=str(profile_dir),
            use_persistent_session=False,
            auto_login=False,
            import_profile_from=None,
            export_profile_to=None,
        ),
    )

    data = config.to_dict()
    restored = ServerConfig.from_dict(json.loads(json.dumps(data)))

    assert restored.headless is True
    assert restored.timeout == 45
    assert restored.default_notebook_id == "abc"
    assert restored.server_name == "custom"
    assert restored.auth.profile_dir == str(profile_dir)
    assert restored.auth.use_persistent_session is False


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"timeout": 0}, "Timeout must be positive"),
        ({"streaming_timeout": 0}, "Streaming timeout must be positive"),
        (
            {"response_stability_checks": 0},
            "Response stability checks must be positive",
        ),
        ({"retry_attempts": -1}, "Retry attempts cannot be negative"),
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


def test_server_config_save_and_load(tmp_path):
    config = ServerConfig(default_notebook_id="abc")
    path = tmp_path / "config.json"

    config.save_to_file(str(path))
    loaded = ServerConfig.from_file(str(path))

    assert loaded.default_notebook_id == "abc"


def test_setup_and_export_profile(tmp_path, monkeypatch):
    source = tmp_path / "source"
    dest = tmp_path / "profile"
    exported = tmp_path / "exported"
    source.mkdir()
    (source / "prefs.txt").write_text("data")

    config = ServerConfig(
        auth=AuthConfig(
            profile_dir=str(dest),
            import_profile_from=str(source),
            export_profile_to=str(exported),
        )
    )

    config.setup_profile()
    assert dest.exists()
    assert (dest / "prefs.txt").read_text() == "data"

    dest_file = dest / "cache"
    dest_file.write_text("cache-data")

    config.export_profile()
    assert exported.exists()
    assert (exported / "prefs.txt").read_text() == "data"
    assert (exported / "cache").read_text() == "cache-data"


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


def test_export_profile_no_target_is_noop(tmp_path):
    """With export_profile_to unset, export_profile must return without doing
    anything (covers the early-return branch, config.py 177)."""
    source = tmp_path / "profile"
    source.mkdir()
    (source / "data.txt").write_text("x")

    config = ServerConfig(
        auth=AuthConfig(profile_dir=str(source), export_profile_to=None)
    )

    # Must not raise and must not create anything.
    config.export_profile()
    assert list(tmp_path.iterdir()) == [source]


def test_export_profile_overwrites_existing_target(tmp_path):
    """When the export target already exists it must be wiped and replaced
    (covers the rmtree-on-export branch, config.py 188)."""
    source = tmp_path / "profile"
    source.mkdir()
    (source / "current.txt").write_text("current")

    export_target = tmp_path / "exported"
    export_target.mkdir()
    (export_target / "old.txt").write_text("old")

    config = ServerConfig(
        auth=AuthConfig(profile_dir=str(source), export_profile_to=str(export_target))
    )
    config.export_profile()

    assert (export_target / "current.txt").read_text() == "current"
    # The pre-existing content was removed before the copy.
    assert not (export_target / "old.txt").exists()


def test_chrome_channel_and_binary_round_trip(tmp_path):
    """The chrome_channel / chrome_binary fields must survive a full
    to_dict -> from_dict -> save_to_file -> from_file round trip."""
    profile_dir = tmp_path / "profiles" / "p"
    profile_dir.parent.mkdir()

    config = ServerConfig(
        chrome_binary="/opt/google/chrome/chrome",
        auth=AuthConfig(
            profile_dir=str(profile_dir),
            chrome_channel="chromium",
        ),
    )

    # to_dict surfaces both fields.
    data = config.to_dict()
    assert data["chrome_binary"] == "/opt/google/chrome/chrome"
    assert data["auth"]["chrome_channel"] == "chromium"

    # from_dict restores them.
    restored = ServerConfig.from_dict(json.loads(json.dumps(data)))
    assert restored.chrome_binary == "/opt/google/chrome/chrome"
    assert restored.auth.chrome_channel == "chromium"

    # And they survive a file save/load round trip.
    path = tmp_path / "cfg.json"
    config.save_to_file(str(path))
    from_file = ServerConfig.from_file(str(path))
    assert from_file.chrome_binary == "/opt/google/chrome/chrome"
    assert from_file.auth.chrome_channel == "chromium"


def test_chrome_channel_defaults_to_chrome():
    """The default channel is 'chrome' and chrome_binary defaults to None."""
    config = ServerConfig()
    assert config.auth.chrome_channel == "chrome"
    assert config.chrome_binary is None


def test_engine_defaults_to_rpc():
    """The RPC engine is the new default and storage_state_path defaults None."""
    config = ServerConfig()
    assert config.engine == "rpc"
    assert config.auth.storage_state_path is None


def test_engine_and_storage_state_round_trip(tmp_path):
    """``engine`` and ``auth.storage_state_path`` must survive a full
    to_dict -> from_dict -> save_to_file -> from_file round trip."""
    profile_dir = tmp_path / "profiles" / "p"
    profile_dir.parent.mkdir()

    config = ServerConfig(
        engine="patchright",
        auth=AuthConfig(
            profile_dir=str(profile_dir),
            storage_state_path="/tmp/state/storage_state.json",
        ),
    )

    # to_dict surfaces both new fields.
    data = config.to_dict()
    assert data["engine"] == "patchright"
    assert data["auth"]["storage_state_path"] == "/tmp/state/storage_state.json"

    # from_dict restores them (through a JSON round trip to catch serialization
    # surprises).
    restored = ServerConfig.from_dict(json.loads(json.dumps(data)))
    assert restored.engine == "patchright"
    assert restored.auth.storage_state_path == "/tmp/state/storage_state.json"

    # And they survive a file save/load round trip.
    path = tmp_path / "cfg.json"
    config.save_to_file(str(path))
    from_file = ServerConfig.from_file(str(path))
    assert from_file.engine == "patchright"
    assert from_file.auth.storage_state_path == "/tmp/state/storage_state.json"


def test_engine_round_trips_default_rpc(tmp_path):
    """The default engine='rpc' / storage_state_path=None also round-trips
    (so a default config written to disk loads back identically)."""
    config = ServerConfig(default_notebook_id="abc")
    path = tmp_path / "default_cfg.json"
    config.save_to_file(str(path))

    from_file = ServerConfig.from_file(str(path))
    assert from_file.engine == "rpc"
    assert from_file.auth.storage_state_path is None


def test_export_profile_missing_source(tmp_path):
    config = ServerConfig(
        auth=AuthConfig(
            profile_dir=str(tmp_path / "profile"),
            export_profile_to=str(tmp_path / "exported"),
        )
    )

    with pytest.raises(ConfigurationError, match="Source profile does not exist"):
        config.export_profile()


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
