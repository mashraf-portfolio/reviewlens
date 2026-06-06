"""Node-level tracing — logs entry/exit, decisions, and token spend to JSON.

Each run overwrites data/results/trace_last_run.json so the latest run is
always readable without file accumulation.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DEFAULT_TRACE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "results" / "trace_last_run.json"
)


class TraceContext:
    """Context manager that records per-node timings and decisions.

    Usage:
        tracer = TraceContext()
        with tracer:
            ...run graph...
        entries = tracer.entries   # list[dict]
    """

    def __init__(self, output_path: Path | None = None) -> None:
        self.entries: list[dict[str, Any]] = []
        self._output_path = output_path or _DEFAULT_TRACE_PATH
        self._node_starts: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> TraceContext:
        self.entries.clear()
        self._node_starts.clear()
        return self

    def __exit__(self, *_: object) -> None:
        self.flush()

    # ------------------------------------------------------------------
    # Node lifecycle hooks (called from node functions)
    # ------------------------------------------------------------------

    def node_enter(self, node: str, state: dict[str, Any]) -> None:
        self._node_starts[node] = time.monotonic()
        self.entries.append(
            {
                "type": "node_enter",
                "node": node,
                "ts": datetime.now(UTC).isoformat(),
                "fetch_loop": state.get("fetch_loop_count", 0),
                "raw_reviews": len(state.get("raw_reviews", [])),
            }
        )

    def node_exit(
        self,
        node: str,
        state: dict[str, Any],
        *,
        decision: str | None = None,
    ) -> None:
        elapsed_ms = round(
            (time.monotonic() - self._node_starts.get(node, time.monotonic())) * 1000, 1
        )
        entry: dict[str, Any] = {
            "type": "node_exit",
            "node": node,
            "ts": datetime.now(UTC).isoformat(),
            "latency_ms": elapsed_ms,
        }
        if decision is not None:
            entry["decision"] = decision
            entry["reason"] = _decision_reason(node, decision, state)
        self.entries.append(entry)
        log.debug("node %-12s  %6.1f ms  %s", node, elapsed_ms, decision or "")

    def tool_call(self, node: str, tool: str, tokens_in: int, tokens_out: int) -> None:
        self.entries.append(
            {
                "type": "tool_call",
                "node": node,
                "tool": tool,
                "ts": datetime.now(UTC).isoformat(),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            }
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return {node: {latency_ms, tool_calls}} for all exited nodes."""
        result: dict[str, Any] = {}
        for e in self.entries:
            if e["type"] == "node_exit":
                n = e["node"]
                result.setdefault(n, {"latency_ms": 0, "tool_calls": 0})
                result[n]["latency_ms"] += e["latency_ms"]
            elif e["type"] == "tool_call":
                n = e["node"]
                result.setdefault(n, {"latency_ms": 0, "tool_calls": 0})
                result[n]["tool_calls"] += 1
        return result

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def flush(self) -> None:
        try:
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            self._output_path.write_text(
                json.dumps({"entries": self.entries, "summary": self.summary()}, indent=2),
                encoding="utf-8",
            )
            log.info("Trace written to %s", self._output_path)
        except Exception as exc:
            log.warning("Could not write trace: %s", exc)


# ---------------------------------------------------------------------------
# Decision reason strings (human-readable for the trace log)
# ---------------------------------------------------------------------------


def _decision_reason(node: str, decision: str, state: dict[str, Any]) -> str:
    if node == "triage":
        n = len(state.get("triaged_reviews", []))
        floor = state.get("min_n_floor", 30)
        if decision == "classify":
            return f"triaged={n} >= min_n_floor={floor} → proceed to classify"
        return f"triaged={n} < min_n_floor={floor} → retry fetch (loop {state.get('fetch_loop_count', 0)})"

    if node == "critique":
        if decision == "end":
            return "critique accepted — claims meet quality bar or loop limit reached"
        lc = state.get("low_confidence_count", 0)
        total = len(state.get("classified", [])) or 1
        return f"critique rejected — low_confidence={lc}/{total} ({lc / total:.0%}); retrying fetch"

    return ""
