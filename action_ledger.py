from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    insert,
    select,
    update,
    or_,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


metadata = MetaData()

actions = Table(
    "agent_actions",
    metadata,
    Column("action_key", String(200), primary_key=True),
    Column("action_type", String(100), nullable=False),
    Column("status", String(30), nullable=False),
    Column("lease_owner", String(200), nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("request_payload", JSON, nullable=False),
    Column("result_payload", JSON, nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)


def initialize_ledger(engine: Engine) -> None:
    """Create the action ledger table if it does not exist."""
    metadata.create_all(engine)



def claim_action(
    engine: Engine,
    action_key: str,
    action_type: str,
    request_payload: dict,
    lease_owner: str = "worker-1",
    lease_seconds: int = 60,
) -> dict:
    """Claim a new action or return its existing record."""
    from datetime import datetime, timedelta, timezone

    if not action_key.strip():
        raise ValueError("action_key cannot be empty")

    if not lease_owner.strip():
        raise ValueError("lease_owner cannot be empty")

    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")

    lease_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=lease_seconds
    )

    try:
        with engine.begin() as connection:
            connection.execute(
                insert(actions).values(
                    action_key=action_key,
                    action_type=action_type,
                    status="in_progress",
                    request_payload=request_payload,
                    lease_owner=lease_owner,
                    lease_expires_at=lease_expires_at,
                )
            )

        return {
            "claimed": True,
            "action_key": action_key,
            "action_type": action_type,
            "status": "in_progress",
            "request_payload": request_payload,
            "result_payload": None,
            "lease_owner": lease_owner,
            "lease_expires_at": lease_expires_at,
        }

    except IntegrityError as error:
        with engine.connect() as connection:
            existing = connection.execute(
                select(actions).where(
                    actions.c.action_key == action_key
                )
            ).mappings().one_or_none()

        if existing is None:
            raise error

        if (
            existing["action_type"] != action_type
            or existing["request_payload"] != request_payload
        ):
            raise ValueError(
                "The action key already belongs to a different request"
            )

        return {
            "claimed": False,
            "action_key": existing["action_key"],
            "action_type": existing["action_type"],
            "status": existing["status"],
            "request_payload": existing["request_payload"],
            "result_payload": existing["result_payload"],
            "lease_owner": existing["lease_owner"],
            "lease_expires_at": existing["lease_expires_at"],
        }


def mark_action_uncertain(
    engine: Engine,
    action_key: str,
    lease_owner: str,
) -> None:
    """Mark an in-progress action uncertain if the caller owns its lease."""
    from datetime import datetime, timezone

    if not action_key.strip():
        raise ValueError("action_key cannot be empty")

    if not lease_owner.strip():
        raise ValueError("lease_owner cannot be empty")

    now = datetime.now(timezone.utc)

    with engine.begin() as connection:
        result = connection.execute(
            update(actions)
            .where(
                actions.c.action_key == action_key,
                actions.c.status == "in_progress",
                actions.c.lease_owner == lease_owner,
                actions.c.lease_expires_at.is_not(None),
                actions.c.lease_expires_at > now,
            )
            .values(
                status="uncertain",
                updated_at=func.now(),
            )
        )

        if result.rowcount != 1:
            raise ValueError(
                "Action not found, lease expired, "
                "or worker does not own the lease"
            )

def get_action(
    engine: Engine,
    action_key: str,
) -> dict | None:
    """Retrieve an action record, or return None if it does not exist."""
    with engine.connect() as connection:
        existing = connection.execute(
            select(actions).where(
                actions.c.action_key == action_key
            )
        ).mappings().one_or_none()

    if existing is None:
        return None

    return {
        "action_key": existing["action_key"],
        "action_type": existing["action_type"],
        "status": existing["status"],
        "request_payload": existing["request_payload"],
        "result_payload": existing["result_payload"],
    }

def get_recovery_decision(action: dict | None) -> str:
    """Choose a safe next step based on the saved action record."""
    if action is None:
        return "not_found"

    status = action["status"]

    if status == "completed":
        return "use_saved_result"

    if status == "uncertain":
        return "reconcile_or_escalate"

    if status == "in_progress":
        return "inspect_before_retry"

    raise ValueError(f"Unsupported action status: {status}")

def reclaim_expired_lease(
    engine: Engine,
    action_key: str,
    new_lease_owner: str,
    lease_seconds: int = 60,
) -> bool:
    """Transfer an expired in-progress action lease to another worker."""
    from datetime import datetime, timedelta, timezone

    if not action_key.strip():
        raise ValueError("action_key must not be empty")

    if not new_lease_owner.strip():
        raise ValueError("new_lease_owner must not be empty")

    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")

    now = datetime.now(timezone.utc)
    new_expiry = now + timedelta(seconds=lease_seconds)

    with engine.begin() as connection:
        result = connection.execute(
            update(actions)
            .where(
                actions.c.action_key == action_key,
                actions.c.status == "in_progress",
                actions.c.lease_expires_at.is_not(None),
                actions.c.lease_expires_at <= now,
                # A reclaimed lease must have a different owner identity.
                # Reusing the same owner lets a stale worker appear current.
                or_(
                    actions.c.lease_owner.is_(None),
                    actions.c.lease_owner != new_lease_owner,
                ),
            )
            .values(
                lease_owner=new_lease_owner,
                lease_expires_at=new_expiry,
                updated_at=func.now(),
            )
        )

    return result.rowcount == 1

def complete_action(
    engine: Engine,
    action_key: str,
    result_payload: dict,
    lease_owner: str,
) -> None:
    """Complete an action only while the caller owns a valid lease."""
    from datetime import datetime, timezone

    if not action_key.strip():
        raise ValueError("action_key cannot be empty")

    if not lease_owner.strip():
        raise ValueError("lease_owner cannot be empty")

    now = datetime.now(timezone.utc)

    with engine.begin() as connection:
        result = connection.execute(
            update(actions)
            .where(
                actions.c.action_key == action_key,
                actions.c.status == "in_progress",
                actions.c.lease_owner == lease_owner,
                actions.c.lease_expires_at.is_not(None),
                actions.c.lease_expires_at > now,
            )
            .values(
                status="completed",
                result_payload=result_payload,
                updated_at=func.now(),
            )
        )

        if result.rowcount != 1:
            raise ValueError(
                "Action not found, lease expired, "
                "or worker does not own the lease"
            )
