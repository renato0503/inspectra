"""
Gerador de relatorios formatados a partir de achados estruturados.

Aceita JSON (stdin ou arquivo) com achados e gera markdown/HTML formatado.
Projetado para agentes LLM consumirem saida de outras tools e gerarem
relatorios finais.

Formato de entrada (JSON):
    {
      "titulo": "Relatorio de Investigacao",
      "subtitulo": "Fornecedor X",
      "data": "2026-01-15",
      "nivel": "auditoria|forense|osint|due_diligence",
      "sumario": "Breve resumo em 1-2 frases",
      "achados": [
        {
          "id": "A-001",
          "titulo": "Titulo do achado",
          "severidade": "forte|moderada|atencao|info",
          "fato": "O que foi encontrado (fato verificavel)",
          "metodo": "Como foi descoberto",
          "fonte": ["URL ou base de dados"],
          "base_legal": "Lei ou regulamento aplicavel",
          "ressalva": "O que pode ser falsa luz",
          "tags": ["tag1", "tag2"]
        }
      ],
      "recomendacoes": ["Recomendacao 1", ...],
      "anexos": [{"nome": "...", "conteudo": "..."}]
    }

Uso:
    python -m inspectra.shortcuts.relatorio < achados.json
    python -m inspectra.shortcuts.relatorio achados.json --formato html --saida relatorio.html
    python -m inspectra.shortcuts.relatorio --demo  (gera exemplo)
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import os
RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))

TEMPLATE_MD = """\
# {titulo}

{subtitulo} &middot; {data}

---

## Sumario

{sumario}

**Nivel:** {nivel} &nbsp;|&nbsp; **Achados:** {n_achados} &nbsp;|&nbsp; **Fortes:** {n_fortes}

---

## Achados

{achados_md}

---

## Recomendacoes

{recomendacoes_md}

---

## Fontes

{fontes_md}

> _Gerado automaticamente por Inspectra. Indicio nao e prova. Todo numero tem fonte._

"""

ACHADO_MD = """\
### [{id}] {titulo} &nbsp; [{severidade}]

**Fato:** {fato}

**Metodo:** {metodo}

**Fonte:** {fonte}

**Base legal:** {base_legal}

**Ressalva:** {ressalva}

"""

REC_MD = """\
1. {i}. {rec}
"""

FONTE_MD = """\
- {fonte}
"""


SEVERIDADE_ICONE = {
    "forte": "\u26a0\ufe0f **Forte**",
    "moderada": "\u26a0 **Moderada**",
    "atencao": "\u2139\ufe0f Atencao",
    "info": "\u2139\ufe0f Info",
}


def _severidade_md(s: str) -> str:
    s = s.lower().strip()
    return SEVERIDADE_ICONE.get(s, s)


def _render_achados(achados: list) -> str:
    out = []
    for a in achados:
        out.append(ACHADO_MD.format(
            id=a.get("id", "?"),
            titulo=a.get("titulo", "Sem titulo"),
            severidade=_severidade_md(a.get("severidade", "info")),
            fato=a.get("fato", "Nao informado"),
            metodo=a.get("metodo", "Nao informado"),
            fonte=", ".join(a.get("fonte", [])) or "Nao informada",
            base_legal=a.get("base_legal", "N/A"),
            ressalva=a.get("ressalva", "N/A"),
        ))
    return "\n".join(out)


def _render_recomendacoes(recs: list) -> str:
    out = []
    for i, r in enumerate(recs, 1):
        out.append(REC_MD.format(i=i, rec=r))
    return "\n".join(out) if out else "_Nenhuma recomendacao registrada._"


def _render_fontes(achados: list) -> str:
    fontes = set()
    for a in achados:
        for f in a.get("fonte", []):
            if f and f != "Nao informada":
                fontes.add(f)
    if not fontes:
        return "_Nenhuma fonte registrada._"
    return "\n".join(FONTE_MD.format(fonte=f) for f in sorted(fontes))


def de_json(entrada: dict) -> str:
    """Converte JSON de achados em markdown."""
    achados = entrada.get("achados", [])
    n_fortes = sum(1 for a in achados if a.get("severidade", "").lower() == "forte")
    return TEMPLATE_MD.format(
        titulo=entrada.get("titulo", "Relatorio sem titulo"),
        subtitulo=entrada.get("subtitulo", ""),
        data=entrada.get("data", str(date.today())),
        nivel=entrada.get("nivel", "auditoria"),
        sumario=entrada.get("sumario", "Sem sumario."),
        n_achados=len(achados),
        n_fortes=n_fortes,
        achados_md=_render_achados(achados),
        recomendacoes_md=_render_recomendacoes(entrada.get("recomendacoes", [])),
        fontes_md=_render_fontes(achados),
    )


def de_html(markdown_text: str) -> str:
    """Conversao simples markdown -> HTML (sem dependencias)."""
    html = markdown_text
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"^\d+\. (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"><title>{'Relatorio Inspectra'}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;
      padding:0 1rem;line-height:1.6;color:#222}}
h1{{color:#1a3c5e}}h2{{color:#2c5f8a;margin-top:2rem}}h3{{color:#444}}
blockquote{{border-left:4px solid #ccc;padding-left:1rem;color:#555}}
li{{margin:.3rem 0}}strong{{color:#c00}}
hr{{margin:2rem 0;border:none;border-top:1px solid #ddd}}
</style></head>
<body>{html}</body></html>"""


DEMO_JSON = {
    "titulo": "Relatorio de Investigacao",
    "subtitulo": "COSTA OESTE SERVICOS LTDA",
    "data": str(date.today()),
    "nivel": "auditoria",
    "sumario": "Fornecedor com suspensao ativa no CEIS vigente ate janeiro de 2028, "
               "porem com contratos ativos em 3 prefeituras de Mato Grosso em 2026.",
    "achados": [
        {
            "id": "A-001",
            "titulo": "Suspensao ativa no CEIS (5 janeiro 2026 a 4 janeiro 2028)",
            "severidade": "forte",
            "fato": "CNPJ 07.192.414/0001-09 (COSTA OESTE SERVICOS LTDA) "
                     "consta no CEIS com suspensions ate eing2028.",
            "metodo": "Cross-reference CEIS via Inspectra",
            "fonte": ["CEIS/CGU portaltransparencia.gov.br"],
            "base_legal": "Lei 13303 art. 83 II e III",
            "ressalva": "SUSPENSAO pode ter excecoes definidas pelo tribunal.",
            "tags": ["CEIS", "suspensao", "contrato_bloqueado"]
        },
        {
            "id": "A-002",
            "titulo": "Contrato ativo com a Prefeitura de Cuiaba (R$ 43M)",
            "severidade": "atencao",
            "fato": "Empenhos de R$ 43.2M registrados em 2025 na Prefeitura de Cuiaba.",
            "metodo": "Query macro_mt.db",
            "fonte": ["macro_mt.db / Prefeitura de Cuiaba"],
            "base_legal": "LC 101/2000 art. 16",
            "ressalva": "Empenho nao significa pagamento efetivo.",
            "tags": ["Cuiaba", "empenho", "valor_alto"]
        },
    ],
    "recomendacoes": [
        "Verificar se os contratos vigentes tem garantia contratual.",
        "Notificar o tribunal de contas do estado sobre a suspensao.",
        "Confrontar os pagamentos com o CEIS para verificar sobrepreco."
    ]
}


def main():
    p = argparse.ArgumentParser(prog="relatorio")
    p.add_argument("arquivo", nargs="?", help="Arquivo JSON de entrada (stdin se omitido)")
    p.add_argument("--formato", choices=["md", "html"], default="md")
    p.add_argument("--saida", help="Arquivo de saida (stdout se omitido)")
    p.add_argument("--demo", action="store_true", help="Gera relatorio de exemplo")
    args = p.parse_args()

    if args.demo:
        dados = DEMO_JSON
    elif args.arquivo:
        with open(args.arquivo, encoding="utf-8") as f:
            dados = json.load(f)
    else:
        dados = json.load(sys.stdin)

    if args.formato == "html":
        texto = de_html(de_json(dados))
    else:
        texto = de_json(dados)

    if args.saida:
        Path(args.saida).write_text(texto, encoding="utf-8")
        print(f"[OK] Salvo em {args.saida}")
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
