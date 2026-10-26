"""Smoke tests for the mcp-fortianalyzer server.

These tests do not require a live FortiAnalyzer: they verify that the server
module imports, registers the expected tools, and omits the add/delete/create
operations that are intentionally not shipped.
"""

from __future__ import annotations

import asyncio

import mcp_fortianalyzer.server as server

# Tool-name fragments that must never appear: the add/delete/create operations
# are intentionally omitted from this build.
_FORBIDDEN_FRAGMENTS = ("add_", "delete_", "create_", "remove_")


def _tool_names() -> list[str]:
    return sorted(t.name for t in asyncio.run(server.mcp.list_tools()))


def test_server_registers_tools() -> None:
    """The server registers a non-trivial set of tools."""
    names = _tool_names()
    assert len(names) == 71, f"expected 71 tools, got {len(names)}"


def test_no_add_delete_create_tools() -> None:
    """No add/delete/create/remove tools are exposed."""
    names = _tool_names()
    forbidden = [n for n in names if any(f in n for f in _FORBIDDEN_FRAGMENTS)]
    assert not forbidden, f"unexpected add/delete/create tools: {forbidden}"


def test_core_tools_present() -> None:
    """A few well-known read tools are present."""
    names = set(_tool_names())
    for expected in ("list_adoms", "get_system_status", "query_logs"):
        assert expected in names, f"expected tool {expected!r} to be registered"


def test_reporting_and_archive_tools_present() -> None:
    """Reporting schedule visibility and archived-log tools are exposed."""
    names = set(_tool_names())
    for expected in (
        "list_report_schedules",
        "get_report_schedule_details",
        "search_archived_logs",
        "get_archived_log_data",
    ):
        assert expected in names, f"expected tool {expected!r} to be registered"
