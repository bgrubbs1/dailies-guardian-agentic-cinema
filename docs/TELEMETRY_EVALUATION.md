# Synthetic telemetry and evaluation

This project checks in one deterministic, fictional fixture and exports it in
formats that can be inspected before any cloud account exists. The exporter
makes no network calls, reads no credentials, and does not claim that telemetry
has been uploaded to Grafana Cloud.

Run:

```powershell
python scripts/export_fixture.py
```

The generated `artifacts/public` directory contains:

- `telemetry_v1.openmetrics`: UTF-8 OpenMetrics 1.0 text with Unix-epoch-second
  timestamps and the required final `# EOF` marker;
- `loki_push_v1.json`: the documented `/loki/api/v1/push` JSON shape, with
  nanosecond epoch timestamps encoded as strings;
- `case_index_v1.json`: case metadata without raw metric or log records; and
- `artifact_manifest_v1.json`: the canonical fixture SHA-256 plus byte count
  and SHA-256 for each generated seed artifact.

Historical timestamps are intentional here: this is a reproducible incident
fixture, not a live process exporter. The OpenMetrics specification permits
timestamps but recommends that live/raw exporters normally let the ingestor
assign them. The Loki payload contains no URL, tenant, authorization header, or
token.

For a disposable local integration check, run:

```powershell
powershell -File scripts/smoke_loki.ps1
```

The script shifts the same fixture to an explicit recent UTC anchor, starts a
digest-pinned Loki 3.5.1 container on a random loopback-only port, pushes the
official JSON body, and requires a query to return all seven logs in exactly
three synthetic streams. It stops and removes the container in `finally`,
leaves the generated evidence in the printed temporary directory, and never
reads a cloud URL, tenant, token, or credential.

For the full local partner-path proof, run:

```powershell
powershell -File scripts/smoke_grafana_mcp.ps1
```

This provisions the checked-in synthetic Loki datasource and three-panel
dashboard in a digest-pinned, loopback-only Grafana container. It creates a
Viewer service-account token only inside that disposable instance, then runs
the reviewed application image's source-pinned `mcp-grafana` v1.0.0 binary in
`--disable-write` mode. The smoke client must successfully call exactly four
read tools and observe all three fictional production IDs. The output summary
contains no token and is saved beside the temporary telemetry artifacts; all
containers and the private Docker network are removed in `finally`.

Primary format references:

- OpenMetrics specification: <https://github.com/prometheus/OpenMetrics/blob/main/specification/OpenMetrics.md>
- Grafana Loki HTTP API: <https://grafana.com/docs/loki/latest/reference/loki-http-api/#ingest-logs>

## Evaluation contract

`dailies_guardian.evaluation.score_brief` returns a deterministic 100-point
audit result:

| Criterion | Points | Required evidence |
| --- | ---: | --- |
| Evidence contract | 40 | Five ordered sections and every observed fact tied to an actually successful read-only Grafana query plus exact UTC window |
| Case evidence | 30 | Three independent, case-specific signals found in observed facts, not merely repeated under unknowns |
| Calibration | 20 | Correlation/hypothesis language for supported cases; explicit abstention for the ambiguous case; no hard causal overclaim |
| Reversible action | 10 | The fixture's read-only next action and fictional escalation owner |

The scorer is an audit aid, not a claim that the language model will always
produce a perfect answer. Contract violations and the ambiguous case's causal
overclaim return an ineligible zero. Missing signals reduce the score even when
the prose is polished.
