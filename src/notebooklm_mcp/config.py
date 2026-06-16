"""
Configuration management for NotebookLM MCP Server
"""

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from shutil import copytree, rmtree
from typing import Any, Dict, Optional

from .exceptions import ConfigurationError


def _copy_tree(src: Path, dest: Path) -> None:
    """Copy ``src`` onto ``dest``, replacing ``dest`` if it already exists.

    Shared by the profile import/export paths (CLI commands and
    :meth:`ServerConfig.setup_profile`) so the wipe-then-copy logic lives in
    one place. Callers are responsible for validating that ``src`` exists.
    """
    if dest.exists():
        rmtree(dest)
    copytree(src, dest)


@dataclass
class AuthConfig:
    """Authentication configuration"""

    profile_dir: str = "./chrome_profile_notebooklm"

    # storage_state JSON used by the RPC engine (notebooklm-py). Created with
    # ``notebooklm login``. When unset, the RPC engine looks for a
    # ``storage_state.json`` in ``profile_dir`` and then defers to
    # notebooklm-py's own discovery (NOTEBOOKLM_AUTH_JSON / ~/.notebooklm).
    storage_state_path: Optional[str] = None

    # Quick setup options
    import_profile_from: Optional[str] = None  # Path to existing Chrome profile
    skip_manual_login: bool = False  # Skip manual login if profile exists


@dataclass
class ServerConfig:
    """Server configuration"""

    # General settings
    headless: bool = False
    timeout: int = 60
    debug: bool = False

    # NotebookLM settings
    default_notebook_id: Optional[str] = None

    # Authentication
    auth: AuthConfig = field(default_factory=AuthConfig)

    @classmethod
    def from_file(cls, config_path: str) -> "ServerConfig":
        """Load configuration from JSON file"""
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except FileNotFoundError:
            raise ConfigurationError(f"Config file not found: {config_path}")
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in config file: {e}")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerConfig":
        """Create configuration from a (possibly stale) dictionary.

        Unknown keys are silently ignored so config files written by older
        versions — which may still carry removed keys like ``engine``,
        ``chrome_channel`` or ``stdio_mode`` — load cleanly instead of raising
        ``TypeError``. Both the top-level data and the ``auth`` sub-dict are
        filtered down to the known dataclass field names.
        """
        data = dict(data)  # don't mutate the caller's dict
        auth_data = data.pop("auth", {}) or {}
        auth_fields = {f.name for f in fields(AuthConfig)}
        auth_config = AuthConfig(
            **{k: v for k, v in auth_data.items() if k in auth_fields}
        )
        server_fields = {f.name for f in fields(cls)} - {"auth"}
        return cls(
            auth=auth_config,
            **{k: v for k, v in data.items() if k in server_fields},
        )

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Load configuration from environment variables"""
        return cls(
            headless=os.getenv("NOTEBOOKLM_HEADLESS", "false").lower() == "true",
            timeout=int(os.getenv("NOTEBOOKLM_TIMEOUT", "60")),
            debug=os.getenv("NOTEBOOKLM_DEBUG", "false").lower() == "true",
            default_notebook_id=os.getenv("NOTEBOOKLM_NOTEBOOK_ID"),
            auth=AuthConfig(
                profile_dir=os.getenv(
                    "NOTEBOOKLM_PROFILE_DIR", "./chrome_profile_notebooklm"
                ),
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, AuthConfig):
                result[key] = value.__dict__
            else:
                result[key] = value
        return result

    def save_to_file(self, config_path: str) -> None:
        """Save configuration to JSON file"""
        config_data = self.to_dict()

        # Ensure directory exists
        config_dir = os.path.dirname(config_path)
        if config_dir:  # Only create if there's a directory component
            os.makedirs(config_dir, exist_ok=True)

        with open(config_path, "w") as f:
            json.dump(config_data, f, indent=2)

    def validate(self) -> None:
        """Validate configuration settings"""
        if self.timeout <= 0:
            raise ConfigurationError("Timeout must be positive")

        if self.auth.profile_dir and not Path(self.auth.profile_dir).parent.exists():
            raise ConfigurationError(
                f"Profile directory parent does not exist: {self.auth.profile_dir}"
            )

        # Validate import profile path
        if (
            self.auth.import_profile_from
            and self.auth.import_profile_from.strip()
            and not Path(self.auth.import_profile_from).exists()
        ):
            raise ConfigurationError(
                f"Import profile path does not exist: {self.auth.import_profile_from}"
            )

    def setup_profile(self) -> None:
        """Setup Chrome profile based on configuration"""
        profile_path = Path(self.auth.profile_dir)

        # Import existing profile if specified
        if self.auth.import_profile_from and self.auth.import_profile_from.strip():
            import_path = Path(self.auth.import_profile_from)
            _copy_tree(import_path, profile_path)
            print(f"✅ Imported profile from: {import_path}")

        # Create profile directory if it doesn't exist
        elif not profile_path.exists():
            profile_path.mkdir(parents=True, exist_ok=True)
            print(f"✅ Created new profile directory: {profile_path}")


def load_config(config_path: Optional[str] = None) -> ServerConfig:
    """
    Load configuration with priority:
    1. Explicit config file path
    2. Environment variables
    3. Default config file (./config.json)
    4. Default values
    """
    if config_path and os.path.exists(config_path):
        return ServerConfig.from_file(config_path)

    # Try default config file
    default_config = "./config.json"
    if os.path.exists(default_config):
        return ServerConfig.from_file(default_config)

    # Fall back to environment variables
    return ServerConfig.from_env()
