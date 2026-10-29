"""Strict allowlisted mock tools and approval-gated execution."""
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OrderLookupArgs(StrictArgs):
    order_id: str = Field(min_length=1, max_length=100)


class RefundArgs(StrictArgs):
    order_id: str = Field(min_length=1, max_length=100)
    amount_cents: int = Field(gt=0, le=500000)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    requires_approval: bool = False


class ToolExecutionError(RuntimeError):
    """Raised when a tool cannot safely execute."""


class ApprovalManager:
    """Single-process approval store for development and deterministic tests.

    This store is intentionally in-memory. It is not suitable for multi-worker
    production deployments; persistent approval storage and authenticated
    approval endpoints are added in a later integration batch.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._requests: dict[str, dict[str, Any]] = {}

    def request(self, tool_name: str, arguments: dict[str, Any]) -> str:
        request_id = str(uuid4())
        with self._lock:
            self._requests[request_id] = {
                "tool_name": tool_name,
                "arguments": dict(arguments),
                "status": "pending",
            }
        return request_id

    def approve(self, request_id: str, *, approved_by: str) -> None:
        if not approved_by.strip():
            raise ValueError("approved_by must not be empty")

        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                raise ToolExecutionError("Approval request not found")
            if request["status"] != "pending":
                raise ToolExecutionError("Approval is not pending")
            request["status"] = "approved"
            request["approved_by"] = approved_by

    def consume(
        self,
        request_id: str | None,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        if not request_id:
            raise ToolExecutionError("Approval required before execution")

        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                raise ToolExecutionError("Approval request not found")
            if request["status"] != "approved":
                raise ToolExecutionError("Approval has not been granted")
            if request["tool_name"] != tool_name:
                raise ToolExecutionError("Approval is for a different tool")
            if request["arguments"] != arguments:
                raise ToolExecutionError("Approval arguments do not match")
            request["status"] = "consumed"


def _mock_order_status(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_id": args["order_id"],
        "status": "delivered",
        "mode": "mock",
    }


def _mock_refund(args: dict[str, Any]) -> dict[str, Any]:
    # Deliberately no real payment/refund integration.
    return {
        "order_id": args["order_id"],
        "amount_cents": args["amount_cents"],
        "simulated": True,
        "status": "refund_simulated",
    }


class ToolRegistry:
    def __init__(self, approvals: Any | None = None) -> None:
        # Accept either the in-memory manager or PersistentApprovalManager.
        # Both implement request/approve/consume with the same interface.
        self.approvals = approvals if approvals is not None else ApprovalManager()
        self._tools: dict[str, ToolSpec] = {}
        self.register(
            ToolSpec(
                name="get_order_status",
                description="Read a mock order status.",
                args_model=OrderLookupArgs,
                handler=_mock_order_status,
            )
        )
        self.register(
            ToolSpec(
                name="issue_refund",
                description="Simulate a refund; requires explicit approval.",
                args_model=RefundArgs,
                handler=_mock_refund,
                requires_approval=True,
            )
        )

    def register(self, spec: ToolSpec) -> None:
        if not spec.name or spec.name in self._tools:
            raise ValueError("Tool name must be non-empty and unique")
        self._tools[spec.name] = spec

    def get_tool_spec(self, tool_name: str) -> ToolSpec | None:
        """Return a registered tool specification for trusted orchestration code."""
        return self._tools.get(tool_name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "requires_approval": spec.requires_approval,
            }
            for spec in self._tools.values()
        ]

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        spec = self._tools.get(tool_name)
        if spec is None:
            raise ToolExecutionError("Tool is not allowlisted")

        try:
            validated = spec.args_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolExecutionError(
                "Tool arguments failed schema validation"
            ) from exc

        clean_arguments = validated.model_dump()

        # Check approval before invoking any side-effecting handler.
        if spec.requires_approval:
            self.approvals.consume(
                approval_id,
                tool_name=tool_name,
                arguments=clean_arguments,
            )

        return spec.handler(clean_arguments)
