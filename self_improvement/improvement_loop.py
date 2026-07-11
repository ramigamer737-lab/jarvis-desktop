"""Phase 29 — ImprovementLoop: orchestrates the 7-step self-improvement cycle."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .tool_generator import ToolGenerator, GeneratedTool
from .tool_tester import ToolTester
from .tool_registrar import ToolRegistrar

log = logging.getLogger(__name__)

MAX_FIX_ATTEMPTS = 2


@dataclass
class ImprovementReport:
    cycle_id: str
    trigger: str
    tools_generated: int = 0
    tools_registered: int = 0
    tools_failed: int = 0
    duration_ms: float = 0.0
    cost_usd: float = 0.0
    details: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class ImprovementLoop:
    """
    Runs the 7-step self-improvement cycle:
      Analyze → Suggest → Generate → Test → Fix → Register → Report
    """

    def __init__(self, provider: Any, tool_registry: Any = None) -> None:
        self.generator  = ToolGenerator(provider)
        self.tester     = ToolTester(provider)
        self.registrar  = ToolRegistrar(tool_registry)
        self.registry   = tool_registry
        self._history: list[ImprovementReport] = []

    # ── public API ────────────────────────────────────────────────────────────

    async def run_cycle(self, trigger: str = "user_request",
                        goal: Optional[str] = None) -> ImprovementReport:
        """Run a full improvement cycle and return a report."""
        cycle_id = uuid.uuid4().hex[:8]
        t0 = time.monotonic()
        report = ImprovementReport(cycle_id=cycle_id, trigger=trigger)
        log.info("[Cycle %s] Starting (%s)", cycle_id, trigger)

        # Step 1 — Suggest
        existing = self._existing_tool_names()
        try:
            suggestions = await self.generator.suggest_tools(
                goal or "improve JARVIS capabilities", existing
            )
        except Exception as e:
            log.error("[Cycle %s] Suggest failed: %s", cycle_id, e)
            suggestions = []

        # Steps 2-5 — Generate / Test / Fix / Register
        for sug in suggestions[:5]:
            detail = {"name": sug.name, "description": sug.description}
            try:
                tool = await self.generator.generate_tool(sug.description, sug.category)
                report.tools_generated += 1
                report.cost_usd += tool.cost_usd

                result = await self.tester.test_tool(tool)

                # Fix loop
                for attempt in range(MAX_FIX_ATTEMPTS):
                    if result.ok:
                        break
                    log.info("[Cycle %s] Fixing %s (attempt %d)", cycle_id, tool.name, attempt + 1)
                    tool = await self.generator.improve_tool(tool, result.output)
                    result = await self.tester.test_tool(tool)

                reg = self.registrar.register_tool(tool, result)
                if reg.success:
                    report.tools_registered += 1
                    detail["status"] = "registered"
                else:
                    report.tools_failed += 1
                    detail["status"] = "failed"
                    detail["error"] = reg.error
            except Exception as e:
                report.tools_failed += 1
                detail["status"] = "error"
                detail["error"] = str(e)
                log.error("[Cycle %s] Error on %s: %s", cycle_id, sug.name, e)

            report.details.append(detail)

        report.duration_ms = round((time.monotonic() - t0) * 1000, 1)
        self._history.append(report)
        log.info("[Cycle %s] Done — %d registered, %d failed",
                 cycle_id, report.tools_registered, report.tools_failed)
        return report

    async def improve_from_failure(self, goal: str, error: str) -> ImprovementReport:
        """Triggered when ReAct loop fails due to a missing tool."""
        log.info("Auto-improve triggered for goal: %s", goal[:80])
        return await self.run_cycle(trigger="goal_failed", goal=goal)

    def get_history(self) -> list[dict]:
        return [r.to_dict() for r in self._history]

    # ── private ───────────────────────────────────────────────────────────────

    def _existing_tool_names(self) -> list[str]:
        if self.registry and hasattr(self.registry, "tools"):
            return list(self.registry.tools.keys())
        return []
