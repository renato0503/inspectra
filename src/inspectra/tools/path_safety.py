"""Helpers de seguranca de caminhos para tools."""
from pathlib import Path
from typing import Optional


def safe_path(rel: str, raiz: Path) -> Optional[Path]:
    """Resolve rel dentro de raiz. Retorna None se escapar."""
    if not rel:
        return None
    try:
        p = (raiz / rel).resolve()
        if not str(p).startswith(str(raiz.resolve())):
            return None
        return p
    except Exception:
        return None