"""Add src/ to sys.path so tests import project packages without install."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
