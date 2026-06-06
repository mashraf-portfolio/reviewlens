"""Add src/ and project root to sys.path so tests import project packages without install."""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))
# project root needed so `import app.streamlit_app` resolves
if str(_ROOT) not in sys.path:
    sys.path.insert(1, str(_ROOT))
