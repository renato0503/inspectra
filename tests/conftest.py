"""Fixtures pytest para tests/test_shortcuts.py."""
import os
import sys
from pathlib import Path

# Configura INSPECTA_RAIZ para tests
RAIZ_TEST = Path(__file__).resolve().parents[1]
os.environ["INSPECTA_RAIZ"] = str(RAIZ_TEST)
sys.path.insert(0, str(RAIZ_TEST / "src"))
