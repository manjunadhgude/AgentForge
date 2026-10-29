import asyncio
import pytest

from resilience import RetryEvent, TransientToolError, run_with_resilience


def test_exponential_backoff_emits_retry_events():
    async def scenario():
        calls = 0
        events = []

        async def flaky():
            nonlocal calls
            calls += 1
            if calls < 4:
                raise TransientToolError("temporary")
            return "ok"

        result = await run_with_resilience(
            flaky,
            max_attempts=4,
            timeout_seconds=1,
            retry_delay_seconds=0.001,
            backoff_multiplier=2,
            max_retry_delay_seconds=0.003,
            on_retry=events.append,
        )
        assert result == "ok"
        assert calls == 4
        assert [event.failed_attempt for event in events] == [1, 2, 3]
        assert [event.delay_seconds for event in events] == pytest.approx([0.001, 0.002, 0.003])
        assert all(isinstance(event, RetryEvent) for event in events)
        assert all(event.error_type == "TransientToolError" for event in events)
    asyncio.run(scenario())


def test_retry_observer_is_not_called_after_final_failure():
    async def scenario():
        events = []

        async def broken():
            raise TransientToolError("still broken")

        with pytest.raises(TransientToolError):
            await run_with_resilience(broken, max_attempts=1, on_retry=events.append)
        assert events == []
    asyncio.run(scenario())


def test_backoff_configuration_is_validated():
    async def scenario():
        async def ok():
            return True

        with pytest.raises(ValueError, match="backoff_multiplier"):
            await run_with_resilience(ok, backoff_multiplier=0.5)
        with pytest.raises(ValueError, match="max_retry_delay_seconds"):
            await run_with_resilience(ok, max_retry_delay_seconds=-1)
    asyncio.run(scenario())
