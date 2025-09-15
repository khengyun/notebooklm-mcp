"""
Configuration management for NotebookLM MCP Server
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .exceptions import ConfigurationError


@dataclass
class AuthConfig:
    """Authentication configuration"""

    cookies_path: Optional[str] = None
    profile_dir: str = "./chrome_profile_notebooklm"
    use_persistent_session: bool = True
    auto_login: bool = True

    # Quick setup options
    import_profile_from: Optional[str] = None  # Path to existing Chrome profile
    export_profile_to: Optional[str] = None  # Path to export current profile
    skip_manual_login: bool = False  # Skip manual login if profile exists


@dataclass
class ServerConfig:
    """Server configuration"""

    # Browser settings
    headless: bool = False
    timeout: int = 60
    debug: bool = False

    # NotebookLM settings
    default_notebook_id: Optional[str] = None
    base_url: str = "https://notebooklm.google.com"

    # MCP settings
    server_name: str = "notebooklm-mcp"
    stdio_mode: bool = True

    # Authentication
    auth: AuthConfig = field(default_factory=AuthConfig)

    # Advanced settings
    streaming_timeout: int = 60
    response_stability_checks: int = 3
    retry_attempts: int = 3

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
        """Create configuration from dictionary"""
        auth_data = data.pop("auth", {})
        auth_config = AuthConfig(**auth_data)
        return cls(auth=auth_config, **data)

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Load configuration from environment variables"""
        return cls(
            headless=os.getenv("NOTEBOOKLM_HEADLESS", "false").lower() == "true",
            timeout=int(os.getenv("NOTEBOOKLM_TIMEOUT", "60")),
            debug=os.getenv("NOTEBOOKLM_DEBUG", "false").lower() == "true",
            default_notebook_id=os.getenv("NOTEBOOKLM_NOTEBOOK_ID"),
            auth=AuthConfig(
                cookies_path=os.getenv("NOTEBOOKLM_COOKIES_PATH"),
                profile_dir=os.getenv(
                    "NOTEBOOKLM_PROFILE_DIR", "./chrome_profile_notebooklm"
                ),
                use_persistent_session=os.getenv(
                    "NOTEBOOKLM_PERSISTENT_SESSION", "true"
                ).lower()
                == "true",
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

        if self.streaming_timeout <= 0:
            raise ConfigurationError("Streaming timeout must be positive")

        if self.response_stability_checks <= 0:
            raise ConfigurationError("Response stability checks must be positive")

        if self.retry_attempts < 0:
            raise ConfigurationError("Retry attempts cannot be negative")

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
        from shutil import copytree, rmtree

        profile_path = Path(self.auth.profile_dir)

        # Import existing profile if specified
        if self.auth.import_profile_from and self.auth.import_profile_from.strip():
            import_path = Path(self.auth.import_profile_from)

            if profile_path.exists():
                rmtree(profile_path)

            copytree(import_path, profile_path)
            print(f"✅ Imported profile from: {import_path}")

        # Create profile directory if it doesn't exist
        elif not profile_path.exists():
            profile_path.mkdir(parents=True, exist_ok=True)
            print(f"✅ Created new profile directory: {profile_path}")

    def export_profile(self) -> None:
        """Export current Chrome profile to specified location"""
        if not self.auth.export_profile_to:
            return

        from shutil import copytree, rmtree

        source_path = Path(self.auth.profile_dir)
        export_path = Path(self.auth.export_profile_to)

        if not source_path.exists():
            raise ConfigurationError(f"Source profile does not exist: {source_path}")

        if export_path.exists():
            rmtree(export_path)

        copytree(source_path, export_path)
        print(f"✅ Exported profile to: {export_path}")


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
