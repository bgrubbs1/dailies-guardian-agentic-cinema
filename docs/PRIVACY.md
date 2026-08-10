# Privacy and provenance boundary

- All production IDs, incidents, metrics, logs, dashboards, screenshots, and
  people in the demo must be fictional and generated for this contest.
- Never connect the app to employer, customer, household, lab, or existing Bee
  systems.
- Never place contact details, precise location, private network values,
  credentials, or personal recordings in Git, Grafana, screenshots, video, or
  the public Devpost entry.
- Store Google Cloud and Grafana credentials only in private environment/secret
  managers. `.env` is ignored and `.env.example` contains placeholders only.
- The Grafana MCP subprocess runs with `--disable-write` and a narrow tool
  allowlist. Use a contest-only least-privilege service account.
- The demo UI accepts only the three published synthetic production IDs and
  rejects contact, URL, local/private-network, confidential, and credential-like
  input before it is sent to Gemini.
- Generated briefs are checked again before display. Email addresses, phone
  numbers, private-network addresses, credential-like tokens, missing required
  sections, and uncited observed facts fail closed with a generic error.
- Displayed observed facts must match a successful read-only Grafana query and
  its exact absolute UTC request window; prose that merely resembles a citation
  is rejected. The fixed ambiguous fixture also requires an explicit abstention.
- `fixtures/telemetry_v1.json` contains only fixed synthetic identifiers,
  timestamps, metrics, logs, and alerts. Its validator rejects private markers,
  unapproved labels/metrics, malformed timestamps, and non-synthetic environments.
- Existing Bee submission code is not reused; this project began during the
  official contest period.

Before publication, rerun the public-tree privacy test, credential scanner,
dependency/license audit, image metadata review, and logged-out URL checks.
