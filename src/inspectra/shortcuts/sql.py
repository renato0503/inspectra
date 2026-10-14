"""Pergunta em linguagem natural -> SQL -> executa no banco especificado."""
from inspectra.agents.coding import CodingAgent


TAREFA_TEMPLATE = """\
Traduza a pergunta em linguagem natural abaixo para SQL (sqlite3) e execute no banco `{banco}`.

PERGUNTA: {pergunta}

REGRAS:
- Use APENAS SELECT/WITH/PRAGMA (read-only).
- Sempre `WHERE length(cnpj_cpf) >= 11 AND valor > 0` para evitar lixo de portais sem CNPJ.
- Sempre use LIMIT (max 50).
- Apos obter o resultado, apresente em formato markdown com titulo claro.

SCHEMA esperado (tabela despesas): id, orgao, municipio, exercicio, data, credor, cnpj_cpf, valor, tipo_documento, modalidade, objeto, fase, dotacao, fonte.
"""


def cmd_sql(args) -> int:
    agent = CodingAgent(model=args.model, max_steps=args.steps, temperatura=0.1)
    tarefa = TAREFA_TEMPLATE.format(pergunta=args.pergunta, banco=args.banco)
    print(f"=== SQL a partir de PT-BR ===")
    print(f"Banco: {args.banco}")
    print(f"Modelo: {args.model}\n")
    resp = agent.run(tarefa, verbose=True)
    print("\n" + "=" * 60)
    print("RESPOSTA FINAL:")
    print("=" * 60)
    print(resp)
    return 0