"""Bounded asynchronous retries, timeouts, and retry instrumentation."""
import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


class TransientToolError(Exception):
    """A temporary tool failure that may succeed when retried."""


class ToolExecutionTimeout(TimeoutError):
    """The tool operation exceeded its allowed execution time."""


@dataclass(frozen=True)
class RetryEvent:
    """One retry decision, suitable for logs and metrics."""
    failed_attempt: int
    max_attempts: int
    error_type: str
    delay_seconds: float


async def run_with_resilience(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    timeout_seconds: float = 2.0,
    retry_delay_seconds: float = 0.0,
    retryable_exceptions: tuple[type[Exception], ...] = (TransientToolError,),
    backoff_multiplier: float = 2.0,
    max_retry_delay_seconds: float = 30.0,
    on_retry: Callable[[RetryEvent], None] | None = None,
) -> T:
    """Run an async operation with bounded retries and per-attempt timeout.

    `retry_delay_seconds` is the base delay. When nonzero, retry delays grow
    exponentially and are capped by `max_retry_delay_seconds`. Timeouts are
    retryable; other exceptions are retried only when explicitly listed.
    `on_retry` receives an event before the delay and must be observational.
    """
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("max_attempts must be an integer of at least 1")

    numeric_settings = {
        "timeout_seconds": timeout_seconds,
        "retry_delay_seconds": retry_delay_seconds,
        "backoff_multiplier": backoff_multiplier,
        "max_retry_delay_seconds": max_retry_delay_seconds,
    }
    for name, value in numeric_settings.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds cannot be negative")
    if backoff_multiplier < 1:
        raise ValueError("backoff_multiplier must be at least 1")
    if max_retry_delay_seconds < 0:
        raise ValueError("max_retry_delay_seconds cannot be negative")

    for attempt in range(1, max_attempts + 1):
        try:
            return await asyncio.wait_for(operation(), timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            error = ToolExecutionTimeout(
                f"Tool operation timed out after {timeout_seconds} seconds"
            )
            error.__cause__ = exc
        except retryable_exceptions as exc:
            error = exc

        if attempt == max_attempts:
            raise error

        delay = min(
            retry_delay_seconds * (backoff_multiplier ** (attempt - 1)),
            max_retry_delay_seconds,
        )
        if on_retry is not None:
            on_retry(
                RetryEvent(
                    failed_attempt=attempt,
                    max_attempts=max_attempts,
                    error_type=type(error).__name__,
                    delay_seconds=delay,
                )
            )
        if delay:
            await asyncio.sleep(delay)

    raise RuntimeError("Unreachable resilience state")
