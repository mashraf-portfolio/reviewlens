"""Tests for tools.quantify — Wilson CIs, min-n gating, Supported/Directional.

All tests are pure Python; no LLM, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from statsmodels.stats.proportion import proportion_confint

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import UTC, datetime

from agent.state import ClassifiedReview, ThemeStat
from tools.quantify import _support_level, compute_stats, wilson_ci

# ---------------------------------------------------------------------------
# Wilson CI — hand-computed reference values
# ---------------------------------------------------------------------------


class TestWilsonCI:
    def test_matches_statsmodels_ground_truth(self):
        """wilson_ci(20, 30) must equal statsmodels proportion_confint exactly."""
        expected_lo, expected_hi = proportion_confint(20, 30, alpha=0.05, method="wilson")
        lo, hi = wilson_ci(20, 30)
        assert lo == pytest.approx(expected_lo, abs=1e-9)
        assert hi == pytest.approx(expected_hi, abs=1e-9)

    def test_reference_values_20_of_30(self):
        """Hardcoded reference: wilson_ci(20, 30) ≈ (0.4878, 0.8077) at 95%."""
        lo, hi = wilson_ci(20, 30)
        # Verified against statsmodels proportion_confint(20, 30, method='wilson').
        assert lo == pytest.approx(0.4878, abs=0.001)
        assert hi == pytest.approx(0.8077, abs=0.001)

    def test_reference_values_3_of_30(self):
        """Hardcoded reference: wilson_ci(3, 30) ≈ (0.0346, 0.2562) at 95%."""
        lo, hi = wilson_ci(3, 30)
        assert lo == pytest.approx(0.0346, abs=0.001)
        assert hi == pytest.approx(0.2562, abs=0.001)

    def test_zero_count(self):
        lo, hi = wilson_ci(0, 30)
        assert lo == pytest.approx(0.0, abs=0.01)
        assert hi < 0.12  # CI upper bound with 0 successes from 30 is small

    def test_full_count(self):
        lo, hi = wilson_ci(30, 30)
        assert lo > 0.88  # CI lower bound with 30/30 is large
        assert hi == pytest.approx(1.0, abs=0.001)

    def test_zero_nobs_returns_full_uncertainty(self):
        lo, hi = wilson_ci(0, 0)
        assert lo == 0.0
        assert hi == 1.0


# ---------------------------------------------------------------------------
# _support_level  (isolated unit)
# ---------------------------------------------------------------------------


def _stat(app, theme, sentiment, count, nobs) -> ThemeStat:
    p = count / nobs
    lo, hi = wilson_ci(count, nobs)
    return ThemeStat(
        app=app,
        theme=theme,
        sentiment=sentiment,
        count=count,
        nobs=nobs,
        proportion=p,
        ci_low=lo,
        ci_high=hi,
        per_100=p * 100,
    )


class TestSupportLevel:
    def test_supported_requires_disjoint_cis_and_floor(self):
        """CIs [0.46, 0.79] vs [0.03, 0.26] are disjoint — both n=20,3 >= floor=3."""
        a = _stat("USim", "app_ux", "negative", 20, 30)
        b = _stat("Airalo", "app_ux", "negative", 3, 30)
        assert _support_level(a, b, min_n_floor=3) == "Supported"

    def test_directional_when_n_below_floor(self):
        """Even with disjoint CIs, n < floor → Directional."""
        a = _stat("USim", "app_ux", "negative", 20, 30)
        b = _stat("Airalo", "app_ux", "negative", 3, 30)
        # floor=25 — only 'a' meets it, not 'b' (count=3)
        assert _support_level(a, b, min_n_floor=25) == "Directional"

    def test_directional_when_cis_overlap(self):
        """Overlapping CIs → Directional even when both n >= floor."""
        a = _stat("USim", "app_ux", "negative", 15, 30)
        b = _stat("Airalo", "app_ux", "negative", 14, 30)
        # Proportions 0.5 vs 0.467 — CIs overlap
        assert _support_level(a, b, min_n_floor=5) == "Directional"

    def test_both_n_must_meet_floor(self):
        """Only one of the two cells meeting the floor is not enough."""
        a = _stat("USim", "app_ux", "negative", 20, 30)  # count=20 >= 10
        b = _stat("Airalo", "app_ux", "negative", 2, 30)  # count=2  <  10
        assert _support_level(a, b, min_n_floor=10) == "Directional"


# ---------------------------------------------------------------------------
# compute_stats — integration
# ---------------------------------------------------------------------------


def _make_classified(review_id, app, theme, sentiment):
    return ClassifiedReview(
        review_id=review_id,
        app=app,
        date=datetime(2025, 11, 1, tzinfo=UTC),
        theme=theme,
        sentiment=sentiment,
        friction_phrase="test",
        confidence=0.9,
    )


class TestComputeStats:
    def _corpus(self):
        rows = []
        # USim: 20 app_ux negative, 5 positive positive
        for i in range(20):
            rows.append(_make_classified(f"u{i}", "USim", "app_ux", "negative"))
        for i in range(5):
            rows.append(_make_classified(f"up{i}", "USim", "positive", "positive"))
        # Airalo: 3 app_ux negative, 7 positive positive
        for i in range(3):
            rows.append(_make_classified(f"a{i}", "Airalo", "app_ux", "negative"))
        for i in range(7):
            rows.append(_make_classified(f"ap{i}", "Airalo", "positive", "positive"))
        return rows

    def test_stats_produced_for_each_cell(self):
        stats, _ = compute_stats(self._corpus(), min_n_floor=3, target_app="USim")
        cells = {(s.app, s.theme, s.sentiment) for s in stats}
        assert ("USim", "app_ux", "negative") in cells
        assert ("Airalo", "app_ux", "negative") in cells

    def test_proportion_correct(self):
        stats, _ = compute_stats(self._corpus(), min_n_floor=3, target_app="USim")
        usim_appux = next(s for s in stats if s.app == "USim" and s.theme == "app_ux")
        # USim total = 25, app_ux negative = 20 → proportion = 0.8
        assert usim_appux.count == 20
        assert usim_appux.nobs == 25
        assert usim_appux.proportion == pytest.approx(0.8, abs=1e-6)
        assert usim_appux.per_100 == pytest.approx(80.0, abs=1e-6)

    def test_delta_direction(self):
        _, deltas = compute_stats(self._corpus(), min_n_floor=3, target_app="USim")
        appux_delta = next(d for d in deltas if d.theme == "app_ux" and d.sentiment == "negative")
        # USim 80% vs Airalo 3/10 = 30% → delta > 0
        assert appux_delta.delta_per_100 > 0
        assert appux_delta.target.app == "USim"
        assert appux_delta.baseline.app == "Airalo"

    def test_supported_when_floor_met_and_cis_disjoint(self):
        _, deltas = compute_stats(self._corpus(), min_n_floor=3, target_app="USim")
        appux_delta = next(d for d in deltas if d.theme == "app_ux" and d.sentiment == "negative")
        # count=20 >= 3 AND count=3 >= 3 AND CIs should be disjoint (80% vs 30%)
        assert appux_delta.support_level == "Supported"

    def test_directional_when_floor_not_met(self):
        _, deltas = compute_stats(self._corpus(), min_n_floor=25, target_app="USim")
        # With min_n_floor=25, Airalo's count=3 is too small → Directional
        for d in deltas:
            if d.baseline.app == "Airalo" and d.theme == "app_ux":
                assert d.support_level == "Directional"
                return
        pytest.skip("No matching delta found")

    def test_empty_corpus_returns_empty(self):
        stats, deltas = compute_stats([], min_n_floor=5, target_app="USim")
        assert stats == []
        assert deltas == []

    def test_no_competitor_produces_no_deltas(self):
        """When only the target app is present there are no comparison deltas."""
        rows = [_make_classified(f"u{i}", "USim", "app_ux", "negative") for i in range(10)]
        _, deltas = compute_stats(rows, min_n_floor=3, target_app="USim")
        assert deltas == []
