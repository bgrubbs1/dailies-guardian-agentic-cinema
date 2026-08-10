from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

from fastapi import HTTPException


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from dailies_guardian.service import (  # noqa: E402
    AnalyzeBody,
    FIXTURE_PATH,
    STATIC_INDEX,
    analyze,
    app,
    fixture_cases,
)


VALID_BRIEF = """
## Observed facts
- [source: query_loki_logs; window: 2026-08-09T01:00:00Z/2026-08-09T01:15:00Z] Synthetic transcode workers reported retryable timeouts.

## Inferences
- The retries may explain the queue growth, but they do not yet prove a root cause.

## Unknowns
- The corresponding worker saturation metric has not been retrieved.

## Reversible next actions
- Query worker saturation for the same interval before changing any job.

## Escalation owner
- Fictional dailies on-call operator.
"""


class _SessionService:
    async def create_session(self, **_: str) -> None:
        return None


class _Event:
    def __init__(
        self,
        text: str | None = None,
        calls: tuple[object, ...] = (),
        responses: tuple[object, ...] = (),
    ) -> None:
        self.content = (
            type("Content", (), {"parts": [type("Part", (), {"text": text})()]})()
            if text is not None
            else None
        )
        self._calls = list(calls)
        self._responses = list(responses)

    def is_final_response(self) -> bool:
        return self.content is not None

    def get_function_calls(self) -> list[object]:
        return self._calls

    def get_function_responses(self) -> list[object]:
        return self._responses


class _Runner:
    def __init__(self, *events: _Event) -> None:
        self.events = events
        self.started = False

    async def run_async(self, **_: object):
        self.started = True
        for event in self.events:
            yield event


def _successful_loki_events(text: str) -> tuple[_Event, ...]:
    call = SimpleNamespace(
        id="call-1",
        name="query_loki_logs",
        args={
            "datasourceUid": "synthetic-loki",
            "logql": '{environment="synthetic"}',
            "startRfc3339": "2026-08-09T01:00:00Z",
            "endRfc3339": "2026-08-09T01:15:00Z",
        },
    )
    response = SimpleNamespace(
        id="call-1",
        name="query_loki_logs",
        response={"data": [{"line": "Synthetic timeout retry."}]},
    )
    return (_Event(calls=(call,)), _Event(responses=(response,)), _Event(text=text))


class AnalyzeContractTests(unittest.IsolatedAsyncioTestCase):
    def test_runtime_assets_resolve_outside_the_launch_directory(self) -> None:
        self.assertEqual(FIXTURE_PATH, Path(ROOT, "fixtures", "telemetry_v1.json"))
        self.assertEqual(STATIC_INDEX, Path(ROOT, "static", "index.html"))

    async def asyncSetUp(self) -> None:
        app.state.session_service = _SessionService()

    async def test_valid_generated_brief_is_returned(self) -> None:
        app.state.runner = _Runner(*_successful_loki_events(VALID_BRIEF))
        result = await analyze(
            AnalyzeBody(
                production_id="ORBITAL_DAY_7",
                question="Why is the synthetic editorial package late tonight?",
            )
        )
        self.assertEqual(result.brief, VALID_BRIEF.strip())

    async def test_fixture_catalog_exposes_safe_case_metadata_only(self) -> None:
        catalog = await fixture_cases()
        self.assertEqual(catalog["fixture_id"], "dailies-guardian-synthetic-v1")
        self.assertEqual(len(catalog["cases"]), 3)
        self.assertEqual(
            {case["production_id"] for case in catalog["cases"]},
            {"ORBITAL_DAY_7", "HARBOR_LIGHT_EP2", "PAPER_MOON_TRAILER"},
        )
        self.assertEqual(
            {case["expected_outcome"] for case in catalog["cases"]},
            {"supported_hypothesis", "abstain_or_inconclusive"},
        )
        for case in catalog["cases"]:
            self.assertEqual(set(case["window"]), {"from", "to"})
            self.assertNotIn("metrics", case)
            self.assertNotIn("logs", case)
            self.assertNotIn("alerts", case)

    async def test_invalid_generated_brief_is_not_exposed(self) -> None:
        app.state.runner = _Runner(_Event(text="The root cause is definitely a failed worker."))
        with self.assertRaises(HTTPException) as raised:
            await analyze(
                AnalyzeBody(
                    production_id="ORBITAL_DAY_7",
                    question="Why is the synthetic editorial package late tonight?",
                )
            )
        self.assertEqual(raised.exception.status_code, 502)
        self.assertNotIn("failed worker", str(raised.exception.detail))

    async def test_well_formed_fabricated_citation_is_not_exposed(self) -> None:
        fabricated = VALID_BRIEF.replace("query_loki_logs", "invented_source")
        app.state.runner = _Runner(*_successful_loki_events(fabricated))
        with self.assertRaises(HTTPException) as raised:
            await analyze(
                AnalyzeBody(
                    production_id="ORBITAL_DAY_7",
                    question="Why is the synthetic editorial package late tonight?",
                )
            )
        self.assertEqual(raised.exception.status_code, 502)

    async def test_no_tool_final_response_is_not_exposed(self) -> None:
        app.state.runner = _Runner(_Event(text=VALID_BRIEF))
        with self.assertRaises(HTTPException) as raised:
            await analyze(
                AnalyzeBody(
                    production_id="ORBITAL_DAY_7",
                    question="Why is the synthetic editorial package late tonight?",
                )
            )
        self.assertEqual(raised.exception.status_code, 502)

    async def test_disallowed_tool_call_fails_closed(self) -> None:
        call = SimpleNamespace(id="call-2", name="update_dashboard", args={})
        app.state.runner = _Runner(_Event(calls=(call,)), _Event(text=VALID_BRIEF))
        with self.assertRaises(HTTPException) as raised:
            await analyze(
                AnalyzeBody(
                    production_id="ORBITAL_DAY_7",
                    question="Why is the synthetic editorial package late tonight?",
                )
            )
        self.assertEqual(raised.exception.status_code, 502)

    async def test_failed_tool_response_does_not_support_a_citation(self) -> None:
        events = list(_successful_loki_events(VALID_BRIEF))
        events[1] = _Event(
            responses=(
                SimpleNamespace(
                    id="call-1",
                    name="query_loki_logs",
                    response={"isError": True, "error": "synthetic failure"},
                ),
            )
        )
        app.state.runner = _Runner(*events)
        with self.assertRaises(HTTPException) as raised:
            await analyze(
                AnalyzeBody(
                    production_id="ORBITAL_DAY_7",
                    question="Why is the synthetic editorial package late tonight?",
                )
            )
        self.assertEqual(raised.exception.status_code, 502)
        self.assertNotIn("synthetic failure", str(raised.exception.detail))

    async def test_relative_query_window_fails_closed(self) -> None:
        call = SimpleNamespace(
            id="call-relative",
            name="query_prometheus",
            args={"startTime": "now-15m", "endTime": "now"},
        )
        app.state.runner = _Runner(_Event(calls=(call,)), _Event(text=VALID_BRIEF))
        with self.assertRaises(HTTPException) as raised:
            await analyze(
                AnalyzeBody(
                    production_id="ORBITAL_DAY_7",
                    question="Why is the synthetic editorial package late tonight?",
                )
            )
        self.assertEqual(raised.exception.status_code, 502)

    async def test_ambiguous_fixture_causal_claim_fails_closed(self) -> None:
        causal = VALID_BRIEF.replace(
            "The retries may explain the queue growth, but they do not yet prove a root cause.",
            "The root cause is definitely a failed publishing worker.",
        )
        app.state.runner = _Runner(*_successful_loki_events(causal))
        with self.assertRaises(HTTPException) as raised:
            await analyze(
                AnalyzeBody(
                    production_id="PAPER_MOON_TRAILER",
                    question="Is there evidence that the synthetic review package is late?",
                )
            )
        self.assertEqual(raised.exception.status_code, 502)

    async def test_private_input_is_rejected_before_runner_starts(self) -> None:
        runner = _Runner(*_successful_loki_events(VALID_BRIEF))
        app.state.runner = runner
        with self.assertRaises(HTTPException) as raised:
            await analyze(
                AnalyzeBody(
                    production_id="ORBITAL_DAY_7",
                    question=f"Email {'person'}{'@'}{'example'}{'.com'} about this synthetic delay",
                )
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertFalse(runner.started)


if __name__ == "__main__":
    unittest.main()
