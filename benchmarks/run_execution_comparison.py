"""Matched deterministic reliability evaluation for AgentForge.

Run:
  python benchmarks/run_execution_comparison.py --iterations 1
  python benchmarks/run_execution_comparison.py --output reports/matched_reliability.json

This is a controlled local simulation. It measures handler invocation counts,
attempts, outcomes, and recovery decisions—not latency, production scale, or
performance against another workflow product.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from action_ledger import get_action, initialize_ledger
from action_runtime import (
    ActionExecutionFailed,
    ActionRecoveryRequired,
    ActionRuntime,
)
from resilience import TransientToolError, run_with_resilience


MAX_ATTEMPTS = 3
DUPLICATE_DELIVERIES = 5


def _runtime(tmp: str, name: str) -> tuple[Any, ActionRuntime]:
    engine = create_engine(f"sqlite+pysqlite:///{Path(tmp) / (name + '.sqlite')}")
    initialize_ledger(engine)
    return engine, ActionRuntime(engine, worker_id="matched-benchmark", lease_seconds=30)


def _normal_scenario() -> dict:
    payload = {"case_id": "CASE-NORMAL-001", "decision": "manual_review"}
    baseline_calls = 0

    def baseline_handler(request: dict) -> dict:
        nonlocal baseline_calls
        baseline_calls += 1
        return {"case_id": request["case_id"], "decision": request["decision"]}

    baseline_result = baseline_handler(payload)
    with TemporaryDirectory(prefix="agentforge-matched-normal-") as tmp:
        engine, runtime = _runtime(tmp, "normal")
        agentforge_calls = 0

        def agentforge_handler(request: dict) -> dict:
            nonlocal agentforge_calls
            agentforge_calls += 1
            return {"case_id": request["case_id"], "decision": request["decision"]}

        result = runtime.execute(
            "normal-001", "matched_case_review", payload, agentforge_handler
        )
        state = get_action(engine, "normal-001")["status"]
        engine.dispose()

    assert baseline_result == result["result"]
    assert baseline_calls == agentforge_calls == 1
    assert state == "completed"
    return {
        "input": payload,
        "failure_schedule": [],
        "baseline": {
            "attempts": 1, "handler_invocations": baseline_calls,
            "outcome": "completed", "state": "completed",
        },
        "agentforge": {
            "attempts": 1, "handler_invocations": agentforge_calls,
            "outcome": "completed", "state": state,
        },
        "assertions": {"same_result": True, "one_invocation_each": True},
    }


def _transient_scenario() -> dict:
    payload = {"case_id": "CASE-TRANSIENT-001", "decision": "manual_review"}
    schedule = ["fail_before_side_effect", "succeed"]
    baseline_calls = 0
    baseline_attempts = 0

    def baseline_attempt() -> dict:
        nonlocal baseline_calls, baseline_attempts
        baseline_attempts += 1
        if schedule[baseline_attempts - 1] == "fail_before_side_effect":
            raise TransientToolError("scripted failure before side effect")
        baseline_calls += 1
        return dict(payload)

    baseline_result = None
    for _ in range(MAX_ATTEMPTS):
        try:
            baseline_result = baseline_attempt()
            break
        except TransientToolError:
            continue

    agentforge_calls = 0
    agentforge_attempts = 0

    async def agentforge_attempt() -> dict:
        nonlocal agentforge_calls, agentforge_attempts
        agentforge_attempts += 1
        if schedule[agentforge_attempts - 1] == "fail_before_side_effect":
            raise TransientToolError("scripted failure before side effect")
        agentforge_calls += 1
        return dict(payload)

    agentforge_result = asyncio.run(
        run_with_resilience(
            agentforge_attempt,
            max_attempts=MAX_ATTEMPTS,
            timeout_seconds=1.0,
            retry_delay_seconds=0,
        )
    )
    assert baseline_result == agentforge_result == payload
    assert baseline_attempts == agentforge_attempts == 2
    assert baseline_calls == agentforge_calls == 1
    return {
        "input": payload,
        "failure_schedule": schedule,
        "retry_configuration": {"max_attempts": MAX_ATTEMPTS, "timeout_seconds": 1.0},
        "baseline": {
            "attempts": baseline_attempts, "handler_invocations": baseline_calls,
            "outcome": "recovered", "state": "completed",
        },
        "agentforge": {
            "attempts": agentforge_attempts, "handler_invocations": agentforge_calls,
            "outcome": "recovered", "state": "completed",
        },
        "assertions": {
            "same_schedule": True, "same_attempt_limit": True,
            "both_recovered": True, "one_side_effect_each": True,
        },
    }


def _duplicate_scenario() -> dict:
    payload = {"case_id": "CASE-DUPLICATE-001", "decision": "manual_review"}
    baseline_calls = 0
    baseline_effects = 0
    baseline_results = []

    def baseline_handler(request: dict) -> dict:
        nonlocal baseline_calls, baseline_effects
        baseline_calls += 1
        baseline_effects += 1
        return {"case_id": request["case_id"], "decision": request["decision"]}

    for _ in range(DUPLICATE_DELIVERIES):
        baseline_results.append(baseline_handler(dict(payload)))

    with TemporaryDirectory(prefix="agentforge-matched-duplicate-") as tmp:
        engine, runtime = _runtime(tmp, "duplicate")
        agentforge_calls = 0
        agentforge_effects = 0
        results = []

        def handler(request: dict) -> dict:
            nonlocal agentforge_calls, agentforge_effects
            agentforge_calls += 1
            agentforge_effects += 1
            return {"case_id": request["case_id"], "decision": request["decision"]}

        for _ in range(DUPLICATE_DELIVERIES):
            results.append(runtime.execute(
                "duplicate-001", "matched_case_review", dict(payload), handler
            ))
        state = get_action(engine, "duplicate-001")
        engine.dispose()

    agentforge_results = [item["result"] for item in results]
    assert baseline_calls == DUPLICATE_DELIVERIES
    assert agentforge_calls == 1
    assert baseline_results == agentforge_results
    assert all(result == baseline_results[0] for result in baseline_results)
    assert sum(bool(item["replayed"]) for item in results) == DUPLICATE_DELIVERIES - 1
    assert state["status"] == "completed"
    return {
        "input": payload,
        "failure_schedule": ["same delivery repeated"] * (DUPLICATE_DELIVERIES - 1),
        "deliveries": DUPLICATE_DELIVERIES,
        "baseline": {
            "attempts": baseline_calls, "handler_invocations": baseline_calls,
            "simulated_side_effects": baseline_effects,
            "caller_visible_successes": len(baseline_results),
            "outcome": "completed", "state": "re-executed_on_each_delivery",
        },
        "agentforge": {
            "attempts": DUPLICATE_DELIVERIES, "handler_invocations": agentforge_calls,
            "simulated_side_effects": agentforge_effects,
            "caller_visible_successes": len(agentforge_results),
            "outcome": "completed_with_saved_result_replay", "state": state["status"],
        },
        "assertions": {
            "baseline_reexecutes_each_delivery": baseline_calls == DUPLICATE_DELIVERIES,
            "agentforge_invokes_once": agentforge_calls == 1,
            "per_delivery_results_equivalent": baseline_results == agentforge_results,
            "remaining_deliveries_replayed": sum(bool(item["replayed"]) for item in results) == DUPLICATE_DELIVERIES - 1,
        },
    }


def _ambiguous_scenario() -> dict:
    payload = {"case_id": "CASE-AMBIGUOUS-001", "decision": "submit"}
    schedule = [
        "side_effect_occurs", "response_timeout_reported",
        "redelivery_side_effect_occurs", "response_timeout_reported",
    ]
    baseline_calls = 0
    baseline_attempts = 0
    baseline_effects = 0
    baseline_successes = 0

    def baseline_handler(request: dict) -> dict:
        nonlocal baseline_calls, baseline_effects
        baseline_calls += 1
        baseline_effects += 1
        raise TimeoutError("scripted response timeout after simulated side effect")

    baseline_observed = []
    for _ in range(2):
        baseline_attempts += 1
        try:
            baseline_observed.append(baseline_handler(dict(payload)))
            baseline_successes += 1
        except TimeoutError as exc:
            baseline_observed.append(type(exc).__name__)

    with TemporaryDirectory(prefix="agentforge-matched-ambiguous-") as tmp:
        engine, runtime = _runtime(tmp, "ambiguous")
        agentforge_calls = 0
        agentforge_attempts = 0
        agentforge_effects = 0
        agentforge_successes = 0

        def side_effect_then_timeout(request: dict) -> dict:
            nonlocal agentforge_calls, agentforge_effects
            agentforge_calls += 1
            agentforge_effects += 1
            raise TimeoutError("response timed out after simulated side effect")

        try:
            agentforge_attempts += 1
            runtime.execute(
                "ambiguous-001", "matched_submit", dict(payload), side_effect_then_timeout
            )
            agentforge_successes += 1
        except ActionExecutionFailed:
            pass
        else:
            raise AssertionError("first ambiguous execution should be recorded as failed")

        blocked = False
        try:
            agentforge_attempts += 1
            runtime.execute(
                "ambiguous-001", "matched_submit", dict(payload), side_effect_then_timeout
            )
            agentforge_successes += 1
        except ActionRecoveryRequired:
            blocked = True
        state = get_action(engine, "ambiguous-001")["status"]
        engine.dispose()

    assert baseline_calls == baseline_attempts == baseline_effects == 2
    assert baseline_successes == 0
    assert agentforge_calls == agentforge_effects == 1
    assert agentforge_attempts == 2 and agentforge_successes == 0
    assert blocked and state == "uncertain"
    return {
        "input": payload,
        "failure_schedule": schedule,
        "baseline": {
            "attempts": baseline_attempts, "handler_invocations": baseline_calls,
            "simulated_side_effects": baseline_effects,
            "caller_visible_successes": baseline_successes,
            "outcome": "two_timeouts_after_side_effect",
            "state": "re-executed_without_reconciliation",
        },
        "agentforge": {
            "attempts": agentforge_attempts, "handler_invocations": agentforge_calls,
            "simulated_side_effects": agentforge_effects,
            "caller_visible_successes": agentforge_successes,
            "outcome": "blocked_pending_reconciliation", "state": state,
        },
        "assertions": {
            "baseline_handler_invoked_twice": baseline_calls == 2,
            "baseline_effects_occurred_twice": baseline_effects == 2,
            "agentforge_blocks_second_execution": blocked,
            "agentforge_effect_occurred_once": agentforge_effects == 1,
            "no_caller_observed_success": baseline_successes == agentforge_successes == 0,
        },
    }


def run_comparison(iterations: int = 1) -> dict:
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    scenarios = {
        "normal_execution": _normal_scenario(),
        "recoverable_transient_failure": _transient_scenario(),
        "duplicate_delivery_replay": _duplicate_scenario(),
        "ambiguous_outcome": _ambiguous_scenario(),
    }
    # Preserve the original repeated-delivery comparison and its --iterations
    # interface alongside the new matched failure scenarios.
    baseline_replay_invocations = iterations * DUPLICATE_DELIVERIES
    with TemporaryDirectory(prefix="agentforge-replay-comparison-") as tmp:
        engine, runtime = _runtime(tmp, "replay")
        ledger_replay_invocations = 0
        for index in range(iterations):
            key = f"replay-{index:06d}"
            request = {"case_id": f"CASE-{index:06d}"}
            for _ in range(DUPLICATE_DELIVERIES):
                def replay_handler(payload: dict) -> dict:
                    nonlocal ledger_replay_invocations
                    ledger_replay_invocations += 1
                    return {"case_id": payload["case_id"], "decision": "manual_review"}
                runtime.execute(key, "simulated_case_review", request, replay_handler)
        engine.dispose()
    replay_assertions = {
        "baseline_invocations_match_deliveries": baseline_replay_invocations == iterations * DUPLICATE_DELIVERIES,
        "ledger_invocations_match_logical_actions": ledger_replay_invocations == iterations,
    }
    assert all(replay_assertions.values())
    report = {
        "benchmark": "AgentForge matched reliability evaluation",
        "schema_version": 1,
        "iterations": iterations,
        "original_replay_comparison": {
            "logical_actions": iterations,
            "deliveries_per_action": DUPLICATE_DELIVERIES,
            "baseline_handler_invocations": baseline_replay_invocations,
            "agentforge_handler_invocations": ledger_replay_invocations,
            "handler_invocations_avoided": baseline_replay_invocations - ledger_replay_invocations,
            "handler_invocation_reduction_fraction": (
                baseline_replay_invocations - ledger_replay_invocations
            ) / baseline_replay_invocations,
            "assertions": replay_assertions,
        },
        "scope": (
            "Deterministic local simulation. Counts simulated handler invocations, "
            "attempts, outcomes, and ledger states only."
        ),
        "limitations": [
            "Not a production load, latency, throughput, or competitor benchmark.",
            "The baseline is a deliberately simple naive caller, not a named product.",
            "An uncertain ledger state prevents blind replay but does not prove whether "
            "the remote side effect happened.",
            "Exactly-once external effects require downstream idempotency/deduplication "
            "and reconciliation; the ledger alone cannot guarantee them.",
        ],
        "scenarios": scenarios,
        "all_invariants_passed": all(
            all(scenario["assertions"].values()) for scenario in scenarios.values()
        ),
    }
    assert report["all_invariants_passed"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100,
                        help="logical actions for the preserved repeated-replay comparison")
    parser.add_argument("--output", default="reports/agentforge_matched_reliability.json")
    args = parser.parse_args()
    if not 1 <= args.iterations <= 10000:
        parser.error("--iterations must be between 1 and 10000")
    report = run_comparison(args.iterations)
    output = (ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nBenchmark report written: {output}")


if __name__ == "__main__":
    main()
