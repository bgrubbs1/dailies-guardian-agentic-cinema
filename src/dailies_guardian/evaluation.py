"""Transparent, deterministic scoring for synthetic fixture evidence briefs."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .policy import (
    EvidenceCitation,
    EvidenceContractError,
    REQUIRED_BRIEF_SECTIONS,
    validate_evidence_brief,
    validate_fixture_outcome,
)


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    eligible: bool
    total: int
    breakdown: dict[str, int]
    failures: tuple[str, ...]


CASE_RULES: dict[str, dict[str, object]] = {
    "INGEST_BACKLOG": {
        "production_id": "ORBITAL_DAY_7",
        "signals": (
            (("queue",), ("rising", "increas", "3 to 18")),
            (("completion",), ("flat", "stall", "no progress")),
            (("checksum",), ("retry",)),
        ),
        "owner": "synthetic ingest on-call",
        "action": ("inspect", "no mutation"),
    },
    "TRANSCODE_SATURATION": {
        "production_id": "HARBOR_LIGHT_EP2",
        "signals": (
            (("worker",), ("limit", "saturat")),
            (("duration",), ("grew", "grow", "increas", "3")),
            (("retry",), ("queue", "backlog")),
        ),
        "owner": "synthetic transcode on-call",
        "action": ("investigate", "no mutation"),
    },
    "AMBIGUOUS_REVIEW_DELAY": {
        "production_id": "PAPER_MOON_TRAILER",
        "signals": (
            (("package age",), ("12", "below")),
            (("publish",), ("success", "increment")),
            (("stale",), ("outside", "out-of-window")),
        ),
        "owner": "synthetic editorial coordinator",
        "action": ("request", "query"),
    },
}


def _section(text: str, name: str) -> str:
    names = "|".join(re.escape(section) for section in REQUIRED_BRIEF_SECTIONS)
    match = re.search(
        rf"^##\s+{re.escape(name)}\s*$\n(?P<body>.*?)(?=^##\s+(?:{names})\s*$|\Z)",
        text,
        re.I | re.M | re.S,
    )
    return match.group("body").strip() if match else ""


def _case_evidence_score(observed: str, rules: dict[str, object]) -> int:
    lowered = observed.casefold()
    score = 0
    for required, alternatives in rules["signals"]:  # type: ignore[assignment]
        if all(token in lowered for token in required) and any(
            token in lowered for token in alternatives
        ):
            score += 10
    return score


def _calibration_score(text: str, case_id: str) -> int:
    lowered = text.casefold()
    hard_claims = ("root cause is", "definitely", "proves that")
    if any(claim in lowered for claim in hard_claims):
        return 0
    uncertainty = (
        "inconclusive",
        "insufficient evidence",
        "cannot determine",
        "does not support",
        "unknown",
        "not a proven root cause",
    )
    first = 10 if any(marker in lowered for marker in uncertainty) else 0
    if case_id == "AMBIGUOUS_REVIEW_DELAY":
        second = 10 if any(
            marker in lowered
            for marker in ("inconclusive", "cannot determine", "does not support")
        ) else 0
    else:
        second = 10 if any(
            marker in lowered for marker in ("supports", "correlation", "hypothesis", "may")
        ) else 0
    return first + second


def _action_score(text: str, rules: dict[str, object]) -> int:
    lowered = text.casefold()
    owner = str(rules["owner"])
    action_terms = rules["action"]  # type: ignore[assignment]
    owner_points = 5 if owner in lowered else 0
    action_points = 5 if all(term in lowered for term in action_terms) else 0
    return owner_points + action_points


def score_brief(
    case_id: str,
    text: str,
    observed_citations: set[EvidenceCitation] | frozenset[EvidenceCitation],
) -> EvaluationResult:
    """Score a public brief against contract, evidence, calibration, and action criteria."""

    rules = CASE_RULES.get(case_id)
    if rules is None:
        return EvaluationResult(case_id, False, 0, {}, ("Unknown fixture case",))
    try:
        normalized = validate_evidence_brief(text, observed_citations)
        validate_fixture_outcome(str(rules["production_id"]), normalized)
    except EvidenceContractError as exc:
        return EvaluationResult(case_id, False, 0, {}, (str(exc),))

    breakdown = {
        "evidence_contract": 40,
        "case_evidence": _case_evidence_score(_section(normalized, "Observed facts"), rules),
        "calibration": _calibration_score(normalized, case_id),
        "reversible_action": _action_score(normalized, rules),
    }
    return EvaluationResult(case_id, True, sum(breakdown.values()), breakdown, ())
