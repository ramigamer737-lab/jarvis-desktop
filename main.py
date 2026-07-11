"""
JARVIS — Unified FastAPI Backend (Phases 26 / 26.5 / 29)
=========================================================
Starts the FastAPI server that the Electron desktop app connects to.

Usage:
    python main.py                  # API server on :8000
    python main.py --port 9000      # Custom port
    python main.py --dry-run        # Simulate all tool calls
    python main.py --provider mock  # Use mock LLM (no API key needed)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jarvis")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="JARVIS API",
    description="PC Control ↔ LLM Integration (Phases 26/26.5/29)",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    cfg = _load_config()
    provider_name = os.environ.get("JARVIS_LLM_PROVIDER",
                                   cfg.get("llm", {}).get("default_provider", "mock"))
    dry_run = os.environ.get("JARVIS_DRY_RUN", "").lower() in ("1", "true")

    # Build tool registry
    from autonomous_agent.tool_registry import build_default_registry
    registry = build_default_registry()
    log.info("Tool registry: %d tools", len(registry))

    # Build LLM provider
    from autonomous_agent.llm_providers import create_provider
    llm_cfg = cfg.get("llm", {}).get(provider_name, {})
    provider = create_provider(provider_name, **{
        k: v for k, v in llm_cfg.items() if k in ("model", "temperature", "max_tokens", "timeout")
    })
    log.info("LLM provider: %s / %s", provider.name, provider.model)

    # Build executor + reasoner
    from autonomous_agent.tool_executor import ToolExecutor
    from autonomous_agent.react_reasoner import ReActReasoner
    from autonomous_agent.cost_tracker import CostTracker
    executor = ToolExecutor(registry, dry_run=dry_run)
    cost_tracker = CostTracker()
    reasoner = ReActReasoner(provider, executor)

    # Build self-improvement loop
    from self_improvement.improvement_loop import ImprovementLoop
    from self_improvement.tool_registrar import ToolRegistrar
    improvement_loop = ImprovementLoop(provider, registry)
    registrar = ToolRegistrar(registry)
    reasoner.auto_improve = True
    reasoner.improvement_loop = improvement_loop

    # Register routers
    from autonomous_agent.llm_api import router as llm_router, init as llm_init
    from self_improvement.api import router as si_router, init as si_init

    llm_init(provider, registry, executor, reasoner, cost_tracker)
    si_init(improvement_loop, registrar)

    app.include_router(llm_router)
    app.include_router(si_router)

    log.info("JARVIS ready — %d tools, provider=%s, dry_run=%s",
             len(registry), provider.name, dry_run)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "JARVIS", "version": "1.0.0"}


@app.get("/")
async def root():
    return {"message": "JARVIS API — see /docs for endpoints"}


# ── Config loader ─────────────────────────────────────────────────────────────

def _load_config() -> dict:
    cfg_path = Path(__file__).parent / "config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        import yaml
        with cfg_path.open() as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        log.warning("Config load failed: %s", e)
        return {}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="JARVIS API Server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--provider", default="")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["JARVIS_DRY_RUN"] = "1"
    if args.provider:
        os.environ["JARVIS_LLM_PROVIDER"] = args.provider

    uvicorn.run("main:app", host=args.host, port=args.port,
                reload=args.reload, log_level="info")


if __name__ == "__main__":
    main()
