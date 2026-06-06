"""Source registry — maps source names from config to source classes.

TODO: implement get_sources(config) that:
  - Reads config.sources to determine which adapters are enabled.
  - Instantiates the appropriate source class for each enabled source.
  - Returns a list of instantiated source objects ready to call .fetch().

Example:
    sources = get_sources(settings)
    for src in sources:
        reviews.extend(src.fetch(settings.max_fetch_loops))
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Settings


def get_sources(config: Settings) -> list:
    """Return instantiated source adapters for all enabled sources.

    TODO: implement — map config.sources entries to AppStoreSource,
    PlayStoreSource, TrustpilotSource etc.
    """
    raise NotImplementedError
