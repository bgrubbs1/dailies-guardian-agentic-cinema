from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from dailies_guardian.agent import build_grafana_server_parameters  # noqa: E402
from dailies_guardian.config import Settings  # noqa: E402


class GrafanaProcessBoundaryTests(unittest.TestCase):
    def test_mcp_process_is_configured_read_only_with_minimal_environment(self) -> None:
        settings = Settings(
            "contest-project",
            "us-central1",
            "gemini-flash-latest",
            "https://synthetic.invalid",
            "placeholder-token",
            "mcp-grafana",
        )
        parameters = build_grafana_server_parameters(settings)
        self.assertEqual(parameters.command, "mcp-grafana")
        self.assertEqual(
            parameters.args,
            [
                "--disable-write",
                "--enabled-tools=search,datasource,dashboard,prometheus,loki",
            ],
        )
        self.assertEqual(
            parameters.env,
            {
                "GRAFANA_URL": "https://synthetic.invalid",
                "GRAFANA_SERVICE_ACCOUNT_TOKEN": "placeholder-token",
            },
        )


if __name__ == "__main__":
    unittest.main()
