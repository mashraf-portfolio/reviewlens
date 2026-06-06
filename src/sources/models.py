"""Shared data models for the review-source layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Resolved from the project root at import time so callers don't need to
# know the directory layout.
DEFAULT_CACHE_DIR: Path = Path(__file__).parent.parent.parent / "data" / "raw_cache"


@dataclass(frozen=True)
class Review:
    """Normalised review record — one shape regardless of source."""

    id: str
    source: str  # "appstore" | "playstore" | "trustpilot"
    app: str  # human-readable app name
    country: str  # lowercase ISO-3166-1 alpha-2 (e.g. "us")
    rating: int  # 1–5
    title: str
    body: str
    date: datetime

    def dedup_key(self) -> tuple[str, str]:
        return (self.source, self.id)


@dataclass
class AppTarget:
    """One app to analyse across sources."""

    name: str
    app_store_id: str | None = None  # iTunes numeric trackId (string)
    play_store_id: str | None = None  # Android package name
    countries: list[str] = field(default_factory=list)


@dataclass
class FetchPlan:
    """Fully-resolved fetch instructions produced by plan_node."""

    targets: list[AppTarget]
    max_pages: int = 10
    enabled_sources: list[str] = field(default_factory=lambda: ["appstore", "playstore"])
    cache_dir: Path = field(default_factory=lambda: DEFAULT_CACHE_DIR)
