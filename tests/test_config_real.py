"""Compatibility tests exercising configuration flows expected by CI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from notebooklm_mcp.config import AuthConfig, ServerConfig, load_config
from notebooklm_mcp.exceptions import ConfigurationError


def test_load_config_from_file(tmp_path: Path) -> None:
    """Ensure `load_config` round-trips data written to disk."""

    config_path = tmp_path / "notebooklm.json"
    config_data = {
        "headless": True,
        "timeout": 45,
        "debug": True,
        "default_notebook_id": "abc-123",
        "auth": {
            "cookies_path": str(tmp_path / "cookies"),
            "profile_dir": str(tmp_path / "profile"),
            "use_persistent_session": False,
            "auto_login": False,
        },
    }
    config_path.write_text(json.dumps(config_data))

    loaded = load_config(str(config_path))

    assert loaded.headless is True
    assert loaded.timeout == 45
    assert loaded.debug is True
    assert loaded.default_notebook_id == "abc-123"
    assert loaded.auth.profile_dir.endswith("profile")
    assert loaded.auth.use_persistent_session is False


def test_load_config_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fallback to environment variables when files are missing."""

    env = {
        "NOTEBOOKLM_HEADLESS": "true",
        "NOTEBOOKLM_TIMEOUT": "90",
        "NOTEBOOKLM_DEBUG": "true",
        "NOTEBOOKLM_NOTEBOOK_ID": "env-notebook",
        "NOTEBOOKLM_PROFILE_DIR": "/tmp/profile",
        "NOTEBOOKLM_PERSISTENT_SESSION": "false",
    }

    with (
        patch("os.path.exists", return_value=False),
        patch.dict(os.environ, env, clear=True),
    ):
        loaded = load_config("/missing.json")

    assert loaded.headless is True
    assert loaded.timeout == 90
    assert loaded.debug is True
    assert loaded.default_notebook_id == "env-notebook"
    assert loaded.auth.profile_dir == "/tmp/profile"
    assert loaded.auth.use_persistent_session is False


def test_profile_setup_and_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Importing and exporting profiles should trigger the expected file operations."""

    source_profile = tmp_path / "import_me"
    target_profile = tmp_path / "profile"
    export_path = tmp_path / "export"
    (source_profile / "Default").mkdir(parents=True)

    copied: dict[str, tuple[Path, Path]] = {}

    def fake_copytree(src: Path, dest: Path) -> None:
        dest_path = Path(dest)
        dest_path.mkdir(parents=True, exist_ok=True)
        copied.setdefault("calls", []).append((Path(src), dest_path))

    def fake_rmtree(path: Path) -> None:
        copied.setdefault("removed", []).append(Path(path))

    cfg = ServerConfig(
        auth=AuthConfig(
            profile_dir=str(target_profile),
            import_profile_from=str(source_profile),
            export_profile_to=str(export_path),
        )
    )

    with (
        patch("shutil.copytree", side_effect=fake_copytree),
        patch("shutil.rmtree", side_effect=fake_rmtree),
    ):
        cfg.setup_profile()
        cfg.export_profile()

    # Import should copy from source and export should target the destination
    assert (source_profile, target_profile) in copied.get("calls", [])
    assert (target_profile, export_path) in copied.get("calls", [])


def test_validation_catches_invalid_paths(tmp_path: Path) -> None:
    """Validation should raise informative errors for impossible paths."""

    bad_profile = tmp_path / "missing" / "profile"
    cfg = ServerConfig(auth=AuthConfig(profile_dir=str(bad_profile)))
    with pytest.raises(ConfigurationError):
        cfg.validate()

    import_path = tmp_path / "no_profile"
    cfg = ServerConfig(
        auth=AuthConfig(
            profile_dir=str(tmp_path / "profiles"),
            import_profile_from=str(import_path),
        )
    )
    with pytest.raises(ConfigurationError):
        cfg.validate()
