"""Busca semantica (sem LLM) em todos os dossies/analises via embeddings."""
import math
from pathlib import Path
from typing import List, Dict

from inspectra.llm.client import embed

RAIZ = Path(__file__).resolve().parents[3]


def _cos(a: List[float], b: List[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(x * x for x in b))
    return num / (da * db) if da and db else 0.0


def _coletar_chunks(top_arquivos: int = 30, janela: int = 800, passo: int = 400) -> List[Dict]:
    chunks = []
    for path in RAIZ.glob("orgaos/*/*/data/export/*.json"):
        try:
            txt = path.read_text(encoding="utf-8", errors="replace")
            if 200 < len(txt) < 80000:
                chunks.append({"path": path, "txt": txt, "kind": "json"})
        except Exception:
            pass
    for path in RAIZ.glob("orgaos/*/*/data/export/*.md"):
        try:
            txt = path.read_text(encoding="utf-8", errors="replace")
            if 200 < len(txt) < 80000:
                chunks.append({"path": path, "txt": txt, "kind": "md"})
        except Exception:
            pass
    chunks = chunks[:top_arquivos]

    resultado = []
    for c in chunks:
        txt = c["txt"]
        for i in range(0, len(txt), passo):
            trecho = txt[i:i + janela]
            if len(trecho.strip()) < 120:
                continue
            try:
                vec = embed(trecho[:500])
                resultado.append({
                    "path": str(c["path"].relative_to(RAIZ)),
                    "trecho": trecho,
                    "vec": vec,
                })
            except Exception:
                pass
    return resultado


def cmd_buscar(args) -> int:
    termo = args.termo
    top_k = max(1, min(args.top, 30))
    print(f"=== Busca semantica: '{termo}' (top {top_k}) ===\n")

    try:
        vec_query = embed(termo)
    except Exception as e:
        print(f"ERRO no embedding: {e}")
        return 1

    chunks = _coletar_chunks()
    if not chunks:
        print("(nenhum arquivo de analise encontrado)")
        return 0

    chunks.sort(key=lambda c: _cos(vec_query, c["vec"]), reverse=True)
    for i, c in enumerate(chunks[:top_k], 1):
        sim = _cos(vec_query, c["vec"])
        print(f"\n--- {i}. {c['path']} (sim={sim:.3f}) ---")
        print(c["trecho"][:600])
    print("\n" + "=" * 60)
    print(f"{len(chunks)} chunks indexados | top {top_k} mostrados")
    return 0