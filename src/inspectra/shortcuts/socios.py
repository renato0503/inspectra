"""
Lista socios de um CNPJ com qualificacao e data de entrada.

Uso:
    python -m inspectra.shortcuts.cli socios 07192414000109
    python -m inspectra.shortcuts.cli socios --cnpj 07192414000109 --json
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import os
import time
from pathlib import Path
from typing import Optional, List

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(RAIZ / "src"))

from inspectra.shortcuts._output import output


def _norm_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def _cpf_parcial(cpf: str) -> str:
    c = _norm_cnpj(cpf)
    if len(c) == 11:
        return f"***.***.***{c[-4:]}"
    return cpf


def _buscar_cache(cnpj: str) -> Optional[dict]:
    """Busca no cache brasilapi_cnpj.json."""
    cache = RAIZ / "shared_data" / "brasilapi_cnpj.json"
    if not cache.exists():
        return None
    try:
        db = json.loads(cache.read_text())
        cnpj_limpo = _norm_cnpj(cnpj)
        return db.get(cnpj_limpo)
    except Exception:
        return None


def _buscar_api(cnpj: str) -> Optional[dict]:
    """Fallback: BrasilAPI online."""
    cnpj_limpo = _norm_cnpj(cnpj)
    if len(cnpj_limpo) != 14:
        return None
    try:
        import urllib.request
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
        with urllib.request.urlopen(url, timeout=12) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _mascarar(cpf: str) -> str:
    """Mascara CPF: XXX.XXX.XXX-XX (mostra primeiro digito + ultimos 2)."""
    c = re.sub(r"\D", "", cpf)
    if len(c) != 11:
        return cpf
    return f"{c[0]}***.***.***{c[-2:]}"


def listar_socios(cnpj: str) -> dict:
    """Lista socios de um CNPJ. Retorna JSON estruturado."""
    inicio = time.time()

    cnpj_limpo = _norm_cnpj(cnpj)
    if len(cnpj_limpo) != 14:
        return output(False, None, "BrasilAPI", erro="CNPJ precisa de 14 digitos.")

    # Tenta cache primeiro
    dados = _buscar_cache(cnpj_limpo)
    fonte = "BrasilAPI (cache)"

    # Fallback online
    if not dados:
        dados = _buscar_api(cnpj_limpo)
        fonte = "BrasilAPI (online)"

    if not dados:
        return output(False, None, "BrasilAPI", erro="CNPJ nao encontrado.", prompt_hint="Verifique o CNPJ.")

    qsa = dados.get("qsa", [])
    socios = []
    for s in qsa:
        socios.append({
            "nome": s.get("nome", "?"),
            "cpf_parcial": _mascarar(s.get("cpf", "")),
            "qualificacao": s.get("qualificacao", "?"),
            "data_entrada": s.get("data_entrada", s.get("data_socio", "?")),
        })

    dados_saida = {
        "cnpj": cnpj_limpo,
        "razao_social": dados.get("razao_social"),
        "nome_fantasia": dados.get("nome_fantasia"),
        "situacao": dados.get("situacao"),
        "uf": dados.get("uf"),
        "municipio": dados.get("municipio"),
        "capital_social": dados.get("capital_social"),
        "socios": socios,
        "total_socios": len(socios),
    }

    hint = f"{len(socios)} socio(s) encontrado(s). " \
           f"Capital social: R$ {dados.get('capital_social', 0):,.0f}."

    tempo = round((time.time() - inicio) * 1000)
    resultado = output(True, dados_saida, fonte, prompt_hint=hint)
    resultado["meta"]["tempo_ms"] = tempo
    return resultado


def main():
    p = argparse.ArgumentParser(prog="socios")
    p.add_argument("cnpj", nargs="?", help="CNPJ (com ou sem pontuacao)")
    p.add_argument("--cnpj", dest="cnpj_opt", help="CNPJ via flag")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    cnpj = args.cnpj or args.cnpj_opt or "?"
    resultado = listar_socios(cnpj)

    if args.json:
        print_json(resultado)
    else:
        dados = resultado["dados"]
        print(f"\n=== {dados.get('razao_social', cnpj)} ===")
        print(f"CNPJ: {dados.get('cnpj')} | Situacao: {dados.get('situacao', '?')}")
        print(f"UF: {dados.get('uf')} | Municipio: {dados.get('municipio', '?')}")
        print(f"Capital: R$ {dados.get('capital_social', 0):,.0f}")
        print(f"\nSocios ({len(dados.get('socios', []))}):")
        for s in dados.get("socios", []):
            print(f"  - {s['nome']} ({s['cpf_parcial']}) | {s['qualificacao']} | entrada: {s['data_entrada']}")
        print(f"\n[INFO] {resultado['fonte']} | {resultado['meta']['tempo_ms']:.0f}ms")

    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
