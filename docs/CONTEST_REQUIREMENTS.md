# Agentic Cinema requirements snapshot

Verified against the official rules on 2026-08-09.

## Mandatory entry

- Deadline: 2026-09-07 2:00 PM Pacific / 5:00 PM Eastern.
- New original project created during the July 27–September 7 contest period.
- Functional production-ready agent or multi-agent network powered by Gemini and
  Google Cloud Agent Builder.
- Exactly one partner track. This project targets Grafana.
- Official Grafana MCP must be actively imported/called at runtime; observability
  alone does not satisfy the partner requirement.
- Hosted web testing URL.
- Public open-source repository with license, all source/assets/instructions,
  and detectable runtime Google Cloud and partner calls.
- Public English YouTube/Vimeo demo no longer than three minutes.
- Devpost description with features, functionality, technology, data sources,
  findings, and learnings.

## AI boundary

The project runtime may use only Google Cloud AI and Grafana's built-in AI.
No other AI model, agent framework, or AI API may be included. The submitted
runtime therefore imports Google ADK and Grafana MCP only.

## Current status

- Local contest-only scaffold: present.
- Read-only Grafana MCP code path: present and verified against a disposable
  local Grafana/Loki stack; contest-cloud verification remains pending.
- Policy/privacy/API evidence: sixty-four tests pass, including public-response
  rejection when citations, required sections, or privacy boundaries fail.
- Reproducible container: passes build and local HTTP health/UI smoke test.
- Google Cloud/Grafana accounts and private credentials: owner gate.
- Synthetic Grafana telemetry and four real read-only MCP tool calls: verified
  locally with digest-pinned containers and an ephemeral Viewer token. Hosted
  contest URL and cloud call capture: pending.
- Public repository and credential-free CI: verified. Live cloud evidence,
  hosted URL, public video, and Devpost submission: pending.

## Results monitoring

- Binding rules: potential winners may be selected/notified on or about
  October 7, with only two business days to respond to a notification attempt.
- Public Devpost schedule: winners announced October 12 at noon Pacific / 3:00
  PM Eastern.

Official sources:

- https://agentic-cinema.devpost.com/rules
- https://agentic-cinema.devpost.com/
- https://github.com/grafana/mcp-grafana
- https://adk.dev/tools-custom/mcp-tools/
