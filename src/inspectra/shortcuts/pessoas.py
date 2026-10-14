"""
Investiga pessoas (politicos, socios, doadores) cruzando TSE + QSA.

TSE = prestacao de contas 2024 (parquet em shared_data/tse/).
QSA = quadro societario via BrasilAPI (cache em shared_data/brasilapi_cnpj.json).

Para um CPF ou nome fornecido:
1. Busca em TSE: doador, candidato, eleito
2. Busca em QSA: socio de qual empresa
3. Cruza: socio X = doador de Y = candidato a Z
"""
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from inspectra.llm.client import embed

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))
SHARED = RAIZ / "shared_data"


def _norm_cpf(cpf: str) -> str:
    return re.sub(r"\D", "", cpf)


def _carregar_tse() -> Optional[List[Dict]]:
    """Carrega parquets/jsonl do TSE em shared_data/tse/. Combina todos."""
    tse_dir = SHARED / "tse"
    if not tse_dir.exists():
        return None
    resultado: List[Dict] = []
    for arq in tse_dir.glob("*.parquet"):
        try:
            import pyarrow.parquet as pq
            tbl = pq.read_table(arq)
            for row in tbl.to_pylist():
                if isinstance(row, dict):
                    resultado.append(row)
        except Exception:
            continue
    for arq in tse_dir.glob("*.jsonl"):
        try:
            with arq.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        r = json.loads(line)
                        if isinstance(r, dict):
                            resultado.append(r)
        except Exception:
            continue
    return resultado or None


def _carregar_qsa() -> Dict[str, List[Dict]]:
    """Carrega QSA do BrasilAPI/Minha Receita. Indexa por cpf do socio."""
    idx: Dict[str, List[Dict]] = {}
    cache = SHARED / "brasilapi_cnpj.json"
    if not cache.exists():
        return idx
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        return idx
    for cnpj, info in data.items():
        qsa = info.get("qsa") or []
        for socio in qsa:
            cpf = _norm_cpf(socio.get("cpf", ""))
            if not cpf:
                continue
            idx.setdefault(cpf, []).append({
                "cnpj": cnpj,
                "razao_social": info.get("razao_social", ""),
                "socio_nome": socio.get("nome", ""),
                "qualificacao": socio.get("qualificacao", ""),
                "data_entrada": socio.get("data_entrada", ""),
            })
    return idx


def cmd_pessoas(args) -> int:
    cpf = _norm_cpf(args.cpf) if args.cpf else ""
    nome = args.nome.lower() if args.nome else None
    print(f"=== Investigacao de pessoa ===")
    if cpf:
        print(f"CPF: {cpf}")
    if nome:
        print(f"Nome (parcial): {nome}")
    print()

    tse = _carregar_tse()
    qsa = _carregar_qsa()

    achados: Dict[str, List] = {"tse": [], "qsa": [], "cruzamentos": []}

    if tse:
        for row in tse:
            if not isinstance(row, dict):
                continue
            row_cpf = _norm_cpf(str(row.get("NR_CPF_CANDIDATO") or row.get("cpf") or ""))
            row_cnpj = _norm_cpf(str(row.get("NR_CNPJ") or row.get("cnpj") or ""))
            row_nome = (
                str(row.get("NM_CANDIDATO") or row.get("NM_DOADOR") or
                    row.get("nome") or "")
            ).lower()
            match_cpf = cpf and row_cpf == cpf
            match_cnpj = cpf and len(cpf) == 14 and row_cnpj == cpf
            match_nome = nome and (nome in row_nome)
            if match_cpf or match_cnpj or match_nome:
                achados["tse"].append(row)
    else:
        print("[!] Base TSE nao encontrada em shared_data/tse/")

    if cpf and cpf in qsa:
        achados["qsa"] = qsa[cpf]
    if nome:
        for cpf_qsa, socios in qsa.items():
            for socio in socios:
                if nome in socio["socio_nome"].lower():
                    achados["qsa"].append({**socio, "cpf": cpf_qsa})

    # Cruzamento: socio de X que doou para Y
    for socio in achados["qsa"]:
        socio_cnpj = socio.get("cnpj")
        for tse_row in achados["tse"]:
            tse_cnpj = _norm_cpf(str(tse_row.get("cnpj", "")))
            if socio_cnpj and tse_cnpj and socio_cnpj == tse_cnpj:
                achados["cruzamentos"].append({
                    "socio": socio,
                    "tse": tse_row,
                })

    print(f"--- TSE (prestacao contas 2024) ---")
    if achados["tse"]:
        for r in achados["tse"][:20]:
            nome_r = r.get('NM_CANDIDATO') or r.get('NM_DOADOR') or r.get('nome', '?')
            cpf_raw = r.get('NR_CPF_CANDIDATO') or r.get('cpf', '')
            cpf_r = '(anonimizado)' if cpf_raw == '-4' else (cpf_raw or 'N/D')
            cargo = r.get('DS_CARGO') or r.get('cargo', '?')
            valor = r.get('VR_RECEITA') or r.get('VR_DESPESA') or r.get('valor', '?')
            print(f"  {nome_r} | CPF: {cpf_r} | cargo: {cargo} | valor: R$ {valor}")
    else:
        print("  (nenhum match)")

    print(f"\n--- QSA (socios de contratadas) ---")
    if achados["qsa"]:
        for s in achados["qsa"][:20]:
            print(f"  {s.get('socio_nome','?')} socio de {s.get('razao_social','?')} (CNPJ {s.get('cnpj','?')}) desde {s.get('data_entrada','?')}")
    else:
        print("  (nenhum match)")

    print(f"\n--- CRUZAMENTOS ---")
    if achados["cruzamentos"]:
        for c in achados["cruzamentos"]:
            socio = c["socio"]
            tse = c["tse"]
            print(f"  !! {socio['socio_nome']} e socio de {socio['razao_social']} E doou/candidateou-se ({tse.get('cargo','?')})")
    else:
        print("  (nenhum cruzamento socio-doador)")

    print(f"\nBases: TSE (shared_data/tse/) + BrasilAPI (shared_data/brasilapi_cnpj.json)")
    print(f"Para atualizar: python -m core.fontes.tse  &&  python -m core.fontes.brasilapi")
    return 0