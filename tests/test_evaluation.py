from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.fspath(ROOT / "src"))

from dailies_guardian.evaluation import score_brief  # noqa: E402


def brief(window: str, facts: list[str], inference: str, unknown: str, action: str, owner: str) -> str:
    observed = "\n".join(
        f"- [source: query_prometheus; window: {window}] {fact}" for fact in facts
    )
    return f"""
## Observed facts
{observed}

## Inferences
- {inference}

## Unknowns
- {unknown}

## Reversible next actions
- {action}

## Escalation owner
- {owner}
""".strip()


class EvidenceEvaluationTests(unittest.TestCase):
    def test_supported_ingest_brief_scores_at_least_ninety(self) -> None:
        window = "2026-08-10T01:00:00Z/2026-08-10T01:15:00Z"
        text = brief(
            window,
            [
                "The ingest queue is rising from 3 to 18 items.",
                "The completion counter is flat for nine minutes before progress resumes.",
                "Three checksum retry events coincide with the stalled completion interval.",
            ],
            "The correlation supports an ingest-validation bottleneck hypothesis, not a proven root cause.",
            "The physical media condition and underlying root cause remain unknown.",
            "Inspect the synthetic ingest validation and retry dashboard slice; make no mutation.",
            "Synthetic ingest on-call.",
        )
        result = score_brief(
            "INGEST_BACKLOG", text, {("query_prometheus", window)}
        )
        self.assertTrue(result.eligible)
        self.assertGreaterEqual(result.total, 90)
        self.assertEqual(sum(result.breakdown.values()), result.total)

    def test_missing_case_evidence_loses_signal_points(self) -> None:
        window = "2026-08-10T02:00:00Z/2026-08-10T02:15:00Z"
        text = brief(
            window,
            ["The queue increased during the interval."],
            "The evidence may support a capacity hypothesis, but does not prove a root cause.",
            "Worker saturation, duration, and retries remain unknown.",
            "Query the worker metrics for the same interval; make no mutation.",
            "Synthetic transcode on-call.",
        )
        result = score_brief(
            "TRANSCODE_SATURATION", text, {("query_prometheus", window)}
        )
        self.assertTrue(result.eligible)
        self.assertLessEqual(result.breakdown["case_evidence"], 10)
        self.assertLess(result.total, 80)

    def test_ambiguous_case_rewards_explicit_abstention(self) -> None:
        window = "2026-08-10T03:00:00Z/2026-08-10T03:15:00Z"
        text = brief(
            window,
            [
                "Package age remains at or below 12 minutes.",
                "Publish success increments during the window.",
                "The only stale status log is outside the requested window.",
            ],
            "The evidence is inconclusive and does not support a publishing-failure conclusion.",
            "The cause of the reported delay cannot be determined from current evidence.",
            "Request a narrower current publish-status query; make no mutation.",
            "Synthetic editorial coordinator.",
        )
        result = score_brief(
            "AMBIGUOUS_REVIEW_DELAY", text, {("query_prometheus", window)}
        )
        self.assertTrue(result.eligible)
        self.assertGreaterEqual(result.total, 90)
        self.assertEqual(result.breakdown["calibration"], 20)

    def test_ambiguous_causal_overclaim_is_ineligible(self) -> None:
        window = "2026-08-10T03:00:00Z/2026-08-10T03:15:00Z"
        text = brief(
            window,
            ["The package age remains at 12 minutes."],
            "The root cause is definitely a failed publishing worker.",
            "No unknowns remain.",
            "Restart the publishing worker.",
            "Synthetic editorial coordinator.",
        )
        result = score_brief(
            "AMBIGUOUS_REVIEW_DELAY", text, {("query_prometheus", window)}
        )
        self.assertFalse(result.eligible)
        self.assertEqual(result.total, 0)
        self.assertTrue(result.failures)


if __name__ == "__main__":
    unittest.main()
