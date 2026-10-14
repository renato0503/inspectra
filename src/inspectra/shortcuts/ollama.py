"""
Wrapper direto no Ollama —chat, embed, listar modelos.

Projetado para LLMs agents chamarem: saida é sempre JSON estruturado.

Uso:
    python -m inspectra.shortcuts.ollama chat "Qual a situacao fiscal do Brasil?"
    python -m inspectra.shortcuts.ollama embed "texto para embedar"
    python -m inspectra.shortcuts.ollama models
    python -m inspectra.shortcuts.ollama chat --model gemma4-26b --system "Voce e um auditor." --json "Analise: ..."
"""
from __future__ import annotations
import argparse
import json
import sys
import os
from pathlib import Path

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(RAIZ / "src"))
from inspectra.llm.client import chat, embed, listar_modelos


def cmd_chat(args) -> int:
    """Chat simples com Ollama."""
    model = args.model
    system = args.system or ""
    if system:
        result = chat(model, args.mensagem, system=system,
                      temperatura=args.temperatura, num_ctx=args.ctx)
    else:
        result = chat(model, args.mensagem,
                      temperatura=args.temperatura, num_ctx=args.ctx)

    if isinstance(result, dict):
        print(result.get("content", str(result)))
    else:
        print(result)
    return 0


def cmd_embed(args) -> int:
    """Gera embedding de um texto."""
    model = args.embed_model or "gemma4:latest"
    vec = embed(args.texto, model=model)
    if args.raw:
        print(vec)
    else:
        # Norma L2 para exibicao
        norm = sum(x * x for x in vec) ** 0.5
        print(json.dumps({
            "model": model,
            "dim": len(vec),
            "norm": round(norm, 4),
            "vector": [round(x, 6) for x in vec[:10]] + ("..." if len(vec) > 10 else [])
        }, indent=2))
    return 0


def cmd_models(args) -> int:
    """Lista modelos disponiveis no Ollama."""
    modelos = listar_modelos()
    if isinstance(modelos, list):
        for m in modelos:
            print(f"  {m}")
    else:
        print(modelos)
    return 0


def cmd_complete(args) -> int:
    """Completion (sem history, para agentes)."""
    result = chat(
        args.model,
        args.prompt,
        temperatura=args.temperatura,
        num_ctx=args.ctx,
    )
    if isinstance(result, dict):
        print(result.get("content", str(result)))
    else:
        print(result)
    return 0


def main():
    p = argparse.ArgumentParser(prog="ollama")
    sub = p.add_subparsers(dest="cmd", required=True)

    # chat
    sp = sub.add_parser("chat", help="Conversa com o modelo")
    sp.add_argument("mensagem", help="Mensagem do usuario")
    sp.add_argument("--model", default="gemma4:latest")
    sp.add_argument("--system", default=None)
    sp.add_argument("--temperatura", type=float, default=0.3)
    sp.add_argument("--ctx", type=int, default=8192)

    # embed
    sp = sub.add_parser("embed", help="Gera embedding de um texto")
    sp.add_argument("texto", help="Texto para embedar")
    sp.add_argument("--embed-model", default=None)
    sp.add_argument("--raw", action="store_true", help="Imprime vetor completo")

    # models
    sub.add_parser("models", help="Lista modelos disponiveis")

    # complete
    sp = sub.add_parser("complete", help="Completion unico (sem history)")
    sp.add_argument("prompt", help="Prompt unico")
    sp.add_argument("--model", default="gemma4:latest")
    sp.add_argument("--temperatura", type=float, default=0.3)
    sp.add_argument("--ctx", type=int, default=8192)

    args = p.parse_args()
    if args.cmd == "chat":
        return cmd_chat(args)
    elif args.cmd == "embed":
        return cmd_embed(args)
    elif args.cmd == "models":
        return cmd_models(args)
    elif args.cmd == "complete":
        return cmd_complete(args)


if __name__ == "__main__":
    sys.exit(main())
