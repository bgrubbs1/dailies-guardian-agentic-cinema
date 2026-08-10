# Synthetic telemetry fixture

`telemetry_v1.json` is the deterministic, public-only evidence suite for the
Dailies Guardian demo. It contains no real studio, employer, customer,
household, account, host, IP, contact, credential, file-path, or user data.

The three cases are deliberately different:

1. `INGEST_BACKLOG` supports a narrow ingest-validation bottleneck hypothesis.
2. `TRANSCODE_SATURATION` supports a capacity-saturation correlation.
3. `AMBIGUOUS_REVIEW_DELAY` contains current healthy evidence plus one stale,
   out-of-window log and therefore requires an inconclusive answer.

`dailies_guardian.fixture.validate_fixture` checks the public schema,
allowlists, UTC cadence, finite values, counter monotonicity, log windows, and
privacy boundary. `tests/test_fixture.py` separately checks the scenario
arithmetic and a canonical SHA-256 so accidental fixture drift is visible.

The file is not evidence of a live Grafana deployment. After Bradley creates
contest-only Google Cloud and Grafana accounts and accepts their terms, this
fixture can be loaded into contest-only Prometheus/Loki data sources. Only then
may captured Grafana MCP responses be described as live integration evidence.
