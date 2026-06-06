"""Trustpilot review fetcher (disabled by default in config).

TODO: implement TrustpilotSource using the Trustpilot public API or scraping.
  - Requires TRUSTPILOT_API_KEY in .env when enabled.
  - Cache raw pages under data/raw_cache/trustpilot/<domain>/.
  - Return list[ReviewRecord].
"""


class TrustpilotSource:
    """Fetches and caches reviews from Trustpilot."""

    def __init__(self, domain: str) -> None:
        # TODO: store params, validate API key present
        raise NotImplementedError

    def fetch(self, max_loops: int) -> list[dict]:
        """Return raw review dicts up to max_loops pages."""
        # TODO: paginate + deduplicate
        raise NotImplementedError
