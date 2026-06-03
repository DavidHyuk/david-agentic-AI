# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Pytest fixtures + sys.path wiring so tests can import the standalone scripts
and bootstrap modules the same way Hermes would (flat, no package)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for sub in ("scripts", "bootstrap"):
    p = str(REPO_ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
