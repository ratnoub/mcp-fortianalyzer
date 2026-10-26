from __future__ import annotations

import asyncio
from typing import Any

from mcp_fortianalyzer.tools import log_tools, report_tools


class _Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_report_schedules(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_report_schedules", kwargs))
        return {"data": [{"name": "42"}, {"name": "43"}]}

    async def search_logfiles(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("search_logfiles", kwargs))
        return {"data": [{"srcip": "192.0.2.1"}]}

    async def get_logfiles_data(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_logfiles_data", kwargs))
        return {"data": "YQ=="}


def test_report_schedule_listing_calls_expected_endpoint(monkeypatch: Any) -> None:
    client = _Client()
    monkeypatch.setattr(report_tools, "get_faz_client", lambda: client)

    result = asyncio.run(report_tools.list_report_schedules(adom="root", layout_id=42))

    assert result["status"] == "success"
    assert result["count"] == 2
    assert client.calls == [("get_report_schedules", {"adom": "root", "layout_id": 42})]


def test_archived_log_search_forwards_query(monkeypatch: Any) -> None:
    client = _Client()
    monkeypatch.setattr(log_tools, "get_faz_client", lambda: client)

    result = asyncio.run(
        log_tools.search_archived_logs(
            device="FGT-001", vdom="root", filename="traffic.log",
            logtype="traffic", adom="root", filter="srcip==192.0.2.1",
        )
    )

    assert result["status"] == "success"
    name, kwargs = client.calls[0]
    assert name == "search_logfiles"
    assert kwargs["devid"] == "FGT-001"
    assert kwargs["filename"] == "traffic.log"
    assert kwargs["filter"] == "srcip==192.0.2.1"


def test_archived_log_data_rejects_oversized_chunk_before_api_call(monkeypatch: Any) -> None:
    client = _Client()
    monkeypatch.setattr(log_tools, "get_faz_client", lambda: client)

    result = asyncio.run(
        log_tools.get_archived_log_data(
            device="FGT-001", vdom="root", filename="traffic.log", length=52428801,
        )
    )

    assert result["status"] == "error"
    assert "length" in result["message"]
    assert client.calls == []
