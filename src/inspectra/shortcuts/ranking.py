"""Ranking cross-municipal (top N por valor, CNPJ, ou cross-municipio)."""
from inspectra.agents.coding import CodingAgent


TAREFA_TEMPLATE = """\
No banco `shared_data/macro_mt/macro_mt.db`, gere o ranking {modo} dos {top} credores.

REGRAS CRITICAS:
- Use APENAS registros com CNPJ real (length(cnpj_cpf) >= 11) e valor > 0.
- Exclua registros com cnpj_cpf vazio (Brasnorte/Chapada/Sinop/Varzea Grande nao tem CNPJ no portal).
- NUNCA invente numeros. Copie exatamente o que a query retornar.

MODO {modo}:
- Se for "valor": top {top} credores (por CNPJ raiz = primeiros 8 digitos de cnpj_cpf) ordenados por SUM(valor) DESC. Mostre: cnpj_raiz, valor_total, n_municipios, n_empenhos, credor_mais_frequente.
- Se for "cnpj": top {top} CNPJs raiz distintos ordenados por valor_total DESC.
- Se for "cross": apenas CNPJs raiz que aparecem em 2+ municipios, ordenados por n_municipios DESC.

QUERY BASE (adapte WHERE/ORDER BY conforme modo):
```sql
SELECT SUBSTR(cnpj_cpf, 1, 8) as cnpj_raiz,
       credor,
       SUM(valor) as valor_total,
       COUNT(DISTINCT municipio) as n_municipios,
       COUNT(*) as n_empenhos
FROM despesas
WHERE length(cnpj_cpf) >= 11 AND valor > 0
GROUP BY SUBSTR(cnpj_cpf, 1, 8)
HAVING [condicao do modo]
ORDER BY [campo do modo] DESC
LIMIT {top};
```

Apos executar a query, apresente:
1. Tabela markdown com os resultados
2. Soma total (em R$)
3. Qualquer padrao notavel (ex.: mesmo CNPJ com nomes variando)
"""


def cmd_ranking(args) -> int:
    agent = CodingAgent(model=args.model, max_steps=args.steps, temperatura=0.1)
    tarefa = TAREFA_TEMPLATE.format(top=args.top, modo=args.por)
    print(f"=== Ranking {args.por} (top {args.top}) ===\n")
    print(f"Modelo: {args.model} | max_steps: {args.steps}\n")
    resp = agent.run(tarefa, verbose=True)
    print("\n" + "=" * 60)
    print("RESPOSTA FINAL:")
    print("=" * 60)
    print(resp)
    return 0