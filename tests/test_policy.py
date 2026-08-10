from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from dailies_guardian.config import Settings  # noqa: E402
from dailies_guardian.policy import (  # noqa: E402
    EvidenceContractError,
    IncidentRequest,
    READ_ONLY_GRAFANA_TOOLS,
    system_instruction,
    validate_evidence_brief,
)


VALID_BRIEF = """
## Observed facts
- [source: query_prometheus; window: 2026-08-09T01:00:00Z/2026-08-09T01:15:00Z] The synthetic ingest queue rose from 3 to 18 items.

## Inferences
- The queue growth is consistent with a downstream throughput constraint; this is not yet a root-cause claim.

## Unknowns
- The current worker saturation level is not present in the retrieved evidence.

## Reversible next actions
- Query the worker saturation metric for the same interval before changing any job.

## Escalation owner
- Fictional dailies on-call operator.
"""
VALID_CITATIONS = {
    (
        "query_prometheus",
        "2026-08-09T01:00:00Z/2026-08-09T01:15:00Z",
    )
}


class IncidentPolicyTests(unittest.TestCase):
    def test_known_synthetic_production_is_allowed(self) -> None:
        IncidentRequest(
            "ORBITAL_DAY_7",
            "Why is the editorial package late tonight?",
        ).validate()

    def test_unknown_production_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "fictional demo productions"):
            IncidentRequest("REAL_STUDIO", "Why is the ingest queue late?").validate()

    def test_phone_like_input_is_rejected(self) -> None:
        fictional_phone = "-".join(("212", "555", "0199"))
        with self.assertRaisesRegex(ValueError, "Phone-number-like"):
            IncidentRequest(
                "ORBITAL_DAY_7",
                f"Call the operator at {fictional_phone} about the late render",
            ).validate()

    def test_private_or_credential_like_input_is_rejected_before_runtime(self) -> None:
        private_questions = (
            f"Email {'person'}{'@'}{'example'}{'.com'} about this synthetic delay",
            "Inspect http://localhost:3000 for this synthetic delay",
            "Use Bearer abcdefghijklmnopqrstuvwxyz for the synthetic query",
            f"Check private address {'.'.join(('169', '254', '10', '12'))} for the synthetic delay",
            "This client-confidential synthetic incident needs investigation",
        )
        for question in private_questions:
            with self.subTest(question=question):
                with self.assertRaisesRegex(ValueError, "Private or credential-like"):
                    IncidentRequest("ORBITAL_DAY_7", question).validate()

    def test_instruction_is_read_only_and_evidence_first(self) -> None:
        instruction = system_instruction().casefold()
        self.assertIn("use grafana mcp read tools before", instruction)
        self.assertIn("never invent", instruction)
        self.assertIn("read-only", instruction)
        self.assertIn("unknowns", instruction)

    def test_grafana_tool_allowlist_contains_only_expected_reads(self) -> None:
        self.assertEqual(
            READ_ONLY_GRAFANA_TOOLS,
            (
                "list_datasources",
                "search_dashboards",
                "get_dashboard_by_uid",
                "query_prometheus",
                "query_loki_logs",
            ),
        )

    def test_valid_evidence_brief_passes_contract(self) -> None:
        self.assertEqual(
            validate_evidence_brief(VALID_BRIEF, VALID_CITATIONS),
            VALID_BRIEF.strip(),
        )

    def test_missing_required_section_fails_closed(self) -> None:
        with self.assertRaisesRegex(EvidenceContractError, "Unknowns"):
            validate_evidence_brief(
                VALID_BRIEF.replace("## Unknowns", "## Open items"),
                VALID_CITATIONS,
            )

    def test_observed_fact_without_source_and_window_fails_closed(self) -> None:
        invalid = VALID_BRIEF.replace(
            "[source: query_prometheus; window: 2026-08-09T01:00:00Z/2026-08-09T01:15:00Z] ",
            "",
        )
        with self.assertRaisesRegex(EvidenceContractError, "source.*window"):
            validate_evidence_brief(invalid, VALID_CITATIONS)

    def test_well_formed_but_unobserved_citation_fails_closed(self) -> None:
        fabricated = VALID_BRIEF.replace("query_prometheus", "invented_source")
        with self.assertRaisesRegex(EvidenceContractError, "observed successful tool response"):
            validate_evidence_brief(fabricated, VALID_CITATIONS)

    def test_observed_tool_with_different_window_fails_closed(self) -> None:
        wrong_window = {
            (
                "query_prometheus",
                "2026-08-09T02:00:00Z/2026-08-09T02:15:00Z",
            )
        }
        with self.assertRaisesRegex(EvidenceContractError, "observed successful tool response"):
            validate_evidence_brief(VALID_BRIEF, wrong_window)

    def test_brief_with_private_contact_fails_closed(self) -> None:
        invalid = VALID_BRIEF.replace(
            "Fictional dailies on-call operator.",
            f"Contact the operator at {'person'}{'@'}{'example'}{'.com'}.",
        )
        with self.assertRaisesRegex(EvidenceContractError, "private or credential-like"):
            validate_evidence_brief(invalid, VALID_CITATIONS)


class SettingsTests(unittest.TestCase):
    def test_missing_values_are_named_without_secret_values(self) -> None:
        settings = Settings("", "us-central1", "gemini-flash-latest", "", "", "mcp-grafana")
        self.assertEqual(
            settings.missing_runtime_values(),
            ("GOOGLE_CLOUD_PROJECT", "GRAFANA_URL", "GRAFANA_SERVICE_ACCOUNT_TOKEN"),
        )

    def test_non_https_grafana_url_fails_closed(self) -> None:
        settings = Settings(
            "contest-project",
            "us-central1",
            "gemini-flash-latest",
            "http://grafana.invalid",
            "placeholder-token",
            "mcp-grafana",
        )
        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            settings.assert_runtime_ready()


if __name__ == "__main__":
    unittest.main()
