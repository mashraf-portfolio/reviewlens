"""Google Play Store review fetcher.

Wraps google-play-scraper and normalises output to the shared Review shape.
Raw pages are cached under data/raw_cache/playstore/<package>/ so subsequent
runs are free and CI never touches the network.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sources.models import DEFAULT_CACHE_DIR, Review

log = logging.getLogger(__name__)


def fetch_playstore_reviews(
    package: str,
    app_name: str,
    *,
    max_pages: int = 10,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> list[Review]:
    """Fetch up to max_pages × 100 reviews for the given Android package name.

    Pages are cached as raw JSON under cache_dir/playstore/<package>/.
    Subsequent calls with the same arguments read from cache without hitting
    the network.
    """
    # Deferred import keeps the module importable even when google-play-scraper
    # is not installed (unit tests mock this out entirely).
    from google_play_scraper import Sort  # type: ignore[import-untyped]
    from google_play_scraper import reviews as gps_reviews  # type: ignore[import-untyped]

    all_reviews: list[Review] = []
    token = None  # continuation token from previous page

    for page in range(max_pages):
        cache_file = _cache_path(package, page, cache_dir)

        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                raw_reviews = cached["reviews"]
                token = cached.get("next_token")  # restore for next iteration
            except Exception as exc:
                log.warning("Corrupt Play Store cache %s: %s — re-fetching", cache_file, exc)
                raw_reviews = None
        else:
            raw_reviews = None

        if raw_reviews is None:
            try:
                result, token = gps_reviews(
                    package,
                    lang="en",
                    country="us",
                    sort=Sort.NEWEST,
                    count=100,
                    continuation_token=token,
                )
            except Exception as exc:
                log.warning("Play Store fetch failed (package=%s page=%d): %s", package, page, exc)
                break

            raw_reviews = [_review_to_dict(r) for r in result]
            _save_page({"reviews": raw_reviews, "next_token": token}, package, page, cache_dir)

        if not raw_reviews:
            break

        for r in raw_reviews:
            try:
                all_reviews.append(_parse_review(r, package, app_name))
            except Exception as exc:
                log.warning("Skipping malformed Play review (package=%s): %s", package, exc)

        if not token:
            break

    return all_reviews


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_path(package: str, page: int, cache_dir: Path) -> Path:
    return cache_dir / "playstore" / package / f"page_{page:02d}.json"


def _save_page(data: dict, package: str, page: int, cache_dir: Path) -> None:
    path = _cache_path(package, page, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Serialisation helpers  (datetime → str and back)
# ---------------------------------------------------------------------------


def _review_to_dict(r: dict) -> dict:
    at = r.get("at")
    return {
        "reviewId": r.get("reviewId", ""),
        "content": r.get("content") or "",
        "score": r.get("score", 0),
        "at": at.isoformat() if isinstance(at, datetime) else str(at or ""),
        "userName": r.get("userName", ""),
    }


def _parse_review(r: dict, package: str, app_name: str) -> Review:
    raw_at = r.get("at", "")
    try:
        date = datetime.fromisoformat(raw_at)
    except (ValueError, TypeError):
        date = datetime(2000, 1, 1, tzinfo=UTC)

    content = r.get("content") or ""
    return Review(
        id=r.get("reviewId") or "",
        source="playstore",
        app=app_name,
        country="us",  # google-play-scraper fetches globally; tag as "us"
        rating=int(r.get("score", 0)),
        title="",  # Play Store has no separate title field
        body=content,
        date=date,
    )
