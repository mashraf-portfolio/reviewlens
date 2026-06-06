"""Offline tests for tools.fetch — dedup, cache-first, and graceful degradation.

All network calls and source functions are mocked; no live HTTP in CI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from sources.models import AppTarget, FetchPlan, Review

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _review(review_id: str, source: str = "appstore", country: str = "us") -> Review:
    return Review(
        id=review_id,
        source=source,
        app="TestApp",
        country=country,
        rating=5,
        title="OK",
        body="Great",
        date=datetime(2024, 1, 15, tzinfo=UTC),
    )


def _plan(
    tmp_path: Path,
    *,
    app_store_id: str | None = "6502586159",
    play_store_id: str | None = None,
    countries: list[str] | None = None,
    enabled_sources: list[str] | None = None,
) -> FetchPlan:
    return FetchPlan(
        targets=[
            AppTarget(
                name="TestApp",
                app_store_id=app_store_id,
                play_store_id=play_store_id,
                countries=countries or ["us"],
            )
        ],
        max_pages=1,
        enabled_sources=enabled_sources or ["appstore"],
        cache_dir=tmp_path,
    )


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDedup:
    def test_identical_source_and_id_deduplicated(self):
        """Two reviews with the same (source, id) are collapsed to one."""
        from tools.fetch import _dedup_reviews

        r1 = _review("abc", source="appstore")
        r2 = _review("abc", source="appstore")  # duplicate
        r3 = _review("xyz", source="appstore")

        result = _dedup_reviews([r1, r2, r3])

        assert len(result) == 2
        assert {r.id for r in result} == {"abc", "xyz"}

    def test_same_id_different_source_kept_separately(self):
        """(appstore, "1") and (playstore, "1") are distinct — both kept."""
        from tools.fetch import _dedup_reviews

        r1 = _review("1", source="appstore")
        r2 = _review("1", source="playstore")

        result = _dedup_reviews([r1, r2])

        assert len(result) == 2

    def test_first_occurrence_wins(self):
        """When deduplicating, the first review in the input list is retained."""
        from tools.fetch import _dedup_reviews

        r_first = Review("dup", "appstore", "App A", "us", 5, "First", "F", datetime(2024, 1, 1))
        r_second = Review("dup", "appstore", "App B", "us", 1, "Second", "S", datetime(2024, 1, 2))

        result = _dedup_reviews([r_first, r_second])

        assert len(result) == 1
        assert result[0].title == "First"

    def test_empty_input_returns_empty(self):
        from tools.fetch import _dedup_reviews

        assert _dedup_reviews([]) == []


# ---------------------------------------------------------------------------
# Cache-first — HTTP must not be called on the second fetch
# ---------------------------------------------------------------------------


class TestCacheFirst:
    def test_second_call_does_not_hit_http(self, tmp_path):
        """After the first fetch writes the cache, the second call is pure disk I/O."""
        from sources.appstore import fetch_appstore_reviews

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "feed": {
                "entry": [
                    {
                        "id": {"label": "r1"},
                        "title": {"label": "Nice"},
                        "content": {"label": "Works well.", "attributes": {"type": "text"}},
                        "im:rating": {"label": "5"},
                        "updated": {"label": "2024-03-01T10:00:00-07:00"},
                        "author": {"name": {"label": "Alice"}},
                    }
                ]
            }
        }

        with patch("sources.appstore.httpx.get", return_value=mock_resp) as mock_get:
            result1 = fetch_appstore_reviews(
                "6502586159", "USim", "us", max_pages=1, cache_dir=tmp_path
            )
            first_call_count = mock_get.call_count

            # Second call — cache file now exists, HTTP must NOT be invoked.
            result2 = fetch_appstore_reviews(
                "6502586159", "USim", "us", max_pages=1, cache_dir=tmp_path
            )
            second_call_count = mock_get.call_count

        assert first_call_count == 1, "First fetch should hit HTTP once"
        assert second_call_count == 1, "Second fetch must NOT add any HTTP calls"
        assert result1 == result2

    def test_cache_file_is_written_after_first_fetch(self, tmp_path):
        """The raw JSON cache file is created during the first fetch."""
        from sources.appstore import _cache_path, fetch_appstore_reviews

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"feed": {"entry": []}}

        with patch("sources.appstore.httpx.get", return_value=mock_resp):
            fetch_appstore_reviews("6502586159", "USim", "us", max_pages=1, cache_dir=tmp_path)

        expected = _cache_path("6502586159", "us", 1, tmp_path)
        assert expected.exists(), f"Cache file {expected} was not created"


# ---------------------------------------------------------------------------
# Graceful degradation — one failing source must not abort the whole run
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    def test_failing_source_does_not_raise(self, tmp_path):
        """fetch_reviews returns normally even when the only source raises."""
        from tools.fetch import fetch_reviews

        with patch("tools.fetch.fetch_appstore_reviews", side_effect=Exception("boom")):
            reviews, counts = fetch_reviews(_plan(tmp_path))

        # No exception — empty result is fine
        assert reviews == []
        assert counts == {}

    def test_other_sources_returned_when_one_fails(self, tmp_path):
        """Reviews from healthy sources are returned even if one source explodes."""
        from tools.fetch import fetch_reviews

        good_reviews = [_review("g1", source="appstore"), _review("g2", source="appstore")]

        # Two targets: first raises on appstore, second succeeds.
        plan = FetchPlan(
            targets=[
                AppTarget(
                    name="BadApp",
                    app_store_id="bad-id",
                    countries=["us"],
                ),
                AppTarget(
                    name="GoodApp",
                    app_store_id="good-id",
                    countries=["us"],
                ),
            ],
            max_pages=1,
            enabled_sources=["appstore"],
            cache_dir=tmp_path,
        )

        def _fake_fetch(app_id, app_name, country, **kwargs):
            if app_id == "bad-id":
                raise RuntimeError("DNS failure")
            return good_reviews

        with patch("tools.fetch.fetch_appstore_reviews", side_effect=_fake_fetch):
            reviews, counts = fetch_reviews(plan)

        assert len(reviews) == 2
        assert counts["appstore"] == 2

    def test_counts_by_source_populated(self, tmp_path):
        """counts_by_source correctly tallies reviews per source after dedup."""
        from tools.fetch import fetch_reviews

        fake = [_review("a"), _review("b"), _review("a")]  # "a" is a duplicate

        with patch("tools.fetch.fetch_appstore_reviews", return_value=fake):
            reviews, counts = fetch_reviews(_plan(tmp_path))

        assert counts["appstore"] == 2  # deduped: a and b
        assert len(reviews) == 2
