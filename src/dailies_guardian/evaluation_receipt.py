"""Deterministic, credential-free evaluation evidence for the synthetic cases."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .evaluation import score_brief
from .export import canonical_json_bytes
from .fixture import validate_fixture
from .policy import EvidenceCitation


class EvaluationReceiptError(ValueError):
    """Raised when a canonical case cannot produce defensible public evidence."""


CASE_ORDER = (
    "INGEST_BACKLOG",
    "TRANSCODE_SATURATION",
    "AMBIGUOUS_REVIEW_DELAY",
)

CASE_EVIDENCE: dict[str, dict[str, object]] = {
    "INGEST_BACKLOG": {
        "facts": (
            "The ingest queue is rising from 3 to 18 items.",
            "The completion counter is flat for nine minutes before progress resumes.",
            "Three checksum retry events coincide with the stalled completion interval.",
        ),
        "inference": "The correlation supports an ingest-validation bottleneck hypothesis, not a proven root cause.",
        "unknown": "The physical media condition and underlying root cause remain unknown.",
        "action": "Inspect the synthetic ingest validation and retry dashboard slice; make no mutation.",
        "owner": "Synthetic ingest on-call.",
        "decision": "supported_hypothesis",
    },
    "TRANSCODE_SATURATION": {
        "facts": (
            "Active workers equal the worker limit, showing worker saturation during the interval.",
            "Transcode duration grew by more than 3 times from the first sample.",
            "Retry growth coincides with a rising queue backlog.",
        ),
        "inference": "The correlation supports a capacity-saturation hypothesis, not a proven root cause.",
        "unknown": "The underlying worker or codec cause remains unknown.",
        "action": "Investigate one synthetic worker class and its configuration; make no mutation.",
        "owner": "Synthetic transcode on-call.",
        "decision": "supported_hypothesis",
    },
    "AMBIGUOUS_REVIEW_DELAY": {
        "facts": (
            "Package age remains at or below 12 minutes.",
            "Publish success increments during the window.",
            "The only stale status log is outside the requested window.",
        ),
        "inference": "The evidence is inconclusive and does not support a publishing-failure conclusion.",
        "unknown": "The cause of the reported delay cannot be determined from current evidence.",
        "action": "Request a narrower current publish-status query; make no mutation.",
        "owner": "Synthetic editorial coordinator.",
        "decision": "abstain",
    },
}


def _brief(window: str, evidence: dict[str, object]) -> str:
    facts = "\n".join(
        f"- [source: query_prometheus; window: {window}] {fact}"
        for fact in evidence["facts"]  # type: ignore[union-attr]
    )
    return (
        "## Observed facts\n"
        f"{facts}\n\n"
        "## Inferences\n"
        f"- {evidence['inference']}\n\n"
        "## Unknowns\n"
        f"- {evidence['unknown']}\n\n"
        "## Reversible next actions\n"
        f"- {evidence['action']}\n\n"
        "## Escalation owner\n"
        f"- {evidence['owner']}"
    )


def _fixture_sha256(fixture: dict[str, Any]) -> str:
    payload = json.dumps(fixture, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_evaluation_receipt(
    fixture: dict[str, Any],
    *,
    citation_overrides: dict[str, set[EvidenceCitation]] | None = None,
) -> dict[str, object]:
    """Score all canonical synthetic cases and return a minimal public receipt."""

    validate_fixture(fixture)
    cases = {case["id"]: case for case in fixture["cases"]}
    if set(cases) != set(CASE_ORDER):
        raise EvaluationReceiptError("Fixture case set does not match the evaluation contract")

    records: list[dict[str, object]] = []
    for case_id in CASE_ORDER:
        case = cases[case_id]
        evidence = CASE_EVIDENCE[case_id]
        window = f"{case['window']['from']}/{case['window']['to']}"
        brief = _brief(window, evidence)
        citations = (
            citation_overrides.get(case_id, {("query_prometheus", window)})
            if citation_overrides
            else {("query_prometheus", window)}
        )
        result = score_brief(case_id, brief, citations)
        if not result.eligible or result.total < 90:
            detail = "; ".join(result.failures) or f"score {result.total} is below 90"
            raise EvaluationReceiptError(f"{case_id} failed evaluation receipt: {detail}")
        records.append(
            {
                "case_id": case_id,
                "production_id": case["production_id"],
                "expected_outcome": case["expected_outcome"],
                "decision": evidence["decision"],
                "eligible": result.eligible,
                "total": result.total,
                "breakdown": result.breakdown,
                "citation": {"tool": "query_prometheus", "window": window},
                "brief_sha256": hashlib.sha256(brief.encode("utf-8")).hexdigest(),
            }
        )

    return {
        "schema_version": "1.0",
        "artifact": "dailies-guardian-synthetic-evaluation-receipt",
        "fixture_id": fixture["fixture_id"],
        "fixture_sha256": _fixture_sha256(fixture),
        "scorer": "dailies_guardian.evaluation.score_brief",
        "score_scale": 100,
        "cases": records,
    }


def evaluation_receipt_bytes(fixture: dict[str, Any]) -> bytes:
    """Return canonical JSON bytes for a deterministic public receipt."""

    return canonical_json_bytes(build_evaluation_receipt(fixture))
