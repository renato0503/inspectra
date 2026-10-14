"""Analise temporal (cronograma mensal) de um orgao ou cross-municipal."""
from inspectra.agents.coding import CodingAgent


TAREFA_TEMPLATE = """\
Gere o cronograma mensal de empenhos/pagamentos {filtro_orgao}do projeto EnemyDisclosure.

PASSOS:
1. PRIMEIRO descubra os valores EXATOS da coluna `municipio` usando:
   `SELECT DISTINCT municipio FROM despesas` no banco `shared_data/macro_mt/macro_mt.db`.
   (Municipios tem acento: 'Rondonopolis' = 'Rondonopolis', 'Varzea Grande' etc.)
   ATENCAO: 'Varzea Grande' e 'Brasnorte' podem ter grafia diferente.

2. Depois use `query_sql` com query robusta para ambos formatos de data:
   ```sql
   SELECT
     CASE WHEN length(data) = 10
          THEN substr(data, 7, 4) || '-' || substr(data, 4, 2)
          ELSE substr(data, 1, 7)
     END as mes,
     SUM(valor) as total_emp,
     COUNT(*) as n_emp,
     COUNT(DISTINCT credor) as n_credores
   FROM despesas
   WHERE valor > 0
     AND data IS NOT NULL AND data != ''
     AND length(data) >= 7
   {filtro_municipio}
   GROUP BY mes
   ORDER BY mes;
   ```
   {filtro_municipio} = `AND municipio = '<valor exato retornado no passo 1>'` se aplicavel.

3. Identifique picos atipicos:
   - Meses com valor > 2x a mediana
   - Concentracao em dezembro (sempre suspeita)
   - Meses com muitos credores diferentes mas pouco valor (possivel fracionamento)

4. Apresente:
   - Tabela markdown (mes | n_empenhos | n_credores | total)
   - 3 padroes identificados + base legal (Lei 4.320/64 art. 6o; LC 131/2009)
   - Recomendacao de analise adicional (qual B-suite rodar para aprofundar)
REGRAS: so use dados reais. Nao invente valores. Se retornar 0 linhas, reporte "0 resultados".
"""


def cmd_cronograma(args) -> int:
    orgao = args.orgao
    if orgao.lower() in ("todos", "all", "*"):
        filtro_municipio = ""
        filtro_orgao = "para TODOS os municipios "
    else:
        filtro_municipio = f"AND municipio = '<preencher com valor exato do passo 1>'"
        filtro_orgao = f"do orgao '{orgao}' "
    agent = CodingAgent(model=args.model, max_steps=args.steps, temperatura=0.2)
    tarefa = TAREFA_TEMPLATE.format(filtro_orgao=filtro_orgao, filtro_municipio=filtro_municipio, orgao=orgao)
    print(f"=== Cronograma mensal ({orgao}) ===\n")
    print(f"Modelo: {args.model} | max_steps: {args.steps}\n")
    resp = agent.run(tarefa, verbose=True)
    print("\n" + "=" * 60)
    print("RESPOSTA FINAL:")
    print("=" * 60)
    print(resp)
    return 0