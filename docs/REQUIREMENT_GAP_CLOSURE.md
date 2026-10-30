# Requirement Gap Closure Record

**Status date:** 2026-10-22
**Purpose:** Distinguish implemented behavior from evidence still required before a public release.

## Requirement-to-evidence matrix

| Requirement | Implementation/evidence | Status and limits |
|---|---|---|
| Persistent action ledger and safe replay | `action_ledger.py`, `action_runtime.py`, `tests/test_action_ledger.py`, `tests/test_action_runtime.py` | Implemented; replay behavior applies to the same action key and request. It does not guarantee exactly-once effects in arbitrary external systems. |
| Bounded retry and timeout handling | `resilience.py`, `tests/test_resilience.py`, `tests/test_fault_injection.py`, `benchmarks/run_reliability_benchmark.py` | Simulated scenarios. Not production load testing. |
| Human approval for side-effecting tools | `tool_runtime.py`, `persistent_approval.py`, API approval routes, corresponding tests | Implemented for the simulated allowlisted tools; keep tests passing after changes. |
| Real LLM can propose a tool | `llm_agent.py`, `demo_llm_tool.py`, `tests/test_llm_agent.py` | Adapter and offline mocked-provider tests added. A successful live-provider request must be run with user-supplied credentials before claiming live integration verified. |
| LLM cannot bypass allowlist/schema/approval | `llm_agent.py` delegates execution to `ToolRegistry`; tests reject unknown tools, invalid args, and unapproved refunds | Test-backed for the defined scenarios; not a proof against every possible attack. |
| Compare naïve repeated calls with ledger-backed replay | `benchmarks/run_execution_comparison.py` | Deterministic local SQLite comparison; not a competitor benchmark or production latency claim. Run and retain its generated JSON report. |
| Full regression suite | `tests/` | Must be rerun on the reconciled Windows environment with project dependencies installed and PostgreSQL configured safely. |
| Public repository secret/history audit | `.gitignore`, `.env.example`, local secret scan instructions in security docs | Must be completed against the exact final commit and history before pushing. Never publish `.env`, credentials, DB dumps, virtual environments, or backups. |

## Live LLM configuration

The provider adapter reads `AGENTFORGE_LLM_API_KEY`, `AGENTFORGE_LLM_MODEL`, optional `AGENTFORGE_LLM_BASE_URL`, `AGENTFORGE_LLM_TIMEOUT_SECONDS`, and `AGENTFORGE_LLM_MAX_ATTEMPTS`. The default endpoint is the OpenAI Chat Completions API. The endpoint must use HTTPS. The adapter retries only a bounded number of transient failures and does not log the API key or provider response body.

The LLM is a proposal generator, not an authorization component. All tool names and arguments are checked against the current `ToolRegistry`. Any tool marked as requiring approval still fails closed without a matching approval ID.

## Release gates still requiring execution on the target Windows checkout

1. Merge/reconcile these changes into the verified Windows working tree without overwriting unrelated work.
2. Run `python -m pip check` and the complete pytest suite.
3. Run PostgreSQL-marked tests only against the intended isolated development/test database.
4. Run both benchmark scripts and archive the JSON output with environment/version details.
5. With a valid provider key, run `demo_llm_tool.py`; do not share the key or include it in logs/screenshots.
6. Inspect `git status`, `git diff --check`, secret scan, and all tracked files before commit/push.
7. Verify the public repository contains only intended source, tests, docs, and sanitized example configuration.

A passing automated test suite does not establish production readiness, scale performance, or security against all failures.


## Matched reliability evaluation (2026-10-30)

The existing `benchmarks/run_execution_comparison.py` now exercises four matched deterministic scenarios:

1. Normal execution: baseline and AgentForge complete the same logical action.
2. Recoverable transient failure: both receive the same fail-before-side-effect schedule and a three-attempt bound.
3. Duplicate delivery: the naive baseline invokes the handler on each delivery; AgentForge returns the stored completed result.
4. Ambiguous outcome: the simulated side effect occurs before a timeout is reported. The baseline blindly invokes again; AgentForge records uncertainty and blocks the next execution pending reconciliation.

The benchmark asserts attempts, actual simulated handler invocation counts, final outcomes, and states. It emits `reports/agentforge_matched_reliability.json`. Focused invariants are covered by `tests/test_execution_comparison.py`.

**Interpretation limit:** this is a deterministic local simulation, not a production load/latency benchmark or comparison with another product. Blocking blind replay is not an exactly-once guarantee. A remote side effect may have happened despite a timeout; reliable integrations still need downstream idempotency/deduplication and a reconciliation path.


## Verified GitHub Actions evidence (2026-10-30)

PR run [41054167435](https://github.com/manjunadhgude/AgentForge/actions/runs/41054167435) ran against head `160fe37c775075350541e81c1c3c81020437d5c6`. The workflow provisioned an isolated PostgreSQL 17.4 service and ran the complete suite: **121 passed, 4 subtests passed in 5.32s**, with no skipped or deselected tests. This includes the PostgreSQL concurrency test, persistent checkpoint retry test, and both separate-process recovery tests.

The same job ran `python benchmarks/run_execution_comparison.py`, confirmed `all_invariants_passed: true`, and uploaded [agentforge-matched-reliability-report](https://github.com/manjunadhgude/AgentForge/actions/runs/41054167435/artifacts/12976770005). The downloaded JSON was inspected: 100 logical actions at five deliveries each produced 500 naïve-baseline handler invocations versus 100 ledger-backed invocations; the four matched scenarios passed their assertions. This is a deterministic simulation, not a production performance benchmark.

Still not verified: a live provider-backed LLM request using a user-controlled key, the user's target Windows/Codespaces checkout state, and production deployment/security gates.