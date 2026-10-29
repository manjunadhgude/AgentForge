"""Compare repeated execution with and without AgentForge's action ledger.

This is a deterministic local simulation, not a production load test or a
comparison against another workflow product. Example:
  python benchmarks/run_execution_comparison.py --iterations 100
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timezone

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from action_ledger import initialize_ledger
from action_runtime import ActionRuntime


def run_comparison(iterations: int) -> dict:
    baseline_calls = 0
    ledger_calls = 0

    # Baseline: naïve caller repeats the side effect for every replay.
    for i in range(iterations):
        for _ in range(5):
            baseline_calls += 1

    # AgentForge: execute once, then replay the stored result with the same key.
    with TemporaryDirectory(prefix="agentforge-comparison-") as tmp:
        engine = create_engine(f"sqlite+pysqlite:///{Path(tmp) / 'ledger.sqlite'}")
        initialize_ledger(engine)
        runtime = ActionRuntime(engine, worker_id="benchmark-worker", lease_seconds=30)
        for i in range(iterations):
            action_key = f"benchmark-action-{i:06d}"
            payload = {"case_id": f"CASE-{i:06d}"}
            for _ in range(5):
                def operation(request):
                    nonlocal ledger_calls
                    ledger_calls += 1
                    return {"case_id": request["case_id"], "decision": "manual_review"}
                runtime.execute(action_key, "simulated_case_review", payload, operation)
        engine.dispose()

    total_baseline = iterations * 5
    total_ledger = iterations
    return {
        "benchmark": "AgentForge repeated-action comparison",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "iterations": iterations,
        "replays_per_action": 5,
        "scope": "SQLite-backed local simulation; one successful action followed by identical replays.",
        "not_a_claim": "Not a latency/performance benchmark, not a fault-injection benchmark, and not a competitor comparison. The fair measured outcome is handler invocation count only.",
        "baseline_naive_reexecution": {
            "logical_actions": iterations,
            "side_effect_handler_invocations": baseline_calls,
        },
        "agentforge_action_ledger": {
            "logical_actions": iterations,
            "side_effect_handler_invocations": ledger_calls,
        },
        "handler_invocations_avoided": total_baseline - total_ledger,
        "handler_invocation_reduction_fraction": (total_baseline - total_ledger) / total_baseline,
        "assertions": {
            "baseline_invocations_equal_five_per_action": baseline_calls == total_baseline,
            "ledger_invocations_equal_one_per_action": ledger_calls == total_ledger,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", default="reports/agentforge_execution_comparison.json")
    args = parser.parse_args()
    if not 1 <= args.iterations <= 10000:
        parser.error("--iterations must be between 1 and 10000")
    report = run_comparison(args.iterations)
    if not all(report["assertions"].values()):
        raise SystemExit("benchmark invariant failed")
    output = (ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nBenchmark report written: {output}")


if __name__ == "__main__":
    main()
