import asyncio

import pytest

from resilience import (
    TransientToolError,
    ToolExecutionTimeout,
    run_with_resilience,
)


def test_transient_failure_recovers_after_one_retry():
    calls = {"count": 0}
    retry_events = []

    async def operation():
        calls["count"] += 1
        if calls["count"] == 1:
            raise TransientToolError("temporary simulated tool failure")
        return {"status": "recovered"}

    result = asyncio.run(
        run_with_resilience(
            operation,
            max_attempts=2,
            timeout_seconds=1.0,
            retry_delay_seconds=0,
            on_retry=retry_events.append,
        )
    )

    assert result == {"status": "recovered"}
    assert calls["count"] == 2
    assert len(retry_events) == 1


def test_persistent_transient_failure_stops_at_attempt_limit():
    calls = {"count": 0}

    async def operation():
        calls["count"] += 1
        raise TransientToolError("simulated persistent failure")

    with pytest.raises(TransientToolError):
        asyncio.run(
            run_with_resilience(
                operation,
                max_attempts=3,
                timeout_seconds=1.0,
                retry_delay_seconds=0,
            )
        )

    assert calls["count"] == 3


def test_non_retryable_exception_is_not_retried():
    calls = {"count": 0}

    async def operation():
        calls["count"] += 1
        raise ValueError("simulated invalid input")

    with pytest.raises(ValueError, match="simulated invalid input"):
        asyncio.run(
            run_with_resilience(
                operation,
                max_attempts=4,
                timeout_seconds=1.0,
                retry_delay_seconds=0,
            )
        )

    assert calls["count"] == 1


def test_slow_operation_times_out_and_is_bounded():
    calls = {"count": 0}

    async def operation():
        calls["count"] += 1
        await asyncio.sleep(0.05)
        return {"unexpected": "success"}

    with pytest.raises(ToolExecutionTimeout):
        asyncio.run(
            run_with_resilience(
                operation,
                max_attempts=2,
                timeout_seconds=0.005,
                retry_delay_seconds=0,
            )
        )

    assert calls["count"] == 2


def test_timeout_can_recover_on_later_attempt():
    calls = {"count": 0}

    async def operation():
        calls["count"] += 1
        if calls["count"] == 1:
            await asyncio.sleep(0.05)
        return {"attempt": calls["count"]}

    result = asyncio.run(
        run_with_resilience(
            operation,
            max_attempts=2,
            timeout_seconds=0.01,
            retry_delay_seconds=0,
        )
    )

    assert result == {"attempt": 2}
    assert calls["count"] == 2


def test_retry_observer_receives_attempt_and_exception_details():
    calls = {"count": 0}
    events = []

    async def operation():
        calls["count"] += 1
        if calls["count"] < 3:
            raise TransientToolError(f"temporary-{calls['count']}")
        return {"ok": True}

    result = asyncio.run(
        run_with_resilience(
            operation,
            max_attempts=3,
            timeout_seconds=1.0,
            retry_delay_seconds=0,
            on_retry=events.append,
        )
    )

    assert result == {"ok": True}
    assert len(events) == 2
    assert all(hasattr(event, "failed_attempt") for event in events)
    assert all(hasattr(event, "error_type") for event in events)
    assert [event.failed_attempt for event in events] == [1, 2]
    assert all(event.error_type == "TransientToolError" for event in events)


def test_retry_does_not_happen_after_success():
    calls = {"count": 0}
    events = []

    async def operation():
        calls["count"] += 1
        return {"status": "ok"}

    result = asyncio.run(
        run_with_resilience(
            operation,
            max_attempts=5,
            timeout_seconds=1.0,
            retry_delay_seconds=0,
            on_retry=events.append,
        )
    )

    assert result == {"status": "ok"}
    assert calls["count"] == 1
    assert events == []
