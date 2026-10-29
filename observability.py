"""Small, dependency-free observability primitives for AgentForge.

Events deliberately exclude tool arguments and result payloads by default.
Callers should only put non-sensitive, already-sanitized metadata in attributes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
from typing import Any, Mapping


@dataclass(frozen=True)
class ExecutionEvent:
    event_type: str
    action_key: str | None = None
    attempt: int | None = None
    status: str | None = None
    duration_ms: float | None = None
    error_type: str | None = None
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_type.strip():
            raise ValueError("event_type cannot be empty")
        if self.attempt is not None and self.attempt < 1:
            raise ValueError("attempt must be at least 1")
        if self.duration_ms is not None and (
            not math.isfinite(self.duration_ms) or self.duration_ms < 0
        ):
            raise ValueError("duration_ms must be finite and non-negative")


class JsonlEventSink:
    """Append one JSON event per line; safe for concurrent threads in-process."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def emit(self, event: ExecutionEvent | Mapping[str, Any]) -> None:
        if isinstance(event, ExecutionEvent):
            record = asdict(event)
        elif isinstance(event, Mapping):
            record = dict(event)
        else:
            raise TypeError("event must be ExecutionEvent or a mapping")
        # Validate serializability before opening the file to avoid partial writes.
        line = json.dumps(record, separators=(",", ":"), sort_keys=True, allow_nan=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line + "\n")


class ReliabilityMetrics:
    """Thread-safe counters and duration summaries for local reliability tests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._durations_ms: dict[str, list[float]] = {}

    def increment(self, name: str, amount: int = 1) -> None:
        if not name.strip():
            raise ValueError("metric name cannot be empty")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise ValueError("amount must be a non-negative integer")
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def observe_duration(self, name: str, duration_ms: float) -> None:
        if not name.strip():
            raise ValueError("metric name cannot be empty")
        if not math.isfinite(duration_ms) or duration_ms < 0:
            raise ValueError("duration_ms must be finite and non-negative")
        with self._lock:
            self._durations_ms.setdefault(name, []).append(float(duration_ms))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = dict(sorted(self._counters.items()))
            observations = {
                name: list(values)
                for name, values in sorted(self._durations_ms.items())
            }
        durations: dict[str, dict[str, float | int]] = {}
        for name, values in observations.items():
            ordered = sorted(values)
            if not ordered:
                continue
            p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
            durations[name] = {
                "count": len(ordered),
                "min_ms": ordered[0],
                "max_ms": ordered[-1],
                "mean_ms": sum(ordered) / len(ordered),
                "p95_ms": ordered[p95_index],
            }
        return {"counters": counters, "durations": durations}
