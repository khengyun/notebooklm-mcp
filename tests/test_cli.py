from __future__ import annotations

import json
from pathlib import Path

import pytest

from notebooklm_mcp.cli import create_default_config, extract_notebook_id, update_config_to_headless


def test_extract_notebook_id_from_full_url() -> None:
    url = "https://notebooklm.google.com/notebook/123e4567-e89b-12d3-a456-426614174000"
    assert extract_notebook_id(url) == "123e4567-e89b-12d3-a456-426614174000"


@pytest.mark.parametrize(
    "value",
    [
        "notebooklm.google.com/notebook/123e4567-e89b-12d3-a456-426614174000",
        "123e4567-e89b-12d3-a456-426614174000",
    ],
)
def test_extract_notebook_id_variants(value: str) -> None:
    assert extract_notebook_id(value) == "123e4567-e89b-12d3-a456-426614174000"


@pytest.mark.parametrize("bad_value", ["", "https://example.com", "invalid-id"])
def test_extract_notebook_id_invalid(bad_value: str) -> None:
    with pytest.raises(ValueError):
        extract_notebook_id(bad_value)


def test_create_and_update_config(tmp_path: Path) -> None:
    config_path = tmp_path / "cfg.json"
    notebook_id = "123e4567-e89b-12d3-a456-426614174000"

    create_default_config(notebook_id, str(config_path))
    data = json.loads(config_path.read_text())
    assert data["default_notebook_id"] == notebook_id
    assert data["headless"] is False

    update_config_to_headless(str(config_path))
    data = json.loads(config_path.read_text())
    assert data["headless"] is True
