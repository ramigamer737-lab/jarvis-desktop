"""Phase 29 — ToolRegistrar: persist and hot-reload generated tools."""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_GENERATED_DIR = Path(__file__).parent.parent / "jarvis" / "tools" / "generated"
_LOG_FILE = Path(__file__).parent.parent / "logs" / "self_improvement.jsonl"


@dataclass
class RegistrationResult:
    success: bool
    tool_name: str
    file_path: str = ""
    error: str = ""
    hot_reloaded: bool = False


class ToolRegistrar:
    """Writes approved tools to disk and hot-reloads them into the registry."""

    def __init__(self, tool_registry=None) -> None:
        self.registry = tool_registry
        _GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _init_file = _GENERATED_DIR / "__init__.py"
        if not _init_file.exists():
            _init_file.write_text("# Auto-generated tools\n")

    # ── public API ────────────────────────────────────────────────────────────

    def register_tool(self, tool, test_result) -> RegistrationResult:
        """Write tool to disk and register it if tests passed."""
        if not test_result.ok:
            return RegistrationResult(
                success=False, tool_name=tool.name,
                error=f"Tests did not pass: {test_result.passed}P/{test_result.failed}F/{test_result.errors}E",
            )
        path = _GENERATED_DIR / f"{tool.name}.py"
        try:
            path.write_text(tool.code)
            reloaded = self._hot_reload(tool.name, path)
            if self.registry:
                self._add_to_registry(tool)
            self._log(tool, test_result)
            return RegistrationResult(success=True, tool_name=tool.name,
                                      file_path=str(path), hot_reloaded=reloaded)
        except Exception as e:
            log.error("Registration failed for %s: %s", tool.name, e)
            return RegistrationResult(success=False, tool_name=tool.name, error=str(e))

    def unregister_tool(self, name: str) -> bool:
        path = _GENERATED_DIR / f"{name}.py"
        if path.exists():
            path.unlink()
        mod_key = f"jarvis.tools.generated.{name}"
        sys.modules.pop(mod_key, None)
        if self.registry and hasattr(self.registry, "tools"):
            self.registry.tools.pop(name, None)
        return True

    def list_generated_tools(self) -> list[dict]:
        tools = []
        for p in sorted(_GENERATED_DIR.glob("*.py")):
            if p.name.startswith("_"):
                continue
            tools.append({"name": p.stem, "file": str(p),
                          "size_bytes": p.stat().st_size,
                          "modified": p.stat().st_mtime})
        return tools

    # ── private ───────────────────────────────────────────────────────────────

    def _hot_reload(self, name: str, path: Path) -> bool:
        mod_key = f"jarvis.tools.generated.{name}"
        try:
            spec = importlib.util.spec_from_file_location(mod_key, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            sys.modules[mod_key] = mod
            return True
        except Exception as e:
            log.warning("Hot-reload failed for %s: %s", name, e)
            return False

    def _add_to_registry(self, tool) -> None:
        if not hasattr(self.registry, "register"):
            return
        self.registry.register(
            name=tool.name,
            description=tool.description,
            category=tool.category,
            parameters=tool.parameters,
            risk_level="medium",
            requires_confirmation=False,
            executor=None,
        )

    def _log(self, tool, test_result) -> None:
        entry = {
            "ts": time.time(), "tool": tool.name, "category": tool.category,
            "model": tool.model, "tokens": tool.tokens_used, "cost": tool.cost_usd,
            "passed": test_result.passed, "failed": test_result.failed,
        }
        with _LOG_FILE.open("a") as f:
            f.write(json.dumps(entry) + "\n")
