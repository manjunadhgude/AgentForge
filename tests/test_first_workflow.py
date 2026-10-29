import asyncio

import first_workflow
from first_workflow import run_workflow
from resilience import TransientToolError


def test_degraded_incident():
    result = run_workflow("INC-001")

    assert result["health_status"] == "degraded"
    assert result["events"] == [
        "Mock health check for INC-001: degraded"
    ]


def test_healthy_incident():
    result = run_workflow("INC-002")

    assert result["health_status"] == "healthy"
    assert result["events"] == [
        "Mock health check for INC-002: healthy"
    ]


def test_workflow_retries_transient_tool_failure(monkeypatch):
    calls = 0

    async def flaky_tool(incident_id: str) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TransientToolError("temporary failure")
        return "healthy"

    monkeypatch.setattr(
        first_workflow, "mock_check_service_health_async", flaky_tool
    )

    result = run_workflow("INC-002")

    assert result["health_status"] == "healthy"
    assert calls == 2
    assert result["events"] == [
        "Mock health check for INC-002: healthy"
    ]


def test_workflow_recovers_after_tool_timeout(monkeypatch):
    calls = 0
    monkeypatch.setattr(first_workflow, "TOOL_TIMEOUT_SECONDS", 0.01)

    async def slow_first_attempt(incident_id: str) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(0.1)
        return "healthy"

    monkeypatch.setattr(
        first_workflow,
        "mock_check_service_health_async",
        slow_first_attempt,
    )

    result = run_workflow("INC-002")

    assert result["health_status"] == "healthy"
    assert calls == 2
