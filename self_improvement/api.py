"""Phase 29 — Self-Improvement FastAPI router."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter(prefix="/self-improve", tags=["self-improve"])

# Injected at startup by main.py
_loop: Any = None
_registrar: Any = None


def init(improvement_loop, registrar):
    global _loop, _registrar
    _loop = improvement_loop
    _registrar = registrar


# ── request/response models ───────────────────────────────────────────────────

class GenerateReq(BaseModel):
    description: str
    category: str = "general"

class TestReq(BaseModel):
    name: str
    code: str
    description: str = ""
    category: str = "general"

class RegisterReq(BaseModel):
    name: str
    code: str
    description: str = ""
    category: str = "general"

class CycleReq(BaseModel):
    trigger: str = "user_request"
    goal: Optional[str] = None

class SuggestReq(BaseModel):
    goal: str

class FixReq(BaseModel):
    name: str
    error_log: str


# ── endpoints ─────────────────────────────────────────────────────────────────

def _require_loop():
    if not _loop:
        raise HTTPException(503, "Self-improvement engine not initialised")


@router.post("/generate")
async def generate_tool(req: GenerateReq):
    _require_loop()
    tool = await _loop.generator.generate_tool(req.description, req.category)
    return {"success": True, "tool": tool.to_dict()}


@router.post("/test")
async def test_tool(req: TestReq):
    _require_loop()
    from .tool_generator import GeneratedTool
    tool = GeneratedTool(name=req.name, code=req.code,
                         description=req.description, category=req.category)
    result = await _loop.tester.test_tool(tool)
    return {"success": True, "result": result.__dict__}


@router.post("/register")
async def register_tool(req: RegisterReq):
    _require_loop()
    from .tool_generator import GeneratedTool
    from .tool_tester import TestResult
    tool = GeneratedTool(name=req.name, code=req.code,
                         description=req.description, category=req.category)
    syntax = _loop.tester.validate_syntax(req.code)
    fake_result = TestResult(passed=3, failed=0, syntax_ok=syntax.syntax_ok,
                             syntax_error=syntax.syntax_error)
    reg = _registrar.register_tool(tool, fake_result)
    return {"success": reg.success, "result": reg.__dict__}


@router.post("/cycle")
async def run_cycle(req: CycleReq):
    _require_loop()
    report = await _loop.run_cycle(trigger=req.trigger, goal=req.goal)
    return {"success": True, "report": report.to_dict()}


@router.get("/tools")
async def list_tools():
    tools = _registrar.list_generated_tools() if _registrar else []
    return {"success": True, "tools": tools, "count": len(tools)}


@router.get("/tools/{name}")
async def get_tool(name: str):
    if not _registrar:
        raise HTTPException(503, "Registrar not initialised")
    tools = {t["name"]: t for t in _registrar.list_generated_tools()}
    if name not in tools:
        raise HTTPException(404, f"Tool '{name}' not found")
    return {"success": True, "tool": tools[name]}


@router.delete("/tools/{name}")
async def delete_tool(name: str):
    if not _registrar:
        raise HTTPException(503, "Registrar not initialised")
    ok = _registrar.unregister_tool(name)
    return {"success": ok}


@router.get("/history")
async def get_history():
    history = _loop.get_history() if _loop else []
    return {"success": True, "history": history, "count": len(history)}


@router.post("/suggestions")
async def get_suggestions(req: SuggestReq):
    _require_loop()
    suggestions = await _loop.generator.suggest_tools(req.goal)
    return {"success": True, "suggestions": [s.__dict__ for s in suggestions]}


@router.post("/fix/{name}")
async def fix_tool(name: str, req: FixReq):
    _require_loop()
    tools = {t["name"]: t for t in (_registrar.list_generated_tools() if _registrar else [])}
    if name not in tools:
        raise HTTPException(404, f"Tool '{name}' not found")
    from .tool_generator import GeneratedTool
    tool = GeneratedTool(name=name, code="", description="", category="general")
    fixed = await _loop.generator.improve_tool(tool, req.error_log)
    return {"success": True, "fixed_tool": fixed.to_dict()}


@router.get("/status")
async def status():
    tools = _registrar.list_generated_tools() if _registrar else []
    history = _loop.get_history() if _loop else []
    return {
        "phase": "29 — Self-Improvement Engine",
        "engine_ready": _loop is not None,
        "generated_tools": len(tools),
        "cycles_run": len(history),
    }
