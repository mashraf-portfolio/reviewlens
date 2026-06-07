# Responsible Data — ReviewLens

## Sources

ReviewLens uses two public Apple endpoints only — no third-party scraping library, no authentication, no private data:

| Endpoint | Purpose |
|----------|---------|
| **iTunes Search API** (`itunes.apple.com/search`) | Resolve an app name to a numeric `trackId` |
| **App Store customer-review RSS feed** (`itunes.apple.com/{country}/rss/customerreviews/…/json`) | Paginate public customer reviews in JSON format |

Both endpoints are unauthenticated and documented by Apple for public use. No HTML parsing, no headless browsers, no third-party review-scraping services.

## Volume and storefronts

The completed run collected **~4,000 reviews** across 6 apps (USim + 5 competitors) × 5 storefronts (US, GB, CA, AU, IN), up to 10 pages per app-storefront pair (~50 reviews per page). Total corpus: **4,011 reviews** sourced entirely from the App Store.

## Caching and rate limiting

Raw API responses are written to `data/raw_cache/appstore/<app_id>/<country>/page_NN.json` after the first fetch. Subsequent runs — including CI — read from cache without hitting the network.

Live fetches are rate-limited to **0.4 seconds between pages** (`_PAGE_SLEEP` in `src/sources/appstore.py`) to stay well within Apple's informal request limits.

## What is committed vs. what stays local

| Artefact | Committed? |
|----------|-----------|
| `data/raw_cache/` — raw page JSON | **No** — `.gitignore`d; local only |
| `data/results/last_run.json` — aggregated per-100 rates and CIs | Yes |
| `data/results/trace_last_run.json` — node timings and token counts | Yes |
| `docs/diagnosis.json` — ranked deltas and interventions | Yes |
| `docs/opener.md` — narrative summary | Yes |

Raw review text never leaves the local machine in bulk. Only computed aggregates are committed.

## Aggregates-only output stance

The dashboard and all committed outputs show:

- **Per-100-review rates** with Wilson 95% confidence intervals
- **Theme-level summaries** (counts, deltas, support levels)
- At most a handful of **short paraphrased exemplars** synthesised by the LLM — never verbatim review text in bulk

No page of the UI or file in the repo contains the raw text of customer reviews. Individuals cannot be identified from aggregated rate data.

## Excluded app: USIMS

The App Store contains two superficially similar apps:

| App | iTunes trackId |
|-----|---------------|
| **USim** (target) | 6502586159 |
| **USIMS** (excluded sibling) | 1555283998 |

USIMS is **permanently excluded** from resolution results via the `EXCLUDED_IDS` frozenset in `src/sources/appstore.py`. The iTunes Search API sometimes returns USIMS as the top result for the query "USim"; the exclusion ensures this sibling is never conflated with the intended target.

## Summary

ReviewLens reads only publicly visible, unauthenticated data; caches it locally to avoid redundant requests; never commits raw review text; and presents only aggregated, paraphrased outputs. No personal data, private API access, or terms-of-service violations are involved.
