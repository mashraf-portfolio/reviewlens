"""Build diagnosis.json and render opener.md from completed graph state.

Public API
----------
  build_diagnosis(state)   -> dict   (diagnosis.json content)
  render_opener(diagnosis) -> str    (opener.md content)
  write_outputs(state, docs_dir, results_dir) -> dict  (writes 4 files)

Consumes ONLY state["stats"], state["deltas"], state["claims"] and
state["triaged_reviews"] for source-level counts.  Does NOT recompute
statistics or call the LLM.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

# ---------------------------------------------------------------------------
# Intervention copy keyed by theme  (data-driven, selected by top pains)
# ---------------------------------------------------------------------------

_INTERVENTION_COPY: dict[str, str] = {
    "activation": (
        "Deploy an activation watchdog: alert ops when a QR-code scan fails twice, "
        "trigger an automated re-delivery, and send a 30-minute check-in message — "
        "eliminate silent activation failures before they become refund requests."
    ),
    "support": (
        "Set a 4-hour first-response SLA; auto-triage tickets by theme (activation, "
        "refund) and route to a specialist queue — remove the silence that turns a "
        "resolvable issue into a one-star review."
    ),
    "refund_billing": (
        "Automate refund-status notifications: confirm receipt within 1 hour and send "
        "a resolution update within 48 hours — silence is what escalates a delayed "
        "refund into a chargeback dispute."
    ),
    "coverage_speed": (
        "Publish a real-time coverage map with honest speed tiers per country; set "
        "expectations before purchase to reduce coverage-related disappointment and "
        "the 1-star reviews that follow."
    ),
    "app_ux": (
        "Redesign the activation flow as a 3-step wizard with inline troubleshooting "
        "— reviews describe 40-minute installs that a guided flow would cut to under "
        "three minutes."
    ),
    "value_pricing": (
        "Add a transparent plan-comparison table and an in-app data-usage widget; "
        "pricing confusion surfaces repeatedly in reviews and is a tractable UX fix, "
        "not a pricing problem."
    ),
}

_FALLBACK_INTERVENTION = (
    "Assign the top-ranked pain an owner, a 30-day target metric, and a weekly "
    "review cadence — the data is diagnostic; the fix requires an execution owner."
)


# ---------------------------------------------------------------------------
# build_diagnosis
# ---------------------------------------------------------------------------


def build_diagnosis(state: dict[str, Any]) -> dict[str, Any]:
    """Assemble the diagnosis dict from completed graph state.

    Layout (matches design doc §6):
      generated_at       — UTC ISO timestamp
      recency_window     — months used for triage filter
      total_n            — total classified reviews
      per_source_n       — {source: n}
      target_app         — primary app name
      pains              — ranked by USim loudness descending
      deltas             — Supported first, Directional second
      interventions      — 3 month-one actions
    """
    stats: list = state.get("stats", [])
    deltas: list = state.get("deltas", [])
    claims: list = state.get("claims", [])
    classified: list = state.get("classified", [])
    triaged: list = state.get("triaged_reviews", [])

    # --- metadata ---
    total_n = len(classified)

    per_source_n: dict[str, int] = defaultdict(int)
    for r in triaged:
        src = getattr(r, "source", "unknown")
        per_source_n[src] += 1
    if not per_source_n:
        per_source_n["unknown"] = total_n

    fetch_plan = state.get("fetch_plan")
    target_app = "USim"
    if fetch_plan and getattr(fetch_plan, "targets", None):
        target_app = fetch_plan.targets[0].name

    # --- pains: one entry per (theme, sentiment) ---
    # Group ThemeStat objects by cell key
    cell_stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    for s in stats:
        cell_stats[(s.theme, s.sentiment)][s.app] = {
            "per_100": round(s.per_100, 2),
            "ci_low": round(s.ci_low * 100, 2),
            "ci_high": round(s.ci_high * 100, 2),
            "n": s.count,
        }

    pains: list[dict[str, Any]] = []
    for (theme, sentiment), app_rates in cell_stats.items():
        if target_app not in app_rates:
            continue
        usim_rate = app_rates[target_app]["per_100"]
        all_rates = [v["per_100"] for v in app_rates.values()]
        field_med = round(median(all_rates), 2)
        pains.append(
            {
                "theme": theme,
                "sentiment": sentiment,
                "rates": app_rates,
                "field_median_per_100": field_med,
                "loudness": usim_rate,  # sort key; stripped from final JSON if desired
            }
        )

    pains.sort(key=lambda p: p["loudness"], reverse=True)

    # --- deltas: Supported first, then Directional (both sorted by |delta| desc) ---
    claim_index: dict[tuple[str, str, str], str] = {}
    for c in claims:
        claim_index[(c.theme, c.sentiment, c.vs_app)] = c.claim

    supported_d = sorted(
        [d for d in deltas if d.support_level == "Supported"],
        key=lambda d: abs(d.delta_per_100),
        reverse=True,
    )
    directional_d = sorted(
        [d for d in deltas if d.support_level == "Directional"],
        key=lambda d: abs(d.delta_per_100),
        reverse=True,
    )

    ordered_deltas: list[dict[str, Any]] = []
    for d in supported_d + directional_d:
        ordered_deltas.append(
            {
                "theme": d.theme,
                "sentiment": d.sentiment,
                "vs_app": d.baseline.app,
                "delta_per_100": round(d.delta_per_100, 2),
                "support_level": d.support_level,
                "claim": claim_index.get((d.theme, d.sentiment, d.baseline.app), ""),
                "target": {
                    "app": d.target.app,
                    "per_100": round(d.target.per_100, 2),
                    "ci_low": round(d.target.ci_low * 100, 2),
                    "ci_high": round(d.target.ci_high * 100, 2),
                    "n": d.target.count,
                },
                "baseline": {
                    "app": d.baseline.app,
                    "per_100": round(d.baseline.per_100, 2),
                    "ci_low": round(d.baseline.ci_low * 100, 2),
                    "ci_high": round(d.baseline.ci_high * 100, 2),
                    "n": d.baseline.count,
                },
            }
        )

    # --- month-one interventions: top-3 negative/mixed themes by USim loudness ---
    top_themes: list[str] = []
    for p in pains:
        if p["sentiment"] in ("negative", "mixed") and p["theme"] not in top_themes:
            top_themes.append(p["theme"])
        if len(top_themes) == 3:
            break

    # Fill remaining slots from default priority
    for theme in ("activation", "support", "refund_billing"):
        if theme not in top_themes and len(top_themes) < 3:
            top_themes.append(theme)

    interventions = [_INTERVENTION_COPY.get(t, _FALLBACK_INTERVENTION) for t in top_themes[:3]]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "recency_window": 12,
        "total_n": total_n,
        "per_source_n": dict(per_source_n),
        "target_app": target_app,
        "pains": pains,
        "deltas": ordered_deltas,
        "interventions": interventions,
    }


# ---------------------------------------------------------------------------
# render_opener
# ---------------------------------------------------------------------------


def render_opener(diagnosis: dict[str, Any]) -> str:
    """Render the one-page opener.md from a diagnosis dict (design doc §6).

    Every comparative sentence carries [Supported] or [Directional].
    No 'than' appears without one of those tags.
    """
    target_app = diagnosis.get("target_app", "USim")
    pains = diagnosis.get("pains", [])
    deltas = diagnosis.get("deltas", [])
    interventions = diagnosis.get("interventions", [])
    total_n = diagnosis.get("total_n", 0)
    recency_window = diagnosis.get("recency_window", 12)
    per_source_n = diagnosis.get("per_source_n", {})

    competitor_apps = sorted({d["vs_app"] for d in deltas})
    n_competitors = len(competitor_apps)

    # -----------------------------------------------------------------
    # Headline — Supported pain ONLY (design doc §6 rigor mandate).
    # Presenting a Directional claim as the lede violates the contract;
    # instead degrade honestly when no Supported delta exists.
    # -----------------------------------------------------------------
    supported_themes = {
        (d["theme"], d["sentiment"]) for d in deltas if d["support_level"] == "Supported"
    }

    # Find loudest pain that has at least one Supported delta behind it.
    headline_pain: dict[str, Any] | None = None
    for p in pains:
        if (p["theme"], p["sentiment"]) in supported_themes and p["sentiment"] in (
            "negative",
            "mixed",
        ):
            headline_pain = p
            break

    if headline_pain is not None:
        usim_rate = headline_pain["rates"].get(target_app, {}).get("per_100", 0.0)
        field_med = headline_pain["field_median_per_100"]
        theme_label = headline_pain["theme"].replace("_", " ")
        sentiment_label = headline_pain["sentiment"]
        direction_word = "above" if usim_rate >= field_med else "below"
        headline = (
            f"**{theme_label.title()} is the loudest {sentiment_label} pain in travel eSIM — "
            f"{target_app} sits at {usim_rate:.1f} per-100, "
            f"{direction_word} the field median of {field_med:.1f}.** [Supported]"
        )
    else:
        # No Supported delta: report orientation-only context without a comparative claim.
        loudest = next(
            (p for p in pains if p["sentiment"] in ("negative", "mixed")), None
        )
        if loudest:
            usim_rate = loudest["rates"].get(target_app, {}).get("per_100", 0.0)
            n = loudest["rates"].get(target_app, {}).get("n", 0)
            theme_label = loudest["theme"].replace("_", " ")
            headline = (
                f"**No cross-company difference clears the significance bar in this sample. "
                f"The loudest pain by raw rate is {theme_label} "
                f"({usim_rate:.1f} per-100, n={n}), reported for orientation only.**"
            )
        else:
            headline = (
                f"**No cross-company difference clears the significance bar in this sample "
                f"— insufficient data for a headline claim on {target_app}.**"
            )

    # -----------------------------------------------------------------
    # Method line
    # -----------------------------------------------------------------
    method = (
        f"An LLM agent read {total_n} public reviews across {target_app} and "
        f"{n_competitors} competitor{'s' if n_competitors != 1 else ''} over the last "
        f"{recency_window} months, classified each into a pain taxonomy, and "
        f"benchmarked rates per-100-reviews with 95% confidence intervals."
    )

    # -----------------------------------------------------------------
    # Top-3 pains table
    # -----------------------------------------------------------------
    top_pains = [p for p in pains if target_app in p["rates"]][:3]

    table_rows = [
        "| Pain | USim per-100 (95% CI) | Field median per-100 | Delta | Evidence |",
        "|------|----------------------|---------------------|-------|----------|",
    ]
    for p in top_pains:
        usim_stat = p["rates"].get(target_app, {})
        u_p100 = usim_stat.get("per_100", 0.0)
        u_lo = usim_stat.get("ci_low", 0.0)
        u_hi = usim_stat.get("ci_high", 0.0)
        f_med = p["field_median_per_100"]

        # Best delta for this pain (Supported preferred, then largest |delta|)
        pain_deltas = [
            d for d in deltas
            if d["theme"] == p["theme"] and d["sentiment"] == p["sentiment"]
        ]
        pain_deltas.sort(
            key=lambda d: (d["support_level"] != "Supported", -abs(d["delta_per_100"]))
        )
        best = pain_deltas[0] if pain_deltas else None

        if best:
            delta_str = f"{best['delta_per_100']:+.1f} vs {best['vs_app']}"
            evidence = f"[{best['support_level']}]"
        else:
            delta_str = "—"
            evidence = "—"

        theme_label = p["theme"].replace("_", " ").title()
        sent_label = p["sentiment"].title()
        table_rows.append(
            f"| {theme_label} ({sent_label}) "
            f"| {u_p100:.1f} ({u_lo:.1f}–{u_hi:.1f}) "
            f"| {f_med:.1f} "
            f"| {delta_str} "
            f"| {evidence} |"
        )

    table = "\n".join(table_rows)

    # -----------------------------------------------------------------
    # Competitive read — every sentence with "than" carries a tag.
    # Prefer negative/mixed themes; avoid "positive positive" duplication.
    # -----------------------------------------------------------------
    def _mention_label(theme: str, sentiment: str) -> str:
        """Return a readable label avoiding 'positive positive' repetition."""
        if theme == sentiment:
            return theme.replace("_", " ")
        return f"{theme.replace('_', ' ')} ({sentiment})"

    def _is_negative_or_mixed(d: dict) -> bool:
        return d["sentiment"] in ("negative", "mixed")

    supported_deltas = [d for d in deltas if d["support_level"] == "Supported"]
    directional_deltas = [d for d in deltas if d["support_level"] == "Directional"]

    # Within each group: negative/mixed first, then by |delta| descending
    def _sort_key(d: dict) -> tuple:
        return (not _is_negative_or_mixed(d), -abs(d["delta_per_100"]))

    supported_deltas.sort(key=_sort_key)
    directional_deltas.sort(key=_sort_key)

    competitive_sentences: list[str] = []
    used_keys: set[tuple[str, str]] = set()

    for d in supported_deltas[:2]:
        key = (d["theme"], d["sentiment"])
        if key in used_keys:
            continue
        used_keys.add(key)
        direction = "higher" if d["delta_per_100"] > 0 else "lower"
        mention = _mention_label(d["theme"], d["sentiment"])
        competitive_sentences.append(
            f"{target_app} has {abs(d['delta_per_100']):.1f} per-100 {direction} "
            f"{mention} mentions than {d['vs_app']} [Supported]."
        )

    for d in directional_deltas:
        if len(competitive_sentences) >= 3:
            break
        key = (d["theme"], d["sentiment"])
        if key in used_keys:
            continue
        used_keys.add(key)
        direction = "higher" if d["delta_per_100"] > 0 else "lower"
        mention = _mention_label(d["theme"], d["sentiment"])
        competitive_sentences.append(
            f"On {mention}, {target_app} trends {direction} "
            f"than {d['vs_app']} (n={d['target']['n']}; small sample — treat as "
            f"indicative only) [Directional]."
        )

    if not competitive_sentences:
        competitive_sentences = [
            "The corpus is too small for cross-company comparisons on any theme; "
            "all per-100 rates are reported for orientation only."
        ]

    competitive_read = "  \n".join(competitive_sentences)

    # -----------------------------------------------------------------
    # Month-one interventions
    # -----------------------------------------------------------------
    bullets = "\n".join(f"- {iv}" for iv in interventions[:3])

    # -----------------------------------------------------------------
    # Honesty footer
    # -----------------------------------------------------------------
    source_parts = (
        "; ".join(f"{src}: {n}" for src, n in sorted(per_source_n.items()))
        if per_source_n
        else f"total: {total_n}"
    )
    comp_list = ", ".join(competitor_apps) if competitor_apps else "none"
    footer = (
        f"*Sample: {total_n} reviews ({source_parts}); "
        f"recency window {recency_window} months; "
        f"competitors benchmarked: {comp_list}. "
        f"All rates per-100 reviews with 95% Wilson CIs. "
        f"Supported = both samples ≥ n-floor AND CIs non-overlapping; "
        f"Directional = otherwise (thin sample or overlapping intervals).*"
    )

    # -----------------------------------------------------------------
    # Assemble
    # -----------------------------------------------------------------
    return "\n".join(
        [
            "# ReviewLens · Competitive Diagnosis",
            "",
            headline,
            "",
            method,
            "",
            "## Top-3 Pains",
            "",
            table,
            "",
            "## Competitive Read",
            "",
            competitive_read,
            "",
            "## Month-One Interventions",
            "",
            bullets,
            "",
            "---",
            "",
            footer,
            "",
        ]
    )


# ---------------------------------------------------------------------------
# write_outputs — writes all 4 files
# ---------------------------------------------------------------------------


def write_outputs(
    state: dict[str, Any],
    *,
    docs_dir: Path,
    results_dir: Path,
) -> dict[str, Any]:
    """Build diagnosis + opener and persist all 4 output files.

    Returns the diagnosis dict.
    """
    diagnosis = build_diagnosis(state)
    opener_md = render_opener(diagnosis)

    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "diagnosis.json").write_text(
        json.dumps(diagnosis, indent=2, default=str), encoding="utf-8"
    )
    (docs_dir / "opener.md").write_text(opener_md, encoding="utf-8")

    results_dir.mkdir(parents=True, exist_ok=True)
    last_run = {**diagnosis, "opener_md": opener_md}
    (results_dir / "last_run.json").write_text(
        json.dumps(last_run, indent=2, default=str), encoding="utf-8"
    )
    # trace_last_run.json is written by TraceContext.flush() — not written here

    return diagnosis
