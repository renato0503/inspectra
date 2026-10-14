"""Wrappers para investigacao de fornecedores via coding agent."""
import sys
from pathlib import Path

from inspectra.tools.path_safety import safe_path


def investigar_fornecedor(termo: str, model: str = "gemma4:latest",
                          raiz: str = r"D:\Dev\EnemyDisclosure") -> str:
    """Investiga um fornecedor (nome ou CNPJ) em todos os municipios."""
    from inspectra.agents.coding import CodingAgent
    from inspectra.shortcuts.investigar import TAREFA_TEMPLATE

    agent = CodingAgent(model=model, max_steps=8, temperatura=0.2, raiz=Path(raiz))
    tarefa = TAREFA_TEMPLATE.format(termo=termo)
    return agent.run(tarefa, verbose=False)