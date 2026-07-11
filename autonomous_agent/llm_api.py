"""Phase 26.5 — LLM FastAPI router (/llm/*)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter(prefix="/llm", tags=["llm"])

# Injected at startup
_provider: Any = None
_registry: Any = None
_executor: Any = None
_reasoner: Any = None
_cost_tracker: Any = None


def init(provider, registry, executor, reasoner, cost_tracker=None):
    global _provider, _registry, _executor, _reasoner, _cost_tracker
    _provider, _registry, _executor = provider, registry, executor
    _reasoner, _cost_tracker = reasoner, cost_tracker


# ── Models ────────────────────────────────────────────────────────────────────

class ChatReq(BaseModel):
    messages: List[Dict[str, str]]
    model: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 4096

class ReactReq(BaseModel):
    goal: str
    context: str = ""
    dry_run: bool = False

class SwitchReq(BaseModel):
    provider: str
    model: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _req_provider():
    if not _provider:
        raise HTTPException(503, "LLM provider not initialised")


@router.get("/providers")
async def list_providers():
    from .llm_providers import OpenAIProvider, AnthropicProvider, OllamaProvider
    return {"providers": [
        {"name": "openai",    "available": OpenAIProvider().is_available(),
         "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]},
        {"name": "anthropic", "available": AnthropicProvider().is_available(),
         "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"]},
        {"name": "ollama",    "available": OllamaProvider().is_available(),
         "models": ["llama3", "mistral", "qwen2.5"]},
        {"name": "mock",      "available": True, "models": ["mock-1"]},
    ]}


@router.get("/providers/{name}")
async def get_provider(name: str):
    from .llm_providers import PRICING
    return {"name": name, "pricing": PRICING}


@router.post("/chat")
async def chat(req: ChatReq):
    _req_provider()
    from .llm_providers import Message
    msgs = [Message(role=m["role"], content=m["content"]) for m in req.messages]
    resp = await _provider.complete(msgs, temperature=req.temperature, max_tokens=req.max_tokens)
    if _cost_tracker:
        _cost_tracker.record(_provider.name, resp.model, resp.input_tokens, resp.output_tokens)
    return {"content": resp.content, "model": resp.model,
            "tokens": resp.input_tokens + resp.output_tokens, "cost_usd": resp.cost_usd}


@router.post("/react")
async def react(req: ReactReq):
    _req_provider()
    if req.dry_run and _executor:
        _executor.dry_run = True
    result = await _reasoner.run(req.goal, req.context)
    if req.dry_run and _executor:
        _executor.dry_run = False
    return result.to_dict()


@router.post("/react/stream")
async def react_stream(req: ReactReq):
    _req_provider()

    async def event_gen():
        async for event in _reasoner.stream(req.goal):
            import json
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/usage")
async def usage():
    if not _cost_tracker:
        return {"error": "Cost tracker not initialised"}
    return _cost_tracker.summary()


@router.post("/provider/switch")
async def switch_provider(req: SwitchReq):
    global _provider
    from .llm_providers import create_provider
    _provider = create_provider(req.provider, model=req.model or "")
    return {"switched_to": req.provider, "model": _provider.model}


@router.get("/models")
async def list_models():
    return {"openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
            "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
            "ollama": ["llama3", "mistral", "qwen2.5"]}


@router.get("/status")
async def status():
    return {
        "phase": "26.5 — Real LLM Integration",
        "provider": _provider.name if _provider else None,
        "model": _provider.model if _provider else None,
        "tools": len(_registry) if _registry else 0,
        "cost_tracker": _cost_tracker is not None,
    }
