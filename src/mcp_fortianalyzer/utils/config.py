"""Configuration management for the FortiAnalyzer MCP server.

Configuration is read from a ``config.yaml`` file (see the project root for the
default location). Environment variables may override individual values, which
is handy for secrets in containerised deployments, but the YAML file is the
single source of truth for a normal install.

Expected shape::

    config:
      fortianalyzer:
        host: 172.18.7.15
        api_key: <token>
        verify_ssl: false
        log_level: info
        default_adom: root

Optional keys (with defaults): ``username``, ``password``, ``ca_bundle``,
``timeout``, ``max_retries``, ``log_file``, ``log_format``, ``auth_token``.

``auth_token`` (or the ``FAZ_AUTH_TOKEN`` env var) protects the HTTP endpoint.
When unset, the server generates a random token at startup and prints it.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# Project root: utils -> mcp_fortianalyzer -> src -> project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Candidate locations for config.yaml, in priority order.
_DEFAULT_CONFIG_CANDIDATES = (
    Path(os.environ["FAZ_CONFIG_FILE"]) if os.environ.get("FAZ_CONFIG_FILE") else None,
    Path.cwd() / "config.yaml",
    _PROJECT_ROOT / "config.yaml",
    _PROJECT_ROOT / "config.yml",
)


def _find_config_file() -> Path:
    """Locate the config.yaml file.

    Returns:
        Path to the first existing candidate.

    Raises:
        FileNotFoundError: If no candidate exists.
    """
    for candidate in _DEFAULT_CONFIG_CANDIDATES:
        if candidate is not None and candidate.is_file():
            return candidate
    searched = [str(c) for c in _DEFAULT_CONFIG_CANDIDATES if c is not None]
    raise FileNotFoundError(
        "config.yaml not found. Looked in: "
        + ", ".join(searched)
        + ". Set FAZ_CONFIG_FILE to point at your config file."
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load and normalise the YAML config file."""
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config.yaml root must be a mapping, got {type(raw).__name__}")
    # Accept both the nested {config: {fortianalyzer: {...}}} form and a flat
    # {fortianalyzer: {...}} form for convenience.
    node = raw.get("config", raw)
    if not isinstance(node, dict):
        raise ValueError("config.yaml 'config' section must be a mapping")
    return node.get("fortianalyzer", {}) or {}


def _env_override(name: str, default: Any) -> Any:
    """Return the environment override for a setting, or its default."""
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass
class Settings:
    """Application settings loaded from config.yaml (with env overrides)."""

    # FortiAnalyzer connection
    FORTIANALYZER_HOST: str
    FORTIANALYZER_API_TOKEN: str | None = None
    FORTIANALYZER_USERNAME: str | None = None
    FORTIANALYZER_PASSWORD: str | None = None
    FORTIANALYZER_VERIFY_SSL: bool = True
    FORTIANALYZER_CA_BUNDLE: str = ""
    FORTIANALYZER_TIMEOUT: int = 30
    FORTIANALYZER_MAX_RETRIES: int = 3

    # Default ADOM
    DEFAULT_ADOM: str = "root"

    # HTTP auth token (used to protect the HTTP endpoint). When unset, the
    # server generates a random token at startup and prints it.
    AUTH_TOKEN: str | None = None

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: Path | None = None
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Where the settings were loaded from (for diagnostics).
    config_file: Path | None = field(default=None, repr=False)

    @classmethod
    def from_file(cls, path: Path | None = None) -> Settings:
        """Build settings from a config.yaml file (or auto-discovered)."""
        cfg_path = path or _find_config_file()
        data = _load_yaml(cfg_path)

        host = str(_env_override("FORTIANALYZER_HOST", data.get("host", "")) or "").strip()
        if not host:
            raise ValueError(
                "config.yaml must define 'config.fortianalyzer.host' "
                "(or set FORTIANALYZER_HOST)."
            )
        host = host.replace("https://", "").replace("http://", "").rstrip("/")

        api_key = _env_override("FORTIANALYZER_API_TOKEN", data.get("api_key"))
        username = _env_override("FORTIANALYZER_USERNAME", data.get("username"))
        password = _env_override("FORTIANALYZER_PASSWORD", data.get("password"))
        ca_bundle = _env_override("FORTIANALYZER_CA_BUNDLE", data.get("ca_bundle", ""))
        log_file = _env_override("LOG_FILE", data.get("log_file"))
        auth_token = _env_override("FAZ_AUTH_TOKEN", data.get("auth_token"))

        return cls(
            FORTIANALYZER_HOST=host,
            FORTIANALYZER_API_TOKEN=str(api_key) if api_key else None,
            FORTIANALYZER_USERNAME=str(username) if username else None,
            FORTIANALYZER_PASSWORD=str(password) if password else None,
            FORTIANALYZER_VERIFY_SSL=_env_bool(
                "FORTIANALYZER_VERIFY_SSL", bool(data.get("verify_ssl", True))
            ),
            FORTIANALYZER_CA_BUNDLE=str(ca_bundle) if ca_bundle else "",
            FORTIANALYZER_TIMEOUT=_env_int("FORTIANALYZER_TIMEOUT", int(data.get("timeout", 30))),
            FORTIANALYZER_MAX_RETRIES=_env_int("FORTIANALYZER_MAX_RETRIES", int(data.get("max_retries", 3))),
            DEFAULT_ADOM=str(_env_override("DEFAULT_ADOM", data.get("default_adom", "root"))),
            AUTH_TOKEN=str(auth_token).strip() if auth_token else None,
            LOG_LEVEL=str(_env_override("LOG_LEVEL", data.get("log_level", "info"))).upper(),
            LOG_FILE=Path(log_file).expanduser() if log_file else None,
            LOG_FORMAT=str(
                data.get("log_format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            ),
            config_file=cfg_path,
        )

    # ------------------------------------------------------------------
    # Convenience properties (mirror the legacy env-based settings)
    # ------------------------------------------------------------------
    @property
    def has_token_auth(self) -> bool:
        """Check if API token authentication is configured."""
        return self.FORTIANALYZER_API_TOKEN is not None

    @property
    def has_session_auth(self) -> bool:
        """Check if session-based authentication is configured."""
        return self.FORTIANALYZER_USERNAME is not None and self.FORTIANALYZER_PASSWORD is not None

    @property
    def base_url(self) -> str:
        """Get FortiAnalyzer base URL."""
        return f"https://{self.FORTIANALYZER_HOST}/jsonrpc"

    def configure_logging(self) -> None:
        """Configure application logging based on settings."""
        log_level = getattr(logging, self.LOG_LEVEL.upper(), logging.INFO)

        handlers: list[logging.Handler] = []
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter(self.LOG_FORMAT))
        handlers.append(console_handler)

        if self.LOG_FILE:
            self.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(self.LOG_FILE)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(logging.Formatter(self.LOG_FORMAT))
            handlers.append(file_handler)

        logging.basicConfig(level=log_level, format=self.LOG_FORMAT, handlers=handlers)
        # Reduce noise from chatty libraries.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("pyFMG").setLevel(log_level)


@lru_cache
def get_settings() -> Settings:
    """Get the cached settings instance (loaded from config.yaml).

    Returns:
        Settings instance.

    Raises:
        FileNotFoundError: If config.yaml cannot be found.
        ValueError: If required settings are missing or invalid.
    """
    return Settings.from_file()
