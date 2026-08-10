"""Environment configuration with fail-closed validation."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    google_cloud_project: str
    google_cloud_location: str
    gemini_model: str
    grafana_url: str
    grafana_service_account_token: str
    mcp_grafana_bin: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT", "").strip(),
            google_cloud_location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip(),
            grafana_url=os.getenv("GRAFANA_URL", "").strip(),
            grafana_service_account_token=os.getenv(
                "GRAFANA_SERVICE_ACCOUNT_TOKEN", ""
            ).strip(),
            mcp_grafana_bin=os.getenv("MCP_GRAFANA_BIN", "mcp-grafana").strip(),
        )

    def missing_runtime_values(self) -> tuple[str, ...]:
        required = {
            "GOOGLE_CLOUD_PROJECT": self.google_cloud_project,
            "GRAFANA_URL": self.grafana_url,
            "GRAFANA_SERVICE_ACCOUNT_TOKEN": self.grafana_service_account_token,
            "MCP_GRAFANA_BIN": self.mcp_grafana_bin,
        }
        return tuple(name for name, value in required.items() if not value)

    def assert_runtime_ready(self) -> None:
        missing = self.missing_runtime_values()
        if missing:
            raise RuntimeError(
                "Missing contest-runtime configuration: " + ", ".join(missing)
            )
        if not self.grafana_url.startswith("https://"):
            raise RuntimeError("GRAFANA_URL must use HTTPS for the hosted contest runtime")
