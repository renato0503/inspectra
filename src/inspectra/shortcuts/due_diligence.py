"""
Due diligence completa de empresa ou pessoa (CNPJ/CPF).

Coleta: QSA, situacao cadastral, sancoes, divida ativa, trabalho escravo,
PNCP, macro_mt, geocode, TSE (se pessoa).

Tudo local (sem API keys). Se Ollama estiver rodando, usa LLM para
resumir e classificar.

Uso:
    python -m inspectra.shortcuts.due_diligence cnpj 07192414000109
    python -m inspectra.shortcuts.due_diligence cnpj 07192414000109 --model gemma4:latest --json
    python -m inspectra.shortcuts.due_diligence --demo  (exemplo completo)
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import os
RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))

sys.path.insert(0, str(RAIZ / "src"))

try:
    from inspectra.llm.client import chat
    TEM_OLLAMA = True
except Exception:
    TEM_OLLAMA = False

try:
    from inspectra.shortcuts.sancoes import _buscar_em_csv
    from inspectra.shortcuts.dossie import _enriquecer_brasilapi
    TEM_SANCOES = True
except Exception:
    TEM_SANCOES = False


def _situacao_cadastral(cnpj: str) -> dict:
    """Verifica situacao cadastral na Receita Federal via BrasilAPI (com cache)."""
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    if len(cnpj_limpo) != 14:
        return {"erro": "CNPJ deve ter 14 digitos"}
    # Tenta cache local primeiro
    cache = RAIZ / "shared_data" / "brasilapi_cnpj.json"
    if cache.exists():
        try:
            db = json.loads(cache.read_text())
            if cnpj_limpo in db:
                d = db[cnpj_limpo]
                return {
                    "razao_social": d.get("razao_social"),
                    "nome_fantasia": d.get("nome_fantasia"),
                    "situacao": d.get("situacao") or d.get("situacao_cadastral"),
                    "data_abertura": d.get("data_inicio_atividade") or d.get("data_abertura"),
                    "capital": d.get("capital_social"),
                    "cnae": d.get("cnae") or d.get("cnae_fiscal"),
                    "endereco": (d.get("logradouro", "") + ", " + d.get("numero", "")).strip(),
                    "bairro": d.get("bairro"),
                    "municipio": d.get("municipio"),
                    "uf": d.get("uf"),
                    "qsa": d.get("qsa", []),
                }
        except Exception:
            pass
    # Fallback: API online
    try:
        import urllib.request
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
        with urllib.request.urlopen(url, timeout=12) as r:
            data = json.loads(r.read())
            return {
                "razao_social": data.get("razao_social"),
                "nome_fantasia": data.get("nome_fantasia"),
                "situacao": data.get("situacao_cadastral"),
                "data_abertura": data.get("data_inicio_atividade"),
                "capital": data.get("capital_social"),
                "cnae": data.get("cnae_fiscal"),
                "endereco": (data.get("logradouro", "") + ", " + data.get("numero", "")).strip(),
                "bairro": data.get("bairro"),
                "municipio": data.get("municipio"),
                "uf": data.get("uf"),
                "qsa": data.get("qsa", []),
            }
    except Exception as e:
        return {"erro": str(e)}


def _macro_mt(cnpj: str, limite: int = 20) -> dict:
    """Busca no macro_mt.db por CNPJ raiz."""
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    raiz8 = cnpj_limpo[:8]
    db = RAIZ / "shared_data" / "macro_mt" / "macro_mt.db"
    if not db.exists():
        return {"erro": "macro_mt.db nao encontrado"}
    try:
        cx = sqlite3.connect(str(db))
        cur = cx.execute(
            "SELECT municipio, ano, COUNT(*) as n_emps, SUM(valor) as total "
            "FROM despesas "
            "WHERE cnpj_cpf LIKE ? AND valor > 0 "
            "GROUP BY municipio, ano ORDER BY total DESC LIMIT ?",
            (f"{raiz8}%", limite)
        )
        rows = cur.fetchall()
        total_geral = sum(r[3] or 0 for r in rows)
        return {
            "cnpj_raiz": raiz8,
            "municipios": [{"municipio": r[0], "ano": r[1], "n": r[2], "total": r[3]} for r in rows],
            "total_geral": total_geral,
        }
    except Exception as e:
        return {"erro": str(e)}


def _pncp_contratacoes(cnpj: str) -> dict:
    """Busca contratacoes no PNCP para o CNPJ (via hub local)."""
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    db_pncp = RAIZ / "D:/Dev/PNCP/data/pncp.duckdb"
    if not db_pncp.exists():
        return {"erro": "PNCP DuckDB nao encontrado (rode coleta_total.py)"}
    try:
        import duckdb
        con = duckdb.connect(str(db_pncp), read_only=True)
        rows = con.execute(
            "SELECT ORGAO, MODALIDADE, DATAPUBL, VALORCONTRATO, OBJETO "
            "FROM v_contratacoes WHERE RAIZCNPJ = ? ORDER BY DATAPUBL DESC LIMIT 10",
            (cnpj_limpo[:8],)
        ).fetchall()
        con.close()
        return {"contratacoes": [
            {"orgao": r[0], "modalidade": r[1], "data": r[2], "valor": r[3], "objeto": r[4]}
            for r in rows
        ]}
    except Exception:
        return {"erro": "PNCP DuckDB inacessivel"}


def _divida_ativa(pgfn_csv_dir: Path, cnpj_raiz: str) -> dict:
    """Verifica Divida Ativa da Uniao (PGFN) para o CNPJ raiz."""
    if not pgfn_csv_dir.exists():
        return {}
    import csv
    resultados = []
    for csv_file in pgfn_csv_dir.glob("*.csv"):
        try:
            with open(csv_file, encoding="latin-1", errors="replace") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    if cnpj_raiz[:8] in str(row.get("cpf_cnpj", "")):
                        resultados.append({
                            "tipo": csv_file.stem,
                            "valor": row.get("valor", "?"),
                            "data": row.get("data_inscricao", "?"),
                            "situacao": row.get("situacao", "?"),
                        })
                        if len(resultados) >= 5:
                            break
        except Exception:
            pass
        if len(resultados) >= 5:
            break
    return {"divida_ativa": resultados[:5]}


def _lista_suja(cnpj: str) -> dict:
    """Verifica Lista Suja do Trabalho Escravo (MTE)."""
    lista_suja = RAIZ / "shared_data" / "lista_suja.txt"
    if not lista_suja.exists():
        return {}
    try:
        texto = lista_suja.read_text(encoding="utf-8", errors="replace")
        cnpj_limpo = re.sub(r"\D", "", cnpj)
        if cnpj_limpo in texto:
            return {"trabalho_escravo": True, "fonte": "MTE Lista Suja"}
        return {"trabalho_escravo": False}
    except Exception:
        return {}


def _classificar_risco(dados: dict, modelo: str) -> dict:
    """Classifica risco via LLM."""
    if not TEM_OLLAMA:
        return {"risco": "LLM indisponivel"}
    try:
        prompt = (
            "Classifique o risco de negocio com esta empresa. "
            "Responda em JSON com campos: risco (alto/medio/baixo), "
            "fatores (lista de strings), recomendacao (string).\n\n"
            + json.dumps(dados, ensure_ascii=False, indent=2)[:4000]
        )
        resultado = chat([{"role": "user", "content": prompt}],
                         model=modelo, temperatura=0.1, json_output=True)
        if isinstance(resultado, dict):
            return resultado.get("content", str(resultado))
        return str(resultado)
    except Exception as e:
        return {"erro": str(e)}


def investigar(cnpj: str, modelo: str = "gemma4:latest") -> dict:
    """Due diligence completa de CNPJ."""
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    resultado = {
        "alvo": cnpj,
        "cnpj_limpo": cnpj_limpo,
        "data": str(date.today()),
    }
    # Camadas
    resultado["cadastro"] = _situacao_cadastral(cnpj)
    resultado["sancoes"] = _buscar_em_csv(cnpj_limpo[:8]) if TEM_SANCOES else []
    resultado["macro_mt"] = _macro_mt(cnpj)
    resultado["pncp"] = _pncp_contratacoes(cnpj)
    pgfn_dir = RAIZ / "shared_data" / "pgfn"
    resultado["divida_ativa"] = _divida_ativa(pgfn_dir, cnpj_limpo) if pgfn_dir.exists() else {}
    resultado["lista_suja"] = _lista_suja(cnpj)
    # LLM
    resultado["classificacao"] = _classificar_risco(resultado, modelo)
    return resultado


DEMO_CNPJ = "07192414000109"  # Costa Oeste


def main():
    p = argparse.ArgumentParser(prog="due_diligence")
    p.add_argument("tipo", nargs="?", help="Tipo: cnpj (default)")
    p.add_argument("valor", nargs="?", help="CNPJ ou CPF")
    p.add_argument("--model", default="gemma4:latest")
    p.add_argument("--json", action="store_true")
    p.add_argument("--demo", action="store_true", help=f"Exemplo com CNPJ demo: {DEMO_CNPJ}")
    args = p.parse_args()

    if args.demo:
        cnpj = DEMO_CNPJ
    elif args.tipo == "cnpj" and args.valor:
        cnpj = args.valor
    else:
        p.print_help()
        return 1

    resultado = investigar(cnpj, modelo=args.model)
    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        # Resumo humanizado
        cad = resultado.get("cadastro", {})
        risco = resultado.get("classificacao", {})
        print(f"\n=== DUE DILIGENCE: {cad.get('razao_social', cnpj)} ===")
        print(f"Situacao: {cad.get('situacao', '?')}")
        print(f"Capital: R$ {cad.get('capital_social', cad.get('capital', '?'))}")
        print(f"CNAE: {cad.get('cnae', '?')}")
        sancoes = resultado.get("sancoes", [])
        print(f"\nSancoes: {len(sancoes)} encontrado(s)")
        for s in sancoes[:3]:
            print(f"  - {s.get('tipo', '?')}: {s.get('trecho', str(s))[:120]}")
        mt = resultado.get("macro_mt", {})
        print(f"\nGastos MT: R$ {mt.get('total_geral', 0):,.0f}")
        for m in mt.get("municipios", [])[:5]:
            print(f"  - {m['municipio']}: R$ {m['total']:,.0f} ({m['n']} empenhos)")
        if isinstance(risco, dict) and "risco" in risco:
            print(f"\nRisco: {risco.get('risco', '?')}")
            for f in risco.get("fatores", []):
                print(f"  - {f}")
        elif isinstance(risco, str) and risco:
            print(f"\nRisco: {risco[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
