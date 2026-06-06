"""Apple App Store review fetcher.

TODO: implement AppStoreSource using an iTunes RSS / app-store-scraper library.
  - Accept a list of country codes (e.g. ["us", "gb"]) from config.storefronts.
  - Respect max_fetch_loops and min_n_floor from config.
  - Cache raw pages under data/raw_cache/appstore/<country>/.
  - Return list[ReviewRecord].
"""


class AppStoreSource:
    """Fetches and caches reviews from the Apple App Store."""

    def __init__(self, app_id: str, countries: list[str]) -> None:
        # TODO: store params, initialise any session state
        raise NotImplementedError

    def fetch(self, max_loops: int) -> list[dict]:
        """Return raw review dicts across all configured country storefronts."""
        # TODO: paginate per country, deduplicate by review ID
        raise NotImplementedError
