import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from api import create_app


API_TOKEN = "test-api-token-" + ("a" * 32)
APPROVER_TOKEN = "test-approver-token-" + ("b" * 32)
APPROVER_ID = "configured-security-reviewer"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    app = create_app(
        engine,
        api_token=API_TOKEN,
        approver_token=APPROVER_TOKEN,
        approver_id=APPROVER_ID,
    )
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()


def api_headers():
    return {"Authorization": f"Bearer {API_TOKEN}"}


def approver_headers():
    return {"Authorization": f"Bearer {APPROVER_TOKEN}"}


def test_health_checks_database_and_lists_tools(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    unauthorized = client.get("/tools")
    assert unauthorized.status_code == 401

    tools = client.get("/tools", headers=api_headers())
    assert tools.status_code == 200
    names = {item["name"] for item in tools.json()}
    assert {"get_order_status", "issue_refund"} <= names


def test_api_routes_require_api_token(client):
    payload = {"arguments": {"order_id": "ORD-100", "amount_cents": 1250}}
    assert client.get("/tools").status_code == 401
    assert client.post(
        "/approvals",
        json={"tool_name": "issue_refund", "arguments": payload["arguments"]},
    ).status_code == 401
    assert client.post(
        "/tools/get_order_status/execute",
        json={"arguments": {"order_id": "ORD-500"}},
    ).status_code == 401

    bad = client.get("/tools", headers={"Authorization": "Bearer wrong-token"})
    assert bad.status_code == 401


def test_approval_endpoint_requires_distinct_approver_token(client):
    requested = client.post(
        "/approvals",
        headers=api_headers(),
        json={
            "tool_name": "issue_refund",
            "arguments": {"order_id": "ORD-101", "amount_cents": 1250},
        },
    )
    assert requested.status_code == 201
    request_id = requested.json()["request_id"]

    assert client.post(
        f"/approvals/{request_id}/approve",
        headers=api_headers(),
    ).status_code == 401


def test_refund_requires_approval_then_executes_once(client):
    payload = {"arguments": {"order_id": "ORD-100", "amount_cents": 1250}}

    blocked = client.post(
        "/tools/issue_refund/execute",
        headers=api_headers(),
        json=payload,
    )
    assert blocked.status_code == 403

    requested = client.post(
        "/approvals",
        headers=api_headers(),
        json={"tool_name": "issue_refund", "arguments": payload["arguments"]},
    )
    assert requested.status_code == 201
    request_id = requested.json()["request_id"]
    assert requested.json()["status"] == "pending"

    approved = client.post(
        f"/approvals/{request_id}/approve",
        headers=approver_headers(),
        json={"approved_by": "attacker-supplied-name"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert client.app.state.approvals.get(request_id)["approved_by"] == APPROVER_ID

    execution = client.post(
        "/tools/issue_refund/execute",
        headers=api_headers(),
        json={**payload, "approval_id": request_id},
    )
    assert execution.status_code == 200
    assert execution.json()["result"]["simulated"] is True

    replay = client.post(
        "/tools/issue_refund/execute",
        headers=api_headers(),
        json={**payload, "approval_id": request_id},
    )
    assert replay.status_code == 403


def test_approval_cannot_be_used_for_different_arguments(client):
    requested = client.post(
        "/approvals",
        headers=api_headers(),
        json={
            "tool_name": "issue_refund",
            "arguments": {"order_id": "ORD-200", "amount_cents": 2500},
        },
    )
    assert requested.status_code == 201
    request_id = requested.json()["request_id"]
    client.post(
        f"/approvals/{request_id}/approve",
        headers=approver_headers(),
    )

    response = client.post(
        "/tools/issue_refund/execute",
        headers=api_headers(),
        json={
            "arguments": {"order_id": "ORD-200", "amount_cents": 2600},
            "approval_id": request_id,
        },
    )
    assert response.status_code == 403


def test_approval_request_rejects_invalid_or_unknown_tools(client):
    invalid_arguments = client.post(
        "/approvals",
        headers=api_headers(),
        json={
            "tool_name": "issue_refund",
            "arguments": {"order_id": "ORD-300", "amount_cents": -1},
        },
    )
    assert invalid_arguments.status_code == 422

    unknown_tool = client.post(
        "/approvals",
        headers=api_headers(),
        json={"tool_name": "delete_everything", "arguments": {}},
    )
    assert unknown_tool.status_code == 404


def test_approval_request_rejects_extra_fields(client):
    response = client.post(
        "/approvals",
        headers=api_headers(),
        json={
            "tool_name": "issue_refund",
            "arguments": {"order_id": "ORD-400", "amount_cents": 100},
            "unexpected": "reject me",
        },
    )
    assert response.status_code == 422


def test_read_only_tool_executes_without_approval(client):
    response = client.post(
        "/tools/get_order_status/execute",
        headers=api_headers(),
        json={"arguments": {"order_id": "ORD-500"}},
    )
    assert response.status_code == 200
    assert response.json()["result"]["status"] == "delivered"


def test_non_approval_tool_cannot_create_approval(client):
    response = client.post(
        "/approvals",
        headers=api_headers(),
        json={
            "tool_name": "get_order_status",
            "arguments": {"order_id": "ORD-600"},
        },
    )
    assert response.status_code == 400


def test_app_fails_closed_if_tokens_are_not_configured(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'missing_tokens.db'}")
    app = create_app(engine, api_token=None, approver_token=None, approver_id=None)
    with TestClient(app) as test_client:
        assert test_client.get("/tools").status_code == 503
        assert test_client.post(
            "/tools/get_order_status/execute",
            json={"arguments": {"order_id": "ORD-700"}},
        ).status_code == 503
    engine.dispose()


def test_short_tokens_are_rejected_as_insecure(client):
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    app = create_app(
        engine,
        api_token="weak",
        approver_token=APPROVER_TOKEN,
        approver_id=APPROVER_ID,
    )
    with TestClient(app) as test_client:
        assert test_client.get("/tools", headers={"Authorization": "Bearer weak"}).status_code == 503
    engine.dispose()
