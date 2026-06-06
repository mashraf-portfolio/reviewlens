"""Smoke tests: snapshot loading works without any LLM or network call."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure project root is importable (for `app` package)
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_load_snapshot_returns_diagnosis(tmp_path: Path, monkeypatch) -> None:
    """load_snapshot() parses last_run.json with no LLM/network calls."""
    results_dir = tmp_path / "data" / "results"
    results_dir.mkdir(parents=True)
    snapshot = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "target_app": "USim",
        "total_n": 10,
        "recency_window": 12,
        "per_source_n": {"appstore": 10},
        "pains": [],
        "deltas": [],
        "interventions": [],
        "opener_md": "# test",
    }
    (results_dir / "last_run.json").write_text(json.dumps(snapshot), encoding="utf-8")

    import app.streamlit_app as app_mod

    monkeypatch.setattr(app_mod, "_LAST_RUN", results_dir / "last_run.json")

    # Assert the Anthropic client is never constructed during a snapshot load
    with patch(
        "anthropic.Anthropic",
        side_effect=AssertionError("LLM client must not be constructed on snapshot load"),
    ):
        result = app_mod.load_snapshot()

    assert result is not None
    assert result["target_app"] == "USim"
    assert result["total_n"] == 10
    assert "pains" in result
    assert "deltas" in result
    assert "interventions" in result


def test_load_snapshot_missing_file(tmp_path: Path, monkeypatch) -> None:
    """load_snapshot() returns None when last_run.json does not exist."""
    import app.streamlit_app as app_mod

    monkeypatch.setattr(app_mod, "_LAST_RUN", tmp_path / "nonexistent.json")
    assert app_mod.load_snapshot() is None


def test_load_snapshot_empty_file(tmp_path: Path, monkeypatch) -> None:
    """load_snapshot() returns None for an empty file."""
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")

    import app.streamlit_app as app_mod

    monkeypatch.setattr(app_mod, "_LAST_RUN", empty)
    assert app_mod.load_snapshot() is None


def test_load_snapshot_invalid_json(tmp_path: Path, monkeypatch) -> None:
    """load_snapshot() returns None for malformed JSON."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")

    import app.streamlit_app as app_mod

    monkeypatch.setattr(app_mod, "_LAST_RUN", bad)
    assert app_mod.load_snapshot() is None


def test_load_snapshot_real_fixture() -> None:
    """load_snapshot() parses the committed last_run.json and returns a diagnosis dict."""
    import app.streamlit_app as app_mod

    result = app_mod.load_snapshot()
    # committed snapshot must be present and valid
    assert result is not None, "data/results/last_run.json missing or invalid"
    assert result.get("target_app") == "USim"
    assert isinstance(result.get("pains"), list)
    assert isinstance(result.get("deltas"), list)
    assert isinstance(result.get("interventions"), list)
    assert result.get("total_n", 0) > 0


def test_load_trace_no_llm_no_network(tmp_path: Path, monkeypatch) -> None:
    """_load_trace() reads trace_last_run.json with no LLM or network calls."""
    results_dir = tmp_path / "data" / "results"
    results_dir.mkdir(parents=True)
    trace = {
        "entries": [
            {
                "type": "node_enter",
                "node": "plan",
                "ts": "2026-01-01T00:00:00+00:00",
                "fetch_loop": 0,
                "raw_reviews": 0,
            },
            {
                "type": "node_exit",
                "node": "plan",
                "ts": "2026-01-01T00:00:00+00:00",
                "latency_ms": 0.0,
            },
        ],
        "summary": {"plan": {"latency_ms": 0.0, "tool_calls": 0}},
    }
    (results_dir / "trace_last_run.json").write_text(json.dumps(trace), encoding="utf-8")

    import app.streamlit_app as app_mod

    monkeypatch.setattr(app_mod, "_TRACE_PATH", results_dir / "trace_last_run.json")

    with (
        patch(
            "anthropic.Anthropic",
            side_effect=AssertionError("LLM client must not be constructed loading the trace"),
        ),
        patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("no network during trace load"),
        ),
    ):
        result = app_mod._load_trace()

    assert result is not None
    assert "entries" in result
    assert len(result["entries"]) == 2
    assert result["entries"][0]["node"] == "plan"


def test_load_trace_missing_file(tmp_path: Path, monkeypatch) -> None:
    """_load_trace() returns None when trace file does not exist."""
    import app.streamlit_app as app_mod

    monkeypatch.setattr(app_mod, "_TRACE_PATH", tmp_path / "no_trace.json")
    assert app_mod._load_trace() is None
