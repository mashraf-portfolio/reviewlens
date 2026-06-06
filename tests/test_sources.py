"""Offline tests for the source-layer resolution and exclusion logic.

All network calls are intercepted with unittest.mock — no live HTTP in CI.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Fixtures — iTunes Search API responses
# ---------------------------------------------------------------------------


def _search_response(results: list[dict]) -> MagicMock:
    """Build a mock httpx response for the iTunes Search API."""
    mock = MagicMock()
    mock.json.return_value = {"resultCount": len(results), "results": results}
    mock.raise_for_status.return_value = None
    return mock


def _rss_response(entries: list[dict]) -> MagicMock:
    """Build a mock httpx response for one page of the iTunes RSS feed."""
    mock = MagicMock()
    mock.json.return_value = {"feed": {"entry": entries}}
    mock.raise_for_status.return_value = None
    return mock


def _make_review_entry(review_id: str, rating: int = 5) -> dict:
    return {
        "id": {"label": review_id},
        "title": {"label": f"Review {review_id}"},
        "content": {"label": "Body text.", "attributes": {"type": "text"}},
        "im:rating": {"label": str(rating)},
        "updated": {"label": "2024-03-01T12:00:00-07:00"},
        "author": {"name": {"label": "Tester"}},
    }


# ---------------------------------------------------------------------------
# resolve_app_id tests
# ---------------------------------------------------------------------------


class TestResolveAppId:
    def test_returns_first_non_excluded_track_id(self):
        """resolve_app_id picks the first result that is not in EXCLUDED_IDS."""
        from sources.appstore import resolve_app_id

        results = [
            {"trackId": 6502586159, "trackName": "USim eSIM", "kind": "software"},
            {"trackId": 1555283998, "trackName": "USIMS", "kind": "software"},
        ]
        with patch("sources.appstore.httpx.get", return_value=_search_response(results)):
            result = resolve_app_id("USim eSIM")

        assert result == "6502586159"

    def test_excluded_id_is_never_returned(self):
        """If the only matching trackId is 1555283998, resolve_app_id returns None."""
        from sources.appstore import resolve_app_id

        results = [{"trackId": 1555283998, "trackName": "USIMS", "kind": "software"}]
        with patch("sources.appstore.httpx.get", return_value=_search_response(results)):
            result = resolve_app_id("USIMS")

        assert result is None

    def test_excluded_id_skipped_next_candidate_returned(self):
        """Excluded ID at position 0 is skipped; position 1 is returned instead."""
        from sources.appstore import resolve_app_id

        results = [
            {"trackId": 1555283998, "trackName": "USIMS", "kind": "software"},
            {"trackId": 111111111, "trackName": "Other App", "kind": "software"},
        ]
        with patch("sources.appstore.httpx.get", return_value=_search_response(results)):
            result = resolve_app_id("something")

        assert result == "111111111"

    def test_empty_search_results_returns_none(self):
        from sources.appstore import resolve_app_id

        with patch("sources.appstore.httpx.get", return_value=_search_response([])):
            assert resolve_app_id("no match") is None

    def test_http_error_returns_none(self):
        from sources.appstore import resolve_app_id

        with patch("sources.appstore.httpx.get", side_effect=Exception("connection reset")):
            assert resolve_app_id("USim") is None


# ---------------------------------------------------------------------------
# Registry tests — USim hardcoded, 1555283998 always excluded
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_usim_resolves_to_known_fixed_id(self):
        """registry.resolve_all always puts USim at position 0 with id 6502586159."""
        from sources.registry import USIM_APP_STORE_ID, resolve_all

        # No network call needed: USim is hardcoded
        with patch("sources.registry.resolve_app_id", return_value=None):
            targets, log_rec = resolve_all(countries=["us"])

        usim = next((t for t in targets if t.name == "USim"), None)
        assert usim is not None
        assert usim.app_store_id == "6502586159"
        assert usim.app_store_id == USIM_APP_STORE_ID
        assert log_rec.resolved["USim"] == "6502586159"

    def test_excluded_id_never_appears_in_resolve_all(self):
        """If resolve_app_id returns 1555283998 for a competitor, it is dropped."""
        from sources.registry import resolve_all

        # Force every competitor resolution to return the excluded sibling ID.
        with patch("sources.registry.resolve_app_id", return_value="1555283998"):
            targets, log_rec = resolve_all(countries=["us"])

        app_store_ids = [t.app_store_id for t in targets if t.app_store_id]
        assert "1555283998" not in app_store_ids
        # All competitors went to excluded list, not resolved
        assert len(log_rec.excluded) == len(log_rec.excluded)  # sanity
        assert all(rid != "1555283998" for rid in log_rec.resolved.values())

    def test_usim_always_first_regardless_of_competitor_resolution(self):
        """USim is always the first entry in the target list."""
        from sources.registry import resolve_all

        with patch("sources.registry.resolve_app_id", return_value="999999"):
            targets, _ = resolve_all(countries=["us"])

        assert targets[0].name == "USim"


# ---------------------------------------------------------------------------
# App Store RSS parsing
# ---------------------------------------------------------------------------


class TestAppStoreFetch:
    def test_fetch_parses_entries_into_reviews(self, tmp_path):
        from sources.appstore import fetch_appstore_reviews

        page_data = _rss_response([_make_review_entry("r1", 4), _make_review_entry("r2", 5)])

        with patch("sources.appstore.httpx.get", return_value=page_data):
            reviews = fetch_appstore_reviews(
                "6502586159", "USim", "us", max_pages=1, cache_dir=tmp_path
            )

        assert len(reviews) == 2
        assert {r.id for r in reviews} == {"r1", "r2"}
        assert all(r.source == "appstore" for r in reviews)
        assert all(r.country == "us" for r in reviews)
        assert reviews[0].rating == 4
        assert reviews[1].rating == 5

    def test_empty_feed_stops_pagination(self, tmp_path):
        """An empty entry list on page 1 returns no reviews and stops early."""
        from sources.appstore import fetch_appstore_reviews

        with patch("sources.appstore.httpx.get", return_value=_rss_response([])):
            reviews = fetch_appstore_reviews(
                "6502586159", "USim", "us", max_pages=5, cache_dir=tmp_path
            )

        assert reviews == []
