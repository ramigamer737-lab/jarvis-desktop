"""Phase 26.5 — LLM provider abstraction (OpenAI / Anthropic / Ollama / Mock)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

log = logging.getLogger(__name__)


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str          # system | user | assistant | tool
    content: str
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    name: Optional[str] = None


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    provider: str = ""
    cost_usd: float = 0.0
    raw: Any = None


# ── Abstract base ─────────────────────────────────────────────────────────────

class BaseLLMProvider(ABC):
    name: str = "base"
    default_model: str = ""

    def __init__(self, model: str = "", temperature: float = 0.1,
                 max_tokens: int = 4096, timeout: float = 60.0) -> None:
        self.model = model or self.default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    @abstractmethod
    async def complete(self, messages: List[Message],
                       tools: Optional[List[Dict]] = None, **kw) -> LLMResponse: ...

    @abstractmethod
    async def stream(self, messages: List[Message],
                     tools: Optional[List[Dict]] = None) -> AsyncIterator[str]: ...

    def format_tools(self, registry: Dict[str, Any]) -> List[Dict]:
        return []

    def parse_tool_call(self, resp: LLMResponse) -> Optional[ToolCall]:
        return resp.tool_calls[0] if resp.tool_calls else None

    def is_available(self) -> bool:
        return True

    def get_context_window(self) -> int:
        return 128_000

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    async def _retry(self, coro_fn, attempts: int = 3, base_delay: float = 1.0):
        for i in range(attempts):
            try:
                return await coro_fn()
            except Exception as e:
                if i == attempts - 1:
                    raise
                await asyncio.sleep(base_delay * (2 ** i))
                log.warning("%s retry %d/%d after: %s", self.name, i + 1, attempts, e)


# ── OpenAI ────────────────────────────────────────────────────────────────────

# Pricing per 1M tokens: (input, output)
_OAI_PRICING = {
    "gpt-4o": (5.0, 15.0), "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.0, 30.0),
}

PRICING = _OAI_PRICING  # exported for cost display


class OpenAIProvider(BaseLLMProvider):
    name = "openai"
    default_model = "gpt-4o"

    def __init__(self, api_key: str = "", **kw) -> None:
        super().__init__(**kw)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def format_tools(self, registry: Dict[str, Any]) -> List[Dict]:
        tools = []
        for name, meta in registry.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": getattr(meta, "description", ""),
                    "parameters": getattr(meta, "parameters", {"type": "object", "properties": {}}),
                },
            })
        return tools

    async def complete(self, messages: List[Message],
                       tools: Optional[List[Dict]] = None, **kw) -> LLMResponse:
        async def _call():
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.api_key, timeout=self.timeout)
            oai_msgs = [{"role": m.role, "content": m.content} for m in messages]
            kwargs: Dict[str, Any] = dict(
                model=self.model, messages=oai_msgs,
                temperature=kw.get("temperature", self.temperature),
                max_tokens=kw.get("max_tokens", self.max_tokens),
            )
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            resp = await client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message
            tcs = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tcs.append(ToolCall(
                        id=tc.id, name=tc.function.name,
                        arguments=json.loads(tc.function.arguments or "{}"),
                    ))
            inp, out = resp.usage.prompt_tokens, resp.usage.completion_tokens
            p = _OAI_PRICING.get(self.model, (5.0, 15.0))
            cost = (inp * p[0] + out * p[1]) / 1_000_000
            return LLMResponse(
                content=msg.content or "", tool_calls=tcs,
                finish_reason=resp.choices[0].finish_reason or "stop",
                input_tokens=inp, output_tokens=out,
                model=self.model, provider=self.name, cost_usd=cost, raw=resp,
            )
        return await self._retry(_call)

    async def stream(self, messages: List[Message],
                     tools: Optional[List[Dict]] = None) -> AsyncIterator[str]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.api_key, timeout=self.timeout)
        oai_msgs = [{"role": m.role, "content": m.content} for m in messages]
        async with client.chat.completions.stream(
            model=self.model, messages=oai_msgs,
            temperature=self.temperature, max_tokens=self.max_tokens,
        ) as s:
            async for chunk in s:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta


# ── Anthropic ─────────────────────────────────────────────────────────────────

_ANT_PRICING = {
    "claude-3-5-sonnet-20241022": (3.0, 15.0),
    "claude-3-opus-20240229": (15.0, 75.0),
    "claude-3-haiku-20240307": (0.25, 1.25),
}


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"
    default_model = "claude-3-5-sonnet-20241022"

    def __init__(self, api_key: str = "", **kw) -> None:
        super().__init__(**kw)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def format_tools(self, registry: Dict[str, Any]) -> List[Dict]:
        tools = []
        for name, meta in registry.items():
            tools.append({
                "name": name,
                "description": getattr(meta, "description", ""),
                "input_schema": getattr(meta, "parameters",
                                        {"type": "object", "properties": {}}),
            })
        return tools

    async def complete(self, messages: List[Message],
                       tools: Optional[List[Dict]] = None, **kw) -> LLMResponse:
        async def _call():
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            system = next((m.content for m in messages if m.role == "system"), "")
            ant_msgs = [{"role": m.role, "content": m.content}
                        for m in messages if m.role != "system"]
            kwargs: Dict[str, Any] = dict(
                model=self.model, messages=ant_msgs,
                max_tokens=kw.get("max_tokens", self.max_tokens),
                temperature=kw.get("temperature", self.temperature),
            )
            if system:
                kwargs["system"] = system
            if tools:
                kwargs["tools"] = tools
            resp = await client.messages.create(**kwargs)
            text = ""
            tcs = []
            for block in resp.content:
                if block.type == "text":
                    text += block.text
                elif block.type == "tool_use":
                    tcs.append(ToolCall(id=block.id, name=block.name,
                                        arguments=block.input or {}))
            inp, out = resp.usage.input_tokens, resp.usage.output_tokens
            p = _ANT_PRICING.get(self.model, (3.0, 15.0))
            cost = (inp * p[0] + out * p[1]) / 1_000_000
            return LLMResponse(
                content=text, tool_calls=tcs,
                finish_reason=resp.stop_reason or "stop",
                input_tokens=inp, output_tokens=out,
                model=self.model, provider=self.name, cost_usd=cost, raw=resp,
            )
        return await self._retry(_call)

    async def stream(self, messages: List[Message],
                     tools: Optional[List[Dict]] = None) -> AsyncIterator[str]:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        ant_msgs = [{"role": m.role, "content": m.content}
                    for m in messages if m.role != "system"]
        async with client.messages.stream(
            model=self.model, messages=ant_msgs, max_tokens=self.max_tokens,
        ) as s:
            async for text in s.text_stream:
                yield text


# ── Ollama (local) ────────────────────────────────────────────────────────────

class OllamaProvider(BaseLLMProvider):
    name = "ollama"
    default_model = "llama3"

    def __init__(self, base_url: str = "http://localhost:11434", **kw) -> None:
        super().__init__(**kw)
        self.base_url = base_url

    def is_available(self) -> bool:
        try:
            import httpx
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    async def complete(self, messages: List[Message],
                       tools: Optional[List[Dict]] = None, **kw) -> LLMResponse:
        import httpx
        prompt = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)
        if tools:
            tool_desc = "\n".join(f"- {t.get('name','?')}: {t.get('description','')}"
                                  for t in tools)
            prompt += f"\n\nAvailable tools:\n{tool_desc}\n\nTo call a tool respond with:\nTOOL: <name>\nARGS: {{...json...}}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/api/generate",
                                     json={"model": self.model, "prompt": prompt, "stream": False})
            resp.raise_for_status()
            data = resp.json()
        text = data.get("response", "")
        tcs = self._parse_tool_calls(text)
        tokens = data.get("eval_count", self.estimate_tokens(text))
        return LLMResponse(content=text, tool_calls=tcs, model=self.model,
                           provider=self.name, output_tokens=tokens)

    async def stream(self, messages: List[Message],
                     tools: Optional[List[Dict]] = None) -> AsyncIterator[str]:
        import httpx
        prompt = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/api/generate",
                                     json={"model": self.model, "prompt": prompt}) as r:
                async for line in r.aiter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            if chunk.get("response"):
                                yield chunk["response"]
                        except json.JSONDecodeError:
                            pass

    @staticmethod
    def _parse_tool_calls(text: str) -> List[ToolCall]:
        tcs = []
        for m in re.finditer(r"TOOL:\s*(\S+)\s*\nARGS:\s*(\{.*?\})", text, re.DOTALL):
            try:
                tcs.append(ToolCall(id=f"ollama_{len(tcs)}", name=m.group(1),
                                    arguments=json.loads(m.group(2))))
            except json.JSONDecodeError:
                pass
        return tcs


# ── Mock (testing) ────────────────────────────────────────────────────────────

class MockProvider(BaseLLMProvider):
    name = "mock"
    default_model = "mock-1"

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._queue: list[LLMResponse] = []
        self.calls: list[dict] = []

    def add_response(self, content: str = "", tool_name: str = "",
                     tool_args: Optional[Dict] = None) -> None:
        tcs = []
        if tool_name:
            tcs = [ToolCall(id="mock_tc_0", name=tool_name, arguments=tool_args or {})]
        self._queue.append(LLMResponse(content=content, tool_calls=tcs,
                                       model=self.model, provider=self.name))

    def add_final_answer(self, answer: str) -> None:
        self.add_response(content=f"Final Answer: {answer}")

    async def complete(self, messages: List[Message],
                       tools: Optional[List[Dict]] = None, **kw) -> LLMResponse:
        self.calls.append({"messages": messages, "tools": tools})
        if self._queue:
            return self._queue.pop(0)
        return LLMResponse(content="Final Answer: Task complete.", model=self.model,
                           provider=self.name)

    async def stream(self, messages: List[Message],
                     tools: Optional[List[Dict]] = None) -> AsyncIterator[str]:
        resp = await self.complete(messages, tools)
        for word in resp.content.split():
            yield word + " "
            await asyncio.sleep(0)


# ── Factory ───────────────────────────────────────────────────────────────────

def create_provider(name: str, **kwargs) -> BaseLLMProvider:
    providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
        "mock": MockProvider,
    }
    cls = providers.get(name.lower())
    if not cls:
        raise ValueError(f"Unknown provider: {name!r}. Choose from {list(providers)}")
    return cls(**kwargs)
