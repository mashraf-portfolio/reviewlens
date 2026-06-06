"""Rigor mandate: thin-sample and CI-overlapping deltas are always Directional.

This is ReviewLens's headline statistical guarantee (design doc §2.1 rigor mandate):
a delta that *looks* dramatic but rests on a thin or ambiguous sample must never
be marked Supported.  Tests call compute_stats() directly — no LLM, no network.

The positive-control test (test_floor_met_and_disjoint_cis_yields_supported) makes
the suite non-vacuous: if _support_level() stopped checking either condition, at
least one test here would fail.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.state import ClassifiedReview
from tools.quantify import compute_stats, wilson_ci

_DATE = datetime(2025, 6, 1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cr(review_id: str, app: str, theme: str, sentiment: str) -> ClassifiedReview:
    return ClassifiedReview(
        review_id=review_id,
        app=app,
        date=_DATE,
        theme=theme,
        sentiment=sentiment,
        friction_phrase="",
        confidence=0.9,
    )


def _corpus(
    *,
    target_app: str,
    target_total: int,
    target_hot: int,
    comp_app: str,
    comp_total: int,
    comp_hot: int,
    theme: str = "support",
    sentiment: str = "negative",
) -> list[ClassifiedReview]:
    """Corpus with `target_hot` / `comp_hot` reviews in (theme, sentiment) cell.

    Remaining reviews use a distinct pad cell so they don't create noise deltas
    on the cell under test.
    """
    reviews: list[ClassifiedReview] = []
    for i in range(target_total):
        t, s = (theme, sentiment) if i < target_hot else ("positive", "positive")
        reviews.append(_cr(f"t{i}", target_app, t, s))
    for i in range(comp_total):
        t, s = (theme, sentiment) if i < comp_hot else ("positive", "positive")
        reviews.append(_cr(f"c{i}", comp_app, t, s))
    return reviews


def _find_delta(deltas, *, target_app, comp_app, theme, sentiment):
    for d in deltas:
        if (
            d.target.app == target_app
            and d.baseline.app == comp_app
            and d.theme == theme
            and d.sentiment == sentiment
        ):
            return d
    return None


# ---------------------------------------------------------------------------
# Thin-sample scenarios
# ---------------------------------------------------------------------------


class TestThinSampleIsAlwaysDirectional:
    """Competitor or target count below n-floor → Directional regardless of delta size."""

    def test_huge_delta_thin_comp_sample(self):
        """USim 25% vs competitor 100%, but competitor n=5 < floor=30 → Directional.

        The delta is –75 per-100: enormous.  The rigor mandate downgrades it.
        """
        corpus = _corpus(
            target_app="USim",
            target_total=40,
            target_hot=10,
            comp_app="Rival",
            comp_total=5,
            comp_hot=5,
        )
        _, deltas = compute_stats(corpus, min_n_floor=30, target_app="USim")
        d = _find_delta(
            deltas, target_app="USim", comp_app="Rival", theme="support", sentiment="negative"
        )
        assert d is not None, "delta must exist for this cell"
        assert abs(d.delta_per_100) > 50, "this scenario should produce a large-magnitude delta"
        assert d.support_level == "Directional", (
            f"n={d.baseline.count} < floor=30 must produce Directional (got {d.support_level})"
        )

    def test_thin_target_sample_is_directional(self):
        """Target n=5 < floor=30 → Directional even if competitor has many reviews."""
        corpus = _corpus(
            target_app="USim",
            target_total=5,
            comp_app="Rival",
            target_hot=5,
            comp_total=40,
            comp_hot=2,
        )
        _, deltas = compute_stats(corpus, min_n_floor=30, target_app="USim")
        d = _find_delta(
            deltas, target_app="USim", comp_app="Rival", theme="support", sentiment="negative"
        )
        assert d is not None
        assert d.target.count < 30
        assert d.support_level == "Directional"

    def test_both_thin_is_directional(self):
        """Both samples thin — trivially Directional."""
        corpus = _corpus(
            target_app="USim",
            target_total=10,
            target_hot=8,
            comp_app="Rival",
            comp_total=10,
            comp_hot=2,
        )
        _, deltas = compute_stats(corpus, min_n_floor=30, target_app="USim")
        d = _find_delta(
            deltas, target_app="USim", comp_app="Rival", theme="support", sentiment="negative"
        )
        assert d is not None
        assert d.support_level == "Directional"

    def test_floor_boundary_one_below_is_directional(self):
        """count=29 < floor=30 → Directional even when CIs would be disjoint."""
        corpus = _corpus(
            target_app="USim",
            target_total=100,
            target_hot=29,
            comp_app="Rival",
            comp_total=100,
            comp_hot=80,
        )
        _, deltas = compute_stats(corpus, min_n_floor=30, target_app="USim")
        d = _find_delta(
            deltas, target_app="USim", comp_app="Rival", theme="support", sentiment="negative"
        )
        assert d is not None
        assert d.target.count == 29
        assert d.support_level == "Directional", (
            "count=29 is one below the floor=30 strict threshold; must be Directional"
        )


# ---------------------------------------------------------------------------
# Overlapping-CI scenario
# ---------------------------------------------------------------------------


class TestOverlappingCIsIsDirectional:
    """Both n >= floor but overlapping Wilson CIs → Directional."""

    def test_overlapping_cis_despite_floor(self):
        """USim 15/30 and Rival 20/30: both counts >= floor=15, CIs overlap → Directional.

        min_n_floor=15 so both counts (15, 20) satisfy the floor, isolating the
        CI-overlap path from the n-floor path.

        CI reference (from test_quantify_stats.py):
          wilson_ci(20, 30) ≈ (0.488, 0.808)
          wilson_ci(15, 30) ≈ (0.317, 0.683)
        USim ci_high (0.683) > Rival ci_low (0.488): overlap confirmed → Directional.
        """
        corpus = _corpus(
            target_app="USim",
            target_total=30,
            target_hot=15,
            comp_app="Rival",
            comp_total=30,
            comp_hot=20,
        )
        _, deltas = compute_stats(corpus, min_n_floor=15, target_app="USim")
        d = _find_delta(
            deltas, target_app="USim", comp_app="Rival", theme="support", sentiment="negative"
        )
        assert d is not None
        # Both counts must satisfy the floor so the CI check is the deciding factor
        assert d.target.count >= 15, "USim count must meet floor=15 to isolate CI-overlap path"
        assert d.baseline.count >= 15, "Rival count must meet floor=15 to isolate CI-overlap path"
        # CIs must overlap — verify the test assumption holds
        assert d.target.ci_high > d.baseline.ci_low, (
            "test assumes CIs overlap; adjust counts if wilson_ci values changed"
        )
        assert d.support_level == "Directional"


# ---------------------------------------------------------------------------
# Positive control — verifies tests are non-vacuous
# ---------------------------------------------------------------------------


class TestSupportedRequiresBothConditions:
    """Positive control: floor met AND disjoint CIs → Supported.

    Without this test, the Directional tests above might pass vacuously if
    _support_level() always returned "Directional".
    """

    def test_floor_met_and_disjoint_cis_yields_supported(self):
        """USim 30/100 vs Rival 80/100: both >= floor=30, CIs disjoint → Supported.

        CI reference:
          wilson_ci(30, 100) ≈ (0.215, 0.401)
          wilson_ci(80, 100) ≈ (0.711, 0.870)
        USim ci_high (0.401) < Rival ci_low (0.711): disjoint confirmed.
        """
        corpus = _corpus(
            target_app="USim",
            target_total=100,
            target_hot=30,
            comp_app="Rival",
            comp_total=100,
            comp_hot=80,
        )
        _, deltas = compute_stats(corpus, min_n_floor=30, target_app="USim")
        d = _find_delta(
            deltas, target_app="USim", comp_app="Rival", theme="support", sentiment="negative"
        )
        assert d is not None
        # Verify assumptions about counts and CI shape
        assert d.target.count >= 30
        assert d.baseline.count >= 30
        assert d.target.ci_high < d.baseline.ci_low, (
            "test assumes CIs are disjoint; adjust counts if wilson_ci values changed"
        )
        assert d.support_level == "Supported"

    def test_floor_boundary_exactly_at_floor_with_disjoint_cis(self):
        """count=30 == floor=30 with disjoint CIs → Supported (floor check is >=)."""
        # Use same counts as the test above (target_hot=30): count exactly equals floor
        corpus = _corpus(
            target_app="USim",
            target_total=100,
            target_hot=30,
            comp_app="Rival",
            comp_total=100,
            comp_hot=80,
        )
        _, deltas = compute_stats(corpus, min_n_floor=30, target_app="USim")
        d = _find_delta(
            deltas, target_app="USim", comp_app="Rival", theme="support", sentiment="negative"
        )
        assert d is not None
        assert d.target.count == 30
        lo_t, hi_t = wilson_ci(30, 100)
        lo_b, hi_b = wilson_ci(80, 100)
        assert hi_t < lo_b, "CIs disjoint with these reference counts"
        assert d.support_level == "Supported"

    @pytest.mark.parametrize("floor", [1, 5, 30])
    def test_supported_consistent_across_floor_values(self, floor: int):
        """When floor is satisfied and CIs disjoint, result is always Supported."""
        corpus = _corpus(
            target_app="USim",
            target_total=100,
            target_hot=max(floor, 5),
            comp_app="Rival",
            comp_total=100,
            comp_hot=80,
        )
        _, deltas = compute_stats(corpus, min_n_floor=floor, target_app="USim")
        d = _find_delta(
            deltas, target_app="USim", comp_app="Rival", theme="support", sentiment="negative"
        )
        if d is None:
            pytest.skip("no delta for this cell in this parameterisation")
        if (
            d.target.ci_high < d.baseline.ci_low
            and d.target.count >= floor
            and d.baseline.count >= floor
        ):
            assert d.support_level == "Supported"
