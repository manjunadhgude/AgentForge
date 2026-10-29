# AgentForge Architecture

## Execution path

```text
Caller / local demo
        |
        v
ActionRuntime
        |
        +--> Action ledger: claim, lease ownership, saved result, recovery decision
        |
        +--> Operation callback / tool boundary
        |
        +--> Observability: execution events and metrics
        |
        v
Completed result or explicit recovery/escalation path
```

The retry helper is a separate boundary for operations that can be retried safely. Persistent approval is a gate for sensitive or side-effecting tool actions. The optional LLM component proposes a registered tool call; the registry validates it and remains responsible for execution authorization. `POST /llm/propose` returns `executed: false` and does not invoke the proposed tool.

## Main modules

| Module | Responsibility |
|---|---|
| `agentforge_config.py` | Application settings and database connection configuration |
| `action_ledger.py` | Persistent action records, claims, lease ownership, completion, uncertainty, and recovery decisions |
| `action_runtime.py` | Coordinates action execution and reuses saved results for completed actions |
| `resilience.py` | Bounded retries, timeouts, backoff, and retry observation |
| `persistent_approval.py` | Persistent approval records and single-use / expiry controls |
| `tool_runtime.py` | Validated tool inputs and allowlisted simulated tools |
| `observability.py` | JSONL event sink and in-process reliability metrics |
| `api.py` | Authenticated HTTP/API integration surface, including proposal-only LLM route |
| `llm_agent.py` | OpenAI-compatible tool proposer; validates model proposals but never grants approval |
| `demo_llm_tool.py` | Optional live-provider demo; executes only read-only mock lookup and never auto-executes refund proposals |
| `benchmarks/run_execution_comparison.py` | Deterministic repeated-action handler-count comparison for naive re-execution versus ledger replay |
| `demo_agentforge.py` | Safe local demonstration using temporary SQLite |
| `benchmarks/run_reliability_benchmark.py` | Repeatable simulated retry microbenchmark |

## Action lifecycle (conceptual)

```text
not found -> claim -> execute -> completed -> replay saved result
                         |
                         +-> uncertain -> inspect / reconcile / escalate
```

An expired lease may be reclaimed according to the ledger's ownership rules. A worker whose lease ownership is no longer valid must not complete or mutate the action as if it still owned it.

## Reliability boundaries

- A completed ledger record can prevent repeated execution within the runtime's action-key model.
- An uncertain outcome must not be treated as proof that an external operation did not happen.
- Leases coordinate workers but do not by themselves make a remote side effect exactly once.
- For real integrations, use downstream idempotency keys where supported, durable reconciliation, bounded timeouts, and explicit human approval for high-impact actions.
- Keep secrets in environment variables or a secrets manager; never commit credentials.
