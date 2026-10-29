import pytest
from sqlalchemy import create_engine

from persistent_approval import PersistentApprovalManager
from tool_runtime import ToolExecutionError


@pytest.fixture
def manager():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    instance = PersistentApprovalManager(engine)
    instance.initialize()
    yield instance
    engine.dispose()


def test_approval_survives_manager_recreation(manager):
    request_id = manager.request(
        "issue_refund",
        {"order_id": "ORD-1", "amount_cents": 2500},
    )
    manager.approve(request_id, approved_by="reviewer-1")

    # A new manager uses the same database, rather than in-memory state.
    recreated = PersistentApprovalManager(manager.engine)
    recreated.consume(
        request_id,
        tool_name="issue_refund",
        arguments={"order_id": "ORD-1", "amount_cents": 2500},
    )

    assert recreated.get(request_id)["status"] == "consumed"


def test_pending_approval_cannot_be_consumed(manager):
    request_id = manager.request(
        "issue_refund",
        {"order_id": "ORD-1", "amount_cents": 2500},
    )

    with pytest.raises(ToolExecutionError):
        manager.consume(
            request_id,
            tool_name="issue_refund",
            arguments={"order_id": "ORD-1", "amount_cents": 2500},
        )


def test_wrong_tool_is_rejected(manager):
    request_id = manager.request("issue_refund", {"order_id": "ORD-1"})
    manager.approve(request_id, approved_by="reviewer-1")

    with pytest.raises(ToolExecutionError, match="different tool"):
        manager.consume(
            request_id,
            tool_name="get_order_status",
            arguments={"order_id": "ORD-1"},
        )


def test_changed_arguments_are_rejected(manager):
    request_id = manager.request(
        "issue_refund",
        {"order_id": "ORD-1", "amount_cents": 2500},
    )
    manager.approve(request_id, approved_by="reviewer-1")

    with pytest.raises(ToolExecutionError, match="arguments"):
        manager.consume(
            request_id,
            tool_name="issue_refund",
            arguments={"order_id": "ORD-1", "amount_cents": 5000},
        )


def test_approval_is_single_use(manager):
    args = {"order_id": "ORD-1", "amount_cents": 2500}
    request_id = manager.request("issue_refund", args)
    manager.approve(request_id, approved_by="reviewer-1")

    manager.consume(request_id, tool_name="issue_refund", arguments=args)

    with pytest.raises(ToolExecutionError):
        manager.consume(
            request_id,
            tool_name="issue_refund",
            arguments=args,
        )


def test_unknown_approval_cannot_be_approved(manager):
    with pytest.raises(ToolExecutionError):
        manager.approve("missing-request", approved_by="reviewer-1")


def test_blank_approver_is_rejected(manager):
    request_id = manager.request("issue_refund", {"order_id": "ORD-1"})

    with pytest.raises(ValueError, match="approved_by"):
        manager.approve(request_id, approved_by="   ")
