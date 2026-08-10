"""Deterministic, credential-free exports for the synthetic telemetry fixture."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any

from .fixture import COUNTER_METRICS, parse_utc, validate_fixture


def _escape_label(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _number(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    return format(value, ".15g")


def _epoch_seconds(value: object) -> int:
    return int(parse_utc(value).timestamp())


def _epoch_nanoseconds(value: object) -> str:
    return str(_epoch_seconds(value) * 1_000_000_000)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _shift_timestamp(value: object, delta: timedelta) -> str:
    return _format_utc(parse_utc(value) + delta)


def shift_fixture(fixture: dict[str, Any], anchor: str) -> dict[str, Any]:
    """Return a deep-copied fixture with case one starting at an explicit UTC anchor.

    This preserves every relative interval, including the intentionally stale
    log record. No current-clock default exists, so a cloud or local run cannot
    silently produce a non-reproducible artifact.
    """

    validate_fixture(fixture)
    anchor_time = parse_utc(anchor)
    if anchor_time.microsecond:
        raise ValueError("anchor must use whole UTC seconds")
    first_start = parse_utc(fixture["cases"][0]["window"]["from"])
    delta = anchor_time - first_start
    shifted = deepcopy(fixture)
    shifted["generated_at"] = _shift_timestamp(shifted["generated_at"], delta)
    for case in shifted["cases"]:
        case["window"]["from"] = _shift_timestamp(case["window"]["from"], delta)
        case["window"]["to"] = _shift_timestamp(case["window"]["to"], delta)
        for metric in case["metrics"]:
            for sample in metric["samples"]:
                sample[0] = _shift_timestamp(sample[0], delta)
        for log in case["logs"]:
            log["ts"] = _shift_timestamp(log["ts"], delta)
        for alert in case["alerts"]:
            alert["starts_at"] = _shift_timestamp(alert["starts_at"], delta)
    validate_fixture(shifted)
    return shifted


def build_openmetrics(fixture: dict[str, Any]) -> bytes:
    """Render historical samples as a deterministic OpenMetrics 1.0 exposition.

    The fixture intentionally carries timestamps because it is a reproducible
    historical seed, not a live process metrics endpoint.
    """

    validate_fixture(fixture)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in fixture["cases"]:
        for metric in case["metrics"]:
            grouped[metric["name"]].append(metric)

    lines: list[str] = []
    for sample_name in sorted(grouped):
        is_counter = sample_name in COUNTER_METRICS
        family_name = sample_name.removesuffix("_total") if is_counter else sample_name
        lines.append(f"# TYPE {family_name} {'counter' if is_counter else 'gauge'}")
        lines.append(f"# HELP {family_name} Deterministic synthetic dailies fixture series.")
        metrics = sorted(
            grouped[sample_name],
            key=lambda item: tuple(sorted((str(k), str(v)) for k, v in item["labels"].items())),
        )
        for metric in metrics:
            labels = ",".join(
                f'{key}="{_escape_label(value)}"'
                for key, value in sorted(metric["labels"].items())
            )
            for timestamp, value in metric["samples"]:
                lines.append(
                    f"{sample_name}{{{labels}}} {_number(value)} {_epoch_seconds(timestamp)}"
                )
    lines.append("# EOF")
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_loki_payload(fixture: dict[str, Any]) -> dict[str, list[dict[str, object]]]:
    """Build the documented Loki JSON push body without endpoint or credentials."""

    validate_fixture(fixture)
    grouped: dict[tuple[tuple[str, str], ...], list[list[str]]] = defaultdict(list)
    for case in fixture["cases"]:
        for log in case["logs"]:
            labels = tuple(sorted((str(key), str(value)) for key, value in log["labels"].items()))
            line = json.dumps(
                {key: log[key] for key in ("level", "event", "message")},
                sort_keys=True,
                separators=(",", ":"),
            )
            grouped[labels].append([_epoch_nanoseconds(log["ts"]), line])

    streams: list[dict[str, object]] = []
    for labels, values in grouped.items():
        values.sort(key=lambda item: int(item[0]))
        streams.append({"stream": dict(labels), "values": values})
    streams.sort(
        key=lambda stream: (
            int(stream["values"][0][0]),  # type: ignore[index]
            tuple(sorted(stream["stream"].items())),  # type: ignore[union-attr]
        )
    )
    return {"streams": streams}


def build_case_index(fixture: dict[str, Any]) -> dict[str, object]:
    """Return a public metadata index with no raw metric or log records."""

    validate_fixture(fixture)
    public_fields = (
        "id",
        "production_id",
        "window",
        "question",
        "expected_outcome",
        "expected_owner",
        "expected_action",
    )
    return {
        "schema_version": fixture["schema_version"],
        "fixture_id": fixture["fixture_id"],
        "generated_at": fixture["generated_at"],
        "cases": [{field: case[field] for field in public_fields} for case in fixture["cases"]],
    }


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def build_artifact_manifest(
    fixture: dict[str, Any], outputs: dict[str, bytes]
) -> dict[str, object]:
    """Pin the canonical fixture and each generated output by byte count and SHA-256."""

    validate_fixture(fixture)
    fixture_bytes = json.dumps(fixture, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": "1.0",
        "fixture_id": fixture["fixture_id"],
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "artifacts": {
            name: {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            for name, content in sorted(outputs.items())
        },
    }
