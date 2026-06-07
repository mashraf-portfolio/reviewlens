"""LangGraph pipeline — 8 nodes, 2 conditional edges (design doc §2.1).

Topology:
    plan → fetch → triage ──► classify → cluster → quantify → diagnose → critique
                     ▲   (too few)                                            │
                     └────────────────────────── (retry: low quality) ────────┘
                                                                              ▼
                                                                             END
Run offline with a fixture corpus:
    python -m agent.graph --fixture
"""

from __future__ import annotations

import sys

from langgraph.graph import END, StateGraph

from agent.state import GraphState
from agent.trace import TraceContext

_DEFAULT_THEMES: list[str] = [
    "activation",
    "support",
    "refund_billing",
    "coverage_speed",
    "app_ux",
    "value_pricing",
    "positive",
]


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_graph(
    llm: object | None = None,
    tracer: TraceContext | None = None,
    recency_window_months: int = 12,
    taxonomy_themes: list[str] | None = None,
    cost_meter=None,
):
    """Compile and return the LangGraph StateGraph.

    Args:
        llm:                  LLMClient or StubLLMClient.  When None the real
                              LLMClient is instantiated (requires ANTHROPIC_API_KEY).
        tracer:               TraceContext shared across all nodes.
        recency_window_months: Reviews older than this are excluded in triage.
        taxonomy_themes:      Ordered list of theme labels for classify/cluster.
                              When None and llm is None (production), loaded from
                              config.yaml.  Otherwise the 7-theme default is used.
    """
    if tracer is None:
        tracer = TraceContext()

    # classify_llm uses the low-cost Haiku model (high-volume per-review work).
    # synth_llm uses the Opus model (low-volume judgment: cluster, critique).
    # In stub/test mode a single llm object is reused for all nodes.
    classify_llm: object
    synth_llm: object

    if llm is None:
        from config import get_settings
        from llm.client import CostMeter, LLMClient

        cfg = get_settings()
        shared_meter = (
            cost_meter if cost_meter is not None else CostMeter(ceiling_usd=cfg.cost_ceiling_usd)
        )
        classify_llm = LLMClient(
            model=cfg.models.get("classifier", "claude-haiku-4-5-20251001"),
            cost_meter=shared_meter,
        )
        synth_llm = LLMClient(
            model=cfg.models.get("synth", "claude-opus-4-8"),
            cost_meter=shared_meter,
        )
        recency_window_months = cfg.recency_window_months
        taxonomy_themes = list(cfg.taxonomy_seed.get("themes", {}).keys()) or _DEFAULT_THEMES
    else:
        classify_llm = llm
        synth_llm = llm
        if taxonomy_themes is None:
            taxonomy_themes = _DEFAULT_THEMES

    from agent.nodes import (
        make_classify_node,
        make_cluster_node,
        make_critique_node,
        make_diagnose_node,
        make_fetch_node,
        make_plan_node,
        make_quantify_node,
        make_triage_node,
    )

    workflow = StateGraph(GraphState)

    workflow.add_node("plan", make_plan_node(tracer))
    workflow.add_node("fetch", make_fetch_node(tracer))
    workflow.add_node("triage", make_triage_node(tracer, recency_window_months))
    workflow.add_node("classify", make_classify_node(tracer, classify_llm, taxonomy_themes))
    workflow.add_node("cluster", make_cluster_node(tracer, synth_llm, taxonomy_themes))
    workflow.add_node("quantify", make_quantify_node(tracer))
    workflow.add_node("diagnose", make_diagnose_node(tracer))
    workflow.add_node("critique", make_critique_node(tracer, synth_llm))

    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "fetch")
    workflow.add_edge("fetch", "triage")

    workflow.add_conditional_edges(
        "triage",
        lambda s: s.get("triage_decision", "fetch"),
        {"classify": "classify", "fetch": "fetch"},
    )

    workflow.add_edge("classify", "cluster")
    workflow.add_edge("cluster", "quantify")
    workflow.add_edge("quantify", "diagnose")
    workflow.add_edge("diagnose", "critique")

    workflow.add_conditional_edges(
        "critique",
        lambda s: s.get("critique_decision", "end"),
        {"end": END, "fetch": "fetch"},
    )

    return workflow.compile()


# ---------------------------------------------------------------------------
# Initial state helper
# ---------------------------------------------------------------------------


def make_initial_state(
    fixture_reviews: list | None = None,
    fetch_plan=None,
    min_n_floor: int = 30,
    cost_ceiling_usd: float = 8.0,
    cost_meter=None,
) -> GraphState:
    from llm.client import CostMeter

    return GraphState(
        fetch_plan=fetch_plan,
        _fixture_reviews=fixture_reviews or [],
        raw_reviews=[],
        triaged_reviews=[],
        classified=[],
        low_confidence_count=0,
        theme_map={},
        stats=[],
        deltas=[],
        claims=[],
        trace_entries=[],
        fetch_loop_count=0,
        cost_meter=cost_meter
        if cost_meter is not None
        else CostMeter(ceiling_usd=cost_ceiling_usd),
        min_n_floor=min_n_floor,
        triage_decision="classify",
        critique_decision="end",
    )


# ---------------------------------------------------------------------------
# Fixture / offline runner
# ---------------------------------------------------------------------------


def run_fixture() -> GraphState:
    """Run the full graph offline using the built-in fixture corpus."""
    from agent.fixture import make_fixture_plan, make_fixture_reviews
    from llm.stub import StubLLMClient

    reviews = make_fixture_reviews()
    plan = make_fixture_plan()
    stub = StubLLMClient()
    tracer = TraceContext()

    graph = build_graph(llm=stub, tracer=tracer)
    initial = make_initial_state(
        fixture_reviews=reviews,
        fetch_plan=plan,
        min_n_floor=5,  # low floor so fixture produces Supported deltas
        cost_ceiling_usd=999.0,
    )

    with tracer:
        result = graph.invoke(initial)

    _print_summary(result, tracer)
    return result


def _print_summary(state: GraphState, tracer: TraceContext) -> None:
    print(f"\n{'=' * 60}")
    print("ReviewLens fixture run complete")
    print(f"{'=' * 60}")
    print(f"  reviews fetched  : {len(state.get('raw_reviews', []))}")
    print(f"  triaged          : {len(state.get('triaged_reviews', []))}")
    print(f"  classified       : {len(state.get('classified', []))}")
    print(f"  low-confidence   : {state.get('low_confidence_count', 0)}")
    print(f"  stats            : {len(state.get('stats', []))}")
    deltas = state.get("deltas", [])
    supported = sum(1 for d in deltas if d.support_level == "Supported")
    print(f"  deltas           : {len(deltas)} ({supported} Supported)")
    print(f"  claims           : {len(state.get('claims', []))}")
    print("\nNode timings:")
    for node, info in tracer.summary().items():
        print(f"  {node:<12} {info['latency_ms']:>8.1f} ms")
    print()
    print("Sample claims:")
    for c in state.get("claims", [])[:3]:
        print(f"  [{c.support_level}] {c.claim}")


# ---------------------------------------------------------------------------
# __main__ entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--fixture" in sys.argv:
        run_fixture()
    else:
        print("Usage: python -m agent.graph --fixture")
        sys.exit(1)
