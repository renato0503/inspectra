#!/usr/bin/env python
"""Demonstração do grafo de auditoria (asset + exploration).

Rode na raiz do EnemyDisclosure:

    python complexo/exemplos/demo_grafo.py

Cria um grafo pequeno com dois órgãos, um fornecedor compartilhado (com
sanção) e um sócio operando duas empresas; salva JSON + GraphML.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Garante a raiz do EnemyDisclosure no sys.path quando rodado como script.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from complexo.grafo import GrafoAuditoria


def main() -> None:
    g = GrafoAuditoria()

    # Portais e órgãos
    g.add_portal("https://www.gp.srv.br/transparencia_sinop", vendor="genexus_gp",
                 municipio="Sinop")
    g.add_orgao("prefeitura_sinop", "Prefeitura de Sinop",
                "https://www.gp.srv.br/transparencia_sinop")
    g.add_orgao("prefeitura_cuiaba", "Prefeitura de Cuiabá",
                "https://transparencia.cuiaba.mt.gov.br/portaltransparencia")

    # Fornecedor compartilhado e sancionado
    g.add_fornecedor("07192414000109", "Costa Oeste Serviços", sancionado=True)
    g.ligar_fornecedor_orgao("07192414000109", "prefeitura_sinop", valor=16_400_000)
    g.ligar_fornecedor_orgao("07192414000109", "prefeitura_cuiaba", valor=78_700_000)

    # Operador com duas empresas
    g.add_socio("Jose Guerreiro Filho", "José Guerreiro Filho")
    g.add_fornecedor("11111111000111", "Studio Comércio")
    g.add_fornecedor("22222222000122", "JC Comércio")
    g.ligar_socio_fornecedor("Jose Guerreiro Filho", "11111111000111")
    g.ligar_socio_fornecedor("Jose Guerreiro Filho", "22222222000122")

    # Uma investigação de exemplo
    meta = g.nova_investigacao("Sinop", "mapear fornecedores sancionados")
    intent = g.registrar_intent(meta, "cruzar despesas com CEIS")
    g.concluir_intent(
        intent,
        fatos=["vendor=genexus_gp", "Costa Oeste suspensa desde 05/01/2026"],
        achados=[{"titulo": "Empenho lavrado na mesma data da suspensão"}],
        assets_tocados=["cnpj:07192414000109"],
    )

    saida = Path("shared_data/recon/exemplo_grafo.json")
    g.salvar(saida)
    gm = g.exportar_graphml(saida.with_suffix(".graphml"))

    print("Resumo:", g.resumo())
    print("Multi-órgão:", g.fornecedores_multi_orgao())
    print("Operadores:", g.operadores())
    print("Grafo salvo em:", saida)
    if gm:
        print("GraphML em:", gm)


if __name__ == "__main__":
    main()
