"""ReviewLens Streamlit dashboard.

Cold load: reads data/results/last_run.json — no LLM call, no network.
Live re-run: available when ANTHROPIC_API_KEY is set (real key only).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_ROOT = Path(__file__).parent.parent
_LAST_RUN = _ROOT / "data" / "results" / "last_run.json"
_TRACE_PATH = _ROOT / "data" / "results" / "trace_last_run.json"

# Ensure src/ is importable for the live re-run path
_SRC = str(_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# --- Graphviz DOT diagram (design doc §2.1 — 8 nodes + 2 conditional edges)
# st.graphviz_chart is bundled with Streamlit; renders with no external network call.
_GRAPHVIZ_DOT = """
digraph ReviewLens {
    rankdir=LR
    node [fontname="Helvetica" fontsize=11 style=filled]
    edge [fontname="Helvetica" fontsize=9]

    START [shape=circle label="START" fillcolor="#e2e8f0" color="#94a3b8"]
    plan  [shape=box    label="plan\n(LLM·Sonnet)"   fillcolor="#dbeafe" color="#3b82f6"]
    fetch [shape=box    label="fetch\n(Tool)"         fillcolor="#dcfce7" color="#22c55e"]
    triage   [shape=diamond label="triage\n(Router)"        fillcolor="#fef3c7" color="#f59e0b"]
    classify [shape=box    label="classify\n(LLM·Haiku)"    fillcolor="#dbeafe" color="#3b82f6"]
    cluster  [shape=box    label="cluster\n(LLM·Sonnet)"    fillcolor="#dbeafe" color="#3b82f6"]
    quantify [shape=box    label="quantify\n(Tool·Python)"  fillcolor="#dcfce7" color="#22c55e"]
    diagnose [shape=box    label="diagnose\n(LLM·Sonnet)"   fillcolor="#dbeafe" color="#3b82f6"]
    critique [shape=diamond label="critique\n(LLM·Sonnet)"  fillcolor="#fef3c7" color="#f59e0b"]
    END  [shape=circle label="END"   fillcolor="#e2e8f0" color="#94a3b8"]

    START    -> plan
    plan     -> fetch
    fetch    -> triage
    triage   -> fetch    [label="n too low" color="#ef4444" fontcolor="#ef4444"]
    triage   -> classify [label="enough data"]
    classify -> cluster
    cluster  -> quantify
    quantify -> diagnose
    diagnose -> critique
    critique -> fetch    [label="low conf +\nbudget left" color="#ef4444" fontcolor="#ef4444"]
    critique -> END      [label="ok"]
}
"""


# ---------------------------------------------------------------------------
# Data loading — pure I/O, no LLM/network
# ---------------------------------------------------------------------------


def load_snapshot() -> dict[str, Any] | None:
    """Return parsed last_run.json or None if missing/empty/invalid."""
    if not _LAST_RUN.exists():
        return None
    try:
        text = _LAST_RUN.read_text(encoding="utf-8").strip()
        return json.loads(text) if text else None
    except (json.JSONDecodeError, OSError):
        return None


def _load_trace() -> dict[str, Any] | None:
    if not _TRACE_PATH.exists():
        return None
    try:
        text = _TRACE_PATH.read_text(encoding="utf-8").strip()
        return json.loads(text) if text else None
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Tab 1 — Diagnosis
# ---------------------------------------------------------------------------


def _render_diagnosis_tab(diag: dict[str, Any]) -> None:
    target = diag.get("target_app", "USim")
    pains: list[dict] = diag.get("pains", [])
    deltas: list[dict] = diag.get("deltas", [])
    interventions: list[str] = diag.get("interventions", [])

    st.subheader("Pain Rates per 100 Reviews — 95% Wilson CI")

    if pains:
        rows = []
        for p in pains:
            for app, stat in p.get("rates", {}).items():
                rows.append(
                    {
                        "app": app,
                        "label": f"{p['theme']} / {p['sentiment']}",
                        "per_100": stat["per_100"],
                        "ci_low": stat["ci_low"],
                        "ci_high": stat["ci_high"],
                        "n": stat["n"],
                    }
                )
        df = pd.DataFrame(rows)
        apps_all = df["app"].unique().tolist()
        comp_apps = sorted(a for a in apps_all if a != target)
        ordered_apps = comp_apps + [target]  # USim last → renders on top

        usim_order = (
            df[df["app"] == target]
            .drop_duplicates("label")
            .sort_values("per_100", ascending=True)["label"]
            .tolist()
        )

        fig = go.Figure()
        comp_palette = ["#94a3b8", "#cbd5e1", "#e2e8f0"]
        for idx, app in enumerate(ordered_apps):
            color = "#0066CC" if app == target else comp_palette[idx % len(comp_palette)]
            app_df = (
                df[df["app"] == app]
                .drop_duplicates("label")
                .set_index("label")
                .reindex(usim_order)
                .reset_index()
                .dropna(subset=["per_100"])
            )
            err_minus = (app_df["per_100"] - app_df["ci_low"]).tolist()
            err_plus = (app_df["ci_high"] - app_df["per_100"]).tolist()
            fig.add_trace(
                go.Bar(
                    name=app,
                    y=app_df["label"],
                    x=app_df["per_100"],
                    orientation="h",
                    marker_color=color,
                    error_x=dict(
                        type="data",
                        symmetric=False,
                        array=err_plus,
                        arrayminus=err_minus,
                        color=color,
                        thickness=1.5,
                        width=4,
                    ),
                    customdata=app_df[["n", "ci_low", "ci_high"]].values,
                    hovertemplate=(
                        f"<b>{app}</b> · %{{y}}<br>"
                        "Rate: %{x:.1f} per-100<br>"
                        "95% CI: [%{customdata[1]:.1f}, %{customdata[2]:.1f}]<br>"
                        "n = %{customdata[0]:.0f}<extra></extra>"
                    ),
                )
            )

        fig.update_layout(
            barmode="group",
            height=max(380, len(usim_order) * 28 + 100),
            xaxis_title="Mentions per 100 reviews",
            yaxis_title="",
            legend_title="App",
            margin=dict(l=0, r=20, t=20, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No pain data in snapshot.")

    st.subheader("Comparative Claims")
    if deltas:
        for d in deltas:
            level = d.get("support_level", "Directional")
            col_badge, col_claim = st.columns([1, 6])
            with col_badge:
                if level == "Supported":
                    st.success("Supported")
                else:
                    st.warning("Directional")
            with col_claim:
                st.write(d.get("claim", ""))
    else:
        st.info("No comparative deltas in this run.")

    st.subheader("Month-One Interventions")
    for i, iv in enumerate(interventions, 1):
        st.markdown(f"**{i}.** {iv}")


# ---------------------------------------------------------------------------
# Tab 2 — Competitive heatmap
# ---------------------------------------------------------------------------


def _render_competitive_tab(diag: dict[str, Any]) -> None:
    target = diag.get("target_app", "USim")
    pains: list[dict] = diag.get("pains", [])
    recency = diag.get("recency_window", "?")
    per_source_n: dict = diag.get("per_source_n", {})
    total_n = diag.get("total_n", 0)

    source_str = "  ·  ".join(f"{s}: n={n}" for s, n in per_source_n.items())
    st.info(
        f"**Recency window:** last {recency} months  |  "
        f"**Total reviews classified:** {total_n}  |  "
        f"**Sources:** {source_str or 'n/a'}"
    )
    st.caption(
        "Cell values are **per-100-review rates** — the fair unit across companies of "
        "different review volumes. Raw counts (n) are context, visible on hover."
    )

    if not pains:
        st.warning("No data to display.")
        return

    rows = []
    for p in pains:
        for app, stat in p.get("rates", {}).items():
            rows.append(
                {
                    "app": app,
                    "cell": f"{p['theme']} / {p['sentiment']}",
                    "per_100": stat["per_100"],
                    "ci_low": stat["ci_low"],
                    "ci_high": stat["ci_high"],
                    "n": stat["n"],
                }
            )
    df = pd.DataFrame(rows)

    apps = [target] + sorted(a for a in df["app"].unique() if a != target)
    cell_order = df.groupby("cell")["per_100"].mean().sort_values(ascending=False).index.tolist()

    z: list[list[float | None]] = []
    text_z: list[list[str]] = []
    hover: list[list[str]] = []
    for cell in cell_order:
        row_z, row_t, row_h = [], [], []
        for app in apps:
            sub = df[(df["cell"] == cell) & (df["app"] == app)]
            if sub.empty:
                row_z.append(None)
                row_t.append("")
                row_h.append(f"<b>{app}</b> · {cell}<br>no data")
            else:
                r = sub.iloc[0]
                row_z.append(float(r["per_100"]))
                row_t.append(f"{r['per_100']:.0f}")
                row_h.append(
                    f"<b>{app}</b> · {cell}<br>"
                    f"Rate: {r['per_100']:.1f} per-100<br>"
                    f"95% CI: [{r['ci_low']:.1f}, {r['ci_high']:.1f}]<br>"
                    f"n = {int(r['n'])}"
                )
        z.append(row_z)
        text_z.append(row_t)
        hover.append(row_h)

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=apps,
            y=cell_order,
            text=text_z,
            texttemplate="%{text}",
            hovertext=hover,
            hoverinfo="text",
            colorscale="YlOrRd",
            colorbar=dict(title="per-100"),
            zmin=0,
        )
    )
    # Blue border brackets the USim (index 0) column
    fig.add_shape(
        type="rect",
        x0=-0.5,
        x1=0.5,
        y0=-0.5,
        y1=len(cell_order) - 0.5,
        line=dict(color="#0066CC", width=2),
    )
    fig.update_layout(
        height=max(420, len(cell_order) * 32 + 120),
        xaxis=dict(side="top"),
        yaxis_autorange="reversed",
        margin=dict(l=0, r=0, t=60, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Tab 3 — How this was built
# ---------------------------------------------------------------------------


def _render_how_built_tab() -> None:
    # st.graphviz_chart is bundled with Streamlit (uses the graphviz package) —
    # no CDN, no external network call.
    st.subheader("LangGraph Pipeline (§2.1 — 8 nodes, 2 conditional edges)")
    st.graphviz_chart(_GRAPHVIZ_DOT, use_container_width=True)

    st.subheader("Agent Run Replay")
    trace = _load_trace()
    if trace is None:
        st.info("No trace file found — run the pipeline to generate one.")
        return

    entries: list[dict] = trace.get("entries", [])
    summary: dict = trace.get("summary", {})

    if not entries:
        st.info("Trace is empty.")
        return

    current_loop: int | None = None
    for entry in entries:
        node = entry.get("node", "?")
        etype = entry.get("type", "")
        loop = entry.get("fetch_loop")

        if etype == "node_enter":
            if loop is not None and loop != current_loop:
                current_loop = loop
                if loop and loop > 0:
                    st.markdown(f"---\n**Fetch loop {loop}**")
            raw = entry.get("raw_reviews", 0)
            st.markdown(f"→ **{node}** &nbsp; *(reviews in state: {raw})*")

        elif etype == "node_exit":
            parts: list[str] = []
            latency = entry.get("latency_ms")
            decision = entry.get("decision")
            reason = entry.get("reason")
            if latency:
                parts.append(f"latency: {latency:.0f} ms")
            if decision:
                parts.append(f"decision: **{decision}**")
            if reason:
                parts.append(f"reason: _{reason}_")
            if parts:
                st.markdown("&nbsp;&nbsp;&nbsp;" + " · ".join(parts))

    if summary:
        st.subheader("Node Latency Summary")
        rows = [
            {
                "Node": node,
                "Latency (ms)": f"{s.get('latency_ms', 0):.0f}",
                "Tool calls": s.get("tool_calls", 0),
            }
            for node, s in summary.items()
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Live re-run
# ---------------------------------------------------------------------------


def _run_pipeline_live() -> None:
    """Run the real agent in-process. src/ must be on sys.path."""
    from run_pipeline import run_live  # noqa: PLC0415

    run_live()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="ReviewLens", page_icon="🔍", layout="wide")
    st.title("ReviewLens · Competitive Diagnosis")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    has_real_key = bool(api_key and not api_key.startswith("sk-ant-placeholder"))

    diag = load_snapshot()

    if diag is None:
        st.warning(
            "No snapshot found at `data/results/last_run.json`.  \n"
            "Run `python -m run_pipeline --fixture` from the project root to generate one, "
            "then reload this page."
        )
        if has_real_key:
            if st.button("Run pipeline now", type="primary"):
                with st.spinner("Running agent pipeline…"):
                    try:
                        _run_pipeline_live()
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Pipeline failed: {exc}")
        else:
            st.info("Set `ANTHROPIC_API_KEY` to enable the live pipeline button.")
        return

    generated_at = diag.get("generated_at", "unknown")
    total_n = diag.get("total_n", 0)
    target = diag.get("target_app", "USim")
    c1, c2, c3 = st.columns(3)
    c1.metric("Target app", target)
    c2.metric("Reviews analysed", total_n)
    c3.metric("Generated", generated_at[:10] if len(generated_at) >= 10 else generated_at)

    tab1, tab2, tab3 = st.tabs(["Diagnosis", "Competitive", "How this was built"])
    with tab1:
        _render_diagnosis_tab(diag)
    with tab2:
        _render_competitive_tab(diag)
    with tab3:
        _render_how_built_tab()

    st.divider()
    col_btn, col_note = st.columns([2, 5])
    with col_btn:
        clicked = st.button(
            "Re-run agent live",
            disabled=not has_real_key,
            type="primary",
            help="Runs the full LangGraph pipeline in-process. Requires ANTHROPIC_API_KEY.",
        )
    with col_note:
        if has_real_key:
            st.caption("Budget-guarded by CostMeter. Snapshot reloads automatically on completion.")
        else:
            st.caption(
                "Disabled — no real API key detected. "
                "Default view always loads from `last_run.json` so the link is instant and never blank."
            )

    if clicked and has_real_key:
        with st.spinner("Running agent pipeline… (this may take a minute)"):
            try:
                _run_pipeline_live()
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Pipeline failed: {exc}")


if __name__ == "__main__":
    main()
