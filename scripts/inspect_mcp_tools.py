"""Print the source-pinned Grafana MCP tool schemas without calling Grafana."""

from __future__ import annotations

import asyncio
import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    server = StdioServerParameters(
        command=os.getenv("MCP_GRAFANA_BIN", "mcp-grafana"),
        args=["--disable-write", "--enabled-tools=search,datasource,dashboard,prometheus,loki"],
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
            projection = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                for tool in sorted(tools.tools, key=lambda item: item.name)
            ]
            print(json.dumps(projection, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
