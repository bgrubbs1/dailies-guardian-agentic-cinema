from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dailies_guardian.evaluation_receipt import evaluation_receipt_bytes  # noqa: E402
from dailies_guardian.fixture import load_fixture  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export deterministic synthetic evaluation evidence without network calls or credentials."
    )
    parser.add_argument(
        "--fixture", type=Path, default=ROOT / "fixtures" / "telemetry_v1.json"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "public" / "evaluation_receipt_v1.json",
    )
    args = parser.parse_args()

    content = evaluation_receipt_bytes(load_fixture(args.fixture))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(content)
    print(f"wrote {args.output.name}: {len(content)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
