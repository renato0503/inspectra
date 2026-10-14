"""Consulta direta (sem LLM) nas sancoes federais (CEIS/CNEP/CEPIM/Leniencia)."""
import json
import os
import re
import sqlite3
from pathlib import Path

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))
SHARED = RAIZ / "shared_data"


def _norm(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def _buscar_em_csv(cnpj_norm: str) -> list:
    """Busca CNPJ nos CSVs de sancoes (sem chave de API)."""
    resultados = []
    base = SHARED / "sancoes"
    if not base.exists():
        return resultados
    for arquivo in base.glob("*.csv"):
        tipo = arquivo.stem
        try:
            with arquivo.open("r", encoding="utf-8", errors="replace") as f:
                # Detecta delimitador
                primeira = f.readline()
                if not primeira:
                    continue
                delim = ";" if ";" in primeira else ","
                f.seek(0)
                for linha in f:
                    if cnpj_norm in linha:
                        resultados.append({"tipo": tipo, "trecho": linha.strip()[:300]})
        except Exception:
            continue
    return resultados


def cmd_sancoes(args) -> int:
    cnpj = _norm(args.cnpj)
    raiz = cnpj[:8] if len(cnpj) >= 8 else cnpj
    print(f"=== Sancoes Federais: CNPJ {args.cnpj} (raiz {raiz}) ===\n")

    encontrados = _buscar_em_csv(raiz)
    if not encontrados and len(cnpj) >= 14:
        encontrados = _buscar_em_csv(cnpj)

    if encontrados:
        print(f"!! {len(encontrados)} match(s) encontrado(s) !!\n")
        for r in encontrados:
            print(f"[{r['tipo']}] {r['trecho']}")
        print("\n---\nFONTES: CEIS / CNEP / CEPIM / Leniencia (Portal da Transparencia - CGU)")
    else:
        print("Nenhuma sancao federal encontrada para esta raiz/CNPJ.")
        print("\nFontes consultadas: shared_data/sancoes/*.csv")
        print("Atualizar com: python -m core.fontes.sancoes")

    return 0