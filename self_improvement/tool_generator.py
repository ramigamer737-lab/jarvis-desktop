"""Phase 29 — ToolGenerator: LLM writes new JARVIS tool functions."""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .prompts import render, TOOL_GENERATOR, TOOL_IMPROVER, TOOL_SUGGESTER

log = logging.getLogger(__name__)


@dataclass
class GeneratedTool:
    name: str
    code: str
    description: str
    category: str
    parameters: dict = field(default_factory=dict)
    docstring: str = ""
    model: str = "unknown"
    tokens_used: int = 0
    cost_usd: float = 0.0
    attempt: int = 1
    is_fix: bool = False
    original_name: Optional[str] = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class ToolSuggestion:
    name: str
    description: str
    category: str
    why: str = ""


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_code(text: str) -> Optional[str]:
    """Pull Python code from ```python ... ``` or bare def block."""
    m = re.search(r"```python\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    idx = text.find("def ")
    return text[idx:].strip() if idx != -1 else None


def _parse_tool(code: str) -> tuple[str, str, dict]:
    """Return (func_name, docstring, parameters) from AST, or raise."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            doc = ast.get_docstring(node) or ""
            params: dict[str, Any] = {}
            for arg in node.args.args:
                if arg.arg != "args":
                    params[arg.arg] = {"type": "string"}
            return node.name, doc, params
    raise ValueError("No function definition found in generated code")


def _parse_suggestions(text: str) -> list[ToolSuggestion]:
    suggestions = []
    blocks = re.split(r"\n(?=TOOL:)", text.strip())
    for block in blocks:
        name = re.search(r"TOOL:\s*(\S+)", block)
        desc = re.search(r"DESC:\s*(.+)", block)
        cat  = re.search(r"CAT:\s*(\S+)", block)
        why  = re.search(r"WHY:\s*(.+)", block)
        if name and desc:
            suggestions.append(ToolSuggestion(
                name=name.group(1),
                description=desc.group(1).strip(),
                category=cat.group(1) if cat else "general",
                why=why.group(1).strip() if why else "",
            ))
    return suggestions


# ── main class ────────────────────────────────────────────────────────────────

class ToolGenerator:
    """Uses an LLM provider to write, improve, and suggest JARVIS tools."""

    def __init__(self, provider: Any) -> None:
        self.provider = provider

    async def generate_tool(self, description: str, category: str = "general") -> GeneratedTool:
        """Ask the LLM to write a new tool function."""
        name = re.sub(r"[^a-z0-9]+", "_", description.lower())[:40].strip("_")
        prompt = render(TOOL_GENERATOR, name=name, description=description, category=category)
        resp = await self._complete(prompt)
        code = _extract_code(resp.content)
        if not code:
            raise ValueError(f"LLM returned no code block for: {description}")
        func_name, docstring, params = _parse_tool(code)
        return GeneratedTool(
            name=func_name, code=code, description=description,
            category=category, parameters=params, docstring=docstring,
            model=resp.model, tokens_used=resp.input_tokens + resp.output_tokens,
            cost_usd=getattr(resp, "cost_usd", 0.0),
        )

    async def improve_tool(self, tool: GeneratedTool, error_log: str) -> GeneratedTool:
        """Ask the LLM to fix a failing tool."""
        prompt = render(TOOL_IMPROVER, code=tool.code, error_log=error_log)
        resp = await self._complete(prompt)
        code = _extract_code(resp.content)
        if not code:
            raise ValueError("LLM returned no fixed code block")
        func_name, docstring, params = _parse_tool(code)
        return GeneratedTool(
            name=func_name, code=code, description=tool.description,
            category=tool.category, parameters=params, docstring=docstring,
            model=resp.model, tokens_used=resp.input_tokens + resp.output_tokens,
            attempt=tool.attempt + 1, is_fix=True, original_name=tool.name,
        )

    async def suggest_tools(self, goal: str, existing: list[str] | None = None) -> list[ToolSuggestion]:
        """Suggest new tools that would help achieve a goal."""
        prompt = render(TOOL_SUGGESTER, goal=goal, existing_tools=", ".join(existing or []))
        resp = await self._complete(prompt)
        return _parse_suggestions(resp.content)

    # ── private ───────────────────────────────────────────────────────────────

    async def _complete(self, prompt: str):
        from autonomous_agent.llm_providers import Message
        messages = [Message(role="user", content=prompt)]
        return await self.provider.complete(messages)
