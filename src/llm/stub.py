"""Deterministic LLM stub for offline testing and fixture runs.

Parses review IDs from the classify prompt and returns valid structured
output for every schema the graph uses — no network calls, no API key.
"""

from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel

from llm.client import CostMeter

T = TypeVar("T", bound=BaseModel)

_THEMES = [
    "app_ux",
    "support",
    "refund_billing",
    "coverage_speed",
    "positive",
    "activation",
    "value_pricing",
]
_SENTIMENTS = ["negative", "negative", "positive", "neutral"]


class StubLLMClient:
    """Fully deterministic, zero-cost LLM stub.

    Produces valid Pydantic-validated responses for every schema the graph
    calls structured_output with.  Token counts are faked at 1/1 so the
    CostMeter exercises its accounting code without spending real budget.
    """

    def __init__(self, ceiling_usd: float = 999.0) -> None:
        self._meter = CostMeter(ceiling_usd=ceiling_usd)

    @property
    def meter(self) -> CostMeter:
        return self._meter

    def chat(
        self,
        messages: list[dict],
        *,
        system: str = "",
        max_tokens: int = 2048,
        model: str | None = None,
    ) -> str:
        self._meter.record("stub", 1, 1)
        return '{"accept": true, "reason": "stub"}'

    def structured_output(
        self,
        schema: type[T],
        messages: list[dict],
        *,
        system: str = "",
        max_tokens: int = 2048,
        model: str | None = None,
    ) -> T:
        self._meter.record("stub", 1, 1)
        name = schema.__name__
        user_content = messages[-1]["content"] if messages else ""

        if name == "ClassificationBatch":
            return self._stub_classification(schema, user_content)  # type: ignore[return-value]
        if name == "ThemeMapping":
            return schema.model_validate({"mappings": {}})  # type: ignore[return-value]
        if name == "CritiqueResult":
            return schema.model_validate(  # type: ignore[return-value]
                {"accept": True, "reason": "stub: fixture run accepted", "unsupported_claims": []}
            )
        # Generic fallback — try empty dict (may fail for strict schemas)
        return schema.model_validate({})  # type: ignore[return-value]

    # ------------------------------------------------------------------

    def _stub_classification(self, schema: type[T], content: str) -> T:
        ids = re.findall(r"Review ID: ([^\n]+)", content)
        classifications = []
        for i, rid in enumerate(ids):
            classifications.append(
                {
                    "review_id": rid.strip(),
                    "theme": _THEMES[i % len(_THEMES)],
                    "sentiment": _SENTIMENTS[i % len(_SENTIMENTS)],
                    "friction_phrase": "stub phrase",
                    "confidence": 0.85,
                }
            )
        return schema.model_validate({"classifications": classifications})  # type: ignore[return-value]
