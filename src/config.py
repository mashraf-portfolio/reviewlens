"""Project-wide configuration loaded from .env and config/config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"


def _load_yaml() -> dict[str, Any]:
    with _CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh)


class SourceConfig(BaseModel):
    name: str
    enabled: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_CONFIG_PATH.parent.parent / ".env"),  # project root, not CWD
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- secrets (from .env) ---
    anthropic_api_key: str = Field(..., description="Anthropic API key")

    # --- runtime config (from config.yaml, overridable via env) ---
    sources: list[SourceConfig] = Field(default_factory=list)
    storefronts: list[str] = Field(default_factory=list)
    max_fetch_loops: int = 10
    min_n_floor: int = 30
    recency_window_months: int = 12
    cost_ceiling_usd: float = 8.0
    models: dict[str, str] = Field(default_factory=dict)
    taxonomy_seed: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _merge_yaml(cls, data: Any) -> Any:
        yaml_data = _load_yaml()
        # yaml values are defaults; env/explicit values take precedence
        return {**yaml_data, **data} if isinstance(data, dict) else yaml_data

    @model_validator(mode="after")
    def _check_api_key(self) -> Settings:
        if not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file or export it as an environment variable."
            )
        return self


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        try:
            _settings = Settings()
        except ValidationError as exc:
            missing = [e for e in exc.errors() if e["type"] == "missing"]
            if any(e["loc"] == ("anthropic_api_key",) for e in missing):
                raise SystemExit(
                    "ERROR: ANTHROPIC_API_KEY is not set. "
                    "Add it to your .env file or export it as an environment variable."
                ) from None
            raise
    return _settings
