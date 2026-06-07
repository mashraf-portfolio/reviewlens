"""Regenerate docs/opener.md and docs/diagnosis.json from data/results/last_run.json.

Use this to iterate on the diagnosis/render layer without re-running the full pipeline.
Re-applies the current filtering and intervention logic from diagnosis.py to the saved
pipeline state — no LLM calls, no fetching, no spend.

Usage
-----
    cd src && python regenerate_outputs.py
    cd src && python -m regenerate_outputs

Reads:  data/results/last_run.json
Writes: docs/opener.md
        docs/diagnosis.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_DOCS_DIR = _ROOT / "docs"
_LAST_RUN = _ROOT / "data" / "results" / "last_run.json"


def main() -> None:
    from diagnosis import rediagnose, render_opener

    if not _LAST_RUN.exists():
        print(f"ERROR: {_LAST_RUN} not found — run the pipeline first.", file=sys.stderr)
        sys.exit(1)

    from config import get_settings

    saved = json.loads(_LAST_RUN.read_text(encoding="utf-8"))
    cfg = get_settings()
    diagnosis = rediagnose(saved, min_n_floor=cfg.min_n_floor)
    opener = render_opener(diagnosis)

    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (_DOCS_DIR / "diagnosis.json").write_text(
        json.dumps(diagnosis, indent=2, default=str), encoding="utf-8"
    )
    (_DOCS_DIR / "opener.md").write_text(opener, encoding="utf-8")

    print(f"Regenerated from: {_LAST_RUN}")
    print("  docs/diagnosis.json  written")
    print("  docs/opener.md       written")
    print()
    sys.stdout.buffer.write(opener.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
