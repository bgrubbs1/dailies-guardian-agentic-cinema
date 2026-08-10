"""Small hosted web/API surface for the contest demonstration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from .agent import build_agent
from .config import Settings
from .fixture import load_fixture
from .policy import (
    EvidenceContractError,
    IncidentRequest,
    READ_ONLY_GRAFANA_TOOLS,
    SYNTHETIC_PRODUCTION_IDS,
    validate_evidence_brief,
    validate_fixture_outcome,
)


APP_NAME = "dailies_guardian"
USER_ID = "public_demo"
SOURCE_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _runtime_asset_path(environment_name: str, relative_path: str) -> Path:
    """Resolve an explicit override, container asset, or source-checkout asset."""

    override = os.getenv(environment_name)
    if override:
        return Path(override).expanduser().resolve()
    candidates = (Path.cwd() / relative_path, SOURCE_PROJECT_ROOT / relative_path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    # Preserve a deterministic failure path for the API's existing fail-closed error.
    return candidates[0].resolve()


STATIC_INDEX = _runtime_asset_path("DAILIES_STATIC_INDEX", "static/index.html")
FIXTURE_PATH = _runtime_asset_path("DAILIES_FIXTURE_PATH", "fixtures/telemetry_v1.json")


class AnalyzeBody(BaseModel):
    production_id: str
    question: str = Field(min_length=8, max_length=800)


class AnalyzeResult(BaseModel):
    production_id: str
    brief: str
    mode: str = "gemini-adk-plus-grafana-mcp-read-only"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    settings.assert_runtime_ready()
    session_service = InMemorySessionService()
    app.state.session_service = session_service
    app.state.runner = Runner(
        agent=build_agent(settings),
        app_name=APP_NAME,
        session_service=session_service,
    )
    yield


app = FastAPI(
    title="Dailies Guardian",
    version="0.1.0",
    lifespan=lifespan,
)


def _absolute_utc_timestamp(value: object) -> str | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        return None
    return value


def _query_citation(name: str, args: object) -> tuple[str, str] | None:
    if not isinstance(args, dict):
        return None
    fields = {
        "query_prometheus": ("startTime", "endTime"),
        "query_loki_logs": ("startRfc3339", "endRfc3339"),
    }.get(name)
    if fields is None:
        return None
    start = _absolute_utc_timestamp(args.get(fields[0]))
    end = _absolute_utc_timestamp(args.get(fields[1]))
    if start is None or end is None or start >= end:
        return None
    return (name, f"{start}/{end}")


def _response_succeeded(payload: object) -> bool:
    if payload is None:
        return False
    if isinstance(payload, dict):
        if payload.get("isError") is True:
            return False
        error = payload.get("error")
        if error not in (None, "", False, [], {}):
            return False
    return True


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_INDEX)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "mode": "read-only"}


@app.get("/api/productions")
async def productions() -> dict[str, list[str]]:
    return {"productions": sorted(SYNTHETIC_PRODUCTION_IDS)}


@app.get("/api/fixture-cases")
async def fixture_cases() -> dict[str, object]:
    """Expose presentation metadata, never raw telemetry or canned conclusions."""

    try:
        fixture = load_fixture(FIXTURE_PATH)
    except (OSError, UnicodeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Synthetic fixture catalog is unavailable") from exc
    cases = [
        {
            "id": case["id"],
            "production_id": case["production_id"],
            "window": dict(case["window"]),
            "question": case["question"],
            "expected_outcome": case["expected_outcome"],
            "evidence_counts": {
                "metrics": len(case["metrics"]),
                "logs": len(case["logs"]),
                "alerts": len(case["alerts"]),
            },
        }
        for case in fixture["cases"]
    ]
    return {"fixture_id": fixture["fixture_id"], "cases": cases}


@app.post("/api/analyze", response_model=AnalyzeResult)
async def analyze(body: AnalyzeBody) -> AnalyzeResult:
    request = IncidentRequest(body.production_id, body.question)
    try:
        request.validate()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_id = uuid4().hex
    await app.state.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id,
    )
    prompt = (
        f"Synthetic production: {request.production_id}\n"
        f"Incident question: {request.question}\n"
        "Use the required Grafana evidence sequence and return the incident brief."
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    final_text = ""
    pending_calls: dict[str, tuple[str, str] | None] = {}
    observed_citations: set[tuple[str, str]] = set()
    tool_contract_failed = False
    async for event in app.state.runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=message,
    ):
        for call in event.get_function_calls():
            call_id = getattr(call, "id", None)
            name = getattr(call, "name", "")
            if not isinstance(call_id, str) or not call_id or name not in READ_ONLY_GRAFANA_TOOLS:
                tool_contract_failed = True
                continue
            citation = _query_citation(name, getattr(call, "args", None))
            if name in {"query_prometheus", "query_loki_logs"} and citation is None:
                tool_contract_failed = True
            pending_calls[call_id] = citation

        for response in event.get_function_responses():
            response_id = getattr(response, "id", None)
            name = getattr(response, "name", "")
            if not isinstance(response_id, str) or name not in READ_ONLY_GRAFANA_TOOLS:
                tool_contract_failed = True
                continue
            citation = pending_calls.pop(response_id, None)
            if citation is not None and _response_succeeded(getattr(response, "response", None)):
                observed_citations.add(citation)

        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(
                part.text or "" for part in event.content.parts if hasattr(part, "text")
            ).strip()

    if tool_contract_failed or not final_text:
        raise HTTPException(
            status_code=502,
            detail="Gemini/Grafana produced no final evidence brief",
        )
    try:
        public_brief = validate_evidence_brief(final_text, observed_citations)
        validate_fixture_outcome(request.production_id, public_brief)
    except EvidenceContractError as exc:
        raise HTTPException(
            status_code=502,
            detail="Generated brief did not satisfy the public evidence contract",
        ) from exc
    return AnalyzeResult(production_id=request.production_id, brief=public_brief)
