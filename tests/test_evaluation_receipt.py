from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.fspath(ROOT / "src"))

from dailies_guardian.evaluation_receipt import (  # noqa: E402
    EvaluationReceiptError,
    build_evaluation_receipt,
    evaluation_receipt_bytes,
)
from dailies_guardian.fixture import load_fixture  # noqa: E402


FIXTURE_PATH = ROOT / "fixtures" / "telemetry_v1.json"


class EvaluationReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture(FIXTURE_PATH)

    def test_receipt_covers_all_cases_with_scores_and_explicit_abstention(self) -> None:
        receipt = build_evaluation_receipt(self.fixture)
        self.assertEqual(
            receipt["fixture_sha256"],
            "4413623d91acb49d926acc8b28f0e25fea28677c5e9a5acd82b5713bdef4817c",
        )
        cases = {case["case_id"]: case for case in receipt["cases"]}
        self.assertEqual(
            set(cases),
            {"INGEST_BACKLOG", "TRANSCODE_SATURATION", "AMBIGUOUS_REVIEW_DELAY"},
        )
        self.assertEqual(cases["INGEST_BACKLOG"]["decision"], "supported_hypothesis")
        self.assertEqual(
            cases["TRANSCODE_SATURATION"]["decision"], "supported_hypothesis"
        )
        self.assertEqual(cases["AMBIGUOUS_REVIEW_DELAY"]["decision"], "abstain")
        for case in cases.values():
            self.assertTrue(case["eligible"])
            self.assertGreaterEqual(case["total"], 90)
            self.assertEqual(sum(case["breakdown"].values()), case["total"])
            self.assertEqual(case["citation"]["tool"], "query_prometheus")
            self.assertRegex(case["brief_sha256"], r"^[0-9a-f]{64}$")

    def test_receipt_bytes_are_deterministic_and_contain_no_raw_telemetry(self) -> None:
        first = evaluation_receipt_bytes(self.fixture)
        second = evaluation_receipt_bytes(self.fixture)
        self.assertEqual(first, second)
        rendered = first.decode("utf-8")
        for forbidden in ('"metrics"', '"logs"', '"alerts"', '"samples"', "http://", "https://"):
            self.assertNotIn(forbidden, rendered)
        self.assertNotIn("credential", rendered.casefold())
        self.assertNotIn("token", rendered.casefold())

    def test_unobserved_citation_window_fails_closed(self) -> None:
        with self.assertRaises(EvaluationReceiptError):
            build_evaluation_receipt(
                self.fixture,
                citation_overrides={
                    "INGEST_BACKLOG": {
                        ("query_prometheus", "2026-08-10T00:00:00Z/2026-08-10T00:15:00Z")
                    }
                },
            )

    def test_export_command_matches_library_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evaluation.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    os.fspath(ROOT / "scripts" / "export_evaluation_receipt.py"),
                    "--fixture",
                    os.fspath(FIXTURE_PATH),
                    "--output",
                    os.fspath(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(output.read_bytes(), evaluation_receipt_bytes(self.fixture))
            parsed = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(parsed["schema_version"], "1.0")


if __name__ == "__main__":
    unittest.main()
