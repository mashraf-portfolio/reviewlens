"""Phase 3 tests — diagnosis output correctness (offline, no API key).

Assertions:
1. opener.md has NO untagged comparative claim (every 'than' line carries
   [Supported] or [Directional]).
2. Directional claims never appear above Supported ones in the delta ordering.
3. diagnosis.json has n + CI present on every per-100 rate.
4. last_run.json loads back as valid JSON with no network/LLM call.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# Module-scoped fixture: run the graph once, build diagnosis, render opener
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def phase3_outputs(tmp_path_factory):
    """Run graph on fixture corpus, build diagnosis + opener, write all files."""
    tmp = tmp_path_factory.mktemp("phase3")
    docs_dir = tmp / "docs"
    results_dir = tmp / "results"

    from agent.fixture import make_fixture_plan, make_fixture_reviews
    from agent.graph import build_graph, make_initial_state
    from agent.trace import TraceContext
    from diagnosis import build_diagnosis, render_opener, write_outputs
    from llm.stub import StubLLMClient

    reviews = make_fixture_reviews()
    plan = make_fixture_plan()
    stub = StubLLMClient()
    tracer = TraceContext(output_path=tmp / "trace.json")

    graph = build_graph(llm=stub, tracer=tracer)
    initial = make_initial_state(
        fixture_reviews=reviews,
        fetch_plan=plan,
        min_n_floor=5,
        cost_ceiling_usd=999.0,
    )

    with tracer:
        state = graph.invoke(initial)

    diagnosis = write_outputs(state, docs_dir=docs_dir, results_dir=results_dir)
    opener_md = (docs_dir / "opener.md").read_text(encoding="utf-8")

    return {
        "state": state,
        "diagnosis": diagnosis,
        "opener_md": opener_md,
        "docs_dir": docs_dir,
        "results_dir": results_dir,
    }


# ---------------------------------------------------------------------------
# 1. No untagged comparative claims
# ---------------------------------------------------------------------------


class TestNoUntaggedComparativeClaims:
    """Every line in opener.md that contains 'than' must also carry
    [Supported] or [Directional]."""

    def test_no_than_line_without_tag(self, phase3_outputs):
        opener_md = phase3_outputs["opener_md"]
        tag_re = re.compile(r"\[(Supported|Directional)\]", re.IGNORECASE)
        than_re = re.compile(r"\bthan\b", re.IGNORECASE)

        violations = []
        for lineno, line in enumerate(opener_md.splitlines(), 1):
            if than_re.search(line) and not tag_re.search(line):
                violations.append(f"  line {lineno}: {line!r}")

        assert not violations, (
            "Untagged 'than' lines found in opener.md:\n" + "\n".join(violations)
        )

    def test_opener_md_file_exists(self, phase3_outputs):
        assert (phase3_outputs["docs_dir"] / "opener.md").exists()

    def test_opener_md_is_non_empty(self, phase3_outputs):
        assert len(phase3_outputs["opener_md"].strip()) > 100


# ---------------------------------------------------------------------------
# 2. Supported deltas always precede Directional ones
# ---------------------------------------------------------------------------


class TestDeltaOrdering:
    """No Directional delta may appear at an index lower than any Supported delta."""

    def test_supported_before_directional(self, phase3_outputs):
        deltas = phase3_outputs["diagnosis"].get("deltas", [])
        levels = [d["support_level"] for d in deltas]

        last_supported_idx = -1
        first_directional_idx = len(levels)

        for i, level in enumerate(levels):
            if level == "Supported":
                last_supported_idx = i
            elif level == "Directional" and first_directional_idx == len(levels):
                first_directional_idx = i

        assert last_supported_idx < first_directional_idx, (
            f"Directional delta at position {first_directional_idx} appears before "
            f"the last Supported delta at position {last_supported_idx}.\n"
            f"Levels: {levels}"
        )

    def test_all_deltas_have_valid_support_level(self, phase3_outputs):
        for i, d in enumerate(phase3_outputs["diagnosis"].get("deltas", [])):
            assert d["support_level"] in (
                "Supported",
                "Directional",
            ), f"Delta {i} has unexpected support_level: {d['support_level']!r}"


# ---------------------------------------------------------------------------
# 3. diagnosis.json has n + CI on every per-100 rate
# ---------------------------------------------------------------------------


class TestDiagnosisJsonCompleteness:
    """n, ci_low, ci_high, per_100 must be present on every rate in pains and deltas."""

    _REQUIRED_RATE_KEYS = {"per_100", "ci_low", "ci_high", "n"}

    def test_pains_rates_complete(self, phase3_outputs):
        missing: list[str] = []
        for pain in phase3_outputs["diagnosis"].get("pains", []):
            for app, rate in pain["rates"].items():
                for key in self._REQUIRED_RATE_KEYS:
                    if key not in rate:
                        missing.append(
                            f"pains[{pain['theme']}/{pain['sentiment']}/{app}] missing '{key}'"
                        )
        assert not missing, "Missing fields:\n" + "\n".join(missing)

    def test_delta_target_baseline_complete(self, phase3_outputs):
        missing: list[str] = []
        for i, delta in enumerate(phase3_outputs["diagnosis"].get("deltas", [])):
            for side in ("target", "baseline"):
                stat = delta.get(side, {})
                for key in self._REQUIRED_RATE_KEYS:
                    if key not in stat:
                        missing.append(f"deltas[{i}].{side} missing '{key}'")
        assert not missing, "Missing fields:\n" + "\n".join(missing)

    def test_ci_values_are_numbers(self, phase3_outputs):
        for pain in phase3_outputs["diagnosis"].get("pains", []):
            for app, rate in pain["rates"].items():
                assert isinstance(rate["ci_low"], (int, float)), (
                    f"{pain['theme']}/{app} ci_low is not numeric"
                )
                assert isinstance(rate["ci_high"], (int, float)), (
                    f"{pain['theme']}/{app} ci_high is not numeric"
                )
                assert rate["ci_low"] <= rate["per_100"] <= rate["ci_high"] or (
                    rate["ci_low"] <= rate["ci_high"]
                ), f"{pain['theme']}/{app}: CI [{rate['ci_low']}, {rate['ci_high']}] invalid"

    def test_diagnosis_json_file_exists(self, phase3_outputs):
        assert (phase3_outputs["docs_dir"] / "diagnosis.json").exists()

    def test_diagnosis_json_valid(self, phase3_outputs):
        path = phase3_outputs["docs_dir"] / "diagnosis.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "pains" in data
        assert "deltas" in data
        assert "generated_at" in data


# ---------------------------------------------------------------------------
# 4. last_run.json loads as valid JSON with no network/LLM call
# ---------------------------------------------------------------------------


class TestLastRunJson:
    """last_run.json must exist, be valid JSON, and require no network or LLM."""

    def test_last_run_json_exists(self, phase3_outputs):
        assert (phase3_outputs["results_dir"] / "last_run.json").exists(), (
            "data/results/last_run.json was not created"
        )

    def test_last_run_json_loads(self, phase3_outputs):
        path = phase3_outputs["results_dir"] / "last_run.json"
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert isinstance(data, dict), "last_run.json root must be a JSON object"

    def test_last_run_json_required_keys(self, phase3_outputs):
        path = phase3_outputs["results_dir"] / "last_run.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("generated_at", "total_n", "pains", "deltas", "interventions", "opener_md"):
            assert key in data, f"last_run.json missing key '{key}'"

    def test_last_run_json_opener_md_is_string(self, phase3_outputs):
        path = phase3_outputs["results_dir"] / "last_run.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data.get("opener_md"), str)
        assert len(data["opener_md"]) > 50


# ---------------------------------------------------------------------------
# 5. Non-trivial ordering test: synthetic dict with BOTH Supported + Directional
# ---------------------------------------------------------------------------

def _rate(app: str, per_100: float, n: int, ci_lo: float, ci_hi: float) -> dict:
    return {"app": app, "per_100": per_100, "ci_low": ci_lo, "ci_high": ci_hi, "n": n}


def _delta_dict(
    theme: str,
    sentiment: str,
    support_level: str,
    delta_val: float,
    vs_app: str = "Airalo",
) -> dict:
    direction = "higher" if delta_val > 0 else "lower"
    return {
        "theme": theme,
        "sentiment": sentiment,
        "vs_app": vs_app,
        "delta_per_100": delta_val,
        "support_level": support_level,
        "claim": (
            f"USim has {abs(delta_val):.1f} per-100 {direction} "
            f"{theme} ({sentiment}) mentions than {vs_app} ({support_level})."
        ),
        "target": _rate("USim", 20.0, 10, 12.0, 30.0),
        "baseline": _rate(vs_app, 5.0, 10, 1.0, 15.0),
    }


def _pain(theme: str, sentiment: str, loudness: float) -> dict:
    return {
        "theme": theme,
        "sentiment": sentiment,
        "rates": {"USim": _rate("USim", loudness, 10, loudness * 0.5, loudness * 1.5)},
        "field_median_per_100": loudness * 0.8,
        "loudness": loudness,
    }


def _synthetic_diagnosis(deltas: list[dict], pains: list[dict] | None = None) -> dict:
    return {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "recency_window": 12,
        "total_n": 100,
        "per_source_n": {"appstore": 100},
        "target_app": "USim",
        "pains": pains or [_pain("activation", "negative", 20.0)],
        "deltas": deltas,
        "interventions": ["Action A", "Action B", "Action C"],
    }


class TestDeltaOrderingWithMixedDeltas:
    """Exercises ordering with a synthetic dict that has BOTH Supported AND Directional
    deltas.  The fixture produces 0 Supported deltas, so these tests actually exercise
    the ordering path that the fixture-based test skips by emptiness."""

    def test_build_diagnosis_reorders_directional_before_supported_to_correct_order(self):
        """build_diagnosis must sort Supported before Directional even when deltas arrive
        in the wrong order (Directional first)."""
        from agent.state import Delta, ThemeStat
        from diagnosis import build_diagnosis
        from sources.models import AppTarget, FetchPlan
        from tools.quantify import wilson_ci

        def _ts(app, theme, sentiment, count, nobs):
            prop = count / nobs
            lo, hi = wilson_ci(count, nobs)
            return ThemeStat(
                app=app, theme=theme, sentiment=sentiment,
                count=count, nobs=nobs, proportion=prop,
                ci_low=lo, ci_high=hi, per_100=prop * 100,
            )

        # activation — USim 20/100 vs Airalo 5/100: CIs are disjoint → Supported
        usim_act = _ts("USim", "activation", "negative", 20, 100)
        airalo_act = _ts("Airalo", "activation", "negative", 5, 100)
        # support — USim 8/100 vs Airalo 6/100: CIs overlap → Directional
        usim_supp = _ts("USim", "support", "negative", 8, 100)
        airalo_supp = _ts("Airalo", "support", "negative", 6, 100)

        supported_delta = Delta(
            theme="activation", sentiment="negative",
            target=usim_act, baseline=airalo_act,
            delta_per_100=usim_act.per_100 - airalo_act.per_100,
            support_level="Supported",
        )
        directional_delta = Delta(
            theme="support", sentiment="negative",
            target=usim_supp, baseline=airalo_supp,
            delta_per_100=usim_supp.per_100 - airalo_supp.per_100,
            support_level="Directional",
        )

        plan = FetchPlan(
            targets=[AppTarget(name="USim", app_store_id="x", countries=["us"])],
            max_pages=1, enabled_sources=["appstore"],
        )
        # Feed deltas in WRONG order: Directional first
        state = {
            "stats": [usim_act, airalo_act, usim_supp, airalo_supp],
            "deltas": [directional_delta, supported_delta],
            "claims": [],
            "classified": [],
            "triaged_reviews": [],
            "fetch_plan": plan,
        }

        diagnosis = build_diagnosis(state)
        levels = [d["support_level"] for d in diagnosis["deltas"]]

        assert "Supported" in levels, "Expected at least one Supported delta in output"
        assert "Directional" in levels, "Expected at least one Directional delta in output"

        last_supported = max(i for i, l in enumerate(levels) if l == "Supported")
        first_directional = min(i for i, l in enumerate(levels) if l == "Directional")
        assert last_supported < first_directional, (
            f"build_diagnosis failed to reorder: Directional at {first_directional} "
            f"precedes last Supported at {last_supported}. levels={levels}"
        )

    def test_wrong_order_synthetic_dict_fails_ordering_invariant(self):
        """Verify our ordering check is sensitive: a dict with Directional before
        Supported IS detected as a violation (i.e. the test is not vacuous)."""
        supported = _delta_dict("activation", "negative", "Supported", +15.0)
        directional = _delta_dict("support", "negative", "Directional", +5.0)

        # Intentionally wrong order
        diag = _synthetic_diagnosis([directional, supported])
        levels = [d["support_level"] for d in diag["deltas"]]

        last_supported = max((i for i, l in enumerate(levels) if l == "Supported"), default=-1)
        first_directional = min((i for i, l in enumerate(levels) if l == "Directional"), default=len(levels))

        assert last_supported > first_directional, (
            "Expected a detectable ordering violation when Directional precedes Supported"
        )

    def test_correct_order_synthetic_dict_passes_ordering_invariant(self):
        """Verify a correctly-ordered dict (Supported first) passes the invariant."""
        supported = _delta_dict("activation", "negative", "Supported", +15.0)
        directional = _delta_dict("support", "negative", "Directional", +5.0)

        diag = _synthetic_diagnosis([supported, directional])
        levels = [d["support_level"] for d in diag["deltas"]]

        last_supported = max((i for i, l in enumerate(levels) if l == "Supported"), default=-1)
        first_directional = min((i for i, l in enumerate(levels) if l == "Directional"), default=len(levels))

        assert last_supported < first_directional


# ---------------------------------------------------------------------------
# 6. Headline logic — Supported vs. degradation
# ---------------------------------------------------------------------------


class TestHeadlineLogic:
    """render_opener must headline a Supported pain when one exists, and degrade
    honestly (no [Directional] claim as lede) when none exists."""

    def test_supported_delta_produces_supported_headline(self):
        """When a Supported delta exists, the headline line must contain [Supported]."""
        from diagnosis import render_opener

        diag = _synthetic_diagnosis(
            deltas=[_delta_dict("activation", "negative", "Supported", +15.0)],
            pains=[_pain("activation", "negative", 20.0)],
        )

        opener = render_opener(diag)
        headline = next((l for l in opener.splitlines() if l.startswith("**")), "")
        assert headline, "No bold headline found in opener"
        assert "[Supported]" in headline, (
            f"Expected [Supported] in headline when a Supported delta exists.\n"
            f"Got: {headline!r}"
        )
        assert "[Directional]" not in headline

    def test_no_supported_delta_produces_degradation_headline(self):
        """When NO Supported delta exists, the headline must be the honest degradation
        message — no [Directional] masquerading as a finding."""
        from diagnosis import render_opener

        diag = _synthetic_diagnosis(
            deltas=[_delta_dict("support", "negative", "Directional", -6.7)],
            pains=[_pain("support", "negative", 10.0)],
        )

        opener = render_opener(diag)
        headline = next((l for l in opener.splitlines() if l.startswith("**")), "")
        assert headline, "No bold headline found in opener"
        assert "[Supported]" not in headline, (
            f"Degradation headline must not claim [Supported].\nGot: {headline!r}"
        )
        assert "[Directional]" not in headline, (
            f"Degradation headline must not present a [Directional] claim as lede.\n"
            f"Got: {headline!r}"
        )
        assert any(
            kw in headline.lower()
            for kw in ("no cross-company", "significance", "orientation")
        ), (
            f"Expected degradation language in headline.\nGot: {headline!r}"
        )

    def test_fixture_opener_headline_is_degradation(self, phase3_outputs):
        """The fixture corpus produces 0 Supported deltas, so its headline must be
        the honest degradation message, NOT a [Directional] claim."""
        opener_md = phase3_outputs["opener_md"]
        headline = next(
            (l for l in opener_md.splitlines() if l.startswith("**")), ""
        )
        assert headline, "No bold headline found in fixture opener"
        assert "[Directional]" not in headline, (
            f"Fixture headline must not carry [Directional] as a finding.\n"
            f"Got: {headline!r}"
        )
        assert "[Supported]" not in headline, (
            "Fixture has 0 Supported deltas so headline must not claim [Supported]"
        )
