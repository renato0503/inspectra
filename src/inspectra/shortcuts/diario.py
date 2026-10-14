"""
Busca em diarios oficiais (MT, SC, federal) por termo.

Fontes: AMM MT, TCE-SC, Querido Diario (federal).
Retorna JSON estruturado com matches, data, trecho e link.

Uso:
    python -m inspectra.shortcuts.cli diario "LICITACAO" --uf MT
    python -m inspectra.shortcuts.cli diario "CONTRATO" --uf SC --periodo 2024
    python -m inspectra.shortcuts.cli diario "FRANCISCO" --json
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(RAIZ / "src"))

from inspectra.shortcuts._output import output


def _buscar_amm(termo: str, uf: str = "MT", dias: int = 365) -> list:
    """Busca nos PDFs da AMM (Mato Grosso)."""
    if uf.upper() != "MT":
        return []
    dir_amm = RAIZ / "shared_data" / "amm_diario"
    if not dir_amm.exists():
        return []
    termo_lower = termo.lower()
    resultados = []
    cutoff = datetime.now() - timedelta(days=dias)
    for pdf_dir in dir_amm.iterdir():
        if not pdf_dir.is_dir():
            continue
        try:
            data_dir = datetime.strptime(pdf_dir.name, "%Y-%m-%d")
            if data_dir < cutoff:
                continue
        except ValueError:
            continue
        for pdf_file in pdf_dir.glob("*.txt"):
            try:
                texto = pdf_file.read_text(encoding="utf-8", errors="replace")
                if termo_lower in texto.lower():
                    linhas = texto.split("\n")
                    matches = [l.strip() for l in linhas if termo_lower in l.lower()]
                    snippet = matches[0][:300] if matches else texto[:300]
                    resultados.append({
                        "data": pdf_dir.name,
                        "diario": "AMM-MT",
                        "trecho": snippet,
                        "arquivo": str(pdf_file.name),
                        "uf": "MT",
                    })
                    if len(resultados) >= 20:
                        return resultados
            except Exception:
                continue
    return resultados


def _buscar_tce_sc(termo: str, uf: str = "SC", dias: int = 365) -> list:
    """Busca nos arquivos do TCE-SC."""
    if uf.upper() != "SC":
        return []
    dir_sc = RAIZ / "shared_data" / "tce_sc"
    if not dir_sc.exists():
        return []
    termo_lower = termo.lower()
    resultados = []
    cutoff = datetime.now() - timedelta(days=dias)
    for txt_file in dir_sc.rglob("*.txt"):
        try:
            mtime = datetime.fromtimestamp(txt_file.stat().st_mtime)
            if mtime < cutoff:
                continue
        except Exception:
            pass
        try:
            texto = txt_file.read_text(encoding="utf-8", errors="replace")
            if termo_lower in texto.lower():
                linhas = texto.split("\n")
                matches = [l.strip() for l in linhas if termo_lower in l.lower()]
                snippet = matches[0][:300] if matches else texto[:300]
                resultados.append({
                    "data": mtime.strftime("%Y-%m-%d"),
                    "diario": "TCE-SC",
                    "trecho": snippet,
                    "arquivo": str(txt_file.name),
                    "uf": "SC",
                })
                if len(resultados) >= 20:
                    return resultados
        except Exception:
            continue
    return resultados


def _buscar_querido(termo: str, uf: str = None, dias: int = 365) -> list:
    """Busca via Querido Diario (federal)."""
    try:
        import urllib.request
        import urllib.parse
        query = f"site:diariomunicipal.com.br {termo}"
        if uf:
            query += f" {uf}"
        params = urllib.parse.urlencode({"q": query, "limit": 10})
        url = f"https://queridodiario.ok.org.br/api/v0/search?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "Inspectra/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        resultados = []
        for item in data.get("results", []):
            resultados.append({
                "data": item.get("date_published", "?"),
                "diario": item.get("territory_name", "?"),
                "trecho": item.get("snippet", "")[:300],
                "link": item.get("url", ""),
                "uf": item.get("state", "?"),
            })
        return resultados[:20]
    except Exception:
        return []


def _buscar_macro_mt(termo: str) -> list:
    """Busca no macro_mt.db por nome de fornecedor."""
    try:
        import sqlite3
        db = RAIZ / "shared_data" / "macro_mt" / "macro_mt.db"
        if not db.exists():
            return []
        cx = sqlite3.connect(str(db))
        cur = cx.execute(
            "SELECT DISTINCT municipio, credor, SUM(valor) as total "
            "FROM despesas "
            "WHERE credor LIKE ? AND valor > 0 "
            "GROUP BY municipio, credor ORDER BY total DESC LIMIT 10",
            (f"%{termo}%",)
        )
        resultados = []
        for row in cur.fetchall():
            resultados.append({
                "data": "macro_mt.db",
                "diario": row[0],
                "trecho": f"{row[1]}: R$ {row[2]:,.0f}",
                "uf": "MT",
                "fonte": "macro_mt",
            })
        return resultados
    except Exception:
        return []


def buscar_diario(termo: str, uf: str = None, periodo_dias: int = 365) -> dict:
    """Busca em diarios oficiais. Retorna JSON estruturado."""
    inicio = time.time()
    resultados = []

    # AMM MT
    if not uf or uf.upper() in ("MT", "TODOS"):
        resultados.extend(_buscar_amm(termo, "MT", periodo_dias))

    # TCE SC
    if not uf or uf.upper() in ("SC", "TODOS"):
        resultados.extend(_buscar_tce_sc(termo, "SC", periodo_dias))

    # Querido Diario (federal)
    if not uf or uf.upper() != "SC":
        resultados.extend(_buscar_querido(termo, uf, periodo_dias))

    # Macro MT como fonte complementar
    if not uf or uf.upper() in ("MT", "TODOS"):
        resultados.extend(_buscar_macro_mt(termo))

    # Dedup por trecho
    seen = set()
    unicos = []
    for r in resultados:
        key = r.get("trecho", "")[:100]
        if key not in seen:
            seen.add(key)
            unicos.append(r)

    dados = {
        "termo": termo,
        "uf": uf or "TODOS",
        "matches": unicos,
        "total": len(unicos),
        "fontes": list(set(r.get("diario", "?") for r in unicos)),
    }

    hint = f"{len(unicos)} resultado(s) em {', '.join(dados['fontes'])[:50]}."
    tempo = round((time.time() - inicio) * 1000)
    resultado = output(True, dados, "AMM-MT + TCE-SC + Querido Diario + macro_mt", prompt_hint=hint)
    resultado["meta"]["tempo_ms"] = tempo
    return resultado


def main():
    p = argparse.ArgumentParser(prog="diario")
    p.add_argument("termo", nargs="?", help="Termo de busca")
    p.add_argument("--uf", default=None, help="UF (MT, SC, federal)")
    p.add_argument("--periodo", type=int, default=365, help="Dias para buscar (default 365)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if not args.termo:
        p.print_help()
        return 1

    resultado = buscar_diario(args.termo, args.uf, args.periodo)

    if args.json:
        print_json(resultado)
    else:
        dados = resultado["dados"]
        print(f"\n=== Busca: \"{dados['termo']}\" | UF: {dados['uf']} ===")
        print(f"Resultados: {dados['total']} | Fontes: {', '.join(dados['fontes'])}")
        for r in dados["matches"][:10]:
            print(f"\n[{r.get('data', '?')}] {r.get('diario', '?')} ({r.get('uf', '?')})")
            print(f"  {r.get('trecho', '')[:200]}")
            if r.get("link"):
                print(f"  Link: {r['link']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
