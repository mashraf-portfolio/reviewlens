"""Apple App Store review fetcher.

Uses two public Apple endpoints — no third-party scraping library:
  - iTunes Search API  →  resolve a name to a numeric trackId
  - iTunes RSS feed    →  paginate customer reviews in JSON format

Caches every raw API response under data/raw_cache/appstore/ so subsequent
runs are free and CI never touches the network.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import httpx

from sources.models import DEFAULT_CACHE_DIR, Review

log = logging.getLogger(__name__)

# The USIMS sibling app — must never be returned as a resolved target.
EXCLUDED_IDS: frozenset[str] = frozenset({"1555283998"})

_SEARCH_URL = "https://itunes.apple.com/search"
_RSS_URL = (
    "https://itunes.apple.com/{country}/rss/customerreviews"
    "/page={page}/id={app_id}/sortby=mostrecent/json"
)
_PAGE_SLEEP = 0.4  # seconds between RSS page requests


# ---------------------------------------------------------------------------
# App-ID resolution
# ---------------------------------------------------------------------------


def resolve_app_id(name: str) -> str | None:
    """Return the iTunes numeric trackId (as str) for the best-match app.

    Queries the public iTunes Search API and returns the first result whose
    trackId is not in EXCLUDED_IDS.  Returns None when every candidate is
    excluded or the search yields no software results.
    """
    try:
        resp = httpx.get(
            _SEARCH_URL,
            params={"term": name, "entity": "software", "limit": 25, "media": "software"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("iTunes search failed for %r: %s", name, exc)
        return None

    for result in data.get("results", []):
        track_id = str(result.get("trackId", ""))
        if track_id and track_id not in EXCLUDED_IDS:
            return track_id

    return None


# ---------------------------------------------------------------------------
# Review fetching
# ---------------------------------------------------------------------------


def fetch_appstore_reviews(
    app_id: str,
    app_name: str,
    country: str,
    *,
    max_pages: int = 10,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> list[Review]:
    """Fetch up to max_pages × ~50 reviews for app_id in country.

    Pages are cached as raw JSON under cache_dir/appstore/<app_id>/<country>/.
    Subsequent calls with the same arguments read from cache without hitting
    the network.
    """
    reviews: list[Review] = []

    for page in range(1, max_pages + 1):
        data = _load_page(app_id, country, page, cache_dir)

        if data is None:
            url = _RSS_URL.format(country=country, page=page, app_id=app_id)
            try:
                resp = httpx.get(url, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                log.warning(
                    "App Store fetch failed (app=%s country=%s page=%d): %s",
                    app_id,
                    country,
                    page,
                    exc,
                )
                break

            _save_page(data, app_id, country, page, cache_dir)
            time.sleep(_PAGE_SLEEP)

        entries = data.get("feed", {}).get("entry", [])
        # The first entry on page 1 describes the app itself — skip any entry
        # that lacks an im:rating field.
        review_entries = [e for e in entries if "im:rating" in e]

        if not review_entries:
            break

        for entry in review_entries:
            try:
                reviews.append(_parse_entry(entry, app_id, app_name, country))
            except Exception as exc:
                log.warning("Skipping malformed entry (app=%s): %s", app_id, exc)

    return reviews


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_path(app_id: str, country: str, page: int, cache_dir: Path) -> Path:
    return cache_dir / "appstore" / app_id / country / f"page_{page:02d}.json"


def _load_page(app_id: str, country: str, page: int, cache_dir: Path) -> dict | None:
    path = _cache_path(app_id, country, page, cache_dir)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Corrupt cache file %s: %s — re-fetching", path, exc)
    return None


def _save_page(data: dict, app_id: str, country: str, page: int, cache_dir: Path) -> None:
    path = _cache_path(app_id, country, page, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry parsing
# ---------------------------------------------------------------------------


def _parse_entry(entry: dict, app_id: str, app_name: str, country: str) -> Review:
    raw_date = entry["updated"]["label"]
    return Review(
        id=entry["id"]["label"],
        source="appstore",
        app=app_name,
        country=country,
        rating=int(entry["im:rating"]["label"]),
        title=entry["title"]["label"],
        body=entry["content"]["label"],
        date=datetime.fromisoformat(raw_date),
    )
