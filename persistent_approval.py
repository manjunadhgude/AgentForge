"""PostgreSQL-compatible persistent human approval storage."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    JSON,
    MetaData,
    String,
    Table,
    insert,
    select,
    update,
    func,
)
from sqlalchemy.engine import Engine

from tool_runtime import ToolExecutionError


metadata = MetaData()

approvals = Table(
    "agent_tool_approvals",
    metadata,
    Column("request_id", String(36), primary_key=True),
    Column("tool_name", String(100), nullable=False),
    Column("arguments", JSON, nullable=False),
    Column("status", String(20), nullable=False),
    Column("approved_by", String(200), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)


class PersistentApprovalManager:
    """Store approval requests durably and consume each approval once."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def initialize(self) -> None:
        """Create the approval table if it does not already exist."""
        metadata.create_all(self.engine)

    def request(
        self,
        tool_name: str,
        arguments: dict,
        *,
        expires_in_seconds: int = 900,
    ) -> str:
        if not tool_name.strip():
            raise ValueError("tool_name cannot be empty")
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be a dictionary")
        if expires_in_seconds <= 0:
            raise ValueError("expires_in_seconds must be positive")

        now = datetime.now(timezone.utc)
        request_id = str(uuid4())

        with self.engine.begin() as connection:
            connection.execute(
                insert(approvals).values(
                    request_id=request_id,
                    tool_name=tool_name,
                    arguments=dict(arguments),
                    status="pending",
                    approved_by=None,
                    created_at=now,
                    expires_at=now + timedelta(
                        seconds=expires_in_seconds
                    ),
                    updated_at=now,
                )
            )

        return request_id

    def approve(self, request_id: str, *, approved_by: str) -> None:
        if not approved_by.strip():
            raise ValueError("approved_by must not be empty")

        now = datetime.now(timezone.utc)

        with self.engine.begin() as connection:
            result = connection.execute(
                update(approvals)
                .where(
                    approvals.c.request_id == request_id,
                    approvals.c.status == "pending",
                    approvals.c.expires_at > now,
                )
                .values(
                    status="approved",
                    approved_by=approved_by,
                    updated_at=now,
                )
            )

            if result.rowcount != 1:
                raise ToolExecutionError(
                    "Approval request is missing, expired, "
                    "or no longer pending"
                )

    def consume(
        self,
        request_id: str | None,
        *,
        tool_name: str,
        arguments: dict,
    ) -> None:
        if not request_id:
            raise ToolExecutionError("Approval required before execution")

        now = datetime.now(timezone.utc)

        with self.engine.begin() as connection:
            record = connection.execute(
                select(approvals).where(
                    approvals.c.request_id == request_id,
                    approvals.c.status == "approved",
                    approvals.c.expires_at > now,
                )
            ).mappings().one_or_none()

            if record is None:
                raise ToolExecutionError(
                    "Approval is missing, expired, or not approved"
                )

            if record["tool_name"] != tool_name:
                raise ToolExecutionError(
                    "Approval is for a different tool"
                )

            if record["arguments"] != arguments:
                raise ToolExecutionError(
                    "Approval arguments do not match"
                )

            # Conditional update prevents a second consumer from reusing it.
            result = connection.execute(
                update(approvals)
                .where(
                    approvals.c.request_id == request_id,
                    approvals.c.status == "approved",
                    approvals.c.expires_at > now,
                )
                .values(
                    status="consumed",
                    updated_at=now,
                )
            )

            if result.rowcount != 1:
                raise ToolExecutionError(
                    "Approval was already consumed or expired"
                )

    def get(self, request_id: str) -> dict | None:
        with self.engine.connect() as connection:
            record = connection.execute(
                select(approvals).where(
                    approvals.c.request_id == request_id
                )
            ).mappings().one_or_none()

        return dict(record) if record is not None else None
