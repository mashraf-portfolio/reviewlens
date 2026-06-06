"""LangGraph node functions — 8 nodes per design doc §2.1.

Nodes are plain functions; the LLM client and config values are injected via
the build_graph() closure so tests can swap in StubLLMClient and pass plain
config values without touching get_settings() at all.

Topology:
    plan → fetch → triage → classify → cluster → quantify → diagnose → critique
                      ↑          │                                          │
                      └──fetch───┘ (too few reviews)           END / fetch ─┘
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from agent.state import (
    CritiqueResult,
    DiagnosisClaim,
    GraphState,
)
from agent.trace import TraceContext
from sources.models import FetchPlan
from tools.fetch import fetch_reviews

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# plan_node
# ---------------------------------------------------------------------------


def make_plan_node(tracer: TraceContext):
    def plan_node(state: GraphState) -> dict:
        tracer.node_enter("plan", state)

        # If a plan is already in state (fixture / test mode), keep it.
        plan = state.get("fetch_plan")
        if plan is None:
            from config import get_settings
            from sources.registry import resolve_all

            cfg = get_settings()
            targets, _log = resolve_all(cfg.storefronts)
            plan = FetchPlan(
                targets=targets,
                max_pages=cfg.max_fetch_loops,
                enabled_sources=[s.name for s in cfg.sources if s.enabled],
            )

        tracer.node_exit("plan", state)
        return {"fetch_plan": plan}

    return plan_node


# ---------------------------------------------------------------------------
# fetch_node
# ---------------------------------------------------------------------------


def make_fetch_node(tracer: TraceContext):
    def fetch_node(state: GraphState) -> dict:
        tracer.node_enter("fetch", state)

        loop = state.get("fetch_loop_count", 0)
        plan = state["fetch_plan"]

        # Check budget before fetching
        meter = state.get("cost_meter")
        if meter is not None:
            from llm.client import BudgetExceeded

            try:
                meter.record("fetch", 0, 0)  # zero-cost check — raises if already over
            except BudgetExceeded as exc:
                log.warning("fetch_node: %s — halting", exc)
                tracer.node_exit("fetch", state)
                # Force critique to END by setting a high loop count
                return {"fetch_loop_count": state.get("min_n_floor", 30) * 99}

        # Use pre-loaded fixture reviews when available (first loop only)
        fixture = state.get("_fixture_reviews", [])
        if fixture and loop == 0:
            new_reviews = fixture
            log.info("fetch_node: using %d fixture reviews (offline mode)", len(new_reviews))
        else:
            new_reviews, counts = fetch_reviews(plan)
            log.info("fetch_node: fetched %d reviews %s", len(new_reviews), counts)

        tracer.node_exit("fetch", state)
        return {
            "raw_reviews": new_reviews,
            "fetch_loop_count": loop + 1,
        }

    return fetch_node


# ---------------------------------------------------------------------------
# triage_node
# ---------------------------------------------------------------------------


def make_triage_node(tracer: TraceContext, recency_window_months: int = 12):
    def triage_node(state: GraphState) -> dict:
        tracer.node_enter("triage", state)

        reviews = state.get("raw_reviews", [])
        min_n = state.get("min_n_floor", 30)
        max_loops = state["fetch_plan"].max_pages  # reuse max_pages as loop cap

        cutoff = datetime.now(UTC) - timedelta(days=recency_window_months * 30)
        triaged = [r for r in reviews if r.date >= cutoff]

        decision: str
        loop = state.get("fetch_loop_count", 0)
        if len(triaged) >= min_n:
            decision = "classify"
        elif loop >= max_loops:
            log.warning(
                "triage: max_fetch_loops=%d reached with only %d reviews — forcing classify",
                max_loops,
                len(triaged),
            )
            decision = "classify"
        else:
            decision = "fetch"

        tracer.node_exit("triage", {**state, "triaged_reviews": triaged}, decision=decision)
        return {"triaged_reviews": triaged, "triage_decision": decision}

    return triage_node


# ---------------------------------------------------------------------------
# classify_node
# ---------------------------------------------------------------------------


def make_classify_node(tracer: TraceContext, llm: object, taxonomy_themes: list[str]):
    def classify_node(state: GraphState) -> dict:
        tracer.node_enter("classify", state)

        from tools.classify import classify_reviews

        reviews = state.get("triaged_reviews", [])
        classified, low_conf = classify_reviews(reviews, taxonomy_themes, llm)

        log.info("classify: %d rows, %d low-confidence", len(classified), low_conf)
        tracer.node_exit("classify", state)
        return {"classified": classified, "low_confidence_count": low_conf}

    return classify_node


# ---------------------------------------------------------------------------
# cluster_node
# ---------------------------------------------------------------------------


def make_cluster_node(tracer: TraceContext, llm: object, seed_themes: list[str]):
    def cluster_node(state: GraphState) -> dict:
        tracer.node_enter("cluster", state)

        from tools.cluster import apply_theme_map, cluster_themes

        classified = state.get("classified", [])
        theme_map = cluster_themes(classified, seed_themes, llm)
        normalised = apply_theme_map(classified, theme_map)

        log.info("cluster: mapped %d unique themes", len(theme_map))
        tracer.node_exit("cluster", state)
        return {"classified": normalised, "theme_map": theme_map}

    return cluster_node


# ---------------------------------------------------------------------------
# quantify_node
# ---------------------------------------------------------------------------


def make_quantify_node(tracer: TraceContext):
    def quantify_node(state: GraphState) -> dict:
        tracer.node_enter("quantify", state)

        from tools.quantify import compute_stats

        classified = state.get("classified", [])
        min_n = state.get("min_n_floor", 30)
        target_app = state["fetch_plan"].targets[0].name

        stats, deltas = compute_stats(classified, min_n_floor=min_n, target_app=target_app)
        supported = sum(1 for d in deltas if d.support_level == "Supported")
        log.info("quantify: %d stats, %d deltas (%d supported)", len(stats), len(deltas), supported)

        tracer.node_exit("quantify", state)
        return {"stats": stats, "deltas": deltas}

    return quantify_node


# ---------------------------------------------------------------------------
# diagnose_node
# ---------------------------------------------------------------------------


def make_diagnose_node(tracer: TraceContext):
    def diagnose_node(state: GraphState) -> dict:
        tracer.node_enter("diagnose", state)

        from agent.state import DiagnosisClaim

        deltas = state.get("deltas", [])
        claims: list[DiagnosisClaim] = []
        for delta in deltas:
            direction = "higher" if delta.delta_per_100 > 0 else "lower"
            # Avoid "positive positive" when theme and sentiment share the same label.
            mention = (
                delta.theme
                if delta.theme == delta.sentiment
                else f"{delta.sentiment} {delta.theme}"
            )
            claim_text = (
                f"{delta.target.app} has {abs(delta.delta_per_100):.1f} per-100 "
                f"{direction} {mention} mentions than "
                f"{delta.baseline.app} ({delta.support_level})."
            )
            claims.append(
                DiagnosisClaim(
                    app=delta.target.app,
                    vs_app=delta.baseline.app,
                    theme=delta.theme,
                    sentiment=delta.sentiment,
                    claim=claim_text,
                    delta_per_100=delta.delta_per_100,
                    support_level=delta.support_level,
                    evidence=delta,
                )
            )

        log.info("diagnose: %d claims", len(claims))
        tracer.node_exit("diagnose", state)
        return {"claims": claims}

    return diagnose_node


# ---------------------------------------------------------------------------
# critique_node
# ---------------------------------------------------------------------------


def make_critique_node(tracer: TraceContext, llm: object):
    def critique_node(state: GraphState) -> dict:
        tracer.node_enter("critique", state)

        from agent.state import CritiqueResult

        loop = state.get("fetch_loop_count", 0)
        max_loops = state["fetch_plan"].max_pages
        classified = state.get("classified", [])
        low_conf = state.get("low_confidence_count", 0)
        total = len(classified) or 1

        # Hard stops — don't call LLM
        if loop >= max_loops:
            decision = "end"
            tracer.node_exit("critique", state, decision=decision)
            return {"critique_decision": decision}

        # LLM soft critique
        low_conf_rate = low_conf / total
        claims_text = "\n".join(c.claim for c in state.get("claims", [])[:10])
        prompt = (
            f"Low-confidence rate: {low_conf_rate:.1%}\n"
            f"Claims:\n{claims_text}\n\n"
            "Should we accept these results or retry with more data?"
        )
        try:
            result: CritiqueResult = llm.structured_output(  # type: ignore[union-attr]
                CritiqueResult,
                [{"role": "user", "content": prompt}],
                max_tokens=256,
            )
            decision = "end" if result.accept else "fetch"
        except Exception as exc:
            log.warning("critique LLM call failed: %s — defaulting to end", exc)
            decision = "end"

        tracer.node_exit("critique", state, decision=decision)
        return {"critique_decision": decision}

    return critique_node
