"""Phase 26.5 — ReActReasoner: real-LLM Thought/Action/Observation loop."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from .llm_providers import BaseLLMProvider, Message, ToolCall
from .tool_executor import ToolExecutor, ToolResult
from .prompts import render, SYSTEM, REACT

log = logging.getLogger(__name__)

MAX_ITERATIONS = 20
TOKEN_WARN = 0.80
TOKEN_HARD = 0.95


@dataclass
class ReActStep:
    iteration: int
    thought: str = ""
    tool_name: str = ""
    tool_args: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    is_final: bool = False
    final_answer: str = ""
    tokens: int = 0


@dataclass
class ReActResult:
    success: bool
    answer: str
    goal: str
    steps: List[ReActStep] = field(default_factory=list)
    iterations: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {**self.__dict__, "steps": [s.__dict__ for s in self.steps]}


class ReActReasoner:
    """Drives the ReAct loop using a real LLM provider."""

    def __init__(self, provider: BaseLLMProvider, executor: ToolExecutor,
                 max_iterations: int = MAX_ITERATIONS,
                 auto_improve: bool = False,
                 improvement_loop: Any = None) -> None:
        self.provider = provider
        self.executor = executor
        self.max_iterations = max_iterations
        self.auto_improve = auto_improve
        self.improvement_loop = improvement_loop

    # ── public API ────────────────────────────────────────────────────────────

    async def run(self, goal: str, context: str = "") -> ReActResult:
        t0 = time.monotonic()
        registry = self.executor.registry
        system_msg = render(SYSTEM,
                            tool_count=len(registry),
                            categories=", ".join(registry.categories()))
        react_msg = render(REACT, goal=goal, max_iterations=self.max_iterations)
        messages: List[Message] = [
            Message(role="system", content=system_msg),
            Message(role="user", content=react_msg + (f"\n\nContext: {context}" if context else "")),
        ]
        tools = registry.to_openai_tools()
        steps: List[ReActStep] = []
        total_tokens = 0
        total_cost = 0.0

        for i in range(1, self.max_iterations + 1):
            step = ReActStep(iteration=i)
            try:
                resp = await self.provider.complete(messages, tools=tools)
            except Exception as e:
                return ReActResult(False, "", goal, steps, i, total_tokens, total_cost,
                                   (time.monotonic() - t0) * 1000, error=str(e))

            total_tokens += resp.input_tokens + resp.output_tokens
            total_cost += resp.cost_usd
            step.tokens = resp.input_tokens + resp.output_tokens

            # Check token budget
            ctx = self.provider.get_context_window()
            if total_tokens / ctx >= TOKEN_HARD:
                log.warning("Token hard limit reached at iteration %d", i)
                break

            # Parse response
            tc = self.provider.parse_tool_call(resp) or _parse_text_tool_call(resp.content)
            final = _extract_final_answer(resp.content)

            if final:
                step.is_final = True
                step.final_answer = final
                steps.append(step)
                return ReActResult(True, final, goal, steps, i, total_tokens, total_cost,
                                   round((time.monotonic() - t0) * 1000, 1))

            if tc:
                step.tool_name = tc.name
                step.tool_args = tc.arguments
                step.thought = _extract_thought(resp.content)

                # Execute tool
                result = await self.executor.execute(tc.name, tc.arguments)

                # Auto-improve on tool-not-found
                if not result.success and "not found" in result.error and self.auto_improve:
                    await self._try_improve(goal, result.error)
                    result = await self.executor.execute(tc.name, tc.arguments)

                step.observation = result.to_observation()
                messages.append(Message(role="assistant", content=resp.content))
                messages.append(Message(role="user",
                                        content=f"Observation: {step.observation}"))
            else:
                # No tool call, no final answer — treat as thought and continue
                step.thought = resp.content
                messages.append(Message(role="assistant", content=resp.content))
                messages.append(Message(role="user",
                                        content="Continue. Call a tool or give a Final Answer."))

            steps.append(step)

        return ReActResult(False, "Max iterations reached", goal, steps,
                           self.max_iterations, total_tokens, total_cost,
                           round((time.monotonic() - t0) * 1000, 1),
                           error="Max iterations reached without Final Answer")

    async def stream(self, goal: str) -> AsyncIterator[dict]:
        """Yield SSE-style dicts as the loop progresses."""
        result = await self.run(goal)
        for step in result.steps:
            if step.thought:
                yield {"type": "thought", "content": step.thought}
            if step.tool_name:
                yield {"type": "action", "tool": step.tool_name, "args": step.tool_args}
                yield {"type": "observation", "result": step.observation}
            if step.is_final:
                yield {"type": "final_answer", "content": step.final_answer}
        yield {"type": "usage", "tokens": result.total_tokens, "cost_usd": result.cost_usd}

    # ── private ───────────────────────────────────────────────────────────────

    async def _try_improve(self, goal: str, error: str) -> None:
        if self.improvement_loop:
            try:
                await self.improvement_loop.improve_from_failure(goal, error)
            except Exception as e:
                log.warning("Auto-improve failed: %s", e)


# ── Text parsing helpers ──────────────────────────────────────────────────────

def _extract_thought(text: str) -> str:
    m = re.search(r"Thought:\s*(.+?)(?=\nAction:|\nTOOL:|\Z)", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_final_answer(text: str) -> Optional[str]:
    m = re.search(r"Final Answer:\s*(.+)", text, re.DOTALL)
    return m.group(1).strip() if m else None


def _parse_text_tool_call(text: str) -> Optional[ToolCall]:
    """Parse TOOL: name\nARGS: {...} from plain text (Ollama / fallback)."""
    m = re.search(r"TOOL:\s*(\S+)\s*\nARGS:\s*(\{.*?\})", text, re.DOTALL)
    if not m:
        return None
    try:
        return ToolCall(id="text_tc", name=m.group(1),
                        arguments=json.loads(m.group(2)))
    except json.JSONDecodeError:
        return None
