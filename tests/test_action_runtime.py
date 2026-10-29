import pytest
from sqlalchemy import create_engine

from action_runtime import (
    ActionExecutionFailed,
    ActionRecoveryRequired,
    ActionRuntime,
)
from action_ledger import (
    actions,
    claim_action,
    get_action,
    initialize_ledger,
    mark_action_uncertain,
)


@pytest.fixture
def engine():
    value = create_engine("sqlite+pysqlite:///:memory:")
    initialize_ledger(value)
    yield value
    value.dispose()


def test_first_execution_is_recorded_and_result_returned(engine):
    calls = []
    runtime = ActionRuntime(engine, worker_id="worker-a")
    result = runtime.execute(
        "runtime-001",
        "mock_operation",
        {"input": "hello"},
        lambda payload: calls.append(payload) or {"output": "HELLO"},
    )
    assert result == {
        "action_key": "runtime-001",
        "status": "completed",
        "result": {"output": "HELLO"},
        "replayed": False,
    }
    assert calls == [{"input": "hello"}]
    assert get_action(engine, "runtime-001")["status"] == "completed"


def test_completed_action_returns_saved_result_without_reexecution(engine):
    runtime = ActionRuntime(engine)
    calls = []
    first = runtime.execute(
        "runtime-002", "mock_operation", {"n": 2},
        lambda payload: calls.append(1) or {"value": 4},
    )
    second = runtime.execute(
        "runtime-002", "mock_operation", {"n": 2},
        lambda payload: calls.append(2) or {"value": 999},
    )
    assert first["result"] == second["result"] == {"value": 4}
    assert first["replayed"] is False
    assert second["replayed"] is True
    assert calls == [1]


def test_same_key_with_different_payload_is_rejected(engine):
    runtime = ActionRuntime(engine)
    runtime.execute("runtime-003", "mock_operation", {"n": 2}, lambda _: {"value": 4})
    with pytest.raises(ValueError, match="different request"):
        runtime.execute("runtime-003", "mock_operation", {"n": 3}, lambda _: {"value": 9})


def test_operation_failure_marks_action_uncertain_and_does_not_retry(engine):
    runtime = ActionRuntime(engine)
    calls = []

    def broken(payload):
        calls.append(1)
        raise RuntimeError("simulated ambiguous failure")

    with pytest.raises(ActionExecutionFailed, match="inspect its ledger"):
        runtime.execute("runtime-004", "mock_operation", {"n": 4}, broken)

    assert calls == [1]
    assert get_action(engine, "runtime-004")["status"] == "uncertain"
    with pytest.raises(ActionRecoveryRequired, match="uncertain outcome"):
        runtime.execute("runtime-004", "mock_operation", {"n": 4}, broken)
    assert calls == [1]


def test_existing_in_progress_action_is_not_executed_again(engine):
    claim_action(
        engine, "runtime-005", "mock_operation", {"n": 5},
        lease_owner="other-worker", lease_seconds=60,
    )
    runtime = ActionRuntime(engine, worker_id="worker-b")
    calls = []
    with pytest.raises(ActionRecoveryRequired, match="still in progress"):
        runtime.execute(
            "runtime-005", "mock_operation", {"n": 5},
            lambda payload: calls.append(1) or {"ok": True},
        )
    assert calls == []


def test_existing_uncertain_action_requires_reconciliation(engine):
    claim_action(
        engine, "runtime-006", "mock_operation", {"n": 6},
        lease_owner="worker-a", lease_seconds=60,
    )
    mark_action_uncertain(engine, "runtime-006", lease_owner="worker-a")
    runtime = ActionRuntime(engine)
    with pytest.raises(ActionRecoveryRequired, match="uncertain outcome"):
        runtime.execute(
            "runtime-006", "mock_operation", {"n": 6},
            lambda _: {"should_not_run": True},
        )


def test_operation_must_return_dictionary_and_failure_is_uncertain(engine):
    runtime = ActionRuntime(engine)
    with pytest.raises(ActionExecutionFailed, match="inspect its ledger"):
        runtime.execute("runtime-007", "mock_operation", {}, lambda _: "not-a-dict")
    assert get_action(engine, "runtime-007")["status"] == "uncertain"


def test_runtime_rejects_invalid_worker_and_lease(engine):
    with pytest.raises(ValueError, match="worker_id"):
        ActionRuntime(engine, worker_id=" ")
    with pytest.raises(ValueError, match="lease_seconds"):
        ActionRuntime(engine, lease_seconds=0)
