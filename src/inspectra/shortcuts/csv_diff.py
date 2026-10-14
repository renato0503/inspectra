"""
Diff entre dois arquivos CSV (linhas adicionadas, removidas, alteradas).

Uso:
    python -m inspectra.shortcuts.cli csv_diff compras_jan.csv compras_fev.csv --chave cnpj
    python -m inspectra.shortcuts.cli csv_diff a.csv b.csv --chave id --json
    python -m inspectra.shortcuts.cli csv_diff a.csv b.csv --chave cnpj --saida diff_resultado.json
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
import os
import time
from pathlib import Path
from typing import List, Dict, Optional, Any

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(RAIZ / "src"))

from inspectra.shortcuts._output import output


def _ler_csv(caminho: str) -> tuple:
    """Le CSV. Retorna (headers, rows_dict_list, rows_raw_list)."""
    with open(caminho, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)
    return headers, rows


def _indexar_por_chave(rows: List[Dict], chave: str) -> Dict[str, Dict]:
    """Indexa linhas por chave."""
    resultado = {}
    for row in rows:
        key = row.get(chave, "").strip()
        if key:
            resultado[key] = row
    return resultado


def _comparar_campos(row_a: Dict, row_b: Dict, todos_campos: List[str]) -> Dict[str, Dict]:
    """Retorna campos que mudaram."""
    mudancas = {}
    for campo in todos_campos:
        val_a = row_a.get(campo, "").strip()
        val_b = row_b.get(campo, "").strip()
        if val_a != val_b:
            mudancas[campo] = {"antes": val_a, "depois": val_b}
    return mudancas


def csv_diff(arquivo_a: str, arquivo_b: str, chave: str = "cnpj") -> dict:
    """Compara dois CSVs. Retorna JSON estruturado."""
    inicio = time.time()

    if not Path(arquivo_a).exists():
        return output(False, None, "CSV", erro=f"Arquivo A nao encontrado: {arquivo_a}")
    if not Path(arquivo_b).exists():
        return output(False, None, "CSV", erro=f"Arquivo B nao encontrado: {arquivo_b}")

    headers_a, rows_a = _ler_csv(arquivo_a)
    headers_b, rows_b = _ler_csv(arquivo_b)

    if not headers_a:
        return output(False, None, "CSV", erro="Arquivo A vazio ou invalido.")
    if not headers_b:
        return output(False, None, "CSV", erro="Arquivo B vazio ou invalido.")

    if chave not in headers_a and chave not in headers_b:
        return output(False, None, "CSV",
                      erro=f"Chave '{chave}' nao encontrada em nenhum dos CSVs. "
                           f"Headers A: {headers_a[:5]}. Headers B: {headers_b[:5]}")

    # Indexa por chave
    index_a = _indexar_por_chave(rows_a, chave)
    index_b = _indexar_por_chave(rows_b, chave)

    keys_a = set(index_a.keys())
    keys_b = set(index_b.keys())

    adicionados = [index_b[k] for k in keys_b - keys_a]
    removidos = [index_a[k] for k in keys_a - keys_b]

    todos_campos = list(dict.fromkeys(headers_a + headers_b))
    alterados_raw = []
    for k in keys_a & keys_b:
        mudancas = _comparar_campos(index_a[k], index_b[k], todos_campos)
        if mudancas:
            alterados_raw.append({
                chave: k,
                "antes": index_a[k],
                "depois": index_b[k],
                "mudancas": mudancas,
            })

    # Resumo por campo alterado
    freq_campos: Dict[str, int] = {}
    for a in alterados_raw:
        for campo in a["mudancas"]:
            freq_campos[campo] = freq_campos.get(campo, 0) + 1

    schema_diff = []
    for h in set(headers_a) - set(headers_b):
        schema_diff.append({"tipo": "removido", "campo": h})
    for h in set(headers_b) - set(headers_a):
        schema_diff.append({"tipo": "adicionado", "campo": h})

    dados = {
        "arquivo_a": arquivo_a,
        "arquivo_b": arquivo_b,
        "chave": chave,
        "total_a": len(rows_a),
        "total_b": len(rows_b),
        "adicionados": adicionados,
        "removidos": removidos,
        "alterados": alterados_raw,
        "resumo_campos_alterados": [{"campo": k, "vezes": v} for k, v in freq_campos.items()],
        "schema_diff": schema_diff,
        "totais": {
            "adicionados": len(adicionados),
            "removidos": len(removidos),
            "alterados": len(alterados_raw),
        },
    }

    hint = f"A={len(adicionados)} (+), R={len(removidos)} (-), M={len(alterados_raw)} (~). " \
           f"Campos mais alterados: {', '.join(list(freq_campos.keys())[:3])}."

    tempo = round((time.time() - inicio) * 1000)
    resultado = output(True, dados, "CSV", prompt_hint=hint)
    resultado["meta"]["tempo_ms"] = tempo
    return resultado


def main():
    p = argparse.ArgumentParser(prog="csv_diff")
    p.add_argument("arquivo_a", help="Primeiro CSV (antes)")
    p.add_argument("arquivo_b", help="Segundo CSV (depois)")
    p.add_argument("--chave", default="cnpj", help="Coluna chave para comparacao (default: cnpj)")
    p.add_argument("--saida", help="Salvar resultado em JSON")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    resultado = csv_diff(args.arquivo_a, args.arquivo_b, args.chave)

    if args.saida:
        Path(args.saida).write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Salvo em {args.saida}")

    if args.json:
        print_json(resultado)
    else:
        dados = resultado["dados"]
        t = dados["totais"]
        print(f"\n=== CSV Diff: {dados['arquivo_a']} vs {dados['arquivo_b']} ===")
        print(f"Total A: {dados['total_a']} | Total B: {dados['total_b']}")
        print(f"\n{t['adicionados']} adicionado(s) | {t['removidos']} removido(s) | {t['alterados']} alterado(s)")
        if dados.get("schema_diff"):
            print(f"\nSchema diff:")
            for s in dados["schema_diff"]:
                print(f"  [{s['tipo']}] {s['campo']}")
        if dados.get("resumo_campos_alterados"):
            print(f"\nCampos mais alterados:")
            for c in dados["resumo_campos_alterados"][:5]:
                print(f"  {c['campo']}: {c['vezes']} vez(es)")
        if dados.get("adicionados")[:3]:
            print(f"\nExemplos adicionados:")
            for r in dados["adicionados"][:3]:
                print(f"  {dados['chave']}={r.get(dados['chave'], '?')}")
        if dados.get("removidos")[:3]:
            print(f"\nExemplos removidos:")
            for r in dados["removidos"][:3]:
                print(f"  {dados['chave']}={r.get(dados['chave'], '?')}")
        if dados.get("alterados")[:3]:
            print(f"\nExemplos alterados:")
            for r in dados["alterados"][:3]:
                print(f"  {dados['chave']}={r.get(dados['chave'], '?')}: "
                      f"{', '.join(r['mudancas'].keys())}")

    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
