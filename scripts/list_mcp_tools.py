"""List the official Grafana MCP tools without invoking any Grafana operation."""

from __future__ import annotations

import asyncio
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    server = StdioServerParameters(
        command=os.getenv("MCP_GRAFANA_BIN", "mcp-grafana"),
        args=[
            "--disable-write",
            "--enabled-tools=search,datasource,dashboard,prometheus,loki",
        ],
        env={
            "GRAFANA_URL": os.getenv("GRAFANA_URL", "https://example.invalid"),
            "GRAFANA_SERVICE_ACCOUNT_TOKEN": os.getenv(
                "GRAFANA_SERVICE_ACCOUNT_TOKEN", "placeholder-not-a-real-token"
            ),
        },
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for tool in sorted(tools.tools, key=lambda item: item.name):
                print(tool.name)


if __name__ == "__main__":
    asyncio.run(main())
