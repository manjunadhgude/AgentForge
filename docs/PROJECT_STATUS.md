# AgentForge Project Status

## Current source-review position

The current project contains a reliability-focused prototype with persistent action records, lease-aware recovery, saved-result replay, bounded retry behavior, persistent approvals, an authenticated development API, basic observability, and local simulated demonstrations.

The uploaded project bundle includes historical Windows verification reports. The latest recorded report states that the full suite passed with 104 tests and 4 subtests, but that result predates the current one-shot finalization changes and must not be treated as verification of this revised checkout.

## Finalization changes in this batch

- Added explicit pytest discovery settings so duplicate test modules under `backups/` are not collected as active tests.
- Marked PostgreSQL-backed tests as integration tests and made them skip cleanly when `AGENTFORGE_DB_PASSWORD` is absent. When the variable is set, these tests require a reachable database and write test records/checkpoints.
- Updated the README to document the test-discovery behavior, optional PostgreSQL test command, local run commands, and scope limits.
- Added a finalization report that distinguishes checks run in the review container from checks that require the user's Windows/PostgreSQL environment.

## Evidence and limitations

The local review container did not have all pinned project dependencies available, and network package installation was unavailable. As a result, the complete pytest suite, LangGraph/PostgreSQL integration paths, demo, and benchmark could not all be independently rerun in this container. Python syntax compilation and repository hygiene checks are recorded separately in the finalization report.

Previously reported Windows test results are historical evidence only. Re-run the full verification script on the actual Windows project after applying this batch.

## What this does not demonstrate

- Exactly-once execution of arbitrary remote side effects.
- Safe retries after a timeout without destination-side idempotency or reconciliation.
- A distributed fencing-token guarantee, production load capacity, or multi-region resilience.
- A formal security audit, a complete secret-free repository certification, or penetration-test coverage.
- Production monitoring, alerting, TLS termination, rate limiting, backup/restore validation, or cloud deployment.
- A fair performance comparison against Temporal, Inngest, LangGraph, or other systems.

## Release position

Describe AgentForge as a **reliability-focused engineering prototype / reliability lab**. Before calling the current checkout verified, run the one-shot finalization script on Windows, review its report and Git diff, and intentionally review any database integration results. Do not auto-commit or claim production readiness solely because tests pass.


## LLM integration update — 2026-10-22

- Added an opt-in OpenAI-compatible tool-proposal adapter (`llm_agent.py`).
- Added authenticated `POST /llm/propose`; it returns a proposal only and never executes it.
- Added mocked-provider tests for allowlist enforcement, schema validation, bounded retries, and approval-gated simulated refunds.
- Live provider execution is not verified in this environment because no user API key is configured and network access is unavailable.
- Added a local repeated-action comparison benchmark. Its handler-call counts are deterministic for the modeled case; no latency claim is made.
