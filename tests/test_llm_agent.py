from __future__ import annotations

import json
from urllib.request import Request

import pytest

from llm_agent import (
    LLMConfigurationError,
    LLMIntegrationError,
    OpenAICompatibleToolPlanner,
    ToolProposal,
    execute_proposal,
)
from tool_runtime import ApprovalManager, ToolRegistry


def response_for(name="get_order_status", arguments=None):
    return {
        "choices": [{"message": {"tool_calls": [{"function": {
            "name": name,
            "arguments": json.dumps(arguments if arguments is not None else {"order_id": "ORDER-001"}),
        }}]}}]
    }


def planner_with_response(body, *, calls=None, max_attempts=2):
    calls = calls if calls is not None else []

    def transport(request: Request, timeout: float) -> bytes:
        calls.append((request, timeout))
        return json.dumps(body).encode()

    return OpenAICompatibleToolPlanner(
        ToolRegistry(), api_key="test-key-not-real", model="test-model",
        transport=transport, max_attempts=max_attempts, sleep=lambda _: None,
    ), calls


def test_llm_proposal_uses_allowlisted_tool_and_validated_arguments():
    planner, calls = planner_with_response(response_for())
    proposal = planner.propose("Check the status of ORDER-001")
    assert proposal == ToolProposal("get_order_status", {"order_id": "ORDER-001"}, "test-model")
    assert len(calls) == 1
    payload = json.loads(calls[0][0].data)
    assert payload["parallel_tool_calls"] is False
    assert {item["function"]["name"] for item in payload["tools"]} == {
        "get_order_status", "issue_refund"
    }


def test_missing_api_key_fails_closed():
    with pytest.raises(LLMConfigurationError, match="AGENTFORGE_LLM_API_KEY"):
        OpenAICompatibleToolPlanner(ToolRegistry(), api_key="", model="model")


def test_non_https_provider_url_rejected():
    with pytest.raises(LLMConfigurationError, match="HTTPS"):
        OpenAICompatibleToolPlanner(
            ToolRegistry(), api_key="test-key", model="model", base_url="http://localhost"
        )


def test_model_cannot_propose_unregistered_tool():
    planner, _ = planner_with_response(response_for("delete_database", {}))
    with pytest.raises(LLMIntegrationError, match="not allowlisted"):
        planner.propose("Delete the database")


def test_invalid_arguments_rejected_before_execution():
    planner, _ = planner_with_response(response_for("issue_refund", {
        "order_id": "ORDER-001", "amount_cents": -100
    }))
    with pytest.raises(LLMIntegrationError, match="schema validation"):
        planner.propose("Refund order ORDER-001")


def test_side_effecting_proposal_does_not_execute_without_approval():
    planner, _ = planner_with_response(response_for("issue_refund", {
        "order_id": "ORDER-001", "amount_cents": 2500
    }))
    proposal = planner.propose("Refund order ORDER-001 for 25 dollars")
    with pytest.raises(Exception, match="Approval required"):
        execute_proposal(planner.registry, proposal)


def test_side_effecting_proposal_executes_only_with_matching_approval():
    approvals = ApprovalManager()
    registry = ToolRegistry(approvals)
    planner = OpenAICompatibleToolPlanner(
        registry, api_key="test-key", model="test-model",
        transport=lambda request, timeout: json.dumps(response_for("issue_refund", {
            "order_id": "ORDER-001", "amount_cents": 2500
        })).encode(),
    )
    proposal = planner.propose("Refund order ORDER-001 for 25 dollars")
    approval_id = approvals.request(proposal.tool_name, proposal.arguments)
    approvals.approve(approval_id, approved_by="test-reviewer")
    result = execute_proposal(registry, proposal, approval_id=approval_id)
    assert result["simulated"] is True
    assert result["status"] == "refund_simulated"


def test_transient_provider_failure_retries_only_within_bound():
    calls = []

    def transport(request, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("simulated timeout")
        return json.dumps(response_for()).encode()

    planner = OpenAICompatibleToolPlanner(
        ToolRegistry(), api_key="test-key", model="test-model", transport=transport,
        max_attempts=2, sleep=lambda _: None,
    )
    assert planner.propose("Check ORDER-001") .tool_name == "get_order_status"
    assert len(calls) == 2


def test_provider_failure_is_bounded_and_does_not_execute_tool():
    calls = []

    def transport(request, timeout):
        calls.append(1)
        raise TimeoutError("simulated timeout")

    planner = OpenAICompatibleToolPlanner(
        ToolRegistry(), api_key="test-key", model="test-model", transport=transport,
        max_attempts=2, sleep=lambda _: None,
    )
    with pytest.raises(LLMIntegrationError, match="no tool was executed"):
        planner.propose("Check ORDER-001")
    assert len(calls) == 2
