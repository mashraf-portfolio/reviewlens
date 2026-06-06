"""Google Play Store review fetcher.

TODO: implement PlayStoreSource using google-play-scraper.
  - Accept a package name (e.g. "com.example.app") from config.storefronts.
  - Respect max_fetch_loops and min_n_floor from config.
  - Cache raw pages under data/raw_cache/playstore/<package>/.
  - Return list[ReviewRecord].
"""


class PlayStoreSource:
    """Fetches and caches reviews from Google Play."""

    def __init__(self, package: str) -> None:
        # TODO: store params
        raise NotImplementedError

    def fetch(self, max_loops: int) -> list[dict]:
        """Return raw review dicts up to max_loops pagination rounds."""
        # TODO: paginate + deduplicate by review ID
        raise NotImplementedError
