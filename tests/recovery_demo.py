import os
import uuid

from psycopg.conninfo import make_conninfo
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt, Command
from typing_extensions import TypedDict


class RecoveryState(TypedDict):
    events: list[str]


def step_one(state: RecoveryState) -> dict:
    return {"events": [*state["events"], "step_one_completed"]}


def step_two(state: RecoveryState) -> dict:
    approval = interrupt("Pause here to simulate an interruption")
    return {
        "events": [
            *state["events"],
            f"step_two_resumed:{approval}",
        ]
    }


def build_workflow(checkpointer):
    graph = StateGraph(RecoveryState)
    graph.add_node("step_one", step_one)
    graph.add_node("step_two", step_two)
    graph.add_edge(START, "step_one")
    graph.add_edge("step_one", "step_two")
    graph.add_edge("step_two", END)
    return graph.compile(checkpointer=checkpointer)


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
            "thread_id": f"agentforge-recovery-demo-{uuid.uuid4().hex}"
        }
    }

    with PostgresSaver.from_conn_string(connection_string) as checkpointer:
        checkpointer.setup()
        app = build_workflow(checkpointer)

        first_result = app.invoke({"events": []}, config)
        print("Workflow paused:", bool(first_result.get("__interrupt__")))

        resumed_result = app.invoke(
            Command(resume="continue"),
            config,
        )
        print("Recovery completed:", resumed_result["events"][-1] == "step_two_resumed:continue")
        print("Final events:", resumed_result["events"])


if __name__ == "__main__":
    main()
