"""Trustpilot review fetcher — disabled by default, config-gated.

Returns an empty list immediately when disabled in config.yaml
(sources: [{name: trustpilot, enabled: false}]).  When enabled, a
TRUSTPILOT_API_KEY must be present in .env.

TODO: implement live fetching via the Trustpilot Business Units API:
  GET /v1/business-units/{businessUnitId}/reviews?perPage=100&page={n}
  Cache pages under data/raw_cache/trustpilot/<domain>/.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sources.models import DEFAULT_CACHE_DIR, Review

log = logging.getLogger(__name__)


def fetch_trustpilot_reviews(
    domain: str,
    *,
    enabled: bool = False,
    api_key: str | None = None,
    max_pages: int = 10,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> list[Review]:
    """Return Trustpilot reviews for domain, or [] when disabled.

    Args:
        domain:    Business domain, e.g. "usimglobal.com".
        enabled:   Must be True (from config) to do any work.
        api_key:   TRUSTPILOT_API_KEY from .env.
        max_pages: Maximum pages to fetch.
        cache_dir: Root cache directory.
    """
    if not enabled:
        log.debug("Trustpilot source is disabled — skipping %s", domain)
        return []

    if not api_key:
        log.warning("Trustpilot enabled but TRUSTPILOT_API_KEY is not set — skipping %s", domain)
        return []

    # TODO: implement live fetching and caching
    raise NotImplementedError("Trustpilot live fetching not yet implemented")
