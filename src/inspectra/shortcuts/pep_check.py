"""
Verifica se uma pessoa e PEP (Pessoa Politicamente Exposta).

Fontes: TSE (candidatos/eleitos) + Portal da Transparencia (servidores).
Retorna JSON estruturado para LLM.

Uso:
    python -m inspectra.shortcuts.cli pep_check "JAIR BOLSONARO"
    python -m inspectra.shortcuts.cli pep_check --cpf 01234567890
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import os
import time
import urllib.parse
from pathlib import Path
from typing import Optional

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(RAIZ / "src"))

from inspectra.shortcuts._output import output


def _norm_cpf(cpf: str) -> str:
    return re.sub(r"\D", "", cpf)


def _cpf_parcial(cpf: str) -> str:
    """Mascara CPF: mostra ultimos 4 digitos."""
    c = _norm_cpf(cpf)
    if len(c) != 11:
        return cpf
    return f"***.***.***{c[-4:]}"


def _buscar_tse(nome: str) -> list:
    """Busca no TSE por nome de candidato/eleito."""
    import pandas as pd
    tse_dir = RAIZ / "shared_data" / "tse"
    if not tse_dir.exists():
        return []
    resultados = []
    for arq in tse_dir.glob("*.parquet"):
        try:
            df = pd.read_parquet(arq)
            df.columns = [c.upper() for c in df.columns]
            cols = [c for c in df.columns if "NM_CANDIDATO" in c or "NOME" in c.upper()]
            for col in cols:
                mask = df[col].astype(str).str.contains(nome.upper(), na=False)
                for _, row in df[mask].head(5).iterrows():
                    resultados.append({
                        "nome": row.get("NM_CANDIDATO", row.get("NOME", "?")),
                        "cpf_parcial": _cpf_parcial(str(row.get("NR_CPF_CANDIDATO", ""))),
                        "cargo": row.get("DS_CARGO", row.get("CARGO", "?")),
                        "partido": row.get("SG_PARTIDO", row.get("PARTIDO", "?")),
                        "uf": row.get("SG_UF", row.get("UF", "?")),
                        "situacao": row.get("DS_SITUACAO_CANDIDATO", row.get("SITUACAO", "?")),
                        "fonte": "TSE",
                    })
        except Exception:
            continue
    return resultados


def _buscar_portal_para_pessoas(termo: str) -> list:
    """Busca no Portal da Transparencia por servidores."""
    token_file = RAIZ / "shared_data" / "portal_transparencia_token.json"
    if not token_file.exists():
        return []
    try:
        import urllib.request
        token = json.loads(token_file.read_text()).get("access_token")
        if not token:
            return []
        url = f"https://portaldatransparencia.gov.br/api/v1/servidores/lotacoes?nome={urllib.parse.quote(termo)}&itensPorPagina=5"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            servicos = data.get("data", [])
            return [{
                "nome": s.get("pessoa", {}).get("nome", "?"),
                "orgao": s.get("orgao", {}).get("nome", "?"),
                "funcao": s.get("descricaoFuncao", "?"),
                "fonte": "Portal da Transparencia",
            } for s in servicos]
    except Exception:
        return []


def check_pep(termo: str, cpf: Optional[str] = None) -> dict:
    """Verifica se pessoa e PEP. Retorna JSON estruturado."""
    inicio = time.time()

    if cpf:
        cpf_fmt = _cpf_parcial(cpf)
        resultado_tse = _buscar_tse(cpf)  # busca por CPF
        resultado_portal = []
    else:
        resultado_tse = _buscar_tse(termo)
        resultado_portal = _buscar_portal_para_pessoas(termo)
        cpf_fmt = None

    todos = resultado_tse + resultado_portal
    if todos:
        dados = {
            "pep": True,
            "pessoa": termo,
            "cpf": cpf_fmt,
            "matches": todos,
            "total_matches": len(todos),
        }
        hint = f"PEP confirmado com {len(todos)} registro(s). Verifique cargo e orgao."
    else:
        dados = {
            "pep": False,
            "pessoa": termo,
            "cpf": cpf_fmt,
            "matches": [],
            "total_matches": 0,
        }
        hint = "Pessoa NAO encontrada como PEP em TSE ou Portal da Transparencia."

    tempo = round((time.time() - inicio) * 1000)
    resultado = output(True, dados, "TSE + Portal da Transparencia", prompt_hint=hint)
    resultado["meta"]["tempo_ms"] = tempo
    return resultado


def main():
    p = argparse.ArgumentParser(prog="pep_check")
    g = p.add_mutually_exclusive_group()
    g.add_argument("nome", nargs="?", help="Nome da pessoa")
    g.add_argument("--cpf", help="CPF (11 digitos)")
    g.add_argument("--json", dest="json_out", action="store_true", help="Saida JSON")
    args = p.parse_args()

    termo = args.nome or "?"

    resultado = check_pep(termo, cpf=args.cpf)

    if args.json_out:
        print_json(resultado)
    else:
        dados = resultado["dados"]
        if dados["pep"]:
            print(f"\n=== PEP ENCONTRADO: {dados['pessoa']} ===")
            print(f"CPF: {dados['cpf'] or '?'}")
            print(f"Registros: {dados['total_matches']}")
            for m in dados["matches"][:5]:
                print(f"  - {m.get('nome','?')} | {m.get('cargo','?')} | {m.get('orgao','?')} | {m.get('fonte','?')}")
        else:
            print(f"\n[PASSOU] {dados['pessoa']} — NAO e PEP conhecido.")
        print(f"\n[INFO] Tempo: {resultado['meta']['tempo_ms']:.0f}ms | Fonte: {resultado['fonte']}")

    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
