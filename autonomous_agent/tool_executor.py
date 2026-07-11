"""Phase 26 — ToolExecutor: runs tool calls, handles confirmation + errors."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


@dataclass
class ToolResult:
    success: bool
    tool_name: str
    result: Any = None
    error: str = ""
    duration_ms: float = 0.0
    dry_run: bool = False

    def to_observation(self) -> str:
        if self.dry_run:
            return f"[DRY-RUN] Would call '{self.tool_name}'"
        if self.success:
            return f"✅ Tool '{self.tool_name}' succeeded. {self.result}"
        return f"❌ Tool '{self.tool_name}' failed: {self.error}"


class ToolExecutor:
    """Executes tool calls from the ReAct loop with confirmation + error handling."""

    def __init__(self, registry, dry_run: bool = False,
                 auto_confirm_low_risk: bool = True,
                 confirmation_timeout: float = 60.0) -> None:
        self.registry = registry
        self.dry_run = dry_run
        self.auto_confirm_low_risk = auto_confirm_low_risk
        self.confirmation_timeout = confirmation_timeout
        self._pending_confirmations: Dict[str, asyncio.Event] = {}
        self._confirmation_results: Dict[str, bool] = {}

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> ToolResult:
        meta = self.registry.get(tool_name)
        if not meta:
            return ToolResult(False, tool_name, error=f"Tool '{tool_name}' not found in registry")

        if self.dry_run:
            return ToolResult(True, tool_name, result=f"DRY-RUN args={args}", dry_run=True)

        # Confirmation gate
        if meta.requires_confirmation and not self._should_auto_confirm(meta):
            approved = await self._request_confirmation(tool_name, args)
            if not approved:
                return ToolResult(False, tool_name, error="User rejected confirmation")

        if not meta.executor:
            return ToolResult(False, tool_name, error="No executor registered for this tool")

        t0 = time.monotonic()
        try:
            raw = await asyncio.wait_for(meta.executor(args), timeout=30.0)
            duration = (time.monotonic() - t0) * 1000
            success = raw.get("success", True) if isinstance(raw, dict) else True
            result = raw.get("result", raw) if isinstance(raw, dict) else raw
            error = raw.get("error", "") if isinstance(raw, dict) else ""
            return ToolResult(success=success, tool_name=tool_name,
                              result=result, error=error, duration_ms=round(duration, 1))
        except asyncio.TimeoutError:
            return ToolResult(False, tool_name, error="Tool execution timed out (30s)")
        except Exception as exc:
            return ToolResult(False, tool_name, error=str(exc))

    def approve_confirmation(self, tool_name: str) -> None:
        self._confirmation_results[tool_name] = True
        if tool_name in self._pending_confirmations:
            self._pending_confirmations[tool_name].set()

    def reject_confirmation(self, tool_name: str) -> None:
        self._confirmation_results[tool_name] = False
        if tool_name in self._pending_confirmations:
            self._pending_confirmations[tool_name].set()

    # ── private ───────────────────────────────────────────────────────────────

    def _should_auto_confirm(self, meta) -> bool:
        return self.auto_confirm_low_risk and meta.risk_level in ("low", "medium")

    async def _request_confirmation(self, tool_name: str, args: Dict) -> bool:
        log.warning("⚠️  Confirmation required for '%s' args=%s", tool_name, args)
        event = asyncio.Event()
        self._pending_confirmations[tool_name] = event
        try:
            await asyncio.wait_for(event.wait(), timeout=self.confirmation_timeout)
            return self._confirmation_results.get(tool_name, False)
        except asyncio.TimeoutError:
            log.warning("Confirmation timed out for '%s'", tool_name)
            return False
        finally:
            self._pending_confirmations.pop(tool_name, None)
            self._confirmation_results.pop(tool_name, None)
