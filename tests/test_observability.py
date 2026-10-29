import json
import threading

import pytest

from observability import ExecutionEvent, JsonlEventSink, ReliabilityMetrics


def test_event_defaults_to_utc_timestamp_and_serializes(tmp_path):
    event = ExecutionEvent(event_type="action_started", action_key="demo-1")
    sink = JsonlEventSink(tmp_path / "events.jsonl")
    sink.emit(event)
    record = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8"))
    assert record["event_type"] == "action_started"
    assert record["action_key"] == "demo-1"
    assert "+00:00" in record["timestamp_utc"]


def test_jsonl_sink_appends_multiple_events(tmp_path):
    path = tmp_path / "nested" / "events.jsonl"
    sink = JsonlEventSink(path)
    sink.emit({"event_type": "started"})
    sink.emit({"event_type": "finished"})
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [record["event_type"] for record in records] == ["started", "finished"]


def test_jsonl_sink_rejects_non_serializable_record_without_partial_line(tmp_path):
    path = tmp_path / "events.jsonl"
    sink = JsonlEventSink(path)
    with pytest.raises(TypeError):
        sink.emit({"event_type": "bad", "object": object()})
    assert not path.exists()


def test_event_validates_required_fields_and_attempt():
    with pytest.raises(ValueError):
        ExecutionEvent(event_type="")
    with pytest.raises(ValueError):
        ExecutionEvent(event_type="retry", attempt=0)


@pytest.mark.parametrize("duration", [-1, float("nan"), float("inf")])
def test_event_rejects_invalid_duration(duration):
    with pytest.raises(ValueError):
        ExecutionEvent(event_type="finished", duration_ms=duration)


def test_metrics_counters_and_duration_summary():
    metrics = ReliabilityMetrics()
    metrics.increment("attempts")
    metrics.increment("attempts", 2)
    for value in [10, 20, 30, 40]:
        metrics.observe_duration("tool", value)
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["attempts"] == 3
    assert snapshot["durations"]["tool"]["count"] == 4
    assert snapshot["durations"]["tool"]["min_ms"] == 10
    assert snapshot["durations"]["tool"]["max_ms"] == 40
    assert snapshot["durations"]["tool"]["mean_ms"] == 25
    assert snapshot["durations"]["tool"]["p95_ms"] == 40


def test_metrics_reject_invalid_counter_and_duration():
    metrics = ReliabilityMetrics()
    with pytest.raises(ValueError):
        metrics.increment("attempts", -1)
    with pytest.raises(ValueError):
        metrics.observe_duration("tool", -0.1)


def test_metrics_snapshot_is_detached():
    metrics = ReliabilityMetrics()
    metrics.increment("success")
    snapshot = metrics.snapshot()
    snapshot["counters"]["success"] = 999
    assert metrics.snapshot()["counters"]["success"] == 1


def test_metrics_thread_safety_for_counter_updates():
    metrics = ReliabilityMetrics()
    threads = [
        threading.Thread(target=lambda: [metrics.increment("calls") for _ in range(500)])
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert metrics.snapshot()["counters"]["calls"] == 2000


def test_sink_rejects_unsupported_event_type(tmp_path):
    with pytest.raises(TypeError):
        JsonlEventSink(tmp_path / "events.jsonl").emit("not-an-event")
