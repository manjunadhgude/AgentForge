"""Ledger-backed execution that avoids blindly replaying uncertain actions."""
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.engine import Engine

from action_ledger import (
    claim_action,
    complete_action,
    get_recovery_decision,
    initialize_ledger,
    mark_action_uncertain,
)


class ActionRecoveryRequired(RuntimeError):
    """An action cannot safely be run again without reconciliation."""


class ActionExecutionFailed(RuntimeError):
    """An operation failed and its outcome must be treated conservatively."""


class ActionRuntime:
    """Execute dictionary-in/dictionary-out operations through the action ledger.

    Completed actions return their stored result. Existing in-progress or
    uncertain actions are never executed a second time automatically.
    A thrown operation error is recorded as uncertain while the lease is valid.
    This provides safe replay handling for recorded outcomes, but cannot make
    arbitrary external side effects exactly-once without downstream idempotency.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        worker_id: str = "worker-1",
        lease_seconds: int = 60,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id cannot be empty")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.engine = engine
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        initialize_ledger(engine)

    def execute(
        self,
        action_key: str,
        action_type: str,
        request_payload: dict[str, Any],
        operation: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        claim = claim_action(
            self.engine,
            action_key,
            action_type,
            request_payload,
            lease_owner=self.worker_id,
            lease_seconds=self.lease_seconds,
        )

        if not claim["claimed"]:
            decision = get_recovery_decision(claim)
            if decision == "use_saved_result":
                return {
                    "action_key": action_key,
                    "status": "completed",
                    "result": claim["result_payload"],
                    "replayed": True,
                }
            if decision == "reconcile_or_escalate":
                raise ActionRecoveryRequired(
                    f"Action {action_key!r} has uncertain outcome; reconcile before retry"
                )
            if decision == "inspect_before_retry":
                expiry = claim.get("lease_expires_at")
                if expiry is not None and expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                state = "expired" if expiry is not None and expiry <= now else "active"
                raise ActionRecoveryRequired(
                    f"Action {action_key!r} is still in progress ({state} lease); "
                    "inspect or reconcile before retry"
                )
            raise ActionRecoveryRequired(f"Cannot recover action {action_key!r}: {decision}")

        try:
            result = operation(dict(request_payload))
            if not isinstance(result, dict):
                raise TypeError("Action operation must return a dictionary")
        except Exception as exc:
            try:
                mark_action_uncertain(
                    self.engine,
                    action_key,
                    lease_owner=self.worker_id,
                )
            except Exception:
                # Preserve the original failure; a missing/expired lease itself
                # requires manual reconciliation rather than an automatic retry.
                pass
            raise ActionExecutionFailed(
                f"Action {action_key!r} failed; inspect its ledger state before retry"
            ) from exc

        try:
            complete_action(
                self.engine,
                action_key,
                result,
                lease_owner=self.worker_id,
            )
        except Exception as exc:
            raise ActionExecutionFailed(
                f"Action {action_key!r} ran but completion was not recorded; "
                "reconcile before retry"
            ) from exc

        return {
            "action_key": action_key,
            "status": "completed",
            "result": result,
            "replayed": False,
        }
