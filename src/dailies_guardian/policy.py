"""Safety policy and evidence contract independent of cloud libraries."""

from __future__ import annotations

from dataclasses import dataclass
import re


ALLOWED_ACTION_CLASSES = frozenset({"observe", "summarize", "recommend", "escalate"})
READ_ONLY_GRAFANA_TOOLS = (
    "list_datasources",
    "search_dashboards",
    "get_dashboard_by_uid",
    "query_prometheus",
    "query_loki_logs",
)
FORBIDDEN_PUBLIC_MARKERS = (
    "employer confidential",
    "customer confidential",
    "private household",
    "client-confidential",
    "client confidential",
    "internal only",
    "do not share",
    "proprietary",
)
SYNTHETIC_PRODUCTION_IDS = frozenset(
    {"ORBITAL_DAY_7", "HARBOR_LIGHT_EP2", "PAPER_MOON_TRAILER"}
)
REQUIRED_BRIEF_SECTIONS = (
    "Observed facts",
    "Inferences",
    "Unknowns",
    "Reversible next actions",
    "Escalation owner",
)
PRIVATE_OUTPUT_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"\b(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}\b"),
    re.compile(r"\b(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b169\.254\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b(?:AIza|ghp_|github_pat_)[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bglsa_[A-Za-z0-9_-]{12,}\b", re.I),
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}\b", re.I),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]+)?\b"),
    re.compile(r"\b(?:localhost|::1|fe80:[0-9a-f:]*)\b", re.I),
    re.compile(r"\b(?:fc|fd)[0-9a-f]{2}:[0-9a-f:]+\b", re.I),
    re.compile(r"\b(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}\b", re.I),
    re.compile(r"\bhttps?://[^\s<>()]+", re.I),
)
BRIEF_HEADER_PATTERN = re.compile(
    r"^##\s+(Observed facts|Inferences|Unknowns|Reversible next actions|Escalation owner)\s*$",
    re.I | re.M,
)
FACT_CITATION_PATTERN = re.compile(
    r"^\s*-\s+\[source:\s*([a-z0-9_-]+);\s*window:\s*([^\]\r\n]+)\]",
    re.I,
)

EvidenceCitation = tuple[str, str]


class EvidenceContractError(ValueError):
    """Raised when a generated public brief cannot be safely displayed."""


@dataclass(frozen=True)
class IncidentRequest:
    production_id: str
    question: str

    def validate(self) -> None:
        if self.production_id not in SYNTHETIC_PRODUCTION_IDS:
            raise ValueError("Only the published fictional demo productions are allowed")
        normalized = self.question.strip()
        if len(normalized) < 8 or len(normalized) > 800:
            raise ValueError("Question length must be between 8 and 800 characters")
        lowered = normalized.casefold()
        if any(marker in lowered for marker in FORBIDDEN_PUBLIC_MARKERS):
            raise ValueError("Private or credential-like data is not permitted in the demo")
        if not public_text_is_clean(normalized):
            if re.search(r"\b(?:\d[ -]?){10}\b", normalized):
                raise ValueError("Phone-number-like input is not permitted in the demo")
            raise ValueError("Private or credential-like data is not permitted in the demo")


def system_instruction() -> str:
    """Return the invariant instruction used by the Gemini ADK agent."""

    return """
You are Dailies Guardian, an evidence-first incident assistant for fictional
film post-production pipelines. Use Grafana MCP read tools before making any
incident claim. First discover available data sources and relevant dashboards,
then query the narrowest metric or log window that can answer the question.

Every final brief must use exactly these Markdown section headings in order:
## Observed facts, ## Inferences, ## Unknowns,
## Reversible next actions, and ## Escalation owner. Every observed-fact bullet
must begin with `[source: <Grafana tool>; window: <UTC interval>]`. Never claim
a root cause without supporting Grafana evidence. Never invent a query result,
person, production, metric, log, alert, or test. If tools fail or evidence is
insufficient, preserve all five sections, state the unknowns, and stop.

You are read-only. You may observe, summarize, recommend, or escalate. Never
change dashboards, alerts, incidents, infrastructure, access, data, or jobs.
Use only the synthetic production identifiers supplied by the application.
Do not request or reveal private, customer, employer, household, credential,
personal-contact, or real production information.

For each observed-fact citation, use the exact Grafana query tool name and the
exact absolute UTC start/end interval supplied to that successful tool call,
formatted as `<start>/<end>`. Discovery calls without a time window are context,
not observed-fact evidence.
""".strip()


def public_text_is_clean(text: str) -> bool:
    lowered = text.casefold()
    return not any(marker in lowered for marker in FORBIDDEN_PUBLIC_MARKERS) and not any(
        pattern.search(text) for pattern in PRIVATE_OUTPUT_PATTERNS
    )


def validate_evidence_brief(
    text: str,
    observed_citations: set[EvidenceCitation] | frozenset[EvidenceCitation],
) -> str:
    """Validate the generated brief before it is returned to the public UI."""

    normalized = text.strip()
    if len(normalized) < 80 or len(normalized) > 12_000:
        raise EvidenceContractError("Evidence brief length is outside the public contract")
    if not public_text_is_clean(normalized):
        raise EvidenceContractError("Evidence brief contains private or credential-like data")

    matches = list(BRIEF_HEADER_PATTERN.finditer(normalized))
    found = tuple(match.group(1).casefold() for match in matches)
    expected = tuple(section.casefold() for section in REQUIRED_BRIEF_SECTIONS)
    if found != expected:
        missing = next(
            (section for section in REQUIRED_BRIEF_SECTIONS if section.casefold() not in found),
            None,
        )
        if missing:
            raise EvidenceContractError(f"Missing required brief section: {missing}")
        raise EvidenceContractError("Required brief sections are duplicated or out of order")

    section_bodies: dict[str, str] = {}
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        body = normalized[body_start:body_end].strip()
        if not body or not any(line.lstrip().startswith("- ") for line in body.splitlines()):
            raise EvidenceContractError(
                f"Required brief section has no bullet evidence: {match.group(1)}"
            )
        section_bodies[match.group(1).casefold()] = body

    observed_lines = [
        line for line in section_bodies["observed facts"].splitlines() if line.lstrip().startswith("- ")
    ]
    citation_matches = [FACT_CITATION_PATTERN.match(line) for line in observed_lines]
    if not observed_lines or any(match is None for match in citation_matches):
        raise EvidenceContractError(
            "Observed facts must include source and window citations on every bullet"
        )
    if not observed_citations:
        raise EvidenceContractError("No observed successful tool response supports the brief")
    cited = {
        (match.group(1).casefold(), match.group(2).strip())
        for match in citation_matches
        if match is not None
    }
    if any(source not in READ_ONLY_GRAFANA_TOOLS for source, _ in cited):
        raise EvidenceContractError("Citation is not an observed successful tool response")
    normalized_observed = {(source.casefold(), window) for source, window in observed_citations}
    if not cited.issubset(normalized_observed):
        raise EvidenceContractError("Citation is not an observed successful tool response")
    return normalized


def validate_fixture_outcome(production_id: str, text: str) -> None:
    """Fail closed when the fixed abstention fixture is presented as causal proof."""

    if production_id != "PAPER_MOON_TRAILER":
        return
    lowered = text.casefold()
    causal_claims = ("root cause is", "caused by", "definitely", "proves that")
    uncertainty_markers = (
        "inconclusive",
        "insufficient evidence",
        "cannot determine",
        "does not support",
        "unknown",
    )
    if any(claim in lowered for claim in causal_claims) or not any(
        marker in lowered for marker in uncertainty_markers
    ):
        raise EvidenceContractError("The fixed review-delay fixture requires abstention")
