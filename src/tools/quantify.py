"""Quantify tool — pure Python, no LLM.

Computes per-(app, theme, sentiment) proportions with Wilson 95% CIs and
builds Delta objects comparing the target app against each competitor.

Supported vs Directional rules (design doc §2.1):
  Supported   = count >= min_n_floor  AND  Wilson CIs are disjoint
  Directional = everything else
Raw counts are never compared across apps of different sizes — only
normalised proportions and their CIs are used.
"""

from __future__ import annotations

from collections import defaultdict

from statsmodels.stats.proportion import proportion_confint

from agent.state import ClassifiedReview, Delta, ThemeStat

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_stats(
    classified: list[ClassifiedReview],
    *,
    min_n_floor: int = 30,
    target_app: str = "USim",
) -> tuple[list[ThemeStat], list[Delta]]:
    """Return (stats, deltas) for all apps in classified.

    Args:
        classified:  Output of the cluster node (themes normalised).
        min_n_floor: Minimum count per cell to qualify for Supported status.
        target_app:  The primary app whose results are compared to others.
    """
    if not classified:
        return [], []

    stats = _build_stats(classified)
    deltas = _build_deltas(stats, min_n_floor=min_n_floor, target_app=target_app)
    return stats, deltas


# ---------------------------------------------------------------------------
# Wilson CI helper (exposed so tests can verify directly)
# ---------------------------------------------------------------------------


def wilson_ci(count: int, nobs: int, alpha: float = 0.05) -> tuple[float, float]:
    """Return (lower, upper) Wilson confidence interval.

    Wraps statsmodels proportion_confint with method='wilson'.
    Handles edge cases: count=0 or count=nobs returns a valid degenerate CI.
    """
    if nobs == 0:
        return 0.0, 1.0
    count = max(0, min(count, nobs))
    lo, hi = proportion_confint(count, nobs, alpha=alpha, method="wilson")
    return float(lo), float(hi)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_stats(classified: list[ClassifiedReview]) -> list[ThemeStat]:
    # total reviews per app
    app_totals: dict[str, int] = defaultdict(int)
    for r in classified:
        app_totals[r.app] += 1

    # counts per (app, theme, sentiment)
    cell_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for r in classified:
        cell_counts[(r.app, r.theme, r.sentiment)] += 1

    stats: list[ThemeStat] = []
    for (app, theme, sentiment), count in cell_counts.items():
        nobs = app_totals[app]
        proportion = count / nobs
        ci_low, ci_high = wilson_ci(count, nobs)
        stats.append(
            ThemeStat(
                app=app,
                theme=theme,
                sentiment=sentiment,
                count=count,
                nobs=nobs,
                proportion=proportion,
                ci_low=ci_low,
                ci_high=ci_high,
                per_100=proportion * 100,
            )
        )

    return stats


def _build_deltas(
    stats: list[ThemeStat],
    *,
    min_n_floor: int,
    target_app: str,
) -> list[Delta]:
    # Index stats by (app, theme, sentiment)
    index: dict[tuple[str, str, str], ThemeStat] = {(s.app, s.theme, s.sentiment): s for s in stats}

    apps = {s.app for s in stats}
    competitor_apps = apps - {target_app}
    theme_sentiments = {(s.theme, s.sentiment) for s in stats}

    deltas: list[Delta] = []
    for theme, sentiment in theme_sentiments:
        target_stat = index.get((target_app, theme, sentiment))
        if target_stat is None:
            continue

        for comp_app in sorted(competitor_apps):
            baseline_stat = index.get((comp_app, theme, sentiment))
            if baseline_stat is None:
                continue

            support_level = _support_level(target_stat, baseline_stat, min_n_floor)
            deltas.append(
                Delta(
                    theme=theme,
                    sentiment=sentiment,
                    target=target_stat,
                    baseline=baseline_stat,
                    delta_per_100=target_stat.per_100 - baseline_stat.per_100,
                    support_level=support_level,
                )
            )

    return deltas


def _support_level(a: ThemeStat, b: ThemeStat, min_n_floor: int) -> str:
    """Return "Supported" iff both cells meet the floor AND CIs are disjoint."""
    if a.count < min_n_floor or b.count < min_n_floor:
        return "Directional"
    # Disjoint: one interval lies entirely below the other
    if a.ci_high < b.ci_low or b.ci_high < a.ci_low:
        return "Supported"
    return "Directional"
