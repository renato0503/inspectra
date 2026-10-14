"""
Helper de saida JSON estruturada para LLMs consumirem.

Todo atalho do Inspectra retorna este formato:

    {
        "ok": bool,              # True = sucesso, False = erro
        "dados": Any,            # payload principal (dict, list, str)
        "fonte": str,           # fonte de dados usada
        "erro": str | None,     # mensagem de erro (se ok=False)
        "timestamp": str,        # ISO timestamp
        "prompt_hint": str,     # dica de como usar este resultado
        "meta": {
            "tempo_ms": float,  # tempo de execucao
            "modelo": str | None,  # modelo LLM usado (se aplicavel)
        }
    }
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional


def output(
    ok: bool,
    dados: Any,
    fonte: str,
    erro: Optional[str] = None,
    prompt_hint: Optional[str] = None,
    modelo: Optional[str] = None,
) -> dict:
    """Constrói resposta JSON padronizada."""
    if ok and dados is None:
        ok = False
        erro = erro or "Nenhum dado retornado"

    base = {
        "ok": ok,
        "dados": dados,
        "fonte": fonte,
        "erro": erro,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_hint": prompt_hint or _gerar_hint(dados),
        "meta": {
            "modelo": modelo,
        },
    }
    return base


def _gerar_hint(dados: Any) -> str:
    """Gera hint generico baseado no tipo de dados."""
    if dados is None:
        return "Sem dados. Verifique o erro."
    if isinstance(dados, dict):
        chaves = list(dados.keys())[:5]
        return f"Campos disponiveis: {', '.join(chaves)}"
    if isinstance(dados, list):
        if dados:
            primeiro = dados[0]
            if isinstance(primeiro, dict):
                chaves = list(primeiro.keys())[:5]
                return f"Lista de {len(dados)} itens. Primeiro item tem: {', '.join(chaves)}"
            return f"Lista de {len(dados)} itens."
        return "Lista vazia."
    return f"Tipo: {type(dados).__name__}"


def print_json(resultado: dict,pretty: bool = True) -> None:
    """Imprime resultado em JSON (para CLI)."""
    kwargs = {"indent": 2, "ensure_ascii": False} if pretty else {}
    print(json.dumps(resultado, **kwargs))
