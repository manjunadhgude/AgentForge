"""Live-provider demo; makes no side-effecting tool call without approval."""
from __future__ import annotations

import json

from llm_agent import LLMConfigurationError, OpenAICompatibleToolPlanner
from tool_runtime import ToolRegistry


def main() -> None:
    registry = ToolRegistry()
    try:
        planner = OpenAICompatibleToolPlanner(registry)
    except LLMConfigurationError as exc:
        raise SystemExit(f"LLM is not configured: {exc}") from exc

    request = input(
        "Describe a task for the simulated order tools (e.g. 'Check ORDER-001 status'): "
    ).strip()
    proposal = planner.propose(request)
    spec = registry.get_tool_spec(proposal.tool_name)
    if spec is None:
        raise SystemExit("The proposed tool is no longer registered; nothing was executed.")
    result: dict[str, object] = {
        "provider_model": proposal.model,
        "proposal": {"tool_name": proposal.tool_name, "arguments": proposal.arguments},
        "proposal_only": True,
        "external_services_called": False,
    }
    if spec.requires_approval:
        result["execution"] = "not executed: this tool requires explicit approval"
    else:
        from llm_agent import execute_proposal
        result["execution"] = execute_proposal(registry, proposal)
        result["proposal_only"] = False
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
