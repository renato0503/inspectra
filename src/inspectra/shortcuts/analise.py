"""Roda uma analise do B-suite (fracionamento, benford, nepotismo, etc.) e le o resultado."""
from inspectra.agents.coding import CodingAgent


TAREFA_TEMPLATE = """\
Rode a analise do B-suite: "{nome}" para o orgao "{orgao}" no exercicio {ano}.

PASSOS:
1. Use a tool `run_analysis` com nome="{nome}", orgao="{orgao}", ano={ano}.
2. Depois leia o arquivo `orgaos/<Municipio>/{orgao}/data/export/analises_{ano}.json` (use `list_files` para achar o caminho exato primeiro).
3. Identifique o resultado da analise especifica (campo "titulo" matching "{nome}" ou o modulo executado).
4. Sintetize em portugues:
   - O que a analise mediu
   - Qual o veredito (achou ou nao achou indicios)
   - Os 3-5 achados mais relevantes
   - Base legal aplicavel
REGRAS: reporte apenas dados reais do JSON. NAO invente numeros ou vereditos.
"""


def cmd_analise(args) -> int:
    agent = CodingAgent(model=args.model, max_steps=args.steps, temperatura=0.2)
    tarefa = TAREFA_TEMPLATE.format(nome=args.nome, orgao=args.orgao, ano=args.ano)
    print(f"=== Analise B: {args.nome} | {args.orgao} | {args.ano} ===\n")
    print(f"Modelo: {args.model} | max_steps: {args.steps}\n")
    resp = agent.run(tarefa, verbose=True)
    print("\n" + "=" * 60)
    print("RESPOSTA FINAL:")
    print("=" * 60)
    print(resp)
    return 0