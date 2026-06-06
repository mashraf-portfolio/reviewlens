"""Cluster tool node — groups classified reviews into named theme clusters.

TODO: implement cluster_tool(state: GraphState) → partial GraphState:
  - Group ClassifiedReviews by primary theme
  - Within each theme, sub-cluster by semantic similarity (embedding or LLM)
  - Assign a short human-readable label to each cluster
  - Produce list[Cluster(theme, label, review_ids, representative_quotes)]
  - Store results in state.clusters
"""


def cluster_tool(state):
    """Group classified reviews into semantically coherent clusters."""
    # TODO: implement
    raise NotImplementedError
