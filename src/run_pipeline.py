"""ReviewLens pipeline entry point.

Usage
-----
  python -m run_pipeline            # live agent (requires ANTHROPIC_API_KEY)
  python -m run_pipeline --fixture  # offline fixture corpus (no key needed)

Generates (relative to project root)
-------------------------------------
  docs/diagnosis.json
  docs/opener.md
  data/results/last_run.json
  data/results/trace_last_run.json
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_DOCS_DIR = _ROOT / "docs"
_RESULTS_DIR = _ROOT / "data" / "results"


def run_fixture() -> None:
    """Run the full graph on the offline fixture corpus and write all outputs."""
    from agent.fixture import make_fixture_plan, make_fixture_reviews
    from agent.graph import build_graph, make_initial_state
    from agent.trace import TraceContext
    from diagnosis import write_outputs
    from llm.stub import StubLLMClient

    print("ReviewLens -- fixture run (offline, no API key required)")
    print(f"  docs    -> {_DOCS_DIR}")
    print(f"  results -> {_RESULTS_DIR}")

    reviews = make_fixture_reviews()
    plan = make_fixture_plan()
    stub = StubLLMClient()
    tracer = TraceContext(output_path=_RESULTS_DIR / "trace_last_run.json")

    graph = build_graph(llm=stub, tracer=tracer)
    initial = make_initial_state(
        fixture_reviews=reviews,
        fetch_plan=plan,
        min_n_floor=5,
        cost_ceiling_usd=999.0,
    )

    with tracer:
        state = graph.invoke(initial)

    diagnosis = write_outputs(state, docs_dir=_DOCS_DIR, results_dir=_RESULTS_DIR)

    _print_summary(state, diagnosis)


def run_live() -> None:
    """Run the full graph with real LLM and live sources."""
    from agent.graph import build_graph, make_initial_state
    from agent.trace import TraceContext
    from diagnosis import write_outputs

    print("ReviewLens -- live run")
    tracer = TraceContext(output_path=_RESULTS_DIR / "trace_last_run.json")

    graph = build_graph(tracer=tracer)
    initial = make_initial_state()

    with tracer:
        state = graph.invoke(initial)

    diagnosis = write_outputs(state, docs_dir=_DOCS_DIR, results_dir=_RESULTS_DIR)

    _print_summary(state, diagnosis)


def _print_summary(state: dict, diagnosis: dict) -> None:
    pains = diagnosis.get("pains", [])
    deltas = diagnosis.get("deltas", [])
    supported = sum(1 for d in deltas if d["support_level"] == "Supported")

    print(f"\n{'=' * 60}")
    print("ReviewLens run complete")
    print(f"{'=' * 60}")
    print(f"  classified reviews : {diagnosis['total_n']}")
    print(f"  pains identified   : {len(pains)}")
    print(f"  deltas             : {len(deltas)} ({supported} Supported)")
    print(f"  interventions      : {len(diagnosis.get('interventions', []))}")
    print("")
    print("  docs/diagnosis.json                  written")
    print("  docs/opener.md                       written")
    print("  data/results/last_run.json           written")
    print("  data/results/trace_last_run.json     written")

    print("\nTop pain:")
    if pains:
        p = pains[0]
        usim = p["rates"].get(diagnosis.get("target_app", "USim"), {})
        print(
            f"  {p['theme']} / {p['sentiment']} -- "
            f"USim {usim.get('per_100', 0):.1f} per-100 "
            f"(n={usim.get('n', 0)})"
        )

    print("\nopener.md preview (first 5 lines):")
    opener_path = _DOCS_DIR / "opener.md"
    if opener_path.exists():
        lines = opener_path.read_text(encoding="utf-8").splitlines()
        for line in lines[:5]:
            print(f"  {line}")


if __name__ == "__main__":
    if "--fixture" in sys.argv:
        run_fixture()
    else:
        run_live()
