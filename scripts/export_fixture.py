from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dailies_guardian.export import (  # noqa: E402
    build_artifact_manifest,
    build_case_index,
    build_loki_payload,
    build_openmetrics,
    canonical_json_bytes,
    shift_fixture,
)
from dailies_guardian.fixture import load_fixture  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export deterministic synthetic telemetry without network calls or credentials."
    )
    parser.add_argument("--fixture", type=Path, default=ROOT / "fixtures" / "telemetry_v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "public")
    parser.add_argument(
        "--anchor",
        help="Shift the first incident to this explicit whole-second UTC value (for example, 2026-08-09T12:00:00Z).",
    )
    args = parser.parse_args()

    fixture = load_fixture(args.fixture)
    if args.anchor:
        fixture = shift_fixture(fixture, args.anchor)
    outputs = {
        "telemetry_v1.openmetrics": build_openmetrics(fixture),
        "loki_push_v1.json": canonical_json_bytes(build_loki_payload(fixture)),
        "case_index_v1.json": canonical_json_bytes(build_case_index(fixture)),
    }
    outputs["artifact_manifest_v1.json"] = canonical_json_bytes(
        build_artifact_manifest(fixture, outputs)
    )
    args.output.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        (args.output / name).write_bytes(content)
        print(f"wrote {name}: {len(content)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
