#!/usr/bin/env python
"""Demonstração do recon renderizado + config de coverage (ARTEX).

Rode na raiz do EnemyDisclosure:

    python complexo/exemplos/demo_browser.py <url-do-site-institucional>

Sem argumento, só gera um config.json de coverage de exemplo em memória
(não faz rede). Requer `pip install playwright && playwright install chromium`
para a parte de render.

Exemplo:
    python complexo/exemplos/demo_browser.py https://prefeitura.sinop.mt.gov.br
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from complexo.artex import ApiRecon  # noqa: E402
from complexo.browser import Navegador  # noqa: E402


def mostrar_config_coverage() -> None:
    """Gera (em tempdir) um config.json de exemplo, modo coverage."""
    with tempfile.TemporaryDirectory() as td:
        ar = ApiRecon(td)
        cfg = ar.gerar_config(
            "https://portal.exemplo.gov.br/",
            runtime_mode="coverage",
            mock_tier="L1+L2",
            routes=["/", "/despesas", "/licitacoes"],
            stubs=[
                {
                    "match": "permiss|/menu|role",
                    "body": {"response_code": 0, "code": 0,
                             "data": {"permissions": ["*"], "menus": []}},
                }
            ],
        )
        data = json.loads(cfg.read_text(encoding="utf-8"))
        print("== config.json (coverage) ==")
        print(json.dumps(data, ensure_ascii=False, indent=2))


def descobrir(url: str) -> None:
    ok, motivo = Navegador.disponivel()
    if not ok:
        print(f"[!] render indisponível: {motivo}")
        return
    desc = Navegador().descobrir_portal(url)
    print(f"\n== Descoberta renderizada ==\n{url}")
    print(f"url final: {desc.url_final}")
    print(f"título:    {desc.title}")
    if desc.erro:
        print(f"erro:      {desc.erro}")
    for c in desc.candidatos:
        hint = f" [{c['adapter_hint']}]" if c.get("adapter_hint") else ""
        print(f"  ({c['score']}) {c['href']}{hint}"
              + (f"  — {c['text']}" if c.get("text") else ""))


def main() -> None:
    if len(sys.argv) > 1:
        descobrir(sys.argv[1])
    else:
        mostrar_config_coverage()


if __name__ == "__main__":
    main()
