"""Validation for the checked-in, synthetic-only Grafana seed fixture."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import math
from pathlib import Path
from typing import Any

from .policy import SYNTHETIC_PRODUCTION_IDS, public_text_is_clean


ALLOWED_METRICS = frozenset(
    {
        "dailies_ingest_queue_depth",
        "dailies_ingest_completed_total",
        "dailies_transcode_active_workers",
        "dailies_transcode_worker_limit",
        "dailies_transcode_duration_seconds",
        "dailies_transcode_retry_total",
        "dailies_review_package_age_minutes",
        "dailies_review_publish_success_total",
    }
)
COUNTER_METRICS = frozenset(
    {
        "dailies_ingest_completed_total",
        "dailies_transcode_retry_total",
        "dailies_review_publish_success_total",
    }
)
ALLOWED_LOG_LABELS = frozenset({"production", "stage", "component", "environment"})


def parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("fixture timestamps must be absolute UTC strings ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"invalid fixture timestamp: {value}") from exc
    return parsed


def load_fixture(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_fixture(data)
    return data


def validate_fixture(data: object) -> None:
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise ValueError("fixture schema_version must be 1.0")
    if data.get("fixture_id") != "dailies-guardian-synthetic-v1":
        raise ValueError("unexpected fixture identifier")
    parse_utc(data.get("generated_at"))
    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) != 3:
        raise ValueError("fixture must contain exactly three cases")
    if {case.get("production_id") for case in cases if isinstance(case, dict)} != set(
        SYNTHETIC_PRODUCTION_IDS
    ):
        raise ValueError("fixture production IDs must exactly match the public synthetic allowlist")
    case_ids: set[str] = set()
    windows: set[tuple[datetime, datetime]] = set()
    for case in cases:
        _validate_case(case, case_ids, windows)


def _validate_case(
    case: object,
    case_ids: set[str],
    windows: set[tuple[datetime, datetime]],
) -> None:
    if not isinstance(case, dict):
        raise ValueError("every fixture case must be an object")
    case_id = case.get("id")
    if not isinstance(case_id, str) or case_id in case_ids:
        raise ValueError("fixture case IDs must be unique nonempty strings")
    case_ids.add(case_id)
    production_id = case.get("production_id")
    if production_id not in SYNTHETIC_PRODUCTION_IDS:
        raise ValueError("case has an unknown synthetic production")
    if case.get("expected_outcome") not in {"supported_hypothesis", "abstain_or_inconclusive"}:
        raise ValueError("case has an unsupported expected outcome")
    window = case.get("window")
    if not isinstance(window, dict):
        raise ValueError("case window is required")
    start, end = parse_utc(window.get("from")), parse_utc(window.get("to"))
    if end - start != timedelta(minutes=15) or (start, end) in windows:
        raise ValueError("case windows must be unique, ordered 15-minute intervals")
    windows.add((start, end))
    metrics = case.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("each case needs metric evidence")
    for metric in metrics:
        _validate_metric(metric, production_id, start, end)
    logs = case.get("logs")
    if not isinstance(logs, list):
        raise ValueError("case logs must be a list")
    for log in logs:
        _validate_log(log, production_id, start, end, case_id)
    alerts = case.get("alerts")
    if not isinstance(alerts, list):
        raise ValueError("case alerts must be a list")
    for alert in alerts:
        if not isinstance(alert, dict) or alert.get("state") != "firing":
            raise ValueError("fixture alerts must be explicit firing alerts")
        starts_at = parse_utc(alert.get("starts_at"))
        if not start <= starts_at <= end:
            raise ValueError("alert timestamp is outside its case window")
    public_projection = json.dumps(case, sort_keys=True)
    if not public_text_is_clean(public_projection):
        raise ValueError("fixture contains private or credential-like data")


def _validate_metric(
    metric: object,
    production_id: str,
    start: datetime,
    end: datetime,
) -> None:
    if not isinstance(metric, dict) or metric.get("name") not in ALLOWED_METRICS:
        raise ValueError("fixture metric is not in the public allowlist")
    labels = metric.get("labels")
    if not isinstance(labels, dict) or not labels:
        raise ValueError("metric labels must be a nonempty object")
    if labels.get("production") != production_id or labels.get("environment") != "synthetic":
        raise ValueError("metric labels must identify the case and synthetic environment")
    samples = metric.get("samples")
    if not isinstance(samples, list) or len(samples) != 16:
        raise ValueError("every metric must contain 16 inclusive one-minute samples")
    timestamps: list[datetime] = []
    values: list[float] = []
    for sample in samples:
        if not isinstance(sample, list) or len(sample) != 2:
            raise ValueError("metric samples must be [timestamp, value] pairs")
        timestamp = parse_utc(sample[0])
        value = sample[1]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("metric values must be finite numbers")
        timestamps.append(timestamp)
        values.append(float(value))
    expected = [start + timedelta(minutes=index) for index in range(16)]
    if timestamps != expected or timestamps[-1] != end:
        raise ValueError("metric timestamps must be ordered one-minute samples inside the window")
    if metric["name"] in COUNTER_METRICS and values != sorted(values):
        raise ValueError("counter metrics must be nondecreasing")


def _validate_log(
    log: object,
    production_id: str,
    start: datetime,
    end: datetime,
    case_id: str,
) -> None:
    if not isinstance(log, dict):
        raise ValueError("fixture log must be an object")
    labels = log.get("labels")
    if not isinstance(labels, dict) or set(labels) - ALLOWED_LOG_LABELS:
        raise ValueError("fixture log uses a non-public label")
    if labels.get("production") != production_id or labels.get("environment") != "synthetic":
        raise ValueError("log labels must identify the case and synthetic environment")
    timestamp = parse_utc(log.get("ts"))
    is_named_stale_record = (
        case_id == "AMBIGUOUS_REVIEW_DELAY"
        and log.get("event") == "stale_status_snapshot"
        and timestamp < start
    )
    if not (start <= timestamp <= end or is_named_stale_record):
        raise ValueError("log timestamp is outside its case window")
