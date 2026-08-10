from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.fspath(ROOT / "src"))

from dailies_guardian.fixture import load_fixture  # noqa: E402
from dailies_guardian.policy import (  # noqa: E402
    EvidenceContractError,
    validate_fixture_outcome,
)


FIXTURE_PATH = ROOT / "fixtures" / "telemetry_v1.json"


def metric(case: dict[str, object], name: str) -> dict[str, object]:
    return next(item for item in case["metrics"] if item["name"] == name)  # type: ignore[index]


class SyntheticFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_fixture(FIXTURE_PATH)
        cls.cases = {case["id"]: case for case in cls.data["cases"]}

    def test_fixture_has_stable_canonical_hash(self) -> None:
        canonical = json.dumps(self.data, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            "4413623d91acb49d926acc8b28f0e25fea28677c5e9a5acd82b5713bdef4817c",
        )

    def test_ingest_case_has_independent_supporting_arithmetic(self) -> None:
        case = self.cases["INGEST_BACKLOG"]
        queue = [sample[1] for sample in metric(case, "dailies_ingest_queue_depth")["samples"]]
        completed = [
            sample[1] for sample in metric(case, "dailies_ingest_completed_total")["samples"]
        ]
        retries = [log for log in case["logs"] if log["event"] == "checksum_retry"]
        self.assertGreaterEqual(queue[-1] - queue[0], 15)
        self.assertEqual(completed[:10], [completed[0]] * 10)
        self.assertGreaterEqual(len(retries), 3)
        self.assertGreater(case["alerts"][0]["starts_at"], retries[0]["ts"])

    def test_transcode_case_proves_saturation_correlation(self) -> None:
        case = self.cases["TRANSCODE_SATURATION"]
        queue = [sample[1] for sample in metric(case, "dailies_ingest_queue_depth")["samples"]]
        active = [
            sample[1] for sample in metric(case, "dailies_transcode_active_workers")["samples"]
        ]
        limit = [
            sample[1] for sample in metric(case, "dailies_transcode_worker_limit")["samples"]
        ]
        duration = [
            sample[1] for sample in metric(case, "dailies_transcode_duration_seconds")["samples"]
        ]
        retries = [
            sample[1] for sample in metric(case, "dailies_transcode_retry_total")["samples"]
        ]
        self.assertGreaterEqual(sum(a == b for a, b in zip(active, limit)), 8)
        self.assertGreater(duration[-1], 3 * duration[0])
        self.assertGreaterEqual(retries[-1] - retries[0], 3)
        self.assertGreaterEqual(queue[-1] - queue[0], 20)

    def test_ambiguous_case_requires_abstention(self) -> None:
        case = self.cases["AMBIGUOUS_REVIEW_DELAY"]
        age = [
            sample[1] for sample in metric(case, "dailies_review_package_age_minutes")["samples"]
        ]
        success = [
            sample[1]
            for sample in metric(case, "dailies_review_publish_success_total")["samples"]
        ]
        self.assertLessEqual(max(age), 12)
        self.assertGreaterEqual(success[-1] - success[0], 1)
        self.assertEqual(case["alerts"], [])
        self.assertEqual(case["expected_outcome"], "abstain_or_inconclusive")
        with self.assertRaisesRegex(EvidenceContractError, "requires abstention"):
            validate_fixture_outcome(
                "PAPER_MOON_TRAILER",
                "The root cause is definitely a publishing failure.",
            )
        validate_fixture_outcome(
            "PAPER_MOON_TRAILER",
            "The evidence is inconclusive and the cause remains unknown.",
        )


if __name__ == "__main__":
    unittest.main()
