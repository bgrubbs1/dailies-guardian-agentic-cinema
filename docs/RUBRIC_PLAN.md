# Equal-weight rubric plan

## Technological implementation

- Real Google ADK agent using Gemini on Google Cloud.
- Official `grafana/mcp-grafana` subprocess imported and called at runtime.
- Read-only least privilege, narrow tools, explicit failure behavior.
- Fail-closed response validation requires all evidence sections and a
  source/tool plus UTC time window on every observed-fact bullet.
- Reproducible synthetic incident fixtures and captured tool-call evidence.

## Design

- One-screen incident question to evidence brief.
- Fact / inference / unknown / next-action separation.
- Clear tool/time-window citations and visible read-only boundary.
- Responsive, original interface with no third-party media or marks.

## Potential impact

- Prevent a late or missing editorial review package from wasting a scheduled
  review session.
- Reduce dashboard hopping and unsupported root-cause guesses.
- Demonstrate time-to-first-supported-hypothesis and evidence coverage on a
  fixed synthetic incident suite; do not invent production outcomes.

## Quality of idea

- Entertainment-specific dailies/post-production failure modes.
- Grafana is the decision evidence plane, not decorative telemetry.
- Gemini must abstain when MCP evidence is missing or contradictory.
- Original synthetic incident narrative and original UI assets only.

No win probability will be assigned until live integration, full rubric audit,
and field-quality evidence exist.
