from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.fspath(ROOT / "src"))

from dailies_guardian.export import (  # noqa: E402
    build_artifact_manifest,
    build_case_index,
    build_loki_payload,
    build_openmetrics,
    shift_fixture,
)
from dailies_guardian.fixture import ALLOWED_LOG_LABELS, load_fixture  # noqa: E402
from dailies_guardian.policy import public_text_is_clean  # noqa: E402


FIXTURE_PATH = ROOT / "fixtures" / "telemetry_v1.json"
SAMPLE_PATTERN = re.compile(
    r'^(?P<name>[a-z_]+)\{(?P<labels>[^}]*)\} (?P<value>-?\d+(?:\.\d+)?) (?P<timestamp>\d+)$'
)


class TelemetryExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture(FIXTURE_PATH)

    def test_openmetrics_export_is_deterministic_and_complete(self) -> None:
        first = build_openmetrics(self.fixture)
        second = build_openmetrics(self.fixture)
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"# EOF\n"))
        self.assertNotIn(b"\r", first)

        sample_lines = [
            line for line in first.decode("utf-8").splitlines() if not line.startswith("#")
        ]
        expected_samples = sum(
            len(metric["samples"])
            for case in self.fixture["cases"]
            for metric in case["metrics"]
        )
        self.assertEqual(len(sample_lines), expected_samples)
        for line in sample_lines:
            match = SAMPLE_PATTERN.fullmatch(line)
            self.assertIsNotNone(match, line)
            self.assertIn('environment="synthetic"', match.group("labels"))
            self.assertGreater(int(match.group("timestamp")), 0)

    def test_loki_payload_matches_official_push_shape(self) -> None:
        payload = build_loki_payload(self.fixture)
        self.assertEqual(set(payload), {"streams"})
        expected_logs = sum(len(case["logs"]) for case in self.fixture["cases"])
        self.assertEqual(sum(len(stream["values"]) for stream in payload["streams"]), expected_logs)

        timestamps: list[int] = []
        for stream in payload["streams"]:
            self.assertTrue(set(stream["stream"]).issubset(ALLOWED_LOG_LABELS))
            self.assertEqual(stream["stream"]["environment"], "synthetic")
            for timestamp, line in stream["values"]:
                self.assertRegex(timestamp, r"^\d{19}$")
                timestamps.append(int(timestamp))
                event = json.loads(line)
                self.assertEqual(set(event), {"level", "event", "message"})
        self.assertEqual(timestamps, sorted(timestamps))

    def test_case_index_contains_no_raw_telemetry(self) -> None:
        index = build_case_index(self.fixture)
        self.assertEqual(index["fixture_id"], "dailies-guardian-synthetic-v1")
        self.assertEqual(len(index["cases"]), 3)
        for case in index["cases"]:
            self.assertEqual(
                set(case),
                {
                    "id",
                    "production_id",
                    "window",
                    "question",
                    "expected_outcome",
                    "expected_owner",
                    "expected_action",
                },
            )

    def test_all_exports_remain_public_and_synthetic_only(self) -> None:
        rendered = "\n".join(
            (
                build_openmetrics(self.fixture).decode("utf-8"),
                json.dumps(build_loki_payload(self.fixture), sort_keys=True),
                json.dumps(build_case_index(self.fixture), sort_keys=True),
            )
        )
        # Wire timestamps are intentionally 10/19 digit epochs, which resemble
        # the generic phone-number detector after punctuation is ignored.
        privacy_projection = re.sub(r"\b\d{10,19}\b", "<timestamp>", rendered)
        self.assertTrue(public_text_is_clean(privacy_projection))
        self.assertNotIn("password", rendered.casefold())
        self.assertNotIn("token", rendered.casefold())
        self.assertNotIn("credential", rendered.casefold())

    def test_epoch_conversion_is_exact_to_fixture_seconds(self) -> None:
        payload = build_loki_payload(self.fixture)
        first_timestamp = payload["streams"][0]["values"][0][0]
        expected = datetime.fromisoformat("2026-08-10T01:06:00+00:00")
        self.assertEqual(first_timestamp, str(int(expected.timestamp()) * 1_000_000_000))

    def test_manifest_pins_fixture_and_every_export_hash(self) -> None:
        outputs = {
            "telemetry_v1.openmetrics": build_openmetrics(self.fixture),
            "loki_push_v1.json": json.dumps(
                build_loki_payload(self.fixture), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            + b"\n",
            "case_index_v1.json": json.dumps(
                build_case_index(self.fixture), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            + b"\n",
        }
        manifest = build_artifact_manifest(self.fixture, outputs)
        self.assertEqual(
            manifest["fixture_sha256"],
            "4413623d91acb49d926acc8b28f0e25fea28677c5e9a5acd82b5713bdef4817c",
        )
        self.assertEqual(set(manifest["artifacts"]), set(outputs))
        for name, content in outputs.items():
            self.assertEqual(manifest["artifacts"][name]["bytes"], len(content))
            self.assertRegex(manifest["artifacts"][name]["sha256"], r"^[0-9a-f]{64}$")

    def test_explicit_anchor_shifts_every_timestamp_without_mutating_source(self) -> None:
        source_snapshot = json.dumps(self.fixture, sort_keys=True)
        shifted = shift_fixture(self.fixture, "2026-08-09T11:30:00Z")

        self.assertEqual(
            shifted["cases"][0]["window"]["from"],
            "2026-08-09T11:30:00Z",
        )
        self.assertEqual(
            shifted["cases"][0]["metrics"][0]["samples"][0][0],
            "2026-08-09T11:30:00Z",
        )
        self.assertEqual(
            shifted["cases"][2]["window"]["from"],
            "2026-08-09T13:30:00Z",
        )
        self.assertEqual(
            shifted["cases"][2]["logs"][0]["ts"],
            "2026-08-09T13:15:00Z",
        )
        self.assertEqual(json.dumps(self.fixture, sort_keys=True), source_snapshot)
        self.assertNotEqual(shifted, self.fixture)

    def test_shifted_fixture_remains_valid_and_exports_current_payload(self) -> None:
        shifted = shift_fixture(self.fixture, "2026-08-09T11:30:00Z")
        payload = build_loki_payload(shifted)
        first = payload["streams"][0]["values"][0][0]
        expected = datetime.fromisoformat("2026-08-09T11:36:00+00:00")
        self.assertEqual(first, str(int(expected.timestamp()) * 1_000_000_000))

    def test_anchor_requires_absolute_utc_seconds(self) -> None:
        for invalid in ("2026-08-09 11:30", "2026-08-09T11:30:00+00:00", "now"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    shift_fixture(self.fixture, invalid)


if __name__ == "__main__":
    unittest.main()
