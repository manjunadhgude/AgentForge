"""End-to-end local AgentForge demo using simulated operations only."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine

from action_ledger import initialize_ledger
from action_runtime import ActionRuntime
from observability import ExecutionEvent, JsonlEventSink, ReliabilityMetrics


def main() -> None:
    with TemporaryDirectory(prefix="agentforge-demo-") as temporary:
        root = Path(temporary)
        engine = create_engine(f"sqlite+pysqlite:///{root / 'demo.sqlite'}")
        initialize_ledger(engine)
        sink = JsonlEventSink(root / "events.jsonl")
        metrics = ReliabilityMetrics()
        runtime = ActionRuntime(engine, worker_id="demo-worker", lease_seconds=30)
        calls = {"count": 0}

        def simulated_tool(payload: dict) -> dict:
            calls["count"] += 1
            return {
                "case_id": payload["case_id"],
                "decision": "manual_review",
                "reason": "simulated demo policy: verify before irreversible action",
            }

        request = {"case_id": "DEMO-001"}
        sink.emit(ExecutionEvent(event_type="action_started", action_key="demo-action-001"))
        first = runtime.execute("demo-action-001", "simulated_case_review", request, simulated_tool)
        metrics.increment("actions.completed")
        metrics.observe_duration("action", 0.0)
        sink.emit(ExecutionEvent(
            event_type="action_completed",
            action_key="demo-action-001",
            status=first["status"],
            attributes={"replayed": first["replayed"]},
        ))

        second = runtime.execute("demo-action-001", "simulated_case_review", request, simulated_tool)
        metrics.increment("actions.replayed", 1 if second["replayed"] else 0)

        result = {
            "demo": "AgentForge local reliability demo",
            "external_services_called": False,
            "irreversible_actions_performed": False,
            "first_execution": first,
            "replay_execution": second,
            "simulated_tool_invocations": calls["count"],
            "metrics": metrics.snapshot(),
            "event_count": len((root / "events.jsonl").read_text(encoding="utf-8").splitlines()),
        }
        print(json.dumps(result, indent=2, default=str))
        assert first["replayed"] is False
        assert second["replayed"] is True
        assert calls["count"] == 1
        assert result["event_count"] == 2
        engine.dispose()


if __name__ == "__main__":
    main()
