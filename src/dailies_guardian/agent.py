"""Google ADK agent wired to the official Grafana MCP server at runtime."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .config import Settings
from .policy import READ_ONLY_GRAFANA_TOOLS, system_instruction


def build_grafana_server_parameters(settings: Settings) -> StdioServerParameters:
    """Build the immutable, read-only Grafana MCP process boundary."""

    grafana_env = {
        "GRAFANA_URL": settings.grafana_url,
        "GRAFANA_SERVICE_ACCOUNT_TOKEN": settings.grafana_service_account_token,
    }
    return StdioServerParameters(
        command=settings.mcp_grafana_bin,
        args=[
            "--disable-write",
            "--enabled-tools=search,datasource,dashboard,prometheus,loki",
        ],
        env=grafana_env,
    )


def build_agent(settings: Settings) -> LlmAgent:
    settings.assert_runtime_ready()
    grafana_server = build_grafana_server_parameters(settings)

    return LlmAgent(
        model=settings.gemini_model,
        name="dailies_guardian",
        description=(
            "Read-only Gemini incident agent for synthetic film dailies pipelines"
        ),
        instruction=system_instruction(),
        tools=[
            McpToolset(
                connection_params=StdioConnectionParams(server_params=grafana_server),
                tool_filter=READ_ONLY_GRAFANA_TOOLS,
            )
        ],
    )
