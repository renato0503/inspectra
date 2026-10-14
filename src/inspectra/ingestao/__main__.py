# complexo/__main__.py
"""Permite `python -m complexo <comando>`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
