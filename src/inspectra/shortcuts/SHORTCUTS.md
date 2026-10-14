# Inspectra — Catálogo de Atalhos

> **22 shortcuts** para agentes LLM chamarem diretamente via CLI ou API Python.
> Todos aceitam `INSPECTA_RAIZ` para apontar pro diretório de dados.
> Saída padronizada em JSON estruturado: `{ok, dados, fonte, erro, timestamp, prompt_hint}`.

---

## Instalação

```bash
cd produto/inspectra
pip install -e .

# Ou sem instalar (usa PYTHONPATH):
set PYTHONPATH=src
set INSPECTA_RAIZ=D:\Dev\EnemyDisclosure
```

---

## Atalhos Disponíveis

### 1. `ollama` — Chat, Embed e Modelos

**Chat direto com qualquer modelo Ollama local.**

```bash
# Chat simples
python -m inspectra.shortcuts.cli ollama chat "Analise este contrato" --model gemma4:latest

# Com system prompt
python -m inspectra.shortcuts.cli ollama chat "Voce e um auditor forensic" \
  --system "Fale apenas fatos verificaveis" --temperatura 0.1

# Listar modelos disponiveis
python -m inspectra.shortcuts.cli ollama models

# Embedding de texto
python -m inspectra.shortcuts.cli ollama embed "fornecimento de combustivel 2025"

# Completion unico
python -m inspectra.shortcuts.cli ollama complete "A suspenso do CEIS significa que"
```

---

### 2. `osint` — Reconhecimento OSINT sobre qualquer alvo

**WHOIS, DNS, headers HTTP, BrasilAPI, sanções, macro_mt — para domínio, CNPJ, empresa ou IP.**

```bash
# OSINT de CNPJ (mostra BrasilAPI + sanções + vínculos MT)
python -m inspectra.shortcuts.cli osint cnpj 07192414000109

# De empresa (busca no macro_mt)
python -m inspectra.shortcuts.cli osint empresa "COSTA OESTE"

# De domínio (WHOIS + DNS + headers)
python -m inspectra.shortcuts.cli osint dominio "transparencia.cuiaba.mt.gov.br"

# De IP
python -m inspectra.shortcuts.cli osint ip "192.168.1.1"

# Saida JSON pura
python -m inspectra.shortcuts.cli osint cnpj 07192414000109 --json
```

**Fontes consultadas:** WHOIS (porta 43), DNS (socket), HTTP headers, BrasilAPI, `shared_data/sancoes/*.csv`, `macro_mt.db`, LLM (Ollama) para resumo.

---

### 3. `due_diligence` — Due Diligence Completa de CNPJ

**Pesquisa completa: QSA, situação cadastral, sanções, gastos em MT, PNCP, dívida ativa, lista suja, classificação de risco via LLM.**

```bash
# Due diligence padrao
python -m inspectra.shortcuts.cli due_diligence cnpj 07192414000109

# Com modelo especifico
python -m inspectra.shortcuts.cli due_diligence cnpj 07192414000109 --model gemma4-26b

# Saida JSON completa
python -m inspectra.shortcuts.cli due_diligence cnpj 07192414000109 --json

# Demo (exemplo com Costa Oeste)
python -m inspectra.shortcuts.cli due_diligence --demo
```

**Camadas consultadas:**
| Camada | Fonte |
|--------|-------|
| Cadastro | BrasilAPI (com cache local em `brasilapi_cnpj.json`) |
| QSA | BrasilAPI |
| Sanções | CEIS/CNEP/CEPIM (`shared_data/sancoes/`) |
| Gastos MT | `macro_mt.db` |
| Contratações | PNCP DuckDB (se disponível em `D:\Dev\PNCP`) |
| Dívida Ativa | PGFN CSV (se disponível) |
| Trabalho Escravo | Lista Suja MTE (se disponível) |
| Risco | LLM Ollama (classificação automática) |

---

### 4. `relatorio` — Gerador de Relatórios

**Converte JSON estruturado de achados em markdown ou HTML formatado.**

```bash
# De arquivo JSON
python -m inspectra.shortcuts.cli relatorio achados.json

# De stdin
cat achados.json | python -m inspectra.shortcuts.cli relatorio

# Saida HTML
python -m inspectra.shortcuts.cli relatorio achados.json --formato html --saida relatorio.html

# Demo (exemplo completo)
python -m inspectra.shortcuts.cli relatorio --demo
```

**Formato JSON de entrada:**
```json
{
  "titulo": "Relatorio de Investigacao",
  "subtitulo": "Fornecedor X",
  "nivel": "auditoria",
  "sumario": "Resumo em 1-2 frases",
  "achados": [
    {
      "id": "A-001",
      "titulo": "Titulo do achado",
      "severidade": "forte|moderada|atencao|info",
      "fato": "O que foi encontrado",
      "metodo": "Como foi descoberto",
      "fonte": ["URL ou base"],
      "base_legal": "Lei aplicavel",
      "ressalva": "O que pode ser falsa luz"
    }
  ],
  "recomendacoes": ["Recomendacao 1"]
}
```

---

### 5. `investigar` — Fornecedor Cross-Municipal

**Investiga um fornecedor (nome ou CNPJ) em todos os municípios via coding agent com ferramentas de auditoria.**

```bash
# Por nome
python -m inspectra.shortcuts.cli investigar "COSTA OESTE"

# Por CNPJ
python -m inspectra.shortcuts.cli investigar "07192414000109"

# Com mais passos (mais profundidade)
python -m inspectra.shortcuts.cli investigar "LOTUFO" --steps 12
```

**O agente usa:** `query_sql`, `search_achados`, `grep`, `list_files` para cruzar dados.

---

### 6. `sancoes` — Consulta Direta CEIS/CNEP/CEPIM

**Busca sanções federais sem LLM — direto nos CSVs, <1 segundo.**

```bash
python -m inspectra.shortcuts.cli sancoes 07192414
python -m inspectra.shortcuts.cli sancoes 07.192.414/0001-09
```

**Fontes:** `shared_data/sancoes/cei*.csv` (CEIS, CNEP, CEPIM, Leniência).

---

### 7. `buscar` — Busca Semântica

**Busca em todos os dossies/analises via embeddings (nomic-embed-text), sem LLM.**

```bash
python -m inspectra.shortcuts.cli buscar "fracionamento combustivel 2024"
python -m inspectra.shortcuts.cli buscar "sancao empresario nepotismo" --top 10
```

---

### 8. `sql` — Natural Language to SQL

**Gera SQL via LLM e executa no macro_mt.db.**

```bash
python -m inspectra.shortcuts.cli sql "Qual municipio gastou mais em 2025?"
python -m inspectra.shortcuts.cli sql "Liste os top 10 fornecedores daPrefeitura de Cuiaba"
```

---

### 9. `analise` — Roda Módulo B-Suite

**Executa uma análise do B-suite e lê o resultado.**

```bash
python -m inspectra.shortcuts.cli analise benford camara_cuiaba 2025
python -m inspectra.shortcuts.cli analise fracionamento prefeitura_cuiaba 2025
python -m inspectra.shortcuts.cli analise nepotismo camara_vg 2025 --steps 6
```

**Módulos disponíveis:** `benford`, `fracionamento`, `nepotismo`, `aditivos`, `restos_a_pagar`, `timing_eleitoral`, `lancamentos_atipicos`, `pagamentos_duplicados`, `sobrepreco`, etc.

---

### 10. `ranking` — Rankings Cross-Municipais

```bash
# Top 10 por valor total
python -m inspectra.shortcuts.cli ranking

# Top 20 por valor
python -m inspectra.shortcuts.cli ranking --top 20 --por valor

# Top 10 CNPJs distintos
python -m inspectra.shortcuts.cli ranking --por cnpj

# Fornecedores em 2+ municípios
python -m inspectra.shortcuts.cli ranking --por cross
```

---

### 11. `dossie` — Mini-Dossiê de CNPJ

**Gera mini-dossiê markdown: identificação, vínculos MT, sanções, base legal.**

```bash
python -m inspectra.shortcuts.cli dossie 07192414000109
python -m inspectra.shortcuts.cli dossie 07192414000109 --save
```

---

### 12. `cronograma` — Análise Temporal Mensal

**Empenhos mês a mês + detecção de picos atípicos.**

```bash
# Todos os municípios
python -m inspectra.shortcuts.cli cronograma todos

# Um órgão específico
python -m inspectra.shortcuts.cli cronograma prefeitura_cuiaba
```

---

### 13. `pessoas` — TSE × QSA

**Cruza prestação de contas eleitoral (TSE) com quadro societário (QSA).**

```bash
python -m inspectra.shortcuts.cli pessoas --cpf 12345678901
python -m inspectra.shortcuts.cli pessoas --nome "RENATO ROSA"
```

---

### 14. `shell` — Modo Livre (Coding Agent)

**Passa instrução livre ao coding agent com 11 ferramentas nativas.**

```bash
python -m inspectra.shortcuts.cli shell "Investigue a empresa X sob tous aspectos"
python -m inspectra.shortcuts.cli shell "Compare os gastos de Cuiaba e VG em 2025" --steps 15
```

---

### 15. `pep_check` — Verifica PEP (Pessoa Politicamente Exposta)

**Verifica se pessoa e PEP via TSE (candidatos/eleitos) + Portal da Transparencia. Retorna JSON estruturado.**

```bash
# Por nome
python -m inspectra.shortcuts.cli pep_check "JAIR BOLSONARO"

# Por CPF
python -m inspectra.shortcuts.cli pep_check --cpf 01234567890
```

**Saída JSON:** `{pep: bool, matches: [{nome, cargo, orgao, partido, uf, situacao}], total_matches}`

---

### 16. `socios` — Lista Sócios de CNPJ

**Lista quadro societário com qualificacao e data de entrada. Cache BrasilAPI.**

```bash
python -m inspectra.shortcuts.cli socios 07192414000109
python -m inspectra.shortcuts.cli socios --cnpj 07192414000109
```

**Saída JSON:** `{cnpj, razao_social, socios: [{nome, cpf_parcial, qualificacao, data_entrada}], total_socios}`

---

### 17. `geocode_lote` — Geocodifica Lote de CNPJs em Paralelo

**Geocodifica enderecos de CNPJs via Nominatim/OSM em paralelo (ThreadPoolExecutor). Cache local.**

```bash
# De CSV com coluna CNPJ
python -m inspectra.shortcuts.cli geocode_lote fornecedores.csv

# Lista direta
python -m inspectra.shortcuts.cli geocode_lote --lista 07192414000109 12345678000199

# Paralelo (8 workers)
python -m inspectra.shortcuts.cli geocode_lote fornecedores.csv --max-workers 8
```

**Saída JSON:** `{total, sucessos, falhas, resultados: [{cnpj, lat, lon, tipo_zona, geocodificado}]}`

---

### 18. `metadados` — Extrai EXIF de Imagens

**Extrai metadados EXIF (GPS, camera, software, data). Detecta PII (GPS, CPF em metadata).**

```bash
# Uma imagem
python -m inspectra.shortcuts.cli metadados foto.jpg

# Todas as imagens de um diretorio
python -m inspectra.shortcuts.cli metadados --diretorio ./fotos --extensao .jpg
```

**Saída JSON:** `{arquivo, tamanho, formato, tem_exif, exif, gps, gps_str, tem_pii, pii_flags}`

---

### 19. `diario` — Busca em Diários Oficiais

**Busca em diários oficiais (AMM-MT, TCE-SC, Querido Diario federal) + macro_mt.db.**

```bash
# Busca geral
python -m inspectra.shortcuts.cli diario "LICITACAO" --uf MT

# Periodo personalizado
python -m inspectra.shortcuts.cli diario "CONTRATO" --periodo 180
```

**Saída JSON:** `{termo, uf, matches: [{data, diario, trecho, link}], total, fontes}`

---

### 20. `sql_qualquer` — SQL em Qualquer SQLite

**Executa SQL SELECT em qualquer banco SQLite (nao so macro_mt). Schema discovery automatico.**

```bash
# Query
python -m inspectra.shortcuts.cli sql_qualquer shared_data/macro_mt/macro_mt.db \
  "SELECT municipio, SUM(valor) FROM despesas GROUP BY municipio LIMIT 10"

# Ver schema
python -m inspectra.shortcuts.cli sql_qualquer shared_data/macro_mt/macro_mt.db --schema

# Tabela especifica
python -m inspectra.shortcuts.cli sql_qualquer shared_data/macro_mt/macro_mt.db --tabela despesas
```

**Seguranca:** apenas SELECT; DML/DDL bloqueados.

---

### 21. `csv_diff` — Diff Entre Dois CSVs

**Compara dois CSVs: linhas adicionadas, removidas, alteradas. Detecta mudanca de schema.**

```bash
python -m inspectra.shortcuts.cli csv_diff compras_jan.csv compras_fev.csv --chave cnpj
python -m inspectra.shortcuts.cli csv_diff a.csv b.csv --chave id --saida diff.json
```

**Saída JSON:** `{arquivo_a, arquivo_b, totais: {adicionados, removidos, alterados}, adicionados, removidos, alterados, schema_diff}`

---

### 22. `openwebui` — Gerencia Open WebUI Docker

```bash
# Verificar status
python -m inspectra.shortcuts.cli openwebui check

# Instalar custom tools no container
python -m inspectra.shortcuts.cli openwebui install

# Reiniciar container
python -m inspectra.shortcuts.cli openwebui restart

# Ver logs
python -m inspectra.shortcuts.cli openwebui logs --lines 100
```

---

## Atalhos de Batch (scripts单独的)

```bash
# Classificar todos os achados via LLM
python -m inspectra.shortcuts.batch_classify 2025

# Regenerar dossiês de fornecedores
python -m inspectra.shortcuts.regen_dossies --limite 20

# Job diário (agendar no Windows Task Scheduler)
python -m inspectra.shortcuts.cron_monitor
```

---

## API Python

Todos os atalhos podem ser importados como módulo Python:

```python
import sys
sys.path.insert(0, "src")
import os
os.environ["INSPECTA_RAIZ"] = r"D:\Dev\EnemyDisclosure"

# Via CLI
from inspectra.shortcuts.ollama import cmd_chat, cmd_embed
from inspectra.shortcuts.osint import investigar_cnpj, investigar_dominio
from inspectra.shortcuts.due_diligence import investigar
from inspectra.shortcuts.relatorio import de_json, de_html
from inspectra.shortcuts.sancoes import _buscar_em_csv
from inspectra.shortcuts.pep_check import check_pep
from inspectra.shortcuts.socios import listar_socios
from inspectra.shortcuts.geocode_lote import geocode_lote
from inspectra.shortcuts.metadados import extrair_metadados
from inspectra.shortcuts.diario import buscar_diario
from inspectra.shortcuts.sql_qualquer import executar_sql
from inspectra.shortcuts.csv_diff import csv_diff

# Vertical EnemyDisclosure
from inspectra.verticals.enemy import EnemyDisclosure
ed = EnemyDisclosure()
ed.investigar_fornecedor("COSTA OESTE")
ed.dossie_fornecedor("07192414000109")
ed.listar_sancoes("07192414000109")
```

---

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `INSPECTA_RAIZ` | `Path(__file__).parents[3]` | Diretório raiz dos dados |
| `PYTHONPATH` | `src` | Path para importar `inspectra` sem pip install |

---

## Modelos Disponíveis (Ollama local)

| Modelo | Tamanho | Context | Capabilities |
|--------|---------|---------|--------------|
| `gemma4-26b` | 14 GB | 262k | tools, thinking |
| `gemma4:latest` | 9.6 GB | — | tools, thinking |
| `mythos9b` | 5.6 GB | 1M | — |
| `llama3.1:8b` | 4.9 GB | 131k | tools |
| `qwen2.5:1.5b` | 986 MB | 32k | tools |
| `nomic-embed-text` | 274 MB | — | embedding |
| `gemma3:latest` | 3.3 GB | — | — |

---

## Status: Funcionalidade de Cada Atalho

| Atalho | Status | Notas |
|--------|--------|-------|
| `ollama` | ✅ OK | Testado com gemma4 |
| `osint cnpj` | ✅ OK | BrasilAPI + sanções + macro_mt |
| `osint dominio` | ✅ OK | WHOIS + DNS + HTTP headers |
| `osint empresa` | ✅ OK | macro_mt + LLM |
| `osint ip` | ✅ OK | gethostbyaddr |
| `due_diligence` | ✅ OK | QSA + sanções + macro_mt + PGFN |
| `relatorio` | ✅ OK | markdown + HTML, demo funcionando |
| `investigar` | ✅ OK | CodingAgent com 11 tools |
| `sancoes` | ✅ OK | Leitura direta dos CSVs |
| `buscar` | ✅ OK | Embeddings + similaridade cosseno |
| `sql` | ✅ OK | Gera SQL via LLM |
| `analise` | ✅ OK | Chama core.analises.rodar |
| `ranking` | ✅ OK | 3 modos (valor/cnpj/cross) |
| `dossie` | ✅ OK | Mini-dossiê + BrasilAPI |
| `cronograma` | ✅ OK | Análise mensal + picos |
| `pessoas` | ✅ OK | TSE parquet + QSA |
| `shell` | ✅ OK | CodingAgent livre |
| `pep_check` | ✅ OK | TSE + PortalTransparencia (JSON estruturado) |
| `socios` | ✅ OK | QSA BrasilAPI + mascara CPF (JSON estruturado) |
| `geocode_lote` | ✅ OK | Nominatim paralelo + cache (JSON estruturado) |
| `metadados` | ✅ OK | EXIF/Pillow com deteccao PII (JSON estruturado) |
| `diario` | ✅ OK | AMM-MT + TCE-SC + Querido Diario (JSON estruturado) |
| `sql_qualquer` | ✅ OK | SELECT em qualquer SQLite, schema discovery (JSON) |
| `csv_diff` | ✅ OK | Diff CSVs com schema (JSON estruturado) |
| `openwebui` | ⚠️ Precisa Docker | `docker` lib instalada |
