"""End-to-end graph test using the offline fixture corpus.

The full 8-node pipeline runs with StubLLMClient — no network, no API key.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(scope="module")
def fixture_result():
    """Run the graph once and cache the result for all tests in this module."""
    from agent.fixture import make_fixture_plan, make_fixture_reviews
    from agent.graph import build_graph, make_initial_state
    from agent.trace import TraceContext
    from llm.stub import StubLLMClient

    reviews = make_fixture_reviews()
    plan = make_fixture_plan()
    stub = StubLLMClient()
    tracer = TraceContext(output_path=Path(__file__).parent / "_trace_e2e.json")

    graph = build_graph(llm=stub, tracer=tracer)
    initial = make_initial_state(
        fixture_reviews=reviews,
        fetch_plan=plan,
        min_n_floor=5,
        cost_ceiling_usd=999.0,
    )

    with tracer:
        result = graph.invoke(initial)

    return result, tracer


# ---------------------------------------------------------------------------
# Graph completion
# ---------------------------------------------------------------------------


class TestGraphCompletes:
    def test_graph_returns_a_state(self, fixture_result):
        result, _ = fixture_result
        assert result is not None
        assert isinstance(result, dict)

    def test_all_pipeline_stages_populated(self, fixture_result):
        result, _ = fixture_result
        assert len(result["raw_reviews"]) == 40
        assert len(result["triaged_reviews"]) > 0
        assert len(result["classified"]) > 0
        assert len(result["stats"]) > 0

    def test_loop_count_is_one(self, fixture_result):
        """Fixture should complete in a single fetch loop."""
        result, _ = fixture_result
        assert result["fetch_loop_count"] == 1

    def test_critique_decision_is_end(self, fixture_result):
        result, _ = fixture_result
        assert result["critique_decision"] == "end"

    def test_triage_decision_is_classify(self, fixture_result):
        """40 reviews > min_n_floor=5 so triage routes to classify."""
        result, _ = fixture_result
        assert result["triage_decision"] == "classify"


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class TestClassification:
    def test_all_reviews_classified(self, fixture_result):
        result, _ = fixture_result
        classified_ids = {c.review_id for c in result["classified"]}
        triaged_ids = {r.id for r in result["triaged_reviews"]}
        assert classified_ids == triaged_ids

    def test_no_reviews_silently_dropped(self, fixture_result):
        """Low-confidence rows must be in classified, not absent."""
        result, _ = fixture_result
        assert len(result["classified"]) == len(result["triaged_reviews"])

    def test_low_confidence_count_is_integer(self, fixture_result):
        result, _ = fixture_result
        assert isinstance(result["low_confidence_count"], int)
        assert result["low_confidence_count"] >= 0


# ---------------------------------------------------------------------------
# Quantify
# ---------------------------------------------------------------------------


class TestQuantify:
    def test_stats_produced(self, fixture_result):
        result, _ = fixture_result
        assert len(result["stats"]) > 0

    def test_stats_proportions_sum_to_leq_1_per_app(self, fixture_result):
        """For each app, proportions across all (theme, sentiment) cells sum to 1.0."""
        result, _ = fixture_result
        from collections import defaultdict

        totals: dict[str, float] = defaultdict(float)
        for s in result["stats"]:
            totals[s.app] += s.proportion
        # Each review contributes exactly one (theme, sentiment) pair, so all cells sum to 1.0
        for app, total in totals.items():
            assert total == pytest.approx(1.0, abs=1e-6), (
                f"{app} proportions sum to {total:.4f}, expected 1.0"
            )

    def test_deltas_compare_usim_to_competitors(self, fixture_result):
        result, _ = fixture_result
        for d in result["deltas"]:
            assert d.target.app == "USim"
            assert d.baseline.app in ("Airalo", "Holafly")

    def test_per_100_equals_proportion_times_100(self, fixture_result):
        result, _ = fixture_result
        for s in result["stats"]:
            assert s.per_100 == pytest.approx(s.proportion * 100, abs=1e-6)


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------


class TestDiagnosis:
    def test_diagnosis_object_produced(self, fixture_result):
        """The core requirement: a diagnosis object is produced."""
        result, _ = fixture_result
        assert "claims" in result
        assert isinstance(result["claims"], list)
        assert len(result["claims"]) > 0, "Expected at least one DiagnosisClaim"

    def test_claims_have_required_fields(self, fixture_result):
        result, _ = fixture_result
        for claim in result["claims"]:
            assert claim.app
            assert claim.vs_app
            assert claim.theme
            assert claim.claim
            assert claim.support_level in ("Supported", "Directional")

    def test_claims_match_delta_count(self, fixture_result):
        result, _ = fixture_result
        assert len(result["claims"]) == len(result["deltas"])


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------


class TestTrace:
    def test_all_8_nodes_appear_in_trace(self, fixture_result):
        _, tracer = fixture_result
        exited = {e["node"] for e in tracer.entries if e["type"] == "node_exit"}
        expected = {
            "plan",
            "fetch",
            "triage",
            "classify",
            "cluster",
            "quantify",
            "diagnose",
            "critique",
        }
        assert expected.issubset(exited), f"Missing from trace: {expected - exited}"

    def test_triage_decision_logged(self, fixture_result):
        _, tracer = fixture_result
        triage_exits = [
            e for e in tracer.entries if e["type"] == "node_exit" and e["node"] == "triage"
        ]
        assert triage_exits, "triage node_exit not in trace"
        assert triage_exits[0].get("decision") in ("classify", "fetch")

    def test_critique_decision_logged(self, fixture_result):
        _, tracer = fixture_result
        critique_exits = [
            e for e in tracer.entries if e["type"] == "node_exit" and e["node"] == "critique"
        ]
        assert critique_exits, "critique node_exit not in trace"
        assert critique_exits[0].get("decision") in ("end", "fetch")

    def test_summary_has_latency_for_all_nodes(self, fixture_result):
        _, tracer = fixture_result
        summary = tracer.summary()
        for node in (
            "plan",
            "fetch",
            "triage",
            "classify",
            "cluster",
            "quantify",
            "diagnose",
            "critique",
        ):
            assert node in summary, f"{node} missing from summary"
            assert summary[node]["latency_ms"] >= 0


# ---------------------------------------------------------------------------
# Edge branches — non-happy-path conditional logic
# ---------------------------------------------------------------------------


class TestEdgeBranches:
    """Direct node invocations that force the branches not exercised by the fixture run."""

    def _plan(self, max_pages: int = 3):
        from sources.models import AppTarget, FetchPlan

        return FetchPlan(
            targets=[AppTarget(name="USim", app_store_id="x", countries=["us"])],
            max_pages=max_pages,
            enabled_sources=["appstore"],
        )

    def test_triage_routes_to_fetch_when_too_few_reviews(self):
        """0 triaged < min_n_floor=5 with loops remaining → decision must be 'fetch'."""
        from agent.nodes import make_triage_node
        from agent.trace import TraceContext

        node = make_triage_node(TraceContext(), recency_window_months=12)
        result = node(
            {
                "raw_reviews": [],
                "min_n_floor": 5,
                "fetch_plan": self._plan(max_pages=3),
                "fetch_loop_count": 0,  # 0 < max_pages=3, so not at cap
            }
        )
        assert result["triage_decision"] == "fetch"

    def test_triage_forces_classify_at_loop_cap(self):
        """fetch_loop_count >= max_pages forces 'classify' even with 0 reviews."""
        from agent.nodes import make_triage_node
        from agent.trace import TraceContext

        node = make_triage_node(TraceContext(), recency_window_months=12)
        result = node(
            {
                "raw_reviews": [],
                "min_n_floor": 5,
                "fetch_plan": self._plan(max_pages=2),
                "fetch_loop_count": 2,  # 2 >= max_pages=2 → cap hit
            }
        )
        assert result["triage_decision"] == "classify"

    def test_critique_routes_to_fetch_when_llm_rejects(self):
        """LLM returning accept=False → critique_decision must be 'fetch'."""
        from agent.nodes import make_critique_node
        from agent.trace import TraceContext

        class RejectStub:
            def structured_output(self, schema, messages, **kw):
                return schema.model_validate(
                    {"accept": False, "reason": "needs more data", "unsupported_claims": []}
                )

        node = make_critique_node(TraceContext(), RejectStub())
        result = node(
            {
                "fetch_loop_count": 1,
                "fetch_plan": self._plan(max_pages=3),  # 1 < 3, hard stop not triggered
                "classified": [],
                "low_confidence_count": 0,
                "claims": [],
            }
        )
        assert result["critique_decision"] == "fetch"

    def test_critique_forces_end_at_loop_cap_without_calling_llm(self):
        """fetch_loop_count >= max_pages → hard stop: 'end', LLM must not be called."""
        from agent.nodes import make_critique_node
        from agent.trace import TraceContext

        class NeverCalledStub:
            def structured_output(self, *args, **kw):
                raise AssertionError("LLM must not be called at loop cap")

        node = make_critique_node(TraceContext(), NeverCalledStub())
        result = node(
            {
                "fetch_loop_count": 3,
                "fetch_plan": self._plan(max_pages=3),  # 3 >= 3
                "classified": [],
                "low_confidence_count": 0,
                "claims": [],
            }
        )
        assert result["critique_decision"] == "end"

    def test_budget_exceeded_halts_fetch(self):
        """A pre-exhausted CostMeter causes fetch_node to return a huge loop count."""
        import contextlib

        from agent.nodes import make_fetch_node
        from agent.trace import TraceContext
        from llm.client import BudgetExceeded, CostMeter

        meter = CostMeter(ceiling_usd=0.000001)
        with contextlib.suppress(BudgetExceeded):
            meter.record("stub", 100_000, 100_000)  # pushes total >> ceiling

        node = make_fetch_node(TraceContext())
        result = node(
            {
                "_fixture_reviews": [],  # empty → would fall through to fetch_reviews...
                "fetch_loop_count": 0,
                "fetch_plan": self._plan(max_pages=3),
                "min_n_floor": 5,
                "cost_meter": meter,  # ...but BudgetExceeded fires first
            }
        )
        # fetch_node sets loop_count = min_n_floor * 99 on budget halt
        assert result["fetch_loop_count"] >= 5 * 99
