# Public repository release boundary

The public contest repository must contain the complete application, synthetic
fixtures, Grafana integration assets, tests, reproducibility scripts,
documentation, and MIT license. It must not contain local environments,
credentials, private evidence, generated caches, or Bradley-only handoff notes.
Its exact Python runtime versions and third-party license boundary are recorded
in `requirements.lock` and `THIRD_PARTY_NOTICES.md`.

Build the candidate without publishing it:

```powershell
python scripts/build_public_release.py
```

The command creates `dist/public-repo`, which is already ignored by Git. It
copies from an explicit allowlist and writes `RELEASE_MANIFEST.json` with the
size and SHA-256 of every copied file. It refuses to overwrite or merge into an
existing destination. This protects both user-owned files and the release from
stale content.

The candidate includes `.github/workflows/public-release.yml`. On every push,
pull request, or manual dispatch, the workflow installs the constrained Python
runtime, runs the complete test and compile checks, rebuilds the allowlisted
candidate into a clean temporary directory, verifies every manifest hash and
exclusion, repeats the checks from that candidate, and builds and smoke-tests
the container as its non-root user. The smoke test uses only explicit fictional
placeholder configuration and exercises health, UI, and fixture-catalog reads;
it never calls `/api/analyze` or any live cloud service.

The following internal files are deliberately omitted because they are review
or handoff material, not application source or judge-facing instructions:

- `docs/DEVPOST_SUBMISSION_DRAFT.md`
- `docs/DEMO_STORYBOARD.md`
- `docs/RUBRIC_AUDIT_DRAFT.md`

Before publishing, rebuild into a clean destination, rerun the full test suite,
verify every manifest hash, scan the candidate rather than the working tree,
and inspect the repository while logged out. A candidate directory is not a
public repository, hosted demo, contest submission, or evidence of a live
Gemini/Grafana Cloud call.
