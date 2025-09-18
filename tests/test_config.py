from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from notebooklm_mcp.config import AuthConfig, ServerConfig, load_config
from notebooklm_mcp.exceptions import ConfigurationError


def test_server_config_defaults() -> None:
    config = ServerConfig()

    assert config.headless is False
    assert config.timeout == 60
    assert config.debug is False
    assert config.default_notebook_id is None
    assert isinstance(config.auth, AuthConfig)


def test_server_config_to_and_from_dict(tmp_path: Path) -> None:
    config = ServerConfig(
        headless=True,
        timeout=45,
        debug=True,
        default_notebook_id="abc",
        streaming_timeout=20,
        response_stability_checks=4,
    )

    data = config.to_dict()
    restored = ServerConfig.from_dict(data)

    assert restored.headless is True
    assert restored.timeout == 45
    assert restored.debug is True
    assert restored.default_notebook_id == "abc"
    assert restored.streaming_timeout == 20
    assert restored.response_stability_checks == 4

    file_path = tmp_path / "config.json"
    config.save_to_file(str(file_path))
    loaded = ServerConfig.from_file(str(file_path))
    loaded_dict = loaded.to_dict()
    for key, value in data.items():
        if key == "auth":
            for auth_key, auth_value in value.items():
                assert loaded_dict[key][auth_key] == auth_value
        else:
            assert loaded_dict[key] == value


def test_server_config_validation_checks(tmp_path: Path) -> None:
    config = ServerConfig(timeout=-1)
    with pytest.raises(ConfigurationError):
        config.validate()

    config = ServerConfig(streaming_timeout=0)
    with pytest.raises(ConfigurationError):
        config.validate()

    config = ServerConfig(response_stability_checks=0)
    with pytest.raises(ConfigurationError):
        config.validate()

    config = ServerConfig(retry_attempts=-1)
    with pytest.raises(ConfigurationError):
        config.validate()

    # Profile directory parent must exist
    config = ServerConfig(
        auth=AuthConfig(profile_dir=str(tmp_path / "missing" / "profile"))
    )
    with pytest.raises(ConfigurationError):
        config.validate()

    # Import profile path must exist when provided
    existing_parent = tmp_path / "profiles"
    existing_parent.mkdir()
    config = ServerConfig(
        auth=AuthConfig(
            profile_dir=str(existing_parent / "profile"),
            import_profile_from=str(tmp_path / "nope"),
        )
    )
    with pytest.raises(ConfigurationError):
        config.validate()


def test_setup_profile_creates_and_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "chrome_profile"

    # Branch where directory is created
    cfg = ServerConfig(auth=AuthConfig(profile_dir=str(target)))
    cfg.setup_profile()
    assert target.exists()

    # Branch importing an existing profile
    src = tmp_path / "source_profile"
    (src / "Default").mkdir(parents=True)

    copied = {}

    def fake_copytree(src_path: Path, dest_path: Path) -> None:
        copied["args"] = (Path(src_path), Path(dest_path))

    monkeypatch.setenv("PYTHONPATH", os.environ.get("PYTHONPATH", ""))
    with (
        patch("shutil.copytree", side_effect=fake_copytree),
        patch("shutil.rmtree", MagicMock()),
    ):
        cfg = ServerConfig(
            auth=AuthConfig(
                profile_dir=str(target),
                import_profile_from=str(src),
            )
        )
        cfg.setup_profile()

    assert copied["args"] == (src, target)


def test_export_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "profile"
    dest = tmp_path / "exported"
    (source / "Default").mkdir(parents=True)

    called = {}

    def fake_copytree(src_path: Path, dest_path: Path) -> None:
        called["paths"] = (Path(src_path), Path(dest_path))

    with (
        patch("shutil.copytree", side_effect=fake_copytree),
        patch("shutil.rmtree", MagicMock()),
    ):
        cfg = ServerConfig(
            auth=AuthConfig(profile_dir=str(source), export_profile_to=str(dest))
        )
        cfg.export_profile()

    assert called["paths"] == (source, dest)

    cfg = ServerConfig(
        auth=AuthConfig(
            profile_dir=str(tmp_path / "missing"), export_profile_to=str(dest)
        )
    )
    with pytest.raises(ConfigurationError):
        cfg.export_profile()


def test_load_config_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = tmp_path / "explicit.json"
    explicit.write_text(json.dumps({"headless": True}))

    default = tmp_path / "config.json"
    default.write_text(json.dumps({"headless": False}))

    with patch("os.path.exists", side_effect=lambda p: Path(p).exists()):
        cfg = load_config(str(explicit))
        assert cfg.headless is True

        cfg = load_config(str(default))
        assert cfg.headless is False

    # When files do not exist fall back to environment
    with patch("os.path.exists", return_value=False):
        with patch("notebooklm_mcp.config.ServerConfig.from_env") as mock_from_env:
            mock_from_env.return_value = ServerConfig(debug=True)
            cfg = load_config("/missing.json")
            assert cfg.debug is True
            mock_from_env.assert_called_once()


def test_server_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "NOTEBOOKLM_HEADLESS": "true",
        "NOTEBOOKLM_TIMEOUT": "90",
        "NOTEBOOKLM_DEBUG": "true",
        "NOTEBOOKLM_NOTEBOOK_ID": "env-id",
        "NOTEBOOKLM_COOKIES_PATH": "/tmp/cookies",
        "NOTEBOOKLM_PROFILE_DIR": "/tmp/profile",
        "NOTEBOOKLM_PERSISTENT_SESSION": "false",
    }

    with patch.dict(os.environ, env, clear=True):
        cfg = ServerConfig.from_env()

    assert cfg.headless is True
    assert cfg.timeout == 90
    assert cfg.debug is True
    assert cfg.default_notebook_id == "env-id"
    assert cfg.auth.cookies_path == "/tmp/cookies"
    assert cfg.auth.profile_dir == "/tmp/profile"
    assert cfg.auth.use_persistent_session is False
