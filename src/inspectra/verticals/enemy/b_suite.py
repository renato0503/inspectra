"""Wrappers para o B-suite do EnemyDisclosure."""
import subprocess
import sys
from pathlib import Path

from inspectra.tools.path_safety import safe_path


def listar_orgaos(raiz: str) -> list:
    """Lista slugs de orgaos disponiveis."""
    p = Path(raiz) / "orgaos"
    if not p.exists():
        return []
    out = []
    for muni in p.iterdir():
        if muni.is_dir():
            for slug in muni.iterdir():
                if slug.is_dir():
                    out.append(slug.name)
    return sorted(set(out))


def rodar_analise_b(nome: str, orgao: str, ano: int, model: str = "gemma4-26b",
                    raiz: str = r"D:\Dev\EnemyDisclosure") -> int:
    """Roda analise B-suite via subprocess (chama core.analises.rodar)."""
    # Validacoes
    import re
    if not re.match(r"^[a-z0-9_]+$", orgao):
        raise ValueError(f"orgao invalido: {orgao}")
    if not (2000 <= ano <= 2030):
        raise ValueError(f"ano invalido: {ano}")
    cmd = [sys.executable, "-m", "core.analises.rodar", orgao, str(ano), "--so", nome]
    proc = subprocess.run(cmd, cwd=raiz, capture_output=True, text=True, timeout=600)
    return proc.returncode