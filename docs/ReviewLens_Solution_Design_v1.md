# ReviewLens · Solution Design v1.0
### Agentic Review-Intelligence Pipeline for Travel eSIM

> **What this is.** An LLM-orchestrated, multi-step agent that mines public app-store reviews for **USim** and its travel-eSIM competitors, classifies them into an emergent pain taxonomy, quantifies each pain with sample-size-aware statistics, and outputs a numeric, **competitively-benchmarked** diagnosis — the loudest customer pains and where USim sits on each axis versus the field.
>
> It serves **triple duty**: (1) the interview **opener**; (2) proof of a working **LLM-automation pipeline**; (3) the artifact that **closes the agentic-systems gap** — a genuine LangGraph state machine with tool nodes, conditional routing, and a self-critique loop, not a single prompt.

**Portfolio Project · Mohammad Ashraf Ahmed Hafez** — built for the USim Automation & Data Operations interview.

| Category | Duration | Effort | Deploy | Budget |
|---|---|---|---|---|
| Agentic LLM / GenAI (LangGraph) | 3–4 days | 10–14 hrs | Streamlit Cloud (+opt. Railway) | ~$5–10 API |

> *Naming note:* "ReviewLens" keeps the *Lens family (bankinglens) and reads as analytics. Rename freely — repo slug, package name, README title are the only places it appears.

---

## 1. Project Overview

ReviewLens turns the unstructured voice of the travel-eSIM customer into a defensible, numeric diagnosis. The category is crowded and review-heavy: the failure modes that drive churn — activation that doesn't complete after payment, slow/absent support, refund friction, coverage and speed gaps — are visible in public app-store reviews across the whole field. An agent that reads that corpus at scale, normalizes it fairly, and benchmarks one company against the rest produces operator-grade insight.

USim is the **subject**; competitors are the **baseline**. The agent fetches reviews for USim and a registry of comparators, classifies each into an emergent pain taxonomy with sentiment, quantifies every pain with confidence intervals, and synthesizes a ranked, competitively-positioned diagnosis plus a short list of month-one interventions. Output is a live dashboard **and** a one-page written summary used to open the interview.

### 1.1 What it demonstrates

| Capability | How ReviewLens proves it |
|---|---|
| **Agentic orchestration** | A LangGraph `StateGraph` with an LLM planner, tool nodes, conditional routing, a fetch-loop, and a self-critique node that can send the agent back for more data. Runtime control flow, not a fixed pipeline. |
| **Tool-use & APIs** | Typed tools the agent invokes: App Store RSS reviews, iTunes Search id-resolution, Google Play reviews, optional Trustpilot. Caching, dedup, retry, rate-limiting. |
| **LLM data pipeline** | Batched structured classification (theme + sentiment + friction) over hundreds–thousands of reviews, emergent-taxonomy clustering, synthesis — strict JSON schemas + validation. |
| **Statistical honesty** | Every proportion carries `n` and a Wilson 95% interval; cross-company deltas are gated on sample size and interval overlap. The agent refuses to over-claim on thin samples. |
| **Commercial judgment** | Competitive benchmarking + a prioritized intervention list — the analysis a founder would pay a consultant for, framed as "here's month one." |
| **Production engineering** | Typed Python package, pytest suite incl. statistical-correctness tests, config-driven, CI, pre-commit, Makefile, Dockerfile, deployed live link. |
| **Responsible data** | Public sources only, modest volume, cached; aggregates + paraphrased exemplars in the UI — never raw scraped-text dumps. A documented data-use policy ships with it. |

### 1.2 Triple duty (why this one artifact)

1. **Interview opener** — first 90 seconds: *"Before we start, I pointed an agent at your reviews and your competitors'. Here are the three pains that actually move eSIM churn, where you sit on each, and what I'd build in month one."* Reframes from "can he do the job" to "he's already doing it."
2. **Agentic proof** — a deployed agent with tool-use and control flow you can walk through. Honest close of the agentic gap (master plan Part D).
3. **LLM-automation proof** — a real, batched, schema-validated LLM pipeline over messy real-world text, deployed behind a UI.

### 1.3 Data scope, sources & the rigor mandate

**Scope (locked): category-comparative.** USim's own corpus is thin (Trustpilot carries only a handful of reviews; the App Store entry has tens, not hundreds). Mining USim alone is too small to claim confidently and too easy for a sharp founder to dismiss. Mining USim **against the field** gives the agent a real corpus, turns the opener into competitive intelligence, and showcases commercial judgment.

> **⚠ Rigor mandate (first-class design constraint).** Comparing a 20-review app to a 5,000-review giant on raw percentages is the fastest way to lose credibility. Therefore:
> - all proportions are reported **per-100-reviews** with `n` and a **Wilson 95% CI**;
> - a USim-vs-competitor delta is **Supported** only if both samples clear a configurable `n`-floor **and** their intervals don't overlap — otherwise **Directional** *(small sample, n=…)*;
> - the diagnosis **leads with Supported deltas**;
> - the **critique node mechanically enforces this** before any claim is finalized.
>
> Honest, defensible deltas beat dramatic ones.

**Sources (priority order):** Apple App Store customer-review **RSS JSON feed** (public, documented — no HTML scraping), queried across multiple country storefronts to widen the corpus; **iTunes Search API** to resolve app IDs at runtime (no hard-coded guesses); **Google Play** via `google-play-scraper`; **Trustpilot** optional/de-emphasized (thin for USim, no clean API). App IDs are resolved by the agent, not hand-typed.

**Target:** USim — App Store id `6502586159` (entity AMAS INTERNATIONAL… WLL, Kuwait), domain `usim.me`. Comparators resolve at runtime (Appendix A). The name-collision sibling **"USIMS" (id `1555283998`) is explicitly excluded** so the two are never conflated.

---

## 2. System Architecture

Three layers. **Data/tool** fetches + normalizes reviews. **Agent** is a LangGraph state machine orchestrating tools + LLM reasoning with runtime control flow. **Presentation** is a Streamlit dashboard that loads a committed snapshot instantly and can re-run the agent live.

### 2.1 The agent: a LangGraph state machine

A single typed state object flows through the graph. Two conditional edges create genuine agentic control flow: `triage` can loop back to fetch more data; `critique` can reject its own diagnosis and demand another pass (bounded by loop-count + a hard budget meter).

| Node | Type | Role |
|---|---|---|
| `plan` | LLM (Sonnet) | Reads registry + config; emits a `FetchPlan` (which apps, storefronts, depth). First runtime decision. |
| `fetch` | Tool | Executes the plan via source tools; caches to disk; dedups by review id; records per-source `n`. |
| `triage` | Router (rule + LLM) | Inspects per-source `n` vs floors. **Conditional edge** → proceed to `classify`, or loop back to `fetch`. Bounded by `max_fetch_loops`. |
| `classify` | LLM (Haiku, batched) | Per review → `{theme, sentiment, friction_phrase, confidence}`. Strict JSON schema; low-confidence flagged. |
| `cluster` | LLM (Sonnet) | Merges raw theme labels into a stable taxonomy; may add emergent themes beyond the seed (Appendix B). |
| `quantify` | Tool (pure Python) | Proportions per theme/sentiment/source; Wilson 95% CIs; per-100 normalization; deltas with Supported/Directional flag. |
| `diagnose` | LLM (Sonnet) | Ranks loudest pains; writes competitive positioning + month-one interventions — consuming **only** quantify outputs + flags. |
| `critique` | LLM (Sonnet) | Audits each claim vs stats; enforces small-sample downgrades; if low confidence & budget remains, **conditional edge** → `fetch`; else → `END`. |

```
                 ┌──────┐
      START ───▶ │ plan │
                 └──┬───┘
                    ▼
                 ┌───────┐      (n too low)
            ┌──▶ │ fetch │ ◀───────────────┐
            │    └───┬───┘                  │
            │        ▼                       │
            │    ┌────────┐  loop back       │
            └────┤ triage ├──────────────────┘
                 └───┬────┘ (enough data)
                     ▼
         ┌──────────┐   ┌─────────┐   ┌──────────┐
         │ classify ├──▶│ cluster ├──▶│ quantify │
         └──────────┘   └─────────┘   └────┬─────┘
                                           ▼
                                     ┌──────────┐
                                     │ diagnose │
                                     └────┬─────┘
                                          ▼
                                    ┌──────────┐  (low confidence
                                    │ critique │── & budget left) ─▶ fetch
                                    └────┬─────┘
                                         ▼ (ok)
                                        END
```

### 2.2 Canonical data flow

`registry → plan(FetchPlan) → fetch(reviews) ⇄ triage → classify(rows) → cluster(taxonomy) → quantify(stats+CIs) → diagnose(claims) ⇄ critique → diagnosis.json + opener.md`

The same `fetch → classify → quantify` path is used for full or incremental runs. The state object is the single source of truth; `trace.py` records every node entry, tool call, and conditional decision so the UI can show what the agent actually did.

### 2.3 Statistical-honesty contract

- Every reported proportion ships with `n` and a **Wilson score 95% interval** (better than normal-approximation for small/extreme proportions — exactly USim's situation).
- A **min-`n` floor** (config, default 30) gates any cross-company claim. Below it, the pain is reported for context but cannot anchor a "USim is worse/better" statement.
- A delta is **Supported** only if both companies clear the floor **and** their Wilson intervals do not overlap; otherwise **Directional**.
- All comparisons are **per-100-reviews**; raw counts are never compared across companies of different sizes.
- Optional **recency window** (e.g. last 12 months) avoids comparing stale vs fresh corpora; the window used is reported.
- The `critique` node re-checks each diagnosis sentence against these rules; the UI badges every claim **Supported** or **Directional**.

### 2.4 Cost & rate-limit guardrails

- Bulk classification on **Claude Haiku** (cheap); plan/cluster/diagnose/critique on **Sonnet**. Classification is **batched**.
- A **CostMeter** in the LLM client accumulates token spend and aborts past a ceiling (default ~$8). Fetch + critique loops bounded by `max_fetch_loops`.
- Fetched reviews **cached** to `data/raw_cache/` keyed by source+app+storefront+page; re-runs hit cache first. App Store RSS calls rate-limited + capped per storefront.

### 2.5 Responsible-data contract

- Public sources only; modest volume; respectful rate limits; results cached.
- UI shows aggregates, themes, and short **paraphrased** exemplars — never bulk verbatim text. A few short illustrative quotes (attributed to "a public App Store review") is the maximum.
- `docs/responsible_data.md` documents sources, volumes, retention, aggregates-only stance — itself a trust signal to USim.

---

## 3. Repository Structure

> Every file below should exist before calling the project *done*. Use as the completion checklist.

```
reviewlens/
├── src/
│   ├── config.py                 ← load .env + config.yaml; keys; guardrails
│   ├── sources/
│   │   ├── appstore.py           ← iTunes RSS reviews + Search-API id resolution
│   │   ├── playstore.py          ← google-play-scraper wrapper
│   │   ├── trustpilot.py         ← optional, respectful, de-emphasized
│   │   └── registry.py           ← target + competitor registry (names→ids)
│   ├── tools/
│   │   ├── fetch.py              ← fetch_reviews tool (multi-source, cached, deduped)
│   │   ├── classify.py          ← per-review theme+sentiment (Haiku, batched)
│   │   ├── cluster.py           ← emergent taxonomy merge (Sonnet)
│   │   └── quantify.py          ← proportions + Wilson CIs + deltas + normalization
│   ├── agent/
│   │   ├── state.py             ← typed graph state (Pydantic / TypedDict)
│   │   ├── nodes.py             ← plan, fetch, triage, classify, cluster,
│   │   │                          quantify, diagnose, critique
│   │   ├── graph.py             ← LangGraph StateGraph + conditional edges
│   │   └── trace.py             ← decision / tool-call trace logger (for UI)
│   ├── llm/
│   │   └── client.py            ← provider-agnostic wrapper (Claude default),
│   │                              retry, cost meter
│   └── diagnosis.py             ← assemble diagnosis.json + opener.md generator
├── app/
│   └── streamlit_app.py         ← dashboard: diagnosis, deltas, agent-trace tab
├── tests/
│   ├── test_sources.py
│   ├── test_fetch_tool.py
│   ├── test_classify_schema.py
│   ├── test_quantify_stats.py    ← Wilson CI correctness + min-n gating
│   ├── test_graph_e2e.py         ← graph runs on a fixture corpus end-to-end
│   └── test_critique_downgrades.py ← thin-sample deltas get downgraded
├── data/
│   ├── .gitignore                ← ignore raw_cache/*; keep results/
│   ├── raw_cache/                ← cached fetched reviews (gitignored)
│   └── results/
│       ├── last_run.json         ← committed diagnosis snapshot (instant load)
│       └── trace_last_run.json
├── docs/
│   ├── opener.md                 ← the 1-page interview opener (generated)
│   └── responsible_data.md       ← data-use policy
├── config/
│   └── config.yaml               ← sources, guardrails, taxonomy seed, thresholds
├── .github/workflows/ci.yml      ← lint → test → graph-smoke
├── .env.example                  ← ANTHROPIC_API_KEY, model ids, ceilings
├── pyproject.toml
├── Makefile                      ← install, run, test, lint, fmt, deploy
├── .pre-commit-config.yaml
├── README.md                     ← Mermaid graph, live link, results, data note
└── LICENSE                       ← MIT
```

---

## 4. Phase-by-Phase Implementation Design

> Each phase has: numbered build steps, a paste-ready **Claude Code microprompt**, an **Opus review gate** (must be true before the phase is accepted), and a **commit checkpoint**. Run one phase at a time — do not paste the next microprompt until its predecessor passes its gate. Operating model in §7.

### Phase 0 — Scaffold, Config & Guardrails · ~45 min · Day 2 morning

Stand up everything non-LLM that's painful to retrofit: dependency pinning, config, secrets handling, the cost meter, CI skeleton, pre-commit, Makefile.

1. `pyproject.toml` — PEP 621. Pin: `langgraph, langchain-core, anthropic, pydantic` v2, `httpx, pyyaml, pandas, statsmodels` (Wilson CI), `google-play-scraper, streamlit, plotly`. Dev: `ruff, pytest, pytest-cov, pre-commit`.
2. `config/config.yaml` — sources, storefronts, `max_fetch_loops`, `min_n_floor` (30), `recency_window_months`, `cost_ceiling_usd` (8), `models {planner, classifier, synth}`, taxonomy seed (Appendix B).
3. `src/config.py` — typed loader (pydantic-settings); reads `.env` (`ANTHROPIC_API_KEY`) + `config.yaml`; fails fast on missing keys.
4. `src/llm/client.py` — provider-agnostic wrapper, Claude default; `structured_output(schema, …)` helper (JSON enforced); retry + backoff; a `CostMeter` that tallies tokens×price and raises `BudgetExceeded` past the ceiling.
5. `.gitignore` + `data/.gitignore` (ignore `raw_cache/*`, keep `results/`), `.env.example`, `Makefile`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml` (lint → test → graph-smoke; quality steps skip gracefully on empty repo).

```text
▶ CLAUDE CODE MICROPROMPT — Phase 0
Scaffold a Python 3.11 project named reviewlens (see the repo tree in the design doc).
Create: pyproject.toml (PEP 621, pinned deps as in Phase 0 step 1; dev extras),
config/config.yaml, src/config.py (pydantic-settings loader, fail-fast on missing
ANTHROPIC_API_KEY), src/llm/client.py (provider-agnostic LLM wrapper defaulting to
Anthropic Claude, with: a structured_output(schema, ...) helper that enforces JSON,
retry+backoff, and a CostMeter class that accumulates token cost and raises
BudgetExceeded above config.cost_ceiling_usd).
Add .gitignore, data/.gitignore (ignore raw_cache/*, keep results/), .env.example,
Makefile (install/run/test/lint/fmt), .pre-commit-config.yaml (ruff), and
.github/workflows/ci.yml (lint → pytest → a graph-smoke step that skips if no graph yet).
Do NOT implement sources, tools, or the graph yet. Stub modules with TODOs + docstrings.
Print a tree of what you created and confirm `make install` succeeds.
```

**✓ Opus review gate** (do not merge until all pass):
- [ ] `make install` succeeds in a clean venv; ruff + pre-commit run clean.
- [ ] `src/config.py` fails fast with a clear message when `ANTHROPIC_API_KEY` is absent.
- [ ] `CostMeter` raises `BudgetExceeded` in a unit-level smoke (mock prices) — kill-switch works.
- [ ] No secrets committed; `.env.example` has placeholders only; `data/raw_cache` gitignored.
- [ ] CI green on the empty scaffold (steps skip gracefully).

**Commit checkpoint:** `git commit -am "phase 0: scaffold, config, cost meter, CI"` — CI green.

---

### Phase 1 — Data Layer & Tools · ~90 min · Day 2 afternoon

Build source adapters + the agent-facing fetch tool. App IDs resolve at runtime — nothing hard-coded except USim's id and the excluded sibling.

1. `src/sources/appstore.py` — `resolve_app_id(name)` via iTunes Search API; `fetch_appstore_reviews(app_id, country, pages)` via customer-review RSS JSON; normalize to a `Review` dataclass `{id, source, app, country, rating, title, body, date}`. Rate-limit + cache.
2. `src/sources/playstore.py` — `google-play-scraper` wrapper to the same `Review` shape; resolve by package name.
3. `src/sources/trustpilot.py` — optional, respectful, config-gated; de-emphasized.
4. `src/sources/registry.py` — target + competitor registry (Appendix A); USim id known; USIMS sibling excluded; `resolve_all()` returns concrete targets.
5. `src/tools/fetch.py` — `fetch_reviews(plan)` the agent calls: iterate plan, hit sources, dedup by `(source, id)`, cache to `data/raw_cache/`, return reviews + per-source counts.

```text
▶ CLAUDE CODE MICROPROMPT — Phase 1
Implement the data layer for reviewlens to the Review dataclass shape
{id, source, app, country, rating, title, body, date}:
- src/sources/appstore.py: resolve_app_id(name) using the public iTunes Search API;
  fetch_appstore_reviews(app_id, country, pages) using the App Store customer-review
  RSS JSON feed; rate-limit (sleep between calls) and cache raw JSON to data/raw_cache/
  keyed by app+country+page.
- src/sources/playstore.py: wrap google-play-scraper to the same Review shape.
- src/sources/trustpilot.py: optional, respectful, config-gated; ok to return [] if disabled.
- src/sources/registry.py: encode the registry from Appendix A; USim id=6502586159 is known;
  EXCLUDE the sibling app id=1555283998; resolve competitor ids at runtime via Search API.
- src/tools/fetch.py: fetch_reviews(plan) -> (list[Review], counts_by_source); dedup by
  (source,id); cache-first; never raise on a single source failing (log and continue).
Write tests/test_sources.py and tests/test_fetch_tool.py using a recorded/mocked HTTP
fixture (no live network in CI). Confirm dedup and cache-hit behavior with assertions.
```

**✓ Opus review gate:**
- [ ] Tests pass offline (HTTP mocked/recorded); CI does not hit the network.
- [ ] `fetch_reviews` dedups correctly and is cache-first on the second call.
- [ ] A single failing source degrades gracefully (logged, run continues) — verified by a test.
- [ ] USIMS sibling (`1555283998`) provably excluded; USim resolves to `6502586159`.
- [ ] Rate-limiting present on App Store calls; raw_cache writes gitignored.

**Commit checkpoint:** Tiny live smoke locally (1 app, 1 storefront, 1 page), confirm real reviews parse; then `git commit "phase 1: sources + fetch tool"`.

---

### Phase 2 — The Agent (LangGraph) · ~3 hrs · Day 3 · *the heart*

Build the state machine: typed state, the eight nodes, the two conditional edges, the trace logger. This is the agentic proof — give it the most review attention.

1. `src/agent/state.py` — typed graph state: registry/plan, raw reviews, classified rows, taxonomy, stats, diagnosis, trace, loop counters, cost. Pydantic models for `FetchPlan, ClassifiedReview, ThemeStat, Delta, DiagnosisClaim`.
2. `src/tools/classify.py` — batched Haiku classification → `{theme, sentiment, friction_phrase, confidence}`; strict schema validation; low-confidence flagged, never dropped silently.
3. `src/tools/cluster.py` — Sonnet merges raw theme strings into the canonical taxonomy (seed + emergent); deterministic (low temperature).
4. `src/tools/quantify.py` — pure Python: per-company/theme/sentiment proportions; Wilson 95% CIs (`statsmodels.proportion_confint(method='wilson')`); per-100 normalization; deltas with Supported/Directional flag per §2.3.
5. `src/agent/nodes.py` — `plan, fetch, triage, classify, cluster, quantify, diagnose, critique`. `diagnose`/`critique` consume **only** quantify outputs + flags; `critique` can set `needs_more_data`.
6. `src/agent/graph.py` — `StateGraph` wiring; conditional edges `triage→{classify|fetch}` and `critique→{END|fetch}`; bound by `max_fetch_loops` + cost meter.
7. `src/agent/trace.py` — record node entry/exit, tool calls, each conditional decision with reason; persist to `results/trace_last_run.json`.

```text
▶ CLAUDE CODE MICROPROMPT — Phase 2
Implement the LangGraph agent for reviewlens exactly per design doc §2.1.
1) src/agent/state.py: typed state + Pydantic models (FetchPlan, ClassifiedReview,
   ThemeStat, Delta, DiagnosisClaim) and loop/cost counters.
2) src/tools/classify.py: batched classification on the configured Haiku model via
   llm.client.structured_output; schema {theme, sentiment, friction_phrase, confidence};
   validate every row; flag confidence<0.5; never silently drop.
3) src/tools/cluster.py: Sonnet merges raw theme labels into the seed taxonomy
   (Appendix B) allowing emergent themes; low temperature for stability.
4) src/tools/quantify.py: pure functions; Wilson 95% CIs via statsmodels; per-100
   normalization; build Delta objects flagged Supported only if both n>=min_n_floor AND
   Wilson intervals disjoint, else Directional.
5) src/agent/nodes.py + graph.py: the 8 nodes and the StateGraph with the two conditional
   edges (triage->{classify|fetch}, critique->{END|fetch}); honor max_fetch_loops and the
   CostMeter; diagnose/critique consume ONLY quantify outputs.
6) src/agent/trace.py: log node/tool/decision events to results/trace_last_run.json.
Provide a tiny fixture corpus (~40 reviews across 3 apps) and make
`python -m src.agent.graph --fixture` run the whole graph offline (mock the LLM with a
deterministic stub). Add tests/test_graph_e2e.py (graph completes on fixture) and
tests/test_quantify_stats.py (hand-computed Wilson CI matches; min-n gating works).
```

**✓ Opus review gate:**
- [ ] Graph runs end-to-end on the fixture offline and produces a diagnosis object.
- [ ] Wilson CI values match a hand-computed reference (no off-by-one on `n`).
- [ ] A constructed thin-sample delta (`n<floor`) is flagged Directional, never Supported.
- [ ] Both conditional edges are exercised by tests: low-`n` loops back to fetch; low-confidence critique routes back; loop caps + CostMeter halt runaway loops.
- [ ] `trace_last_run.json` captures every conditional decision with a readable reason.
- [ ] `classify` never drops a row; low-confidence rows flagged + counted.

**Commit checkpoint:** Run the full graph live on a small real plan (USim + 2 competitors, 2 storefronts). Confirm coherent diagnosis + trace. `git commit "phase 2: langgraph agent"`.

---

### Phase 3 — Diagnosis & Opener Output · ~90 min · Day 3 evening

Turn the agent's state into the two deliverables.

1. `src/diagnosis.py` — assemble `diagnosis.json`: ranked pains, per-company per-100 rates with CIs, Supported deltas first then Directional, month-one interventions, recency window + total `n` + per-source `n`, `generated_at`.
2. `opener.md` generator — render `diagnosis.json` into the §6 one-page structure with real numbers; every comparative sentence tagged `[Supported]` or `[Directional]`.
3. Persist `results/last_run.json` + `results/trace_last_run.json` (committed so the live app loads instantly).

```text
▶ CLAUDE CODE MICROPROMPT — Phase 3
Implement src/diagnosis.py: build_diagnosis(state) -> dict matching the schema in design
doc §6 (ranked pains; per-company per-100 rates with Wilson CIs; Supported deltas first,
then Directional; month-one interventions; recency_window; total + per-source n;
generated_at). Then render_opener(diagnosis) -> markdown following the §6 layout, tagging
every comparative sentence [Supported] or [Directional]. Write diagnosis.json and
opener.md to docs/ and snapshot last_run.json/trace_last_run.json to data/results/.
Add a Makefile target `make run` that executes the agent and regenerates all four files.
```

**✓ Opus review gate:**
- [ ] `opener.md` reads as a confident one-pager; NO comparative claim untagged.
- [ ] Directional (thin-sample) claims never appear above Supported ones.
- [ ] `diagnosis.json` validates against the §6 schema; `n` + CI present on every rate.
- [ ] `last_run.json` is committed and loads without any network/LLM call.

**Commit checkpoint:** Eyeball `opener.md` against real data — does it survive the "sharp founder" test? `git commit "phase 3: diagnosis + opener"`.

---

### Phase 4 — Streamlit Dashboard · ~2 hrs · Day 4 morning

The live artifact. Loads the committed snapshot instantly; a button re-runs the agent live. Three tabs.

1. **Tab 1 — Diagnosis:** ranked pains as a bar of per-100 rates with **CI whiskers**; USim highlighted; each comparative claim badged Supported/Directional; month-one interventions.
2. **Tab 2 — Competitive view:** per-theme small-multiples or heatmap of per-100 rates by company with CIs; recency window + `n` prominent; raw counts deliberately not the headline.
3. **Tab 3 — How this was built:** the Mermaid LangGraph diagram + a readable replay of `trace_last_run.json` (plan, fetch loops, triage/critique decisions). Makes "agentic" legible to founder + technical interviewer alike.
4. A **"Re-run agent live"** button (guarded by the cost meter); default view always loads from `last_run.json` so the link is instant and never blank.

```text
▶ CLAUDE CODE MICROPROMPT — Phase 4
Build app/streamlit_app.py for reviewlens. Load data/results/last_run.json on startup so
the page renders instantly with no API call. Three st.tabs:
1) Diagnosis: plotly horizontal bars of per-100 theme rates with Wilson-CI error bars,
   USim highlighted; render each comparative claim with a colored Supported/Directional
   badge; list month-one interventions.
2) Competitive: heatmap (or small multiples) of per-100 rate by company×theme with CI on
   hover; show recency window + per-source n prominently; do NOT headline raw counts.
3) How this was built: render the Mermaid graph from §2.1 and a human-readable replay of
   trace_last_run.json (plan, each fetch loop, triage + critique decisions with reasons).
Add a 'Re-run agent live' button that calls `make run` logic in-process, guarded by the
CostMeter, with a spinner; on completion reload the snapshot. Never show bulk verbatim
review text — aggregates + at most a few short paraphrased exemplars.
```

**✓ Opus review gate:**
- [ ] Cold load is instant from `last_run.json` (no LLM/network on first paint).
- [ ] Every comparative claim in the UI carries a Supported/Directional badge.
- [ ] CI whiskers visible; the competitive view does not let volume masquerade as a delta.
- [ ] Tab 3 reflects the real trace (loops/decisions), not a static picture.
- [ ] No bulk verbatim review text anywhere; exemplars short + paraphrased.

**Commit checkpoint:** `make run-ui`; click through all three tabs + the live re-run. `git commit "phase 4: streamlit dashboard"`.

---

### Phase 5 — Tests & Hardening · ~60 min · Day 4 afternoon

Tests that prove behavior, especially the statistical guarantees.

1. `test_quantify_stats.py` — Wilson CI matches reference; per-100 normalization; min-`n` gating; Supported requires disjoint intervals.
2. `test_critique_downgrades.py` — a planted thin-sample "USim is worse" claim is downgraded to Directional by the critique node.
3. `test_classify_schema.py` — malformed LLM output caught by schema validation; low-confidence flagged.
4. `test_graph_e2e.py` — full graph on fixture; both conditional edges fire under crafted states; loop caps honored.
5. `test_fetch_tool.py` / `test_sources.py` — dedup, cache-first, graceful single-source failure (kept green from Phase 1).

```text
▶ CLAUDE CODE MICROPROMPT — Phase 5
Complete the pytest suite for reviewlens so coverage of src/tools and src/agent is
meaningful (assert behavior, not just imports):
- test_quantify_stats.py: Wilson CI vs hand-computed reference; per-100 normalization;
  min-n gating; Supported requires disjoint intervals AND both n>=floor.
- test_critique_downgrades.py: planted thin-sample delta gets downgraded to Directional.
- test_classify_schema.py: malformed model output rejected; low-confidence flagged.
- test_graph_e2e.py: graph completes on fixture; craft states that force triage->fetch and
  critique->fetch; assert loop caps + CostMeter stop runaway loops.
Wire CI to run all tests offline (LLM + HTTP mocked). Report coverage. Fix anything red.
```

**✓ Opus review gate:**
- [ ] All tests pass offline; CI green; coverage of tools+agent meaningful.
- [ ] Statistical guarantees (Wilson, min-`n`, disjoint-interval) each covered by a test.
- [ ] Both conditional edges and both kill-switches (loop cap, budget) exercised.

**Commit checkpoint:** `make test` green, CI badge green on main. `git commit "phase 5: tests + hardening"`.

---

### Phase 6 — Deploy, README & Opener · ~90 min · Day 4 evening

Ship the live link + the written opener. Streamlit Community Cloud primary; Railway optional.

1. Deploy `app/streamlit_app.py` to Streamlit Community Cloud; set `ANTHROPIC_API_KEY` as a secret; confirm cold load is instant from the committed snapshot.
2. `README.md` — badges, one-liner, the Mermaid LangGraph diagram, tech stack, quick start, statistical-honesty note, responsible-data note, live link, screenshots of all three tabs.
3. `docs/responsible_data.md` — sources, volumes, retention, aggregates-only stance.
4. Finalize `docs/opener.md` from the latest real run — the printed/spoken interview opener (§6).
5. *Optional:* `railway.toml` + a thin FastAPI `/run` trigger if a non-Streamlit endpoint is wanted; otherwise skip.

```text
▶ CLAUDE CODE MICROPROMPT — Phase 6
Prepare reviewlens for deploy: finalize README.md (badges, Mermaid graph from §2.1, tech
stack, quick start, statistical-honesty + responsible-data notes, live-link placeholder,
screenshot placeholders for the 3 tabs); write docs/responsible_data.md; regenerate
docs/opener.md from the latest run. Add Streamlit Cloud config notes (secrets:
ANTHROPIC_API_KEY). Verify the app cold-loads from data/results/last_run.json with no
network. If requested, add railway.toml + a thin FastAPI /run trigger; otherwise leave out.
Print the deploy checklist and the exact Streamlit Cloud steps.
```

**✓ Opus review gate:**
- [ ] Live Streamlit link loads instantly and is not blank; secret set, not committed.
- [ ] README Mermaid graph matches the implemented graph; live link + screenshots present.
- [ ] `opener.md` reflects the latest real numbers; every comparative claim tagged.
- [ ] `responsible_data.md` accurate; no raw review dumps anywhere.

**Commit checkpoint:** Confirm live link from a fresh/incognito browser. Tag `v1.0`. **Done.**

---

## 5. Key Technical Decisions

| Decision | Choice & rationale |
|---|---|
| **Agent framework** | **LangGraph.** Explicit `StateGraph` + conditional edges make the control flow legible + testable — ideal for interview walk-through and the one framework worth deep familiarity. CrewAI/AutoGen named as adjacent (honest framework-familiarity), not used. |
| **LLM provider** | **Claude** via a provider-agnostic wrapper. Haiku for bulk classification (cost), Sonnet for plan/cluster/diagnose/critique (judgment). Swappable; "built on Claude" is a nice in-interview note. |
| **App Store access** | Public customer-review **RSS JSON** + iTunes Search API for id resolution — documented, no HTML scraping, responsible by construction. Multiple storefronts widen the corpus. |
| **Statistics** | **Wilson** intervals (not normal approx) because USim's proportions are small-`n` and often extreme — exactly where naive methods mislead. Min-`n` + disjoint-interval gating prevents volume-driven false deltas. |
| **Taxonomy** | **Seeded but emergent** — `cluster` may add themes beyond the seed, so the analysis isn't blind to unanticipated pains while staying comparable across companies. |
| **Deploy** | **Streamlit Community Cloud** primary: snapshot-backed dashboard, instant load, on-demand re-run. Railway/FastAPI optional. |
| **Snapshot-first UI** | Commit `last_run.json` so the live link is never blank/slow and never costs API $ on a cold visit; live re-run is opt-in + budget-guarded. |

---

## 6. The Opener Deliverable (`docs/opener.md`)

One page, generated from real numbers, used to open the interview and as the README's "what I found." Structure:

1. **Headline (1 line):** the single loudest, Supported pain across the field and where USim sits.
2. **Method line (1 sentence):** *"An LLM agent read N public reviews across USim and M competitors over the last W months, classified each into a pain taxonomy, and benchmarked rates per-100-reviews with 95% confidence intervals."*
3. **Top-3 pains table:** pain | USim per-100 (CI) | field median per-100 | delta | Supported/Directional.
4. **Competitive read (2–3 sentences):** where USim is ahead / lags — Supported claims only; Directional explicitly hedged.
5. **Month-one interventions (3 bullets):** the automation/ops moves the data implies (activation watchdog, support-SLA triage, refund-status automation) — spoken, not built.
6. **Honesty footer (1 line):** sample sizes + windows stated plainly.

> **Why the footer matters.** Volunteering your sample sizes and limitations is counter-intuitively the strongest move: it signals you can't be caught out — the same composure that protects you in the salary conversation (WS4/WS5). The agent enforces the honesty; the footer advertises it.

---

## 7. The Build Workflow — Opus Leads, Claude Code Implements

Two roles. **Opus** (this conversation or its successor) is lead, designer, checker, reviewer. **Claude Code** is the implementer. This doc is the contract between them.

| Role | Owns |
|---|---|
| **Opus (lead)** | Holds the design; issues one phase microprompt at a time; reviews the returned diff against that phase's review gate; approves or sends back with **specific** fixes; decides when to advance; updates the design if reality forces a change and notes it back to the master plan. |
| **Claude Code (implementer)** | Executes exactly the current microprompt; writes code + tests; runs them; reports results + blockers; does **not** scope-creep into later phases. |

### 7.1 The loop, per phase

1. Opus pastes the phase microprompt into Claude Code.
2. Claude Code implements, runs tests, reports back (diff summary + test output).
3. Opus checks the result against the phase's Opus review gate.
4. Any gate item fails → Opus returns a precise fix (not "try again"). All pass → commit at the checkpoint and advance.
5. Phases run in order P0→P6. Within the master timeline: Days 2–4, parallel to WS1/WS4/WS5.

### 7.2 Operating rules

- **One phase at a time.** Don't paste the next microprompt until the current gate passes — keeps diffs reviewable and prevents compounding errors.
- **Tests are part of the phase**, not a later chore. A phase isn't done until its tests are green offline.
- **No live network or real API spend in CI** — mock it. Live runs are deliberate, local, budget-metered.
- **Secrets never leave `.env`.** A proposal to commit a key is an automatic gate failure.
- **Ambiguity → ask, don't guess.** Opus resolves against the design, amending the doc if needed.

### 7.3 Microprompt index

| Phase | Microprompt covers | Gate theme |
|---|---|---|
| P0 | Scaffold, config, LLM client + cost meter, CI | Kill-switch works; no secrets; CI green |
| P1 | Sources + fetch tool | Offline tests; dedup/cache; graceful failure |
| P2 | LangGraph agent (8 nodes, 2 edges, trace) | E2E offline; Wilson correct; edges fire |
| P3 | `diagnosis.json` + `opener.md` | No untagged claims; snapshot loads offline |
| P4 | Streamlit 3-tab dashboard | Instant load; badges; real trace |
| P5 | Test suite + hardening | Stats guarantees covered; loops bounded |
| P6 | Deploy + README + opener | Live link instant; data note accurate |

---

## Appendix A — Competitor Registry

> IDs resolve at runtime via the iTunes Search API; only USim's id + the excluded sibling are fixed.

| Company | Resolve by | Note |
|---|---|---|
| **USim (TARGET)** | App Store id `6502586159` · usim.me | Entity AMAS INTERNATIONAL… WLL (Kuwait) |
| **USIMS (EXCLUDED)** | App Store id `1555283998` | Name-collision sibling — NOT the target; explicitly excluded |
| Airalo | search "Airalo" · airalo.com | Category leader; large corpus |
| Holafly | search "Holafly" · holafly.com | Large corpus; unlimited-plan positioning |
| Saily | search "Saily" · saily.com | Newer (Nord); growing |
| Jetpac | search "Jetpac" · jetpacglobal | High Trustpilot; perks model |
| Nomad | search "Nomad eSIM" · getnomad.app | Popular comparator |
| eSIM.net / getesimtravel / esimcard | domains | Web-review comparators (Trustpilot-rich) if Play/App thin |

> **Resolver discipline.** Never hard-code a guessed numeric app id. `resolve_app_id(name)` queries the Search API and the agent records which id it resolved in the trace, so a wrong match is visible and fixable rather than silent.

## Appendix B — Pain Taxonomy (seed)

> The classifier starts here; the `cluster` node may add emergent themes. Keep labels stable so cross-company rates stay comparable.

| Theme | Captures |
|---|---|
| `activation` | eSIM won't install/activate after purchase; QR/profile failures; "paid but no service" |
| `support` | Slow/absent/unhelpful support; no reply; bot-only; timezone gaps |
| `refund_billing` | Refund delays/denials; double charges; unexpected charges; cancellation friction |
| `coverage_speed` | No signal in country; throttling; slow data; drops |
| `app_ux` | Confusing app; unclear install instructions; missing usage stats |
| `value_pricing` | Price vs competitors; plan flexibility; data-expiry complaints |
| `positive` | Praise (worked instantly, good price, good support) — for honest sentiment balance |

## Appendix C — Pre-flight & Definition of Done

**Before Phase 0**
- [ ] `ANTHROPIC_API_KEY` available locally (never committed).
- [ ] Master-plan Part C security item (the unrelated Gmail app-password revocation) is done — a Day-1 task, unrelated to this repo.
- [ ] Decide cost ceiling (default $8) + min-`n` floor (default 30).

**Definition of done (whole artifact)**
- [ ] Live Streamlit link loads instantly from a committed snapshot; live re-run works + budget-guarded.
- [ ] Every comparative claim in UI + opener badged Supported/Directional; thin samples never anchor a claim.
- [ ] Agent is genuinely agentic: tool nodes + two conditional edges + self-critique, with a visible trace.
- [ ] Tests green offline incl. the statistical guarantees; CI green; no secrets; responsible-data policy shipped.
- [ ] `docs/opener.md` ready to speak in the first 90 seconds.

---

*End of solution design. Build it phase by phase per §7; bring any design change back to the master plan if it shifts the shared strategy.*
