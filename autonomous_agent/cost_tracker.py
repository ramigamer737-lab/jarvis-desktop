"""Phase 26.5 — CostTracker: token usage and cost accounting."""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger(__name__)

_LOG = Path("logs/llm_usage.jsonl")

# Pricing per 1M tokens: {model: (input_usd, output_usd)}
PRICING: Dict[str, tuple[float, float]] = {
    "gpt-4o": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.0, 30.0),
    "claude-3-5-sonnet-20241022": (3.0, 15.0),
    "claude-3-opus-20240229": (15.0, 75.0),
    "claude-3-haiku-20240307": (0.25, 1.25),
}


@dataclass
class UsageEntry:
    ts: float
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    session_id: str = ""


class CostTracker:
    """Tracks LLM token usage and costs; persists to JSONL."""

    def __init__(self, warn_usd: float = 1.0, hard_limit_usd: float = 10.0) -> None:
        self.warn_usd = warn_usd
        self.hard_limit_usd = hard_limit_usd
        self._entries: list[UsageEntry] = []
        self._total_cost: float = 0.0
        _LOG.parent.mkdir(parents=True, exist_ok=True)

    def record(self, provider: str, model: str,
               input_tokens: int, output_tokens: int,
               session_id: str = "") -> float:
        """Record a usage event; return cost in USD."""
        cost = self._calc_cost(model, input_tokens, output_tokens)
        entry = UsageEntry(
            ts=time.time(), provider=provider, model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            cost_usd=cost, session_id=session_id,
        )
        self._entries.append(entry)
        self._total_cost += cost
        self._persist(entry)
        if self._total_cost >= self.hard_limit_usd:
            raise RuntimeError(f"LLM cost hard limit reached: ${self._total_cost:.4f}")
        if self._total_cost >= self.warn_usd:
            log.warning("LLM cost warning: $%.4f / $%.2f", self._total_cost, self.warn_usd)
        return cost

    def summary(self) -> dict:
        by_provider: Dict[str, float] = defaultdict(float)
        by_model: Dict[str, float] = defaultdict(float)
        for e in self._entries:
            by_provider[e.provider] += e.cost_usd
            by_model[e.model] += e.cost_usd
        return {
            "total_tokens": sum(e.input_tokens + e.output_tokens for e in self._entries),
            "total_cost_usd": round(self._total_cost, 6),
            "by_provider": dict(by_provider),
            "by_model": dict(by_model),
            "entries": len(self._entries),
        }

    @staticmethod
    def _calc_cost(model: str, inp: int, out: int) -> float:
        p = PRICING.get(model, (5.0, 15.0))
        return (inp * p[0] + out * p[1]) / 1_000_000

    def _persist(self, entry: UsageEntry) -> None:
        try:
            with _LOG.open("a") as f:
                f.write(json.dumps(entry.__dict__) + "\n")
        except Exception as e:
            log.debug("Cost log write failed: %s", e)
