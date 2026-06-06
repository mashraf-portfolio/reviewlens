"""LangSmith / stdout tracing helpers.

TODO: implement a TraceContext context-manager that:
  - enables LangSmith tracing when LANGCHAIN_API_KEY is set
  - falls back to structured stdout logging otherwise
  - records node timings and token spend per node
  - exposes a summary() method returning a dict of {node: {latency_ms, tokens}}
"""


class TraceContext:
    """Placeholder tracing context manager."""

    def __enter__(self):
        # TODO: initialise LangSmith project or stdout handler
        return self

    def __exit__(self, *args):
        # TODO: flush trace
        pass

    def summary(self) -> dict:
        """Return per-node timing and token usage summary."""
        # TODO: implement
        raise NotImplementedError
