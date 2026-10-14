"""
Regenera os mini-dossiês para todos os CNPJs relevantes do macro_mt.db.

Para cada CNPJ raiz distinto (com valor > R$ 1M agregado ou cross-municipio):
gera `shared_data/dossies_fornecedores/dossie_<raiz>_<data>.md` via BrasilAPI +
macro_mt.db + CEIS/CNEP.

Uso:
    python -m core.ia.regen_dossies                  # todos os CNPJs relevantes
    python -m core.ia.regen_dossies --limite 10      # so os top 10
    python -m core.ia.regen_dossies --raiz 07192414   # um CNPJ especifico
    python -m core.ia.regen_dossies --min-valor 100000  # filtro de valor minimo
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from inspectra.shortcuts.sancoes import _buscar_em_csv, _norm
from inspectra.shortcuts.dossie import (
    _enriquecer_brasilapi,
    _enriquecer_cache,
    _empenhos_no_macro,
    _top_objetos,
)

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))
MACRO_DB = RAIZ / "shared_data" / "macro_mt" / "macro_mt.db"
DEST = RAIZ / "shared_data" / "dossies_fornecedores"


def listar_cnpjs_relevantes(min_valor: float = 0, cross: bool = True, limite: int = None) -> list:
    """Retorna lista de CNPJs raiz relevantes do macro_mt.db."""
    if not MACRO_DB.exists():
        return []
    cx = sqlite3.connect(MACRO_DB)
    try:
        sql = """
        SELECT SUBSTR(cnpj_cpf, 1, 8) as raiz,
               SUM(valor) as total,
               COUNT(DISTINCT municipio) as n_mun,
               COUNT(*) as n_emp
        FROM despesas
        WHERE length(cnpj_cpf) >= 11 AND valor > 0
        GROUP BY raiz
        """
        if not cross:
            sql += " HAVING n_mun = 1"
        sql += " ORDER BY total DESC"
        if limite:
            sql += f" LIMIT {limite}"
        rows = cx.execute(sql).fetchall()
    finally:
        cx.close()
    return [
        {"raiz": r[0], "valor_total": r[1], "n_municipios": r[2], "n_empenhos": r[3]}
        for r in rows
        if r[1] >= min_valor
    ]


def gerar_dossie_raiz(raiz: str) -> Path | None:
    """Gera dossiê markdown para um CNPJ raiz (8 digitos). Retorna path ou None."""
    # Buscar cnpj completo (com filial) a partir do macro_mt
    cx = sqlite3.connect(MACRO_DB)
    try:
        r = cx.execute(
            "SELECT DISTINCT cnpj_cpf FROM despesas "
            "WHERE substr(cnpj_cpf,1,8) = ? AND length(cnpj_cpf) = 14 LIMIT 1",
            (raiz,),
        ).fetchone()
    finally:
        cx.close()
    if not r:
        return None
    cnpj = r[0]

    # Enriquece
    info = _enriquecer_cache(cnpj) or _enriquecer_brasilapi(cnpj) or {}
    empenhos = _empenhos_no_macro(cnpj)
    objetos = _top_objetos(cnpj)
    sancoes = _buscar_em_csv(raiz) or (len(cnpj) >= 14 and _buscar_em_csv(cnpj)) or []
    total = sum(v for _, _, v in empenhos) if empenhos else 0

    # Monta markdown
    hoje = datetime.now().strftime("%Y-%m-%d")
    out = []
    out.append(f"# Dossie do Fornecedor CNPJ {cnpj}")
    out.append(f"_Gerado em {hoje} via `core.ia.regen_dossies` (EnemyDisclosure)_")
    out.append("")
    out.append("## 1. Identificacao Cadastral")
    if info:
        out.append(f"- **Razao social:** {info.get('razao_social', 'N/D')}")
        out.append(f"- **Nome fantasia:** {info.get('nome_fantasia', 'N/D')}")
        out.append(f"- **Capital social:** R$ {info.get('capital_social', 'N/D')}")
        out.append(f"- **CNAE principal:** {info.get('cnae_fiscal_descricao', 'N/D')}")
        end = info.get("endereco", {}) or {}
        if end:
            out.append(f"- **Endereco:** {end.get('logradouro','')}, {end.get('numero','')} - {end.get('municipio','')}/{end.get('uf','')}")
        qsa = info.get("qsa") or []
        if qsa:
            out.append("- **QSA:**")
            for s in qsa[:10]:
                out.append(f"  - {s.get('nome','?')} ({s.get('qualificacao','?')})")
    else:
        out.append("_Cadastro nao disponivel._")
    out.append("")

    out.append("## 2. Vinculos em Mato Grosso")
    if empenhos:
        out.append("| Municipio | n_empenhos | valor_total |")
        out.append("| :--- | ---: | ---: |")
        for m, n, v in empenhos[:20]:
            out.append(f"| {m} | {n} | R$ {v:,.2f} |")
        out.append(f"\n**Total: R$ {total:,.2f}**")
        if objetos:
            out.append("\n### Principais objetos")
            for o, n, v in objetos:
                out.append(f"- {n}x R$ {v:,.2f} - _{o[:120]}_")
    else:
        out.append("_Nenhum empenho._")
    out.append("")

    out.append("## 3. Sancoes Federais")
    if sancoes:
        out.append(f"**{len(sancoes)} match(s)**")
        for s in sancoes:
            out.append(f"- [{s['tipo']}] {s['trecho']}")
    else:
        out.append("_Nenhuma._")
    out.append("")

    out.append("## 4. Base Legal")
    out.append("- LC 131/2009 art. 48-A | Lei 14.133/2021 art. 75 | Lei 8.429/1992 (improbidade)")
    out.append("")
    out.append("**Ressalva:** Indicio, nao prova.")

    conteudo = "\n".join(out)
    destino = DEST / f"dossie_{raiz}_{hoje}.md"
    DEST.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8")
    return destino


def main():
    p = argparse.ArgumentParser(description="Regenera mini-dossiês para todos os CNPJs relevantes")
    p.add_argument("--limite", type=int, help="Maximo de CNPJs a processar (default: todos)")
    p.add_argument("--raiz", help="Processar apenas esta raiz (8 digitos)")
    p.add_argument("--min-valor", type=float, default=1_000_000, help="Valor minimo total para processar (default 1M)")
    p.add_argument("--cross", action="store_true", default=False, help="Apenas CNPJs em 2+ municipios (default: nao)")
    args = p.parse_args()

    if args.raiz:
        cnpjs = [{"raiz": args.raiz}]
    else:
        cnpjs = listar_cnpjs_relevantes(min_valor=args.min_valor, cross=args.cross, limite=args.limite)
        print(f"Encontrados {len(cnpjs)} CNPJs (min_valor=R$ {args.min_valor:,.0f}, cross={args.cross})")
        print(f"Limite: {args.limite or 'sem limite'}\n")

    sucessos = 0
    falhas = 0
    for i, c in enumerate(cnpjs, 1):
        raiz = c["raiz"]
        try:
            destino = gerar_dossie_raiz(raiz)
            if destino:
                sucessos += 1
                if i <= 10 or i % 10 == 0:
                    print(f"  [{i}/{len(cnpjs)}] {raiz} -> {destino.name}")
            else:
                falhas += 1
                print(f"  [{i}/{len(cnpjs)}] {raiz} -> (sem CNPJ completo no banco)")
        except Exception as e:
            falhas += 1
            print(f"  [{i}/{len(cnpjs)}] {raiz} -> ERRO: {e}")

    print(f"\nResumo: {sucessos} sucessos, {falhas} falhas")
    print(f"Destino: {DEST.relative_to(RAIZ)}")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())