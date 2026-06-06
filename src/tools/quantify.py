"""Quantify tool node — statistical significance of cluster volume changes.

TODO: implement quantify_tool(state: GraphState) → partial GraphState:
  - Use statsmodels for proportion z-test or chi-squared on theme counts
    comparing current recency_window vs prior equal-length window
  - Produce QuantStats(theme, count, pct, delta_pct, p_value, significant)
  - Filter to statistically significant changes (p < 0.05)
  - Store results in state.stats
"""


def quantify_tool(state):
    """Compute statistical significance of theme volume changes over time."""
    # TODO: implement
    raise NotImplementedError
