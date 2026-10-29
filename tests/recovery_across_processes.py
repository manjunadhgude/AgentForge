import os
import sys
from typing import TypedDict

from psycopg import conninfo
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class State(TypedDict):
    events: list[str]


def step_one(state: State) -> State:
    return {"events": [*state["events"], "step_one_completed"]}


def step_two(state: State) -> State:
    answer = interrupt("Waiting for the second process to resume")
    return {"events": [*state["events"], f"step_two_resumed:{answer}"]}


def build_graph():
    graph = StateGraph(State)
    graph.add_node("step_one", step_one)
    graph.add_node("step_two", step_two)
    graph.add_edge(START, "step_one")
    graph.add_edge("step_one", "step_two")
    graph.add_edge("step_two", END)
    return graph


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    thread_id = os.environ["AGENTFORGE_TEST_THREAD_ID"]
    password = os.environ["AGENTFORGE_DB_PASSWORD"]

    connection_string = conninfo.make_conninfo(
        host="127.0.0.1",
        port=5432,
        dbname="agentforge",
        user="agentforge",
        password=password,
    )
    config = {"configurable": {"thread_id": thread_id}}

    with PostgresSaver.from_conn_string(connection_string) as checkpointer:
        checkpointer.setup()
        app = build_graph().compile(checkpointer=checkpointer)

        if mode == "pause":
            result = app.invoke({"events": []}, config=config)
            paused = bool(result.get("__interrupt__"))
            print(f"Process 1 paused: {paused}", flush=True)

            if not paused:
                print(f"Unexpected pause result: {result!r}", flush=True)
                return 1

            if os.environ.get("AGENTFORGE_HOLD_AFTER_CHECKPOINT") == "1":
                # invoke() has returned after the interrupt checkpoint was saved.
                print("CHECKPOINT_SAVED_AND_WAITING", flush=True)
                sys.stdin.readline()
                print("Process 1 released.", flush=True)
            else:
                print("Process 1 is exiting.", flush=True)

            return 0

        if mode == "resume":
            result = app.invoke(Command(resume="continue"), config=config)
            events = result.get("events", [])
            recovered = events == [
                "step_one_completed",
                "step_two_resumed:continue",
            ]
            print(f"Process 2 recovered: {recovered}", flush=True)
            print(f"Final events: {events!r}", flush=True)
            return 0 if recovered else 1

        print("Unknown mode. Use 'pause' or 'resume'.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
