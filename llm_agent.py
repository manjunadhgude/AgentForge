"""Optional OpenAI-compatible LLM tool proposer for AgentForge.

The model may propose one registered tool call; it never grants approval and
never executes the tool itself. ToolRegistry remains the authority for
allowlisting, argument validation, and approval-gated execution.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from tool_runtime import ToolExecutionError, ToolRegistry


class LLMConfigurationError(ValueError):
    """LLM provider settings are missing or invalid."""


class LLMIntegrationError(RuntimeError):
    """A provider request or model response could not be used safely."""


@dataclass(frozen=True)
class ToolProposal:
    tool_name: str
    arguments: dict[str, Any]
    model: str


Transport = Callable[[Request, float], bytes]


def _default_transport(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _tool_schemas(registry: ToolRegistry) -> list[dict[str, Any]]:
    schemas: list[dict[str, Any]] = []
    for tool in registry.list_tools():
        spec = registry.get_tool_spec(tool["name"])
        if spec is None:  # Defensive: registry changed while building schemas.
            continue
        schema = spec.args_model.model_json_schema()
        schema.setdefault("type", "object")
        schema.setdefault("additionalProperties", False)
        schemas.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": schema,
            },
        })
    return schemas


class OpenAICompatibleToolPlanner:
    """Ask a configured chat-completions provider to propose a registry tool.

    Environment variables:
      AGENTFORGE_LLM_API_KEY (required)
      AGENTFORGE_LLM_MODEL (required; e.g. a provider-supported model name)
      AGENTFORGE_LLM_BASE_URL (optional; defaults to OpenAI chat completions)
      AGENTFORGE_LLM_TIMEOUT_SECONDS (optional; defaults to 20)
      AGENTFORGE_LLM_MAX_ATTEMPTS (optional; defaults to 2, max 3)
    """

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        max_attempts: int | None = None,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.registry = registry
        self.api_key = api_key if api_key is not None else os.getenv("AGENTFORGE_LLM_API_KEY")
        self.model = model if model is not None else os.getenv("AGENTFORGE_LLM_MODEL")
        self.base_url = (base_url or os.getenv(
            "AGENTFORGE_LLM_BASE_URL", "https://api.openai.com/v1/chat/completions"
        )).strip()
        try:
            self.timeout_seconds = float(
                timeout_seconds if timeout_seconds is not None
                else os.getenv("AGENTFORGE_LLM_TIMEOUT_SECONDS", "20")
            )
            self.max_attempts = int(
                max_attempts if max_attempts is not None
                else os.getenv("AGENTFORGE_LLM_MAX_ATTEMPTS", "2")
            )
        except (TypeError, ValueError) as exc:
            raise LLMConfigurationError("LLM timeout and attempts must be numeric") from exc
        if not self.api_key or not self.api_key.strip():
            raise LLMConfigurationError("Set AGENTFORGE_LLM_API_KEY to enable the real LLM")
        if not self.model or not self.model.strip():
            raise LLMConfigurationError("Set AGENTFORGE_LLM_MODEL to a provider-supported model")
        if not self.base_url.startswith("https://"):
            raise LLMConfigurationError("LLM base URL must use HTTPS")
        if not 0 < self.timeout_seconds <= 120:
            raise LLMConfigurationError("LLM timeout must be greater than 0 and at most 120 seconds")
        if not 1 <= self.max_attempts <= 3:
            raise LLMConfigurationError("LLM max attempts must be between 1 and 3")
        self._transport = transport or _default_transport
        self._sleep = sleep

    def propose(self, user_request: str) -> ToolProposal:
        if not user_request or not user_request.strip():
            raise ValueError("user_request must not be empty")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are AgentForge's tool-selection component. Choose exactly one "
                        "provided tool only when it directly serves the request. Arguments "
                        "must match its schema. A tool call is only a proposal, not permission. "
                        "Never invent tool names or arguments."
                    ),
                },
                {"role": "user", "content": user_request.strip()},
            ],
            "tools": _tool_schemas(self.registry),
            "tool_choice": "required",
            "parallel_tool_calls": False,
            "temperature": 0,
        }
        request = Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "AgentForge/1.0 (LLM integration test)",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                raw = self._transport(request, self.timeout_seconds)
                body = json.loads(raw.decode("utf-8"))
                return self._parse_proposal(body)
            except HTTPError as exc:
                # Retry only transient rate-limit/server responses. Do not echo provider bodies.
                if exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                    raise LLMIntegrationError(f"LLM provider rejected the request (HTTP {exc.code})") from exc
                last_error = exc
            except (URLError, TimeoutError, OSError) as exc:
                last_error = exc
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, IndexError) as exc:
                raise LLMIntegrationError("LLM provider returned an invalid response") from exc
            if attempt + 1 < self.max_attempts:
                self._sleep(min(0.25 * (2 ** attempt), 1.0))
        raise LLMIntegrationError(
            f"LLM request failed after {self.max_attempts} bounded attempt(s); no tool was executed"
        ) from last_error

    def _parse_proposal(self, body: dict[str, Any]) -> ToolProposal:
        try:
            message = body["choices"][0]["message"]
            tool_calls = message["tool_calls"]
            if not isinstance(tool_calls, list) or len(tool_calls) != 1:
                raise LLMIntegrationError("LLM must propose exactly one tool call")
            function = tool_calls[0]["function"]
            tool_name = function["name"]
            raw_arguments = function["arguments"]
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        except LLMIntegrationError:
            raise
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMIntegrationError("LLM response did not contain a valid tool proposal") from exc
        spec = self.registry.get_tool_spec(tool_name)
        if spec is None:
            raise LLMIntegrationError("LLM proposed a tool that is not allowlisted")
        if not isinstance(arguments, dict):
            raise LLMIntegrationError("LLM tool arguments must be a JSON object")
        try:
            validated = spec.args_model.model_validate(arguments)
        except ValidationError as exc:
            raise LLMIntegrationError("LLM tool arguments failed schema validation") from exc
        return ToolProposal(tool_name=tool_name, arguments=validated.model_dump(), model=self.model or "")


def execute_proposal(
    registry: ToolRegistry,
    proposal: ToolProposal,
    *,
    approval_id: str | None = None,
) -> dict[str, Any]:
    """Execute a validated proposal through the registry's normal safety gates."""
    if not isinstance(proposal, ToolProposal):
        raise TypeError("proposal must be a ToolProposal")
    return registry.execute(proposal.tool_name, proposal.arguments, approval_id=approval_id)
