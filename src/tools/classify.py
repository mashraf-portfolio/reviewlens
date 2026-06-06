"""Classify tool node — labels each review with taxonomy themes.

TODO: implement classify_tool(state: GraphState) → partial GraphState:
  - Use LLMClient with config.models.classifier
  - Batch reviews to stay under token limits
  - For each review produce ClassifiedReview(review_id, themes: list[str], sentiment)
  - Use structured_output() with a Pydantic schema to enforce JSON
  - Store results in state.classified
"""


def classify_tool(state):
    """Classify each raw review against the configured taxonomy themes."""
    # TODO: implement
    raise NotImplementedError
