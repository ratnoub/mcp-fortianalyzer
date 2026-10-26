"""FortiAnalyzer MCP Server implementation (FastMCP).

This module creates the FastMCP server, manages the shared FortiAnalyzer
client lifecycle, and registers all tool modules.

Configuration is read from ``config.yaml`` (see ``utils/config.py``). The
server can run over stdio (for local MCP clients such as Claude Desktop) or
HTTP (for containerised / remote deployments).
"""

import argparse
import logging
import os
import secrets
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.auth import StaticTokenVerifier

from mcp_fortianalyzer.api.client import FortiAnalyzerClient
from mcp_fortianalyzer.instructions import build_instructions
from mcp_fortianalyzer.utils.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings (loaded from config.yaml) and logging
# ---------------------------------------------------------------------------
settings = get_settings()
settings.configure_logging()

# Global FortiAnalyzer client, initialised in the server lifespan.
faz_client: FortiAnalyzerClient | None = None


def get_faz_client() -> FortiAnalyzerClient | None:
    """Get the global FortiAnalyzer client instance.

    Returns:
        The shared client, or None before the lifespan has started.
    """
    return faz_client


def _build_client() -> FortiAnalyzerClient:
    """Construct a FortiAnalyzer client from the loaded settings."""
    return FortiAnalyzerClient(
        host=settings.FORTIANALYZER_HOST,
        api_token=settings.FORTIANALYZER_API_TOKEN,
        username=settings.FORTIANALYZER_USERNAME,
        password=settings.FORTIANALYZER_PASSWORD,
        verify_ssl=settings.FORTIANALYZER_VERIFY_SSL,
        ca_bundle=settings.FORTIANALYZER_CA_BUNDLE or None,
        timeout=settings.FORTIANALYZER_TIMEOUT,
        max_retries=settings.FORTIANALYZER_MAX_RETRIES,
    )


# ---------------------------------------------------------------------------
# Server lifespan: connect / disconnect the shared client
# ---------------------------------------------------------------------------
@asynccontextmanager
async def _server_lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage the shared FortiAnalyzer client for the server's lifetime."""
    global faz_client

    logger.info("Initializing FortiAnalyzer connection")
    faz_client = _build_client()
    try:
        await faz_client.connect()
        logger.info("FortiAnalyzer connection established")
    except Exception as e:  # noqa: BLE001 - server must still start
        logger.warning(
            "FortiAnalyzer connection failed: %s. Server will still start; "
            "tools will retry the connection per request.",
            e,
        )

    try:
        yield
    finally:
        logger.info("Closing FortiAnalyzer connection")
        if faz_client is not None:
            try:
                await faz_client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            faz_client = None


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "FortiAnalyzer API Server",
    instructions=build_instructions(),
    lifespan=_server_lifespan,
)


# ---------------------------------------------------------------------------
# Register all tool modules (each module decorates its functions with
# ``@mcp.tool`` and therefore registers itself on import).
# ---------------------------------------------------------------------------
from mcp_fortianalyzer.tools import (  # noqa: E402, F401
    dvm_tools,
    event_tools,
    fortiview_tools,
    incident_tools,
    ioc_tools,
    log_tools,
    pcap_tools,
    report_tools,
    soar_tools,
    system_tools,
    traffic_tools,
    ueba_tools,
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _resolve_transport(cli_transport: str | None) -> str:
    """Decide which transport to run (stdio or http).

    Priority: explicit ``--transport`` flag, then the ``FAZ_TRANSPORT``
    environment variable, then auto-detection (a TTY or Docker environment
    runs HTTP, a piped stdin runs stdio).
    """
    if cli_transport in {"stdio", "http"}:
        return cli_transport

    forced = os.environ.get("FAZ_TRANSPORT", "").strip().lower()
    if forced in {"stdio", "http"}:
        return forced

    is_docker = os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "1"
    if is_docker or sys.stdin.isatty():
        return "http"
    return "stdio"


def _resolve_auth_token(cli_token: str | None) -> str | None:
    """Resolve the HTTP auth token from CLI, env, or config.yaml.

    Returns ``None`` when no token is configured anywhere, in which case the
    caller generates a random one.
    """
    if cli_token:
        return cli_token.strip()
    env_token = os.environ.get("FAZ_AUTH_TOKEN", "").strip()
    if env_token:
        return env_token
    cfg_token = (settings.AUTH_TOKEN or "").strip()
    if cfg_token:
        return cfg_token
    return None


def _build_auth_provider(token: str) -> StaticTokenVerifier:
    """Build a static-token auth provider for the given bearer token."""
    return StaticTokenVerifier(
        tokens={token: {"client_id": "mcp-fortianalyzer", "scopes": []}}
    )


def _daemon_dir() -> Path:
    """Directory for daemon log/PID files (FAZ_DAEMON_DIR or the cwd)."""
    base = Path(os.environ.get("FAZ_DAEMON_DIR", "") or Path.cwd())
    base.mkdir(parents=True, exist_ok=True)
    return base


def _daemon_command(args: argparse.Namespace) -> list[str]:
    """Build the command line for the daemon child process.

    Prefers the installed ``mcp-fortianalyzer`` console entry point. Falls back
    to importing the module and calling ``main()`` via ``-c`` (rather than
    ``python -m``), which avoids the ``__main__`` double-import that would
    leave the running server with no registered tools.
    """
    tail = [
        "--transport",
        "http",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--path",
        args.path,
    ]
    if args.no_auth:
        tail.append("--no-auth")

    import shutil

    entry = shutil.which("mcp-fortianalyzer")
    if entry:
        return [entry, *tail]
    return [sys.executable, "-c", "from mcp_fortianalyzer.server import main; main()", *tail]


def _spawn_daemon(args: argparse.Namespace, token: str | None) -> None:
    """Spawn a detached background process running the HTTP server, then exit.

    The child re-runs the server over HTTP with the same host/port/path and
    the resolved auth token (passed via ``FAZ_AUTH_TOKEN``). Its stdout/stderr
    are written to a log file and its PID to a PID file so it can be stopped.
    """
    cmd = _daemon_command(args)

    env = os.environ.copy()
    if token:
        env["FAZ_AUTH_TOKEN"] = token

    base_dir = _daemon_dir()
    log_path = base_dir / "mcp-fortianalyzer.log"
    pid_path = base_dir / "mcp-fortianalyzer.pid"

    log_file = open(log_path, "ab")
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )
    log_file.close()
    pid_path.write_text(str(proc.pid), encoding="utf-8")

    print("FortiAnalyzer MCP server started in the background (daemon mode).")
    print(f"  PID:        {proc.pid}")
    print(f"  Endpoint:   http://{args.host}:{args.port}{args.path}")
    print(f"  Log file:   {log_path}")
    print(f"  PID file:   {pid_path}")
    if token:
        print(f"  Auth token: {token}")
    stop_cmd = f"taskkill /PID {proc.pid}" if os.name == "nt" else f"kill {proc.pid}"
    print(f"  Stop with:  {stop_cmd}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="mcp-fortianalyzer",
        description="FortiAnalyzer MCP server (FastMCP).",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=None,
        help="Transport to use (default: auto-detect).",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="HTTP bind host (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5750,
        help="HTTP bind port (default: 5750).",
    )
    parser.add_argument(
        "--path",
        default="/mcp",
        help="HTTP endpoint path (default: /mcp).",
    )
    parser.add_argument(
        "--token",
        default=None,
        help=(
            "Auth token for HTTP mode. Falls back to the FAZ_AUTH_TOKEN env "
            "var, then config.yaml 'auth_token', then a generated token."
        ),
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable auth-token enforcement in HTTP mode (not recommended).",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run the HTTP server in the background and exit.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point for the MCP server."""
    args = _parse_args()
    transport = _resolve_transport(args.transport)

    if transport == "stdio":
        logger.info("Starting FortiAnalyzer MCP server in stdio mode")
        mcp.run(transport="stdio")
        return

    # HTTP mode: resolve the auth token (unless auth is disabled).
    token: str | None = None
    generated = False
    if not args.no_auth:
        token = _resolve_auth_token(args.token)
        if token is None:
            token = secrets.token_urlsafe(32)
            generated = True

    if args.daemon:
        _spawn_daemon(args, token)
        return

    if not args.no_auth:
        mcp.auth = _build_auth_provider(token)

    logger.info(
        "Starting FortiAnalyzer MCP server in HTTP mode on %s:%s%s",
        args.host,
        args.port,
        args.path,
    )
    if generated:
        print(f"Generated auth token (none configured): {token}")
    mcp.run(transport="http", host=args.host, port=args.port, path=args.path)


if __name__ == "__main__":
    main()
