import os
from typing import TypedDict

from psycopg.conninfo import make_conninfo
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph


class AgentState(TypedDict):
    incident_id: str
    events: list[str]
    health_status: str


def inspect_service(state: AgentState) -> dict:
    status = (
        "degraded"
        if state["incident_id"] == "INC-001"
        else "healthy"
    )
    event = f"Mock health check for {state['incident_id']}: {status}"

    return {
        "health_status": status,
        "events": [*state["events"], event],
    }


def build_workflow(checkpointer):
    workflow = StateGraph(AgentState)
    workflow.add_node("inspect_service", inspect_service)
    workflow.add_edge(START, "inspect_service")
    workflow.add_edge("inspect_service", END)

    return workflow.compile(checkpointer=checkpointer)


def main():
    connection_string = make_conninfo(
        host="127.0.0.1",
        port=5432,
        dbname="agentforge",
        user="agentforge",
        password=os.environ["AGENTFORGE_DB_PASSWORD"],
    )

    config = {
        "configurable": {
            "thread_id": "agentforge-persistence-test-001"
        }
    }

    initial_state: AgentState = {
        "incident_id": "INC-001",
        "events": [],
        "health_status": "unknown",
    }

    with PostgresSaver.from_conn_string(connection_string) as checkpointer:
        app = build_workflow(checkpointer)

        result = app.invoke(initial_state, config)
        saved_snapshot = app.get_state(config)

        print("Persistent workflow: SUCCESS")
        print(f"Incident: {result['incident_id']}")
        print(f"Health: {result['health_status']}")
        print(f"Saved checkpoint retrieved: {bool(saved_snapshot.values)}")
        print(f"Saved health: {saved_snapshot.values['health_status']}")


if __name__ == "__main__":
    main()
