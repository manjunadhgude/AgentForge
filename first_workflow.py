import asyncio
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from resilience import run_with_resilience


MAX_TOOL_ATTEMPTS = 3
TOOL_TIMEOUT_SECONDS = 2.0


class AgentState(TypedDict):
    incident_id: str
    events: list[str]
    health_status: str


async def mock_check_service_health_async(incident_id: str) -> str:
    """Simulate an asynchronous health-check tool."""
    if incident_id == "INC-001":
        return "degraded"

    return "healthy"


def inspect_service(state: AgentState) -> dict[str, object]:
    """Run the mock tool with bounded retries and a per-attempt timeout."""
    status = asyncio.run(
        run_with_resilience(
            lambda: mock_check_service_health_async(state["incident_id"]),
            max_attempts=MAX_TOOL_ATTEMPTS,
            timeout_seconds=TOOL_TIMEOUT_SECONDS,
        )
    )

    event = f"Mock health check for {state['incident_id']}: {status}"

    return {
        "health_status": status,
        "events": [*state["events"], event],
    }


def build_workflow():
    """Create and compile the AgentForge workflow."""
    workflow = StateGraph(AgentState)

    workflow.add_node("inspect_service", inspect_service)
    workflow.add_edge(START, "inspect_service")
    workflow.add_edge("inspect_service", END)

    return workflow.compile()


def run_workflow(incident_id: str) -> AgentState:
    """Execute the workflow for the specified incident."""
    app = build_workflow()

    initial_state: AgentState = {
        "incident_id": incident_id,
        "events": [],
        "health_status": "unknown",
    }

    return app.invoke(initial_state)


def main() -> None:
    final_state = run_workflow("INC-001")

    print("AgentForge first workflow: SUCCESS")
    print(f"Incident: {final_state['incident_id']}")
    print(f"Mock service health: {final_state['health_status']}")
    print("Execution events:")

    for event in final_state["events"]:
        print(f" - {event}")


if __name__ == "__main__":
    main()
