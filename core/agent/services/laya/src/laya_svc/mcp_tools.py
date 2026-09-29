"""mcp_tools.py — the `laya_decide` MCP surface (the SEAM A attachment).

Dispatched agents reach the judge through THIS (a streamable-HTTP MCP server
mounted at /mcp on the same app), granted via the tools-seed descriptor
`core/agent/tools-seed/laya_decide.json` -> ToolRegistry -> `.claude/mcp.json`
+ `--allowedTools mcp__laya`. The tool is a generic typed-decision passthrough:
the QUESTIONS live caller-side (byte-pinned in the callers' templates), the
service only judges — mechanism, not policy (P11).

fastmcp is an OPTIONAL extra: without it the app serves the scan API and /health
with a typed warning (a smaller product, never a broken one — P18/P14 capability
conventions).
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("agent_api.laya")

MCP_TOOL_NAME = "laya_decide"
MCP_TOOL_DESCRIPTION = (
    "Fast typed-decision judgments over a short text passage (single forward "
    "pass, no generation, nothing to hallucinate). Pass the passage plus typed "
    "questions (choice|score|noul with instructions and criteria); answers come "
    "back with probabilities. Use for decision detection, triage, scoring, "
    "yes/no checks — not for open-ended reasoning."
)


def build_mcp_app(judge: Callable[[str, dict[str, Any]], dict[str, Any]], checkpoint: str):
    """Build the streamable-HTTP MCP ASGI app serving `laya_decide`. Raises
    ImportError when the `mcp` extra is not installed — main.py translates that
    into a typed startup warning and serves without the tool surface."""
    try:
        from fastmcp import FastMCP
    except ImportError as e:  # noqa: TRY302 — translated, logged by main (P18)
        raise ImportError(
            "fastmcp is not installed (pip install 'laya-svc[mcp]'); the MCP "
            "surface will be absent and only the scan API serves."
        ) from e

    mcp = FastMCP("laya")

    @mcp.tool(
        name=MCP_TOOL_NAME,
        description=MCP_TOOL_DESCRIPTION,
        tags={"laya", "system1"},
    )
    def laya_decide(state_text: str, questions: dict[str, Any]) -> dict[str, Any]:
        """Judge `state_text` against typed `questions`. questions maps a short
        name to {type: choice|score|noul, instructions, criteria}. Returns
        {answers, checkpoint, usage} — probabilities included, so the caller can
        weigh low-confidence answers itself."""
        try:
            answers = judge(state_text, questions)
        except Exception as e:  # noqa: BLE001 — surfaced to the agent turn (P18)
            return {"error": f"laya judge failed (checkpoint={checkpoint}): {e}"}
        return {
            "answers": answers.get("answers", answers),
            "checkpoint": checkpoint,
            "usage": answers.get("usage", {}),
        }

    return mcp
