# Inspectra

**Análise forense e inteligência industrial com IAs locais (Ollama + function calling).**

*22 atalhos CLI de auditoria, OSINT e investigação — prontos para agentes LLM chamarem.*

[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://pypi.org/project/inspectra/)
[![state](https://img.shields.io/badge/State-v0.1.0--beta-green.svg)]()

---

## O que é

Inspectra é uma biblioteca Python + CLI para agentes LLM fazerem **investigação forense**
em dados públicos brasileiros — CNPJ, PEP, sócios, sanções federais, diários oficiais,
geocodificação, diff de CSVs — tudo rodando **100% local**, sem enviar dados para nuvens.

Derivado do projeto [EnemyDisclosure](https://github.com/renato0503/EnemyDisclosure)
(auditoria de gastos públicos de Mato Grosso), mas **genérico**: serve para qualquer
domínio que use dados públicos brasileiros.

> Este projeto usa **Ollama local** (`127.0.0.1:11434`) para chamadas de modelo.
> Nenhum dado sai da sua máquina.

---

## Instalação

```bash
pip install -e .                    # instalação básica
pip install -e ".[llm]"             # + suporte a Ollama (chat, embeddings)
pip install -e ".[ingestao]"        # + Playwright para raspagem de páginas JS-heavy
pip install -e ".[busca]"           # + curl-cffi para HTTP com fingerprints de browser
pip install -e ".[tudo]"            # tudo exceto Ollama (roda localmente)
```

Ou simplesmente clone e use:

```bash
git clone https://github.com/renato0503/inspectra.git
cd inspectra
pip install -e .

# Configure o diretório de dados (opcional — padrão = parents[3] do módulo)
set INSPECTA_RAIZ=D:\Dev\EnemyDisclosure
```

### Requisitos

- Python 3.10+
- Ollama rodando em `127.0.0.1:11434` (para recursos de LLM)
- [Playwright](https://playwright.dev/python/) (`pip install playwright && playwright install chromium`) para `ingestao`
- [curl-cffi](https://github.com/0c-0x0c/curl-cffi) para `busca`

---

## Quick Start

```bash
# Após pip install -e .

# Verificar se Ollama está a responder
python -m inspectra.shortcuts.cli ollama list

# Verificar se o Ollama聊天 funciona
python -m inspectra.shortcuts.cli ollama chat "Qual a capital de Mato Grosso?"

# Checar PEP (Pessoa Politicamente Exposta)
python -m inspectra.shortcuts.cli pep_check "JAIR BOLSONARO"

# Listar sócios de uma empresa
python -m inspectra.shortcuts.cli socios 07192414000109

# Sanções de um CNPJ
python -m inspectra.shortcuts.cli inspectra-osint cnpj 07192414000109

# SQL em qualquer SQLite
python -m inspectra.shortcuts.cli inspectra-sqlx shared_data/macro_mt/macro_mt.db \
  "SELECT municipio, SUM(valor) FROM despesas GROUP BY municipio LIMIT 5"

# Diff entre CSVs
python -m inspectra.shortcuts.cli inspectra-csvdiff a.csv b.csv --chave cnpj
```

---

## Os 22 atalhos

### Investigação de CNPJ / empresa

| Comando | Descrição |
|---------|-----------|
| `pep_check` | Verifica se pessoa é PEP via TSE + Portal da Transparência |
| `socios` | Lista quadro societário (QSA) com CPF mascarado |
| `inspectra-osint cnpj` | CNPJ: razão social, situação, CNAE, endereço, QSA |
| `inspectra-osint empresa` | OSINT por nome de empresa (macro_mt + LLM) |
| `due_diligence` | Dossiê completo: QSA + sanções + macro_mt + PGFN |
| `inspectra-dd` | Alias para due_diligence |

### Sanções e compliance

| Comando | Descrição |
|---------|-----------|
| `inspectra-osint` | CEIS / CNEP / CEPIM / Leniência (busca por CNPJ) |
| `sancoes` | Leitura direta dos CSVs de sanções federais |

### Dados públicos

| Comando | Descrição |
|---------|-----------|
| `inspectra-sqlx` | SELECT em qualquer SQLite com schema discovery automático |
| `inspectra-diario` | Busca em diários oficiais (AMM-MT, TCE-SC, Querido Diário) |
| `inspectra-geo` | Geocodificação de CNPJs em lote via Nominatim (paralelo, 8 workers) |
| `inspectra-meta` | Extração EXIF de imagens (GPS, câmera, PII em metadados) |
| `csv_diff` | Diff entre dois CSVs: adicionados / removidos / alterados |

### LLM e agentes

| Comando | Descrição |
|---------|-----------|
| `ollama chat` | Chat com function calling via Ollama local |
| `ollama embed` | Gera embeddings (nomic-embed-text) |
| `ollama list` | Lista modelos disponíveis no Ollama |
| `inspectra-relatorio` | Gera relatório em Markdown ou HTML a partir de dados estruturados |
| `shell` | CodingAgent livre — passa instrução ao agente com 11 ferramentas nativas |
| `investigar` | Wrapper do CodingAgent para investigação forense |

### Análise de gastos (EnemyDisclosure como vertical)

| Comando | Descrição |
|---------|-----------|
| `analise` | Executa B-suite de análises forenses num órgão |
| `ranking` | Ranking de fornecedores (por valor / CNPJ distinto / cross-município) |
| `dossie` | Mini-dossiê de CNPJ com vínculos, sanções e base legal |
| `cronograma` | Análise temporal mensal de empenhos |
| `pessoas` | Cruzamento TSE × QSA (doadores / sócios candidatos) |

### Infra

| Comando | Descrição |
|---------|-----------|
| `inspectra-openwebui` | Gerencia Open WebUI via Docker (check / install / restart / logs) |

---

## Saída JSON padronizada

Os 7 novos atalhos (16–22) retornam **sempre** o mesmo formato:

```json
{
  "ok": true,
  "dados": { ... },
  "fonte": "BrasilAPI (cache)",
  "erro": null,
  "timestamp": "2026-10-14T19:23:45.123456",
  "prompt_hint": "Use este resultado para..."
}
```

Exemplo — `pep_check`:

```json
{
  "ok": true,
  "dados": {
    "pep": true,
    "matches": [
      {"nome": "JAIR MESSIAS BOLSONARO", "cargo": "PRESIDENTE", "orgao": "REPÚBLICA FEDERATIVA DO BRASIL", "partido": "sem partido", "uf": "SP", "situacao": "DEFERIDO"}
    ],
    "total_matches": 1
  },
  "fonte": "TSE parquet 2024 + Portal Transparência",
  "erro": null,
  "timestamp": "2026-10-14T19:23:46.123456",
  "prompt_hint": "PEP confirmado. Verifique se há conflito de interesse com contratações públicas."
}
```

---

## Entry points (scripts)

Após `pip install -e .`, estos comandos ficam disponíveis no PATH:

```
inspectra                  # CLI principal (23 subcomandos)
inspectra-osint            # OSINT rápido (cnpj/dominio/empresa/ip)
inspectra-dd               # Due diligence de CNPJ
inspectra-relatorio        # Gerador de relatórios
inspectra-ollama           # Chat + list + embeddings
inspectra-openwebui        # Gerenciador Docker do Open WebUI
inspectra-pep              # Verificação de PEP
inspectra-socios           # Lista de sócios
inspectra-geo               # Geocodificação em lote
inspectra-meta              # Extração EXIF
inspectra-diario            # Busca em diários oficiais
inspectra-sqlx              # SQL em qualquer SQLite
inspectra-csvdiff           # Diff entre CSVs
classificar                # Classifica achados via LLM
regen-dossies              # Regenera dossiês de fornecedores
cron-monitor               # Job diário (agendar no Windows Task Scheduler)
batch-classify             # Classifica em batch via LLM
```

---

## EnemyDisclosure como vertical

O Inspectra foi **originado** do EnemyDisclosure (auditoria de gastos públicos de
Mato Grosso). A vertical está disponível como classe Python:

```python
from inspectra.verticals.enemy import EnemyDisclosure

ed = EnemyDisclosure()
ed.investigar_fornecedor("COSTA OESTE")
ed.dossie_fornecedor("07192414000109")
ed.listar_sancoes("07192414000109")
```

EnemyDisclosure cobre **11 órgãos** de Mato Grosso com:
- 12 módulos forenses (B-suite): fracionamento, direcionamento, empresa de fachada,
  nepotismo, aditivos, timing eleitoral, restos a pagar, Benford, etc.
- 8 famílias de portal de transparência reconhecidas
- Cruzamento com CEIS/CNEP/CEPIM, PNCP, Radar TCE-MT, CADPREV, TSE

---

## Modelos compatíveis (Ollama)

| Modelo | Tamanho | Context | Notas |
|--------|---------|---------|-------|
| `gemma4-26b` | 14 GB | 262k | tools, thinking |
| `gemma4:latest` | 9.6 GB | — | tools, thinking |
| `mythos9b` | 5.6 GB | 1M | — |
| `llama3.1:8b` | 4.9 GB | 131k | tools |
| `qwen2.5:1.5b` | 986 MB | 32k | tools |
| `nomic-embed-text` | 274 MB | — | embeddings |

---

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `INSPECTA_RAIZ` | `Path(__file__).parents[3]` | Diretório raiz dos dados |
| `PYTHONPATH` | `src` | Para importar sem pip install |

---

## Limitações conhecidas

- **BrasilAPI**: HTTP 403 neste ambiente → cache local (`shared_data/brasilapi_cnpj.json`) é usado como fallback
- **Docker**: `openwebui_install` requer Docker Desktop rodando
- **Ollama**: nenhum dado sai da máquina — mas os modelos precisam estar baixados localmente

---

## Licença

MIT — [Renato Rosa](https://github.com/renato0503)

https://github.com/renato0503/inspectra
