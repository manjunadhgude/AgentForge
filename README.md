# AgentForge — Fault-Tolerant Agent Runtime & Reliability Lab

AgentForge is a reliability-focused engineering prototype for studying how tool-using workflows behave when actions are retried, interrupted, replayed, or left in an uncertain state.

## Capabilities

- Persistent action ledger with lease ownership and recovery decisions.
- Reuse of stored results for completed actions.
- Conservative handling of uncertain action outcomes.
- Bounded asynchronous retries, per-attempt timeouts, and exponential backoff.
- Persistent, expiring, single-use human approvals for allowlisted tools.
- FastAPI endpoints with separate API and approver bearer tokens.
- Optional authenticated `/llm/propose` endpoint that returns a validated tool proposal without executing it.
- JSONL execution events and lightweight reliability metrics.
- Fault-injection, replay, recovery, and approval tests.
- Local end-to-end demonstration and a repeatable simulated retry microbenchmark.
- Optional OpenAI-compatible LLM tool proposer with schema validation and bounded provider retries.
- Repeated-action comparison benchmark for naïve re-execution versus ledger-backed replay.
- Optional PostgreSQL-backed LangGraph checkpoint and separate-process recovery exercises.

## Important safety and scope limits

The default tools and demo are simulated; they do not issue real refunds or perform irreversible external actions. The local retry benchmark is not a production load test and is not a comparison against Temporal, Inngest, LangGraph, or other systems.

A ledger cannot guarantee exactly-once execution of arbitrary external side effects. A remote tool can succeed while the caller times out or crashes before recording completion. Real integrations need destination-side idempotency keys or equivalent deduplication, durable reconciliation, and an explicit uncertain-outcome path. Timeouts must be treated as potentially ambiguous when a side effect may already have happened.

The API is a development surface, not a security-certified public service. Keep it local-only unless deployment controls, TLS, secret management, rate limits, logging, and access policies have been reviewed.

## Optional LLM tool proposal

The real LLM integration is opt-in. It asks a configured OpenAI-compatible chat-completions endpoint to propose one tool from the registry. The authenticated `POST /llm/propose` route returns the proposal and whether it requires approval; it does not execute the proposal. The standalone demo executes only the read-only mock lookup. The model cannot approve its own actions. `ToolRegistry` validates tool names and arguments, and its existing approval gate remains mandatory for `issue_refund`.

Set `AGENTFORGE_LLM_API_KEY` and `AGENTFORGE_LLM_MODEL` in your local environment, optionally set `AGENTFORGE_LLM_BASE_URL`, then run:

```powershell
.\.venv\Scripts\python.exe .\demo_llm_tool.py
```

This demo may execute the read-only mock order lookup. A refund proposal is displayed but not executed because it requires approval. No real order system or payment processor is connected. A real provider call may incur provider charges. The live-provider path has not been verified in this environment; run it with a valid provider configuration before claiming live integration verified.

## Benchmarks

Run the retry microbenchmark and the repeated-action comparison:

```powershell
.\.venv\Scripts\python.exe .\benchmarks\run_reliability_benchmark.py --iterations 50
.\.venv\Scripts\python.exe .\benchmarks\run_execution_comparison.py --iterations 100
```

The repeated-action comparison models five identical calls per logical action. It demonstrates saved-result replay in a local SQLite simulation; it is not a production latency or competitor benchmark.

## Requirements

- Python 3.12 (the project was developed and tested with Python 3.12).
- Dependencies installed in the project virtual environment.
- Docker Desktop and PostgreSQL for PostgreSQL-backed integration paths.
- `AGENTFORGE_DB_PASSWORD` set in the current PowerShell session to enable PostgreSQL integration tests. Those tests write test rows/checkpoints to the configured development database; use an isolated test database when possible.
- Separate random values of at least 32 characters for `AGENTFORGE_API_TOKEN` and `AGENTFORGE_APPROVER_TOKEN`, plus `AGENTFORGE_APPROVER_ID`, before using protected API routes.

Do not commit credentials, `.env` files, database dumps, or local test artifacts.

## Run locally on Windows PowerShell

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m py_compile .\action_ledger.py .\action_runtime.py .\resilience.py .\observability.py .\api.py .\persistent_approval.py .\tool_runtime.py .\demo_agentforge.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe .\demo_agentforge.py
.\.venv\Scripts\python.exe .\benchmarks\run_reliability_benchmark.py --iterations 50
.\.venv\Scripts\python.exe -m pip check
```

Pytest is configured to discover only `tests/test_*.py` and to ignore backups, virtual environments, and caches. PostgreSQL integration tests are skipped if `AGENTFORGE_DB_PASSWORD` is not set; if it is set, ensure the configured PostgreSQL server is reachable and that the database is safe for test writes.

To explicitly run PostgreSQL integration tests after confirming the database target:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m postgres
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Operations runbook](docs/OPERATIONS_RUNBOOK.md)
- [Project status and verification](docs/PROJECT_STATUS.md)
- [Reliability and observability notes](docs/RELIABILITY_AND_OBSERVABILITY.md)
- [Release readiness checklist](docs/RELEASE_READINESS.md)
- [Mega review findings](docs/MEGA_REVIEW_FINDINGS.md)
- [Finalization report](docs/FINALIZATION_REPORT.md)
- [Requirement gap closure](docs/REQUIREMENT_GAP_CLOSURE.md)

## Verification claims

Historical reports in `reports/` describe runs from the user's configured Windows environment. They are not proof that the current checkout passes after subsequent edits. Re-run the commands above and inspect the generated output before release. The project should be presented as a reliability-focused engineering prototype, not as production-ready infrastructure.

### Matched reliability evaluation

The execution comparison now includes four deterministic matched scenarios: normal completion, a fail-before-side-effect transient retry, duplicate delivery/replay, and an ambiguous outcome where the side effect occurs before a timeout is reported. Each scenario uses the same logical input and scripted schedule for the baseline and AgentForge paths. The benchmark asserts handler invocation counts, attempts, final outcomes, and recovery/blocked states, then writes a JSON report to `reports/agentforge_matched_reliability.json`.

Run it with:

```powershell
.\\.venv\\Scripts\\python.exe .\\benchmarks\\run_execution_comparison.py
```

The baseline is a deliberately simple naive caller, not a named product. The report measures simulated handler invocations and state transitions only; it makes no latency, throughput, production-scale, or competitor-performance claim. An uncertain ledger state prevents blind re-execution but cannot determine whether a remote side effect actually occurred. Exactly-once external effects require downstream idempotency/deduplication and reconciliation; the AgentForge ledger alone does not provide that guarantee.
