"""Investigar fornecedor (nome parcial ou CNPJ) em todos os municípios via coding agent."""
from inspectra.agents.coding import CodingAgent


TAREFA_TEMPLATE = """\
Investigue o fornecedor "{termo}" em todos os municipios do projeto.

PASSOS OBRIGATORIOS:
1. Use `search_achados` com o termo para ver o que ja temos documentado.
2. Use `query_sql` no banco `shared_data/macro_mt/macro_mt.db` com:
   ```sql
   SELECT municipio, COUNT(*) as n_emps, SUM(valor) as total
   FROM despesas
   WHERE (credor LIKE '%{termo}%' OR cnpj_cpf LIKE '%{termo}%')
     AND valor IS NOT NULL AND valor > 0
   GROUP BY municipio
   ORDER BY total DESC
   ```
3. Se houver CNPJ raiz com valor total > 0 em 2+ municipios, faca nova query detalhada:
   ```sql
   SELECT credor, municipio, COUNT(*) as n, SUM(valor) as total
   FROM despesas
   WHERE cnpj_cpf LIKE '<raiz>%' AND valor > 0
   GROUP BY credor, municipio
   ORDER BY total DESC LIMIT 20
   ```
4. Escreva resposta estruturada em markdown com:
   - Tabela de municipios (municipio | n_empenhos | valor_total)
   - CNPJ raiz encontrado (se houver)
   - Observacoes relevantes dos dossies (do search_achados)
   - Base legal aplicavel (LC 131/2009, Lei 14.133/2021 art. 75)
REGRAS: nunca invente numeros. Use apenas dados retornados pelas tools. Se nao encontrou nada, diga "nada encontrado".
"""


def cmd_investigar(args) -> int:
    agent = CodingAgent(model=args.model, max_steps=args.steps, temperatura=0.2)
    tarefa = TAREFA_TEMPLATE.format(termo=args.termo)
    print(f"=== Investigando: {args.termo} ===\n")
    print(f"Modelo: {args.model} | max_steps: {args.steps}\n")
    resp = agent.run(tarefa, verbose=True)
    print("\n" + "=" * 60)
    print("RESPOSTA FINAL:")
    print("=" * 60)
    print(resp)
    return 0