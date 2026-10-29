import asyncio
import unittest

from resilience import (
    ToolExecutionTimeout,
    TransientToolError,
    run_with_resilience,
)


class ResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_temporary_failure_then_succeeds(self):
        calls = 0

        async def operation():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise TransientToolError("temporary failure")
            return "success"

        result = await run_with_resilience(operation, max_attempts=3)

        self.assertEqual(result, "success")
        self.assertEqual(calls, 3)

    async def test_does_not_retry_permanent_failure(self):
        calls = 0

        async def operation():
            nonlocal calls
            calls += 1
            raise ValueError("invalid input")

        with self.assertRaises(ValueError):
            await run_with_resilience(operation, max_attempts=3)

        self.assertEqual(calls, 1)

    async def test_timeout_can_recover_on_next_attempt(self):
        calls = 0

        async def operation():
            nonlocal calls
            calls += 1
            if calls == 1:
                await asyncio.sleep(0.1)
            return "recovered"

        result = await run_with_resilience(
            operation,
            max_attempts=2,
            timeout_seconds=0.01,
        )

        self.assertEqual(result, "recovered")
        self.assertEqual(calls, 2)

    async def test_timeout_exhaustion_raises_clear_error(self):
        async def operation():
            await asyncio.sleep(0.1)

        with self.assertRaises(ToolExecutionTimeout):
            await run_with_resilience(
                operation,
                max_attempts=2,
                timeout_seconds=0.01,
            )

    async def test_transient_failure_stops_at_attempt_limit(self):
        calls = 0

        async def operation():
            nonlocal calls
            calls += 1
            raise TransientToolError("still unavailable")

        with self.assertRaises(TransientToolError):
            await run_with_resilience(operation, max_attempts=3)

        self.assertEqual(calls, 3)

    async def test_rejects_invalid_configuration(self):
        async def operation():
            return "success"

        with self.assertRaises(ValueError):
            await run_with_resilience(operation, max_attempts=0)

        with self.assertRaises(ValueError):
            await run_with_resilience(operation, timeout_seconds=0)


    async def test_rejects_non_finite_numeric_configuration(self):
        async def operation():
            return "ok"

        invalid_settings = (
            {"timeout_seconds": float("nan")},
            {"retry_delay_seconds": float("inf")},
            {"backoff_multiplier": float("nan")},
            {"max_retry_delay_seconds": float("inf")},
        )
        for settings in invalid_settings:
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    await run_with_resilience(operation, **settings)


if __name__ == "__main__":
    unittest.main()
