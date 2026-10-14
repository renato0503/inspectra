"""
Executa SQL em qualquer banco SQLite (nao so macro_mt).

Uso:
    python -m inspectra.shortcuts.cli sql_qualquer data/meu.db "SELECT * FROM vendas LIMIT 5"
    python -m inspectra.shortcuts.cli sql_qualquer data/meu.db "SELECT municipio, SUM(valor) FROM despesas GROUP BY municipio"
    python -m inspectra.shortcuts.cli sql_qualquer data/meu.db --json
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
import sys
import os
import time
from pathlib import Path
from typing import Optional, List

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(RAIZ / "src"))

from inspectra.shortcuts._output import output


MAX_ROWS = 1000


def _sanitizar_query(query: str) -> bool:
    """Verifica se query e apenas SELECT (nao permite DML/DDL)."""
    query_upper = query.strip().upper()
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "EXEC", "GRANT", "REVOKE"]
    for kw in forbidden:
        if re.search(rf"\b{kw}\b", query_upper):
            return False
    return True


def _schema_db(db_path: str) -> List[dict]:
    """Retorna schema do banco (tabelas + colunas)."""
    try:
        cx = sqlite3.connect(db_path)
        cur = cx.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tabelas = []
        for row in cur.fetchall():
            nome, sql_create = row
            cols = cx.execute(f"PRAGMA table_info({nome})").fetchall()
            tabelas.append({
                "tabela": nome,
                "sql": sql_create,
                "colunas": [c[1] for c in cols],
                "n_linhas": cx.execute(f"SELECT COUNT(*) FROM {nome}").fetchone()[0],
            })
        cx.close()
        return tabelas
    except Exception as e:
        return []


def executar_sql(db_path: str, query: str, limite: int = MAX_ROWS) -> dict:
    """Executa SQL em SQLite. Retorna JSON estruturado."""
    inicio = time.time()

    db_full = RAIZ / db_path if not Path(db_path).is_absolute() else Path(db_path)

    if not db_full.exists():
        return output(False, None, "SQLite", erro=f"Banco nao encontrado: {db_path}")

    if not query.strip():
        return output(False, None, "SQLite", erro="Query vazia.")

    if not _sanitizar_query(query):
        return output(False, None, "SQLite",
                      erro="Apenas SELECT e permitido. UPDATE/INSERT/DELETE bloqueados por seguranca.")

    if limite:
        if not re.search(r"\bLIMIT\b", query.strip(), re.IGNORECASE):
            query = query.strip().rstrip(";") + f" LIMIT {limite}"

    try:
        cx = sqlite3.connect(str(db_full))
        cx.row_factory = sqlite3.Row
        cur = cx.execute(query)
        colunas = [d[0] for d in cur.description] if cur.description else []
        rows_raw = cur.fetchall()
        rows = [dict(r) for r in rows_raw]
        truncado = len(rows_raw) >= limite
        cx.close()
    except Exception as e:
        return output(False, None, "SQLite", erro=f"Erro SQL: {e}")

    dados = {
        "db": str(db_full),
        "query": query,
        "colunas": colunas,
        "rows": rows,
        "total": len(rows),
        "truncado": truncado,
        "limite": limite,
    }

    hint = f"{len(rows)} linha(s). Colunas: {', '.join(colunas[:10])}" \
           f"{' (...truncado)' if truncado else ''}."

    tempo = round((time.time() - inicio) * 1000)
    resultado = output(True, dados, f"SQLite ({db_full.name})", prompt_hint=hint)
    resultado["meta"]["tempo_ms"] = tempo
    return resultado


def _tabela_schema(db_path: str, tabela: str) -> dict:
    """Retorna schema de uma tabela especifica."""
    try:
        cx = sqlite3.connect(str(db_path))
        cols = cx.execute(f"PRAGMA table_info({tabela})").fetchall()
        n = cx.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        cx.close()
        return {"tabela": tabela, "colunas": [c[1] for c in cols], "n_linhas": n}
    except Exception as e:
        return {"tabela": tabela, "erro": str(e)}


def main():
    p = argparse.ArgumentParser(prog="sql_qualquer")
    p.add_argument("db", help="Caminho do banco SQLite")
    p.add_argument("query", nargs="?", help="Query SQL (apenas SELECT)")
    p.add_argument("--schema", action="store_true", help="Mostra schema do banco")
    p.add_argument("--tabela", dest="tabela", help="Schema de uma tabela especifica")
    p.add_argument("--limite", type=int, default=MAX_ROWS)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    db_path = str(RAIZ / args.db) if not Path(args.db).is_absolute() else args.db

    if args.schema:
        tabelas = _schema_db(db_path)
        resultado = output(True, {"db": db_path, "tabelas": tabelas}, "SQLite", prompt_hint="Schema do banco.")
        print_json(resultado)
        return 0

    if args.tabela:
        t = _tabela_schema(db_path, args.tabela)
        resultado = output(True, t, "SQLite")
        print_json(resultado)
        return 0

    if not args.query:
        p.print_help()
        return 1

    resultado = executar_sql(args.db, args.query, args.limite)

    if args.json:
        print_json(resultado)
    else:
        dados = resultado["dados"]
        print(f"\n=== SQL: {dados['db']} ===")
        print(f"Query: {dados['query']}")
        print(f"Colunas: {', '.join(dados['colunas'])}")
        print(f"Rows: {dados['total']}{' (TRUNCADO)' if dados.get('truncado') else ''}")
        print(f"Tempo: {resultado['meta']['tempo_ms']:.0f}ms")
        if dados["rows"]:
            print(f"\nPrimeiras linhas:")
            for row in dados["rows"][:5]:
                print(f"  {dict(row)}")

    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
