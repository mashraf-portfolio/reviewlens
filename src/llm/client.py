"""Provider-agnostic LLM wrapper with cost metering and structured output."""

from __future__ import annotations

import json
import time
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from config import get_settings

T = TypeVar("T", bound=BaseModel)

# Approximate cost per million tokens (USD) for billing guard-rails.
# Update when Anthropic revises pricing.
_COST_PER_M: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
    # fallback for unknown models
    "__default__": {"input": 3.0, "output": 15.0},
}


class BudgetExceeded(Exception):
    """Raised when accumulated LLM spend crosses config.cost_ceiling_usd."""

    def __init__(self, spent: float, ceiling: float) -> None:
        self.spent = spent
        self.ceiling = ceiling
        super().__init__(f"LLM budget exceeded: ${spent:.4f} spent, ceiling is ${ceiling:.4f}")


class CostMeter:
    """Accumulates token usage and enforces a USD spend ceiling."""

    def __init__(self, ceiling_usd: float) -> None:
        self.ceiling_usd = ceiling_usd
        self._total_usd: float = 0.0

    @property
    def total_usd(self) -> float:
        return self._total_usd

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        rates = _COST_PER_M.get(model, _COST_PER_M["__default__"])
        cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
        self._total_usd += cost
        if self._total_usd > self.ceiling_usd:
            raise BudgetExceeded(self._total_usd, self.ceiling_usd)

    def reset(self) -> None:
        self._total_usd = 0.0


class LLMClient:
    """Thin wrapper around the Anthropic client with retry, backoff, and cost metering."""

    def __init__(
        self,
        *,
        model: str | None = None,
        cost_meter: CostMeter | None = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        settings = get_settings()
        self._model = model or settings.models.get("synth", "claude-sonnet-4-6")
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._meter = cost_meter or CostMeter(ceiling_usd=settings.cost_ceiling_usd)
        self._max_retries = max_retries
        self._base_delay = base_delay

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        system: str = "",
        max_tokens: int = 2048,
        model: str | None = None,
    ) -> str:
        """Send a chat request and return the text response."""
        return self._call_with_retry(
            messages=messages,
            system=system,
            max_tokens=max_tokens,
            model=model or self._model,
        )

    def structured_output(
        self,
        schema: type[T],
        messages: list[dict[str, str]],
        *,
        system: str = "",
        max_tokens: int = 2048,
        model: str | None = None,
    ) -> T:
        """Return a validated Pydantic model by asking the LLM for JSON."""
        json_instruction = (
            f"\n\nYou MUST respond with valid JSON that conforms to this schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}\n"
            "Return ONLY the JSON object — no prose, no markdown fences."
        )
        augmented_system = system + json_instruction

        raw = self._call_with_retry(
            messages=messages,
            system=augmented_system,
            max_tokens=max_tokens,
            model=model or self._model,
        )

        # Strip accidental markdown fences if the model adds them
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return schema.model_validate_json(raw)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call_with_retry(
        self,
        *,
        messages: list[dict[str, str]],
        system: str,
        max_tokens: int,
        model: str,
    ) -> str:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,  # type: ignore[arg-type]
                )
                self._meter.record(
                    model=model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )
                return response.content[0].text  # type: ignore[union-attr]
            except BudgetExceeded:
                raise
            except anthropic.RateLimitError as exc:
                last_exc = exc
                time.sleep(self._base_delay * (2**attempt))
            except anthropic.APIStatusError as exc:
                if exc.status_code and exc.status_code >= 500:
                    last_exc = exc
                    time.sleep(self._base_delay * (2**attempt))
                else:
                    raise

        raise RuntimeError(f"LLM call failed after {self._max_retries} retries") from last_exc
