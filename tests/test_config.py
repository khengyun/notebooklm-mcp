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
        max_concurrent_requests=4,
        enable_metrics=False,
        metrics_port=9200,
        enable_health_checks=False,
        health_check_interval=15,
        streaming_timeout=30,
        response_stability_checks=2,
        retry_attempts=1,
        allow_remote_access=True,
        require_api_key=True,
        api_keys=["token-1", "token-2"],
        api_key_header="X-Notebook-Key",
        allow_bearer_tokens=False,
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
    assert restored.max_concurrent_requests == 4
    assert restored.enable_metrics is False
    assert restored.metrics_port == 9200
    assert restored.enable_health_checks is False
    assert restored.health_check_interval == 15
    assert restored.allow_remote_access is True
    assert restored.require_api_key is True
    assert restored.api_keys == ["token-1", "token-2"]
    assert restored.api_key_header == "X-Notebook-Key"
    assert restored.allow_bearer_tokens is False


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
        (
            {"max_concurrent_requests": 0},
            "Max concurrent requests must be greater than zero",
        ),
        ({"metrics_port": 0}, "Metrics port must be positive"),
        (
            {"health_check_interval": 0},
            "Health check interval must be positive",
        ),
        (
            {"require_api_key": True},
            "API key authentication enabled but no API keys were provided",
        ),
    ],
)
def test_server_config_validate_errors(tmp_path, overrides, expected):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    base = {
        "auth": AuthConfig(profile_dir=str(profiles_dir / "a")),
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


def test_server_config_from_env_security(monkeypatch, tmp_path):
    profile_root = tmp_path / "profiles"
    profile_root.mkdir()
    monkeypatch.setenv("NOTEBOOKLM_PROFILE_DIR", str(profile_root))
    monkeypatch.setenv("NOTEBOOKLM_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "one,two, ,three")
    monkeypatch.setenv("NOTEBOOKLM_API_KEY_HEADER", "X-Test-Key")
    monkeypatch.setenv("NOTEBOOKLM_ALLOW_BEARER_TOKENS", "false")

    config = ServerConfig.from_env()

    assert config.require_api_key is True
    assert config.api_keys == ["one", "two", "three"]
    assert config.api_key_header == "X-Test-Key"
    assert config.allow_bearer_tokens is False
