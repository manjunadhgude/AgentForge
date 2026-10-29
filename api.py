from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Engine

from persistent_approval import PersistentApprovalManager
from tool_runtime import ToolExecutionError, ToolRegistry


MIN_TOKEN_LENGTH = 32


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ApprovalRequest(StrictRequest):
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any]
    expires_in_seconds: int = Field(default=900, gt=0, le=86400)


class ToolExecutionRequest(StrictRequest):
    arguments: dict[str, Any]
    approval_id: str | None = None


class LLMProposalRequest(StrictRequest):
    request: str = Field(min_length=1, max_length=4000)


def _token_matches(expected: str | None, authorization: str | None) -> bool:
    if not expected or len(expected) < MIN_TOKEN_LENGTH:
        raise HTTPException(
            status_code=503,
            detail="API authentication is not configured securely",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    supplied = authorization[7:].strip()
    if not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    return True


def create_app(
    engine: Engine,
    registry: ToolRegistry | None = None,
    *,
    api_token: str | None = None,
    approver_token: str | None = None,
    approver_id: str | None = None,
    llm_planner: Any | None = None,
) -> FastAPI:
    """Create the API. Mutating/tool routes fail closed without strong tokens."""
    api_token = api_token if api_token is not None else os.getenv("AGENTFORGE_API_TOKEN")
    approver_token = (
        approver_token
        if approver_token is not None
        else os.getenv("AGENTFORGE_APPROVER_TOKEN")
    )
    approver_id = (
        approver_id
        if approver_id is not None
        else os.getenv("AGENTFORGE_APPROVER_ID")
    )
    if approver_id is not None:
        approver_id = approver_id.strip() or None

    approvals = PersistentApprovalManager(engine)
    approvals.initialize()
    tools = registry if registry is not None else ToolRegistry(approvals=approvals)
    if registry is not None:
        tools.approvals = approvals

    app = FastAPI(title="AgentForge API", version="0.2.0")
    app.state.engine = engine
    app.state.approvals = approvals
    app.state.tools = tools
    app.state.llm_planner = llm_planner

    def require_api_token(authorization: str | None) -> None:
        _token_matches(api_token, authorization)

    def require_approver_token(authorization: str | None) -> None:
        _token_matches(approver_token, authorization)
        if not approver_id:
            raise HTTPException(
                status_code=503,
                detail="Approver identity is not configured",
            )

    @app.get("/health")
    def health() -> dict[str, str]:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        return {"status": "ok", "service": "AgentForge"}

    @app.get("/tools")
    def list_tools(
        authorization: str | None = Header(default=None),
    ) -> list[dict[str, Any]]:
        require_api_token(authorization)
        return tools.list_tools()

    @app.post("/approvals", status_code=201)
    def request_approval(
        body: ApprovalRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        require_api_token(authorization)
        spec = tools._tools.get(body.tool_name)
        if spec is None:
            raise HTTPException(status_code=404, detail="Tool is not allowlisted")
        try:
            validated = spec.args_model.model_validate(body.arguments)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail="Tool arguments failed schema validation",
            ) from exc
        if not spec.requires_approval:
            raise HTTPException(status_code=400, detail="This tool does not require approval")
        try:
            request_id = approvals.request(
                body.tool_name,
                validated.model_dump(),
                expires_in_seconds=body.expires_in_seconds,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"request_id": request_id, "status": "pending"}

    @app.post("/approvals/{request_id}/approve")
    def approve_request(
        request_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        require_approver_token(authorization)
        # Identity is configured by the service, never accepted from request JSON.
        assert approver_id is not None
        try:
            approvals.approve(request_id, approved_by=approver_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ToolExecutionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"request_id": request_id, "status": "approved"}

    @app.post("/llm/propose")
    def propose_tool(
        body: LLMProposalRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_api_token(authorization)
        planner = app.state.llm_planner
        if planner is None:
            try:
                from llm_agent import OpenAICompatibleToolPlanner
                planner = OpenAICompatibleToolPlanner(tools)
                app.state.llm_planner = planner
            except ValueError as exc:
                raise HTTPException(status_code=503, detail="LLM provider is not configured") from exc
        try:
            proposal = planner.propose(body.request)
            spec = tools.get_tool_spec(proposal.tool_name)
            if spec is None:
                raise ToolExecutionError("Tool is not allowlisted")
            # Revalidate at the API boundary even when a custom planner is injected.
            validated_arguments = spec.args_model.model_validate(proposal.arguments)
            proposal_arguments = validated_arguments.model_dump()
        except ToolExecutionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except Exception as exc:
            # Keep provider details, request bodies, and credentials out of API responses.
            from llm_agent import LLMIntegrationError
            if isinstance(exc, LLMIntegrationError):
                raise HTTPException(status_code=502, detail="LLM could not produce a safe tool proposal") from exc
            raise HTTPException(status_code=502, detail="LLM proposal failed") from exc
        return {
            "tool_name": proposal.tool_name,
            "arguments": proposal_arguments,
            "model": proposal.model,
            "requires_approval": spec.requires_approval,
            "executed": False,
        }

    @app.post("/tools/{tool_name}/execute")
    def execute_tool(
        tool_name: str,
        body: ToolExecutionRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_api_token(authorization)
        try:
            result = tools.execute(
                tool_name,
                body.arguments,
                approval_id=body.approval_id,
            )
        except ToolExecutionError as exc:
            message = str(exc)
            status_code = 404 if message == "Tool is not allowlisted" else 403
            raise HTTPException(status_code=status_code, detail=message) from exc
        return {"tool_name": tool_name, "result": result}

    return app
