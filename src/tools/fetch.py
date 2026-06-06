"""Fetch tool — retrieves and deduplicates reviews for all targets in a FetchPlan.

Design contract:
  - A single failing source never aborts the run; a warning is logged and the
    remaining sources continue normally.
  - Reviews are deduplicated by (source, id) — first occurrence wins.
  - Returns both the flat review list and per-source counts so callers can
    detect coverage problems early.
"""

from __future__ import annotations

import logging

from sources.appstore import fetch_appstore_reviews
from sources.models import FetchPlan, Review
from sources.playstore import fetch_playstore_reviews
from sources.trustpilot import fetch_trustpilot_reviews

log = logging.getLogger(__name__)


def fetch_reviews(plan: FetchPlan) -> tuple[list[Review], dict[str, int]]:
    """Fetch all reviews described by plan and return (reviews, counts_by_source).

    Args:
        plan: A fully-resolved FetchPlan from plan_node (or built directly in
              tests / scripts).

    Returns:
        reviews:          Deduplicated list of Review objects across all targets
                          and enabled sources.
        counts_by_source: Dict mapping source name → number of reviews returned
                          (after deduplication).
    """
    raw: list[Review] = []

    for target in plan.targets:
        # ----------------------------------------------------------------
        # App Store
        # ----------------------------------------------------------------
        if "appstore" in plan.enabled_sources and target.app_store_id:
            for country in target.countries:
                try:
                    batch = fetch_appstore_reviews(
                        target.app_store_id,
                        target.name,
                        country,
                        max_pages=plan.max_pages,
                        cache_dir=plan.cache_dir,
                    )
                    raw.extend(batch)
                    log.info(
                        "appstore %s/%s → %d reviews",
                        target.name,
                        country,
                        len(batch),
                    )
                except Exception as exc:
                    log.warning(
                        "appstore fetch failed (target=%s country=%s): %s — continuing",
                        target.name,
                        country,
                        exc,
                    )

        # ----------------------------------------------------------------
        # Play Store
        # ----------------------------------------------------------------
        if "playstore" in plan.enabled_sources and target.play_store_id:
            try:
                batch = fetch_playstore_reviews(
                    target.play_store_id,
                    target.name,
                    max_pages=plan.max_pages,
                    cache_dir=plan.cache_dir,
                )
                raw.extend(batch)
                log.info("playstore %s → %d reviews", target.name, len(batch))
            except Exception as exc:
                log.warning(
                    "playstore fetch failed (target=%s): %s — continuing",
                    target.name,
                    exc,
                )

        # ----------------------------------------------------------------
        # Trustpilot (disabled by default)
        # ----------------------------------------------------------------
        if "trustpilot" in plan.enabled_sources:
            try:
                batch = fetch_trustpilot_reviews("", enabled=False)
                raw.extend(batch)
            except Exception as exc:
                log.warning(
                    "trustpilot fetch failed (target=%s): %s — continuing", target.name, exc
                )

    deduped = _dedup_reviews(raw)
    counts = _count_by_source(deduped)
    return deduped, counts


def _dedup_reviews(reviews: list[Review]) -> list[Review]:
    """Return reviews with duplicates removed; first occurrence by (source, id) wins."""
    seen: set[tuple[str, str]] = set()
    out: list[Review] = []
    for r in reviews:
        key = r.dedup_key()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _count_by_source(reviews: list[Review]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in reviews:
        counts[r.source] = counts.get(r.source, 0) + 1
    return counts
