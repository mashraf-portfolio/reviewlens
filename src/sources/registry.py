"""App registry — defines the target and competitor universe (design doc §Appendix A).

Hard rules:
  - USim App Store ID 6502586159 is fixed and never re-resolved.
  - App ID 1555283998 (USIMS, the confusable sibling) is permanently excluded
    from any resolution result and from the returned target list.
  - Competitor App Store IDs are resolved at runtime via resolve_app_id so
    the registry stays correct even as numeric IDs change between app updates.
    No guessed numeric IDs are hard-coded for competitors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sources.appstore import EXCLUDED_IDS, resolve_app_id
from sources.models import AppTarget

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixed identifiers (design doc §Appendix A)
# ---------------------------------------------------------------------------

USIM_APP_STORE_ID: str = "6502586159"

# Competitors: search term → human-readable display name.
# resolve_all() resolves each term to a live trackId at call time.
_COMPETITOR_SEARCH_TERMS: dict[str, str] = {
    "Airalo eSIM": "Airalo",
    "Holafly eSIM": "Holafly",
    "Saily eSIM": "Saily",
    "Jetpac eSIM": "Jetpac",
    "Nomad eSIM": "Nomad",
    "eSIM.net": "eSIM.net",
    "esim travel getesim": "getesimtravel",
    "esimcard eSIM": "esimcard",
}


# ---------------------------------------------------------------------------
# Resolution result
# ---------------------------------------------------------------------------


@dataclass
class ResolutionLog:
    """Records which app_store_id each name resolved to (or failed)."""

    resolved: dict[str, str] = field(default_factory=dict)  # name → id
    failed: list[str] = field(default_factory=list)  # names that returned None
    excluded: list[str] = field(default_factory=list)  # names that hit EXCLUDED_IDS


def resolve_all(countries: list[str]) -> tuple[list[AppTarget], ResolutionLog]:
    """Return (targets, log) for the full analysis universe.

    USim is added first with its fixed ID.  Competitors are resolved in order;
    any result in EXCLUDED_IDS is silently skipped (recorded in log.excluded).

    Args:
        countries: App Store country codes to attach to each target.
    """
    log_rec = ResolutionLog()
    targets: list[AppTarget] = []

    # --- primary target (fixed, never re-resolved) ---
    targets.append(
        AppTarget(
            name="USim",
            app_store_id=USIM_APP_STORE_ID,
            play_store_id=None,  # TODO: add Android package name when confirmed
            countries=list(countries),
        )
    )
    log_rec.resolved["USim"] = USIM_APP_STORE_ID

    # --- competitors (runtime resolution) ---
    for search_term, display_name in _COMPETITOR_SEARCH_TERMS.items():
        app_id = resolve_app_id(search_term)

        if app_id is None:
            log.warning("Could not resolve App Store ID for %r (%s)", display_name, search_term)
            log_rec.failed.append(display_name)
            continue

        # Double-check: resolve_app_id already filters EXCLUDED_IDS, but be
        # explicit here as a defence-in-depth guard.
        if app_id in EXCLUDED_IDS:
            log.warning("Resolved ID %s for %r is in EXCLUDED_IDS — skipping", app_id, display_name)
            log_rec.excluded.append(display_name)
            continue

        targets.append(
            AppTarget(
                name=display_name,
                app_store_id=app_id,
                play_store_id=None,
                countries=list(countries),
            )
        )
        log_rec.resolved[display_name] = app_id
        log.info("Resolved %s → %s", display_name, app_id)

    return targets, log_rec
