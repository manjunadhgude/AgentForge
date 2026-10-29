import pytest

from tool_runtime import (
    ApprovalManager,
    ToolExecutionError,
    ToolRegistry,
)


def test_allowlisted_read_tool_executes():
    registry = ToolRegistry()
    result = registry.execute(
        "get_order_status", {"order_id": "ORDER-001"}
    )
    assert result["status"] == "delivered"
    assert result["mode"] == "mock"


def test_unknown_tool_is_rejected():
    with pytest.raises(ToolExecutionError, match="not allowlisted"):
        ToolRegistry().execute("delete_database", {})


def test_extra_arguments_are_rejected():
    with pytest.raises(ToolExecutionError, match="schema validation"):
        ToolRegistry().execute(
            "get_order_status",
            {"order_id": "ORDER-001", "admin": True},
        )


def test_invalid_refund_amount_is_rejected():
    with pytest.raises(ToolExecutionError, match="schema validation"):
        ToolRegistry().execute(
            "issue_refund",
            {"order_id": "ORDER-001", "amount_cents": -1},
        )


def test_refund_requires_approval():
    with pytest.raises(ToolExecutionError, match="Approval required"):
        ToolRegistry().execute(
            "issue_refund",
            {"order_id": "ORDER-001", "amount_cents": 2500},
        )


def test_refund_executes_after_matching_approval():
    approvals = ApprovalManager()
    registry = ToolRegistry(approvals)
    args = {"order_id": "ORDER-001", "amount_cents": 2500}
    approval_id = approvals.request("issue_refund", args)
    approvals.approve(approval_id, approved_by="test-reviewer")

    result = registry.execute(
        "issue_refund", args, approval_id=approval_id
    )
    assert result["simulated"] is True
    assert result["status"] == "refund_simulated"


def test_approval_cannot_be_reused():
    approvals = ApprovalManager()
    registry = ToolRegistry(approvals)
    args = {"order_id": "ORDER-001", "amount_cents": 2500}
    approval_id = approvals.request("issue_refund", args)
    approvals.approve(approval_id, approved_by="test-reviewer")

    registry.execute("issue_refund", args, approval_id=approval_id)
    with pytest.raises(ToolExecutionError, match="not been granted"):
        registry.execute("issue_refund", args, approval_id=approval_id)


def test_approval_cannot_be_used_for_changed_arguments():
    approvals = ApprovalManager()
    registry = ToolRegistry(approvals)
    approved_args = {"order_id": "ORDER-001", "amount_cents": 2500}
    approval_id = approvals.request("issue_refund", approved_args)
    approvals.approve(approval_id, approved_by="test-reviewer")

    with pytest.raises(ToolExecutionError, match="do not match"):
        registry.execute(
            "issue_refund",
            {"order_id": "ORDER-001", "amount_cents": 9900},
            approval_id=approval_id,
        )


def test_pending_approval_does_not_authorize_execution():
    approvals = ApprovalManager()
    registry = ToolRegistry(approvals)
    args = {"order_id": "ORDER-001", "amount_cents": 2500}
    approval_id = approvals.request("issue_refund", args)

    with pytest.raises(ToolExecutionError, match="not been granted"):
        registry.execute("issue_refund", args, approval_id=approval_id)


def test_approval_cannot_be_granted_twice():
    approvals = ApprovalManager()
    args = {"order_id": "ORDER-001", "amount_cents": 2500}
    approval_id = approvals.request("issue_refund", args)
    approvals.approve(approval_id, approved_by="test-reviewer")

    with pytest.raises(ToolExecutionError, match="not pending"):
        approvals.approve(approval_id, approved_by="another-reviewer")
