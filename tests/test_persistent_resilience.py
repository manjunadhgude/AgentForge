import asyncio
import os

import pytest
import uuid
from typing import TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg.conninfo import make_conninfo

from resilience import TransientToolError, run_with_resilience


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("AGENTFORGE_DB_PASSWORD"),
        reason="PostgreSQL integration test requires AGENTFORGE_DB_PASSWORD",
    ),
]


class WorkflowState(TypedDict):
    events: list[str]
    health_status: str


def test_transient_tool_failure_recovers_with_postgres_checkpoint():
    calls = 0

    async def mock_tool() -> str:
        nonlocal calls
        calls += 1

        if calls == 1:
            raise TransientToolError("simulated temporary outage")

        return "healthy"

    def inspect_service(state: WorkflowState) -> dict:
        status = asyncio.run(
            run_with_resilience(
                mock_tool,
                max_attempts=3,
                timeout_seconds=2.0,
            )
        )
        return {
            "health_status": status,
            "events": [*state["events"], f"health_check:{status}"],
        }

    graph = StateGraph(WorkflowState)
    graph.add_node("inspect_service", inspect_service)
    graph.add_edge(START, "inspect_service")
    graph.add_edge("inspect_service", END)

    connection_string = make_conninfo(
        host=os.environ.get("AGENTFORGE_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("AGENTFORGE_DB_PORT", "5432")),
        dbname=os.environ.get("AGENTFORGE_DB_NAME", "agentforge"),
        user=os.environ.get("AGENTFORGE_DB_USER", "agentforge"),
        password=os.environ["AGENTFORGE_DB_PASSWORD"],
    )
    config = {
        "configurable": {
            "thread_id": f"agentforge-resilience-{uuid.uuid4().hex}"
        }
    }

    with PostgresSaver.from_conn_string(connection_string) as checkpointer:
        checkpointer.setup()
        app = graph.compile(checkpointer=checkpointer)

        result = app.invoke(
            {"events": [], "health_status": "unknown"},
            config,
        )
        snapshot = app.get_state(config)

    assert calls == 2
    assert result["health_status"] == "healthy"
    assert result["events"] == ["health_check:healthy"]
    assert snapshot.values["health_status"] == "healthy"
    assert snapshot.values["events"] == ["health_check:healthy"]
