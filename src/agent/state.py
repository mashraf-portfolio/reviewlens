"""LangGraph graph state — all fields carried through the 8-node pipeline."""

from __future__ import annotations

import operator
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from sources.models import FetchPlan, Review

# ---------------------------------------------------------------------------
# LLM-output schemas (Pydantic — validated via structured_output)
# ---------------------------------------------------------------------------


class ClassifiedReview(BaseModel):
    """One review after the classify node, with denormalised app/date fields."""

    review_id: str
    app: str
    date: datetime
    theme: str
    sentiment: Literal["positive", "negative", "neutral", "mixed"]
    friction_phrase: str
    confidence: float = Field(ge=0.0, le=1.0)
    low_confidence: bool = False


class ThemeStat(BaseModel):
    """Proportion stats for one (app, theme, sentiment) cell."""

    app: str
    theme: str
    sentiment: str
    count: int  # reviews matching this cell
    nobs: int  # total reviews for this app
    proportion: float
    ci_low: float
    ci_high: float
    per_100: float  # proportion × 100


class Delta(BaseModel):
    """Comparison of one (theme, sentiment) cell between two apps."""

    theme: str
    sentiment: str
    target: ThemeStat  # USim (or whatever the primary app is)
    baseline: ThemeStat  # competitor
    delta_per_100: float
    support_level: Literal["Supported", "Directional"]


class DiagnosisClaim(BaseModel):
    """One human-readable finding derived from a Delta."""

    app: str
    vs_app: str
    theme: str
    sentiment: str
    claim: str
    delta_per_100: float
    support_level: str
    evidence: Delta


# ---------------------------------------------------------------------------
# LLM classification-batch schema  (used only during classify node)
# ---------------------------------------------------------------------------


class ReviewClassification(BaseModel):
    """Raw LLM output for a single review — before denormalisation."""

    review_id: str
    theme: str
    sentiment: Literal["positive", "negative", "neutral", "mixed"]
    friction_phrase: str
    confidence: float = Field(ge=0.0, le=1.0)


class ClassificationBatch(BaseModel):
    classifications: list[ReviewClassification]


# ---------------------------------------------------------------------------
# Cluster / critique schemas
# ---------------------------------------------------------------------------


class ThemeMapping(BaseModel):
    """LLM output mapping raw theme labels → canonical taxonomy labels."""

    mappings: dict[str, str]  # raw_label → canonical_label (or emergent label)


class CritiqueResult(BaseModel):
    accept: bool
    reason: str
    unsupported_claims: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Graph state  (TypedDict — compatible with LangGraph StateGraph)
# ---------------------------------------------------------------------------


from typing import TypedDict  # noqa: E402  (after Pydantic imports to avoid circular)


class GraphState(TypedDict):
    # ---- input ----
    fetch_plan: FetchPlan
    _fixture_reviews: list[Review]  # pre-loaded reviews for offline / fixture mode

    # ---- pipeline stages ----
    raw_reviews: Annotated[list[Review], operator.add]  # accumulates across retry loops
    triaged_reviews: list[Review]
    classified: list[ClassifiedReview]
    low_confidence_count: int
    theme_map: dict[str, str]  # raw_label → canonical_label
    stats: list[ThemeStat]
    deltas: list[Delta]
    claims: list[DiagnosisClaim]

    # ---- bookkeeping ----
    trace_entries: Annotated[list[dict[str, Any]], operator.add]
    fetch_loop_count: int
    cost_meter: Any  # CostMeter — not serialisable; fine without checkpointer
    min_n_floor: int  # copied from config so quantify is self-contained

    # ---- routing signals ----
    triage_decision: str  # "classify" | "fetch"
    critique_decision: str  # "end" | "fetch"
