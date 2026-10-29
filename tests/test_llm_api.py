from __future__ import annotations

from sqlalchemy import create_engine
from fastapi.testclient import TestClient

from api import create_app
from llm_agent import ToolProposal
from tool_runtime import ToolRegistry


class FakePlanner:
    def __init__(self, tool_name="get_order_status", arguments=None):
        self.tool_name = tool_name
        self.arguments = arguments or {"order_id": "ORDER-001"}

    def propose(self, request: str) -> ToolProposal:
        assert request
        return ToolProposal(self.tool_name, self.arguments, "fake-test-model")


def build_client(planner):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    app = create_app(
        engine,
        registry=ToolRegistry(),
        api_token="a" * 40,
        approver_token="b" * 40,
        approver_id="test-reviewer",
        llm_planner=planner,
    )
    return TestClient(app), engine


def test_llm_proposal_route_requires_api_authentication():
    client, engine = build_client(FakePlanner())
    try:
        response = client.post("/llm/propose", json={"request": "Check ORDER-001"})
        assert response.status_code == 401
    finally:
        engine.dispose()


def test_llm_proposal_route_returns_proposal_without_execution():
    client, engine = build_client(FakePlanner())
    try:
        response = client.post(
            "/llm/propose", json={"request": "Check ORDER-001"},
            headers={"Authorization": "Bearer " + "a" * 40},
        )
        assert response.status_code == 200
        assert response.json() == {
            "tool_name": "get_order_status",
            "arguments": {"order_id": "ORDER-001"},
            "model": "fake-test-model",
            "requires_approval": False,
            "executed": False,
        }
    finally:
        engine.dispose()


def test_llm_proposal_route_marks_refund_as_approval_gated_and_does_not_execute():
    client, engine = build_client(FakePlanner(
        "issue_refund", {"order_id": "ORDER-001", "amount_cents": 2500}
    ))
    try:
        response = client.post(
            "/llm/propose", json={"request": "Refund ORDER-001"},
            headers={"Authorization": "Bearer " + "a" * 40},
        )
        assert response.status_code == 200
        assert response.json()["requires_approval"] is True
        assert response.json()["executed"] is False
    finally:
        engine.dispose()


def test_llm_proposal_route_revalidates_injected_planner_arguments():
    client, engine = build_client(FakePlanner(
        "issue_refund", {"order_id": "ORDER-001", "amount_cents": -10}
    ))
    try:
        response = client.post(
            "/llm/propose", json={"request": "Refund ORDER-001"},
            headers={"Authorization": "Bearer " + "a" * 40},
        )
        assert response.status_code == 502
    finally:
        engine.dispose()
