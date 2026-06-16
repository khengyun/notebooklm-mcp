"""Bridge the browser login session into a Playwright ``storage_state`` JSON.

The RPC engine (notebooklm-py) authenticates from a ``storage_state`` file.
The user logs in once with the persistent Chrome profile (via Patchright);
this module exports that profile's cookies into a ``storage_state.json`` the
RPC backend can consume. Pattern: *browser bootstraps the session, RPC drives
the actions.*
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from .config import ServerConfig

APP_URL = "https://notebooklm.google.com/"


def default_storage_state_path(config: ServerConfig) -> Path:
    """Where the bootstrapped storage_state lives when not set explicitly."""
    if config.auth.storage_state_path:
        return Path(config.auth.storage_state_path).expanduser()
    return Path(config.auth.profile_dir).expanduser() / "storage_state.json"


async def export_storage_state(config: ServerConfig, out_path: Path) -> Path:
    """Launch the persistent Chrome profile and dump its ``storage_state``.

    Returns the path written. Raises if the browser cannot start.
    """
    # Imported lazily so the RPC engine has no hard import-time dependency on
    # Patchright when a storage_state already exists.
    from patchright.async_api import async_playwright

    profile_path = Path(config.auth.profile_dir).expanduser().absolute()
    profile_path.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    launch_kwargs: dict = {
        "user_data_dir": str(profile_path),
        "headless": config.headless,
        "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        "no_viewport": True,
    }
    if config.auth.chrome_channel:
        launch_kwargs["channel"] = config.auth.chrome_channel
    if config.chrome_binary:
        launch_kwargs["executable_path"] = config.chrome_binary

    logger.info("Bootstrapping storage_state from Chrome profile...")
    pw = await async_playwright().start()
    try:
        context = await pw.chromium.launch_persistent_context(**launch_kwargs)
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(APP_URL, wait_until="domcontentloaded")
            await context.storage_state(path=str(out_path))
        finally:
            await context.close()
    finally:
        await pw.stop()

    logger.info(f"storage_state written to {out_path}")
    return out_path
