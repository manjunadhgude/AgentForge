"""Reproducible local microbenchmark for AgentForge retry behavior.

This uses simulated operations only. It does not call external services.
Example: python benchmarks/run_reliability_benchmark.py --iterations 50
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from resilience import TransientToolError, run_with_resilience


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]


async def run_scenario(iterations: int, scenario: str) -> dict:
    durations_ms: list[float] = []
    successful = 0
    total_attempts = 0

    for _ in range(iterations):
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            # Simulated failures are deterministic and have no external side effects.
            if scenario == "transient_recovery" and attempts == 1:
                raise TransientToolError("benchmark-only simulated transient error")
            if scenario == "exhausted_retries":
                raise TransientToolError("benchmark-only persistent simulated error")
            await asyncio.sleep(0)
            return {"ok": True}

        start = time.perf_counter()
        try:
            await run_with_resilience(
                operation,
                max_attempts=3,
                timeout_seconds=1.0,
                retry_delay_seconds=0,
            )
            successful += 1
        except TransientToolError:
            pass
        durations_ms.append((time.perf_counter() - start) * 1000)
        total_attempts += attempts

    return {
        "scenario": scenario,
        "iterations": iterations,
        "successes": successful,
        "failures": iterations - successful,
        "success_rate": successful / iterations,
        "total_attempts": total_attempts,
        "mean_attempts": total_attempts / iterations,
        "latency_ms": {
            "min": min(durations_ms),
            "mean": statistics.fmean(durations_ms),
            "p50": percentile(durations_ms, 0.50),
            "p95": percentile(durations_ms, 0.95),
            "max": max(durations_ms),
        },
    }


async def main_async(iterations: int) -> dict:
    results = []
    for scenario in ("success", "transient_recovery", "exhausted_retries"):
        results.append(await run_scenario(iterations, scenario))
    return {
        "benchmark": "AgentForge local retry microbenchmark",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "iterations_per_scenario": iterations,
        "note": "Simulated local operations only; not a production or competitor benchmark.",
        "scenarios": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--output", default="reports/agentforge_reliability_benchmark.json")
    args = parser.parse_args()
    if args.iterations < 1 or args.iterations > 10000:
        parser.error("--iterations must be between 1 and 10000")
    report = asyncio.run(main_async(args.iterations))
    output = (ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nBenchmark report written: {output}")


if __name__ == "__main__":
    main()
