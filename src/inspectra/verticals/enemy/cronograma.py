"""Cronograma mensal (analise temporal) de um orgao."""
from pathlib import Path

from inspectra.shortcuts.cronograma import cmd_cronograma
from types import SimpleNamespace


def cronograma_mensal(orgao: str = "todos", model: str = "gemma4:latest",
                       raiz: str = r"D:\Dev\EnemyDisclosure") -> str:
    """Gera tabela com empenhos mes a mes + picos atipicos."""
    args = SimpleNamespace(orgao=orgao, model=model, steps=6)
    rc = cmd_cronograma(args)
    return f"(rc={rc})"