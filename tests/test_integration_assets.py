from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integration" / "grafana"


class GrafanaProvisioningAssetTests(unittest.TestCase):
    def test_container_pins_public_runtime_assets_independent_of_workdir(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("DAILIES_STATIC_INDEX=/app/static/index.html", dockerfile)
        self.assertIn("DAILIES_FIXTURE_PATH=/app/fixtures/telemetry_v1.json", dockerfile)

    def test_loki_datasource_is_fixed_read_only_synthetic_target(self) -> None:
        text = (
            INTEGRATION / "provisioning" / "datasources" / "datasources.yaml"
        ).read_text(encoding="utf-8")
        for required in (
            "name: Synthetic Loki",
            "uid: synthetic-loki",
            "type: loki",
            "url: http://loki:3100",
            "access: proxy",
            "editable: false",
        ):
            self.assertIn(required, text)
        self.assertNotIn("password", text.casefold())
        self.assertNotIn("token", text.casefold())

    def test_dashboard_provider_loads_only_checked_in_dashboard_directory(self) -> None:
        text = (
            INTEGRATION / "provisioning" / "dashboards" / "dashboards.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("disableDeletion: true", text)
        self.assertIn("allowUiUpdates: false", text)
        self.assertIn("path: /var/lib/grafana/dashboards", text)

    def test_dashboard_has_three_synthetic_loki_evidence_panels(self) -> None:
        dashboard = json.loads(
            (INTEGRATION / "dashboards" / "dailies-overview.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(dashboard["uid"], "dailies-overview")
        self.assertEqual(dashboard["title"], "Synthetic Dailies Overview")
        self.assertIn("synthetic-only", dashboard["tags"])
        self.assertEqual(len(dashboard["panels"]), 3)
        expressions = []
        for panel in dashboard["panels"]:
            self.assertEqual(panel["type"], "logs")
            self.assertEqual(panel["datasource"]["uid"], "synthetic-loki")
            expressions.extend(target["expr"] for target in panel["targets"])
        for production in ("ORBITAL_DAY_7", "HARBOR_LIGHT_EP2", "PAPER_MOON_TRAILER"):
            self.assertTrue(any(production in expression for expression in expressions))
        self.assertEqual(dashboard["time"], {"from": "now-2h", "to": "now"})

    def test_mcp_smoke_calls_only_expected_read_tools(self) -> None:
        source = (ROOT / "scripts" / "smoke_grafana_mcp.py").read_text(encoding="utf-8")
        calls = set(
            re.findall(r'_call\(\s*session,\s*"([a-z0-9_]+)"', source, re.MULTILINE)
        )
        self.assertEqual(
            calls,
            {
                "list_datasources",
                "search_dashboards",
                "get_dashboard_by_uid",
                "query_loki_logs",
            },
        )
        for forbidden in ("update_dashboard", "create_dashboard", "delete_dashboard"):
            self.assertNotIn(forbidden, source)

    def test_disposable_stack_is_digest_pinned_loopback_only_and_cleans_up(self) -> None:
        source = (ROOT / "scripts" / "smoke_grafana_mcp.ps1").read_text(encoding="utf-8")
        self.assertEqual(source.count("@sha256:"), 2)
        loopback_bind = "127" + ".0.0.1:${"
        self.assertGreaterEqual(source.count(loopback_bind), 2)
        self.assertIn("finally {", source)
        self.assertIn("docker network rm", source)
        self.assertNotIn("grafana.net", source)


if __name__ == "__main__":
    unittest.main()
