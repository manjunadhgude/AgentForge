# AgentForge Reliability and Observability

## Scope

AgentForge explores safe execution and recovery for tool-using AI workflows. This increment adds dependency-free local event logging, in-process metrics, and a reproducible retry microbenchmark.

## Observability primitives

- `ExecutionEvent` describes a sanitized event such as action start, retry, completion, timeout, or escalation.
- `JsonlEventSink` appends one JSON record per line and serializes concurrent writes within one process.
- `ReliabilityMetrics` records counters and duration summaries (count, min, mean, max, and p95).

These are primitives, not yet a distributed telemetry pipeline. In-process metrics reset when the process exits. JSONL writes are local-file append operations; this does not claim multi-process locking, tamper-proof audit storage, rotation, or centralized monitoring.

**Privacy:** do not place secrets, credentials, raw tool arguments, personal data, or full tool outputs into event attributes. Pass only sanitized metadata.

## Local retry benchmark

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe .\benchmarks\run_reliability_benchmark.py --iterations 50
```

The script exercises three deterministic simulated scenarios: immediate success, one transient failure followed by success, and retries exhausted. It writes a JSON report under `reports/`.

This is a reproducible local microbenchmark for regression and demonstration. It is not a comparison against Temporal, Inngest, LangGraph, or any production system, and its latency numbers should not be presented as production performance.

## Recovery safety boundaries

The action ledger supports recovery decisions, lease ownership, expired-lease reclamation, completion, and uncertain-state marking. A lease can prevent stale workers from updating ledger state, but it cannot by itself undo or guarantee exactly-once execution of an external side effect. External systems should provide idempotency keys or a reconciliation path.

## Validation

The batch script compiles the new files, runs focused observability tests, runs the full existing test suite, and executes the simulated benchmark. Review all output and benchmark caveats before treating the batch as complete.
