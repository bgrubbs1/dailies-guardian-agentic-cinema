"""Call the official Grafana MCP server against the disposable synthetic stack."""

from __future__ import annotations

import asyncio
import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from dailies_guardian.fixture import parse_utc


def _result_text(result: object) -> str:
    blocks = getattr(result, "content", ())
    return "\n".join(
        text
        for block in blocks
        if isinstance((text := getattr(block, "text", None)), str)
    )


async def _call(session: ClientSession, name: str, arguments: dict[str, object]) -> str:
    result = await session.call_tool(name, arguments)
    if getattr(result, "isError", False):
        raise RuntimeError(f"Read-only MCP smoke call failed: {name}")
    text = _result_text(result)
    if not text:
        raise RuntimeError(f"Read-only MCP smoke call returned no evidence: {name}")
    return text


async def main() -> None:
    start = os.environ["SMOKE_START_RFC3339"]
    end = os.environ["SMOKE_END_RFC3339"]
    if parse_utc(start) >= parse_utc(end):
        raise ValueError("MCP smoke window must be an ordered absolute UTC interval")

    server = StdioServerParameters(
        command=os.getenv("MCP_GRAFANA_BIN", "mcp-grafana"),
        args=["--disable-write", "--enabled-tools=search,datasource,dashboard,prometheus,loki"],
        env={
            "GRAFANA_URL": os.environ["GRAFANA_URL"],
            "GRAFANA_SERVICE_ACCOUNT_TOKEN": os.environ[
                "GRAFANA_SERVICE_ACCOUNT_TOKEN"
            ],
        },
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            datasources = await _call(session, "list_datasources", {"type": "loki"})
            dashboards = await _call(
                session, "search_dashboards", {"query": "Synthetic Dailies Overview"}
            )
            dashboard = await _call(
                session, "get_dashboard_by_uid", {"uid": "dailies-overview"}
            )
            logs = await _call(
                session,
                "query_loki_logs",
                {
                    "datasourceUid": "synthetic-loki",
                    "logql": '{environment="synthetic"}',
                    "startRfc3339": start,
                    "endRfc3339": end,
                    "direction": "forward",
                    "limit": 100,
                    "queryType": "range",
                },
            )

    requirements = {
        "datasource": (datasources, ("synthetic-loki", "Synthetic Loki")),
        "dashboard_search": (dashboards, ("dailies-overview",)),
        "dashboard_read": (dashboard, ("Synthetic Dailies Overview",)),
        "loki_evidence": (
            logs,
            (
                "ORBITAL_DAY_7",
                "HARBOR_LIGHT_EP2",
                "PAPER_MOON_TRAILER",
                "checksum_retry",
                "codec_timeout_retry",
                "stale_status_snapshot",
            ),
        ),
    }
    for label, (text, markers) in requirements.items():
        if not all(marker in text for marker in markers):
            raise RuntimeError(f"MCP smoke evidence was incomplete: {label}")

    print(
        json.dumps(
            {
                "status": "pass",
                "transport": "official mcp-grafana v1.0.0 over stdio",
                "write_mode": "disabled",
                "tools_called": [
                    "list_datasources",
                    "search_dashboards",
                    "get_dashboard_by_uid",
                    "query_loki_logs",
                ],
                "datasource_uid": "synthetic-loki",
                "dashboard_uid": "dailies-overview",
                "production_ids_observed": [
                    "ORBITAL_DAY_7",
                    "HARBOR_LIGHT_EP2",
                    "PAPER_MOON_TRAILER",
                ],
                "window": f"{start}/{end}",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
