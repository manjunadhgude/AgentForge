# AgentForge Release Readiness Checklist

## One-shot local verification

Run `AgentForge_OneShot_Finalization.ps1` from the extracted finalization package. It backs up files before applying the patch, runs the checks available in the local environment, writes a report under `reports/`, and does not commit changes.

## Required checks

- [ ] Python compilation passes on the current checkout.
- [ ] Full pytest suite passes; PostgreSQL integration tests are either intentionally run against the configured test database or explicitly skipped because `AGENTFORGE_DB_PASSWORD` is unset.
- [ ] Lease reclamation rejects reuse of the same owner identity; stale-worker completion is rejected.
- [ ] Non-finite retry configuration is rejected.
- [ ] Demo proves saved-result replay without invoking the simulated handler twice.
- [ ] Benchmark JSON is regenerated and clearly labeled as simulated.
- [ ] Dependency consistency check passes.
- [ ] Dependency vulnerability scan is run where `pip-audit` is available, and findings are reviewed.
- [ ] `git status --short`, `git diff --check`, and the complete diff are reviewed before staging.
- [ ] Credentials, local database files, virtual environments, backups, and transient artifacts are excluded from commits.
- [ ] Any real side-effecting integration has downstream idempotency or reconciliation for ambiguous outcomes.

## PostgreSQL integration safety

The PostgreSQL integration tests write test records and/or LangGraph checkpoints to the configured database. Do not run them against a production database. They use unique IDs for most test runs, but do not assume they are read-only. Do not delete or recreate the existing PostgreSQL container or volume as a test shortcut.

## Production scope limits

A successful local test suite is necessary but not sufficient for production release. The action ledger does not guarantee exactly-once behavior for arbitrary external systems. The API has not undergone a formal security audit. Public deployment still requires reviewed TLS, access policies, rate limits, secret management, logging, monitoring, backup/restore validation, and rollback procedures.


## Additional release gates (2026-10-22)

- [x] LLM proposal adapter added with bounded retries and strict registry validation.
- [x] API proposal route requires the configured API token and returns `executed: false`.
- [x] Offline tests cover malformed/unallowlisted proposals and approval-required tools.
- [x] Repeated-action local comparison benchmark added; report explicitly limits interpretation.
- [ ] Run the complete test suite in the target Windows environment with all pinned dependencies installed.
- [ ] Run PostgreSQL integration tests against the intended safe test database.
- [ ] Run one live LLM smoke test using a locally configured key; never commit or share the key.
- [ ] Run secret scanning and `git diff --check` against the exact release commit/history.
- [ ] Create/push the public GitHub repository and verify its published contents.

Do not describe the project as production-ready. The live-provider test and final Windows/PostgreSQL regression run remain outstanding.


## Matched reliability evaluation (2026-10-30)

- [x] Run `python benchmarks/run_execution_comparison.py` in GitHub Actions and retain `reports/agentforge_matched_reliability.json` as the `agentforge-matched-reliability-report` artifact.
- [x] Confirm all four scenario invariants pass: normal completion, matched fail-before-side-effect retry, duplicate replay, and ambiguous-outcome blocking.
- [x] Review the report limitations. Do not describe uncertain-state blocking as exactly-once external execution.

**Verified CI evidence:** PR run [41054167435](https://github.com/manjunadhgude/AgentForge/actions/runs/41054167435), head `160fe37c775075350541e81c1c3c81020437d5c6`: 121 tests passed and 4 subtests passed in 5.32 seconds, including PostgreSQL integration tests against an ephemeral PostgreSQL 17.4 service. The matched benchmark CLI completed successfully and uploaded the JSON artifact. Local Windows regression and live-provider smoke testing remain separate release gates.
