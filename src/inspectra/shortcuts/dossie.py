"""
Gera mini-dossie de um CNPJ com base no macro_mt.db + sancoes + BrasilAPI.

Saida: dossie_fornecedor_<raiz>_<data>.md com:
- Identificacao (razao social, endereco, CNAE, capital, data abertura)
- Vinculos em Mato Grosso (empenhos por municipio)
- Sancoes federais (CEIS/CNEP/CEPIM)
- Base legal + ressalvas
"""
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path

from inspectra.shortcuts.sancoes import _buscar_em_csv, _norm

RAIZ = Path(__file__).resolve().parents[3]
SHARED = RAIZ / "shared_data"


def _enriquecer_brasilapi(cnpj: str) -> dict:
    """Consulta BrasilAPI + Minha Receita."""
    cnpj_limpo = _norm(cnpj)
    if len(cnpj_limpo) != 14:
        return {}
    try:
        with urllib.request.urlopen(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}", timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def _enriquecer_cache(cnpj: str) -> dict:
    cache = SHARED / "brasilapi_cnpj.json"
    if not cache.exists():
        return {}
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        return data.get(cnpj_limpo := _norm(cnpj), data.get(cnpj, {}))
    except Exception:
        return {}


def _empenhos_no_macro(cnpj: str) -> list:
    import sqlite3
    cx = sqlite3.connect(f"{RAIZ}/shared_data/macro_mt/macro_mt.db")
    try:
        r = cx.execute(
            "SELECT municipio, COUNT(*), SUM(valor) "
            "FROM despesas WHERE cnpj_cpf = ? OR cnpj_cpf LIKE ? "
            "GROUP BY municipio ORDER BY 3 DESC",
            (cnpj, _norm(cnpj)[:8] + "%"),
        ).fetchall()
        return [(m, n, v) for m, n, v in r]
    except Exception:
        return []
    finally:
        cx.close()


def _top_objetos(cnpj: str, limite: int = 5) -> list:
    import sqlite3
    cx = sqlite3.connect(f"{RAIZ}/shared_data/macro_mt/macro_mt.db")
    try:
        r = cx.execute(
            "SELECT objeto, COUNT(*), SUM(valor) FROM despesas "
            "WHERE (cnpj_cpf = ? OR cnpj_cpf LIKE ?) AND objeto IS NOT NULL "
            "GROUP BY objeto ORDER BY 3 DESC LIMIT ?",
            (cnpj, _norm(cnpj)[:8] + "%", limite),
        ).fetchall()
        return [(o, n, v) for o, n, v in r]
    except Exception:
        return []
    finally:
        cx.close()


def cmd_dossie(args) -> int:
    cnpj = _norm(args.cnpj)
    if len(cnpj) not in (11, 14):
        print(f"ERRO: CNPJ invalido (precisa ter 11 ou 14 digitos, veio {len(cnpj)})")
        return 1
    raiz = cnpj[:8]

    print(f"=== Dossie de fornecedor: {cnpj} (raiz {raiz}) ===\n")
    print("Coletando dados de multiplas fontes...\n")

    info = _enriquecer_cache(cnpj) or {}
    if not info or "razao_social" not in info:
        print("[1/4] BrasilAPI ao vivo...")
        info = _enriquecer_brasilapi(cnpj)
    else:
        print("[1/4] BrasilAPI (cache local)")
    if not info:
        print("  [!] Sem dados cadastrais (BrasilAPI indisponivel e sem cache).")
        print("      Preencha o cache: python -m core.fontes.brasilapi")
        info = {}

    print("[2/4] Empenhos no macro_mt.db...")
    empenhos = _empenhos_no_macro(cnpj)
    total_geral = sum(v for _, _, v in empenhos) if empenhos else 0

    print("[3/4] Objetos principais...")
    objetos = _top_objetos(cnpj)

    print("[4/4] Sancoes federais (CEIS/CNEP/CEPIM)...")
    sancoes = _buscar_em_csv(raiz)
    if not sancoes and len(cnpj) >= 14:
        sancoes = _buscar_em_csv(cnpj)

    # Monta markdown
    hoje = datetime.now().strftime("%Y-%m-%d")
    out = []
    out.append(f"# Dossie do Fornecedor CNPJ {args.cnpj}")
    out.append(f"_Gerado em {hoje} via `core.ia.atalhos dossie` (EnemyDisclosure)_")
    out.append("")
    out.append("## 1. Identificacao Cadastral (BrasilAPI/Minha Receita)")
    if info:
        out.append(f"- **Razao social:** {info.get('razao_social', 'N/D')}")
        out.append(f"- **Nome fantasia:** {info.get('nome_fantasia', 'N/D')}")
        out.append(f"- **CNPJ:** {info.get('cnpj', args.cnpj)}")
        out.append(f"- **Situacao:** {info.get('descricao_situacao_cadastral', 'N/D')}")
        out.append(f"- **Data abertura:** {info.get('data_inicio_atividade', 'N/D')}")
        out.append(f"- **Capital social:** R$ {info.get('capital_social', 'N/D')}")
        out.append(f"- **CNAE principal:** {info.get('cnae_fiscal_descricao', 'N/D')}")
        end = info.get("endereco", {}) or {}
        if end:
            out.append(f"- **Endereco:** {end.get('logradouro','')}, {end.get('numero','')} - {end.get('bairro','')}, {end.get('municipio','')}/{end.get('uf','')} CEP {end.get('cep','')}")
        qsa = info.get("qsa") or []
        if qsa:
            out.append("- **Quadro societario (QSA):**")
            for s in qsa[:10]:
                out.append(f"  - {s.get('nome','?')} ({s.get('qualificacao','?')}) - entrada {s.get('data_entrada','?')}")
    else:
        out.append("_Dados nao disponiveis._")
    out.append("")

    out.append("## 2. Vinculos em Mato Grosso (macro_mt.db)")
    if empenhos:
        out.append("| Municipio | n_empenhos | valor_total |")
        out.append("| :--- | ---: | ---: |")
        for m, n, v in empenhos[:20]:
            out.append(f"| {m} | {n} | R$ {v:,.2f} |")
        out.append("")
        out.append(f"**Total cross-municipio: R$ {total_geral:,.2f} em {len(empenhos)} municipio(s)**")
        if objetos:
            out.append("")
            out.append("### 2.1 Principais objetos contratados")
            for o, n, v in objetos:
                preview = (o or '')[:120]
                out.append(f"- {n}x - R$ {v:,.2f} - _{preview}_")
    else:
        out.append("_Nenhum empenho encontrado no macro_mt.db._")
        out.append("_Possiveis razoes:_")
        out.append("- _Portal do municipio nao expoe CNPJ_")
        out.append("- _Credor registrado apenas com razao social_")
    out.append("")

    out.append("## 3. Sancoes Federais (CEIS / CNEP / CEPIM / Leniencia)")
    if sancoes:
        out.append(f"**{len(sancoes)} match(s) encontrado(s)**")
        for s in sancoes:
            out.append(f"- [{s['tipo']}] {s['trecho']}")
        out.append("")
        out.append("> [!] ATENCAO: ha sancao federal vigente. Verificar data de vigencia vs data dos empenhos.")
    else:
        out.append("_Nenhuma sancao federal encontrada para esta raiz/CNPJ._")
        out.append("_Fontes: shared_data/sancoes/*.csv (atualizar com `python -m core.fontes.sancoes`)_")
    out.append("")

    out.append("## 4. Base Legal e Ressalvas")
    out.append("- **LC 131/2009 art. 48-A** - obrigacao de divulgacao de receitas/despesas")
    out.append("- **Lei 14.133/2021 art. 75** - vedacao a fracionamento")
    out.append("- **Lei 8.429/1992** - improbidade administrativa")
    out.append("- **CEIS/CNEP/CEPIM** - cadastros federais de inidoneidade/impedimento")
    out.append("")
    out.append("**Ressalva:** Este dossie e INDICIO, nao prova. Cada numero precisa ser confirmado na fonte primaria. Indicios devem ser reportados ao orgao de controle competente (TCE-MT, MP, CGE).")
    out.append("")

    conteudo = "\n".join(out)

    # Salva
    save = getattr(args, 'save', None)
    if save is False or save == 'false':
        destino = None
    elif save and save is not True:
        destino = Path(save)
    else:
        destino = RAIZ / "shared_data" / "dossies_fornecedores" / f"dossie_{raiz}_{hoje}.md"

    if destino:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
        print(f"\n[OK] Salvo em: {destino.relative_to(RAIZ)}")

    print("\n" + "=" * 60)
    print(conteudo)
    return 0