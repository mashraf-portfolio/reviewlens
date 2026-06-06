"""Fetch tool node — retrieves raw reviews from all enabled sources.

TODO: implement fetch_tool(state: GraphState) → partial GraphState:
  - Call sources.registry.get_sources(config)
  - Call .fetch(max_loops) on each source
  - Deduplicate across sources by review ID + date
  - Apply recency_window_months filter
  - Enforce min_n_floor; raise if insufficient data
  - Store results in state.raw_reviews
"""


def fetch_tool(state):
    """Fetch and deduplicate reviews from all configured sources."""
    # TODO: implement
    raise NotImplementedError
