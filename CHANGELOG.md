# Changelog

All notable changes to **Inspectra** are documented here.

Inspectra follows [Semantic Versioning](https://semver.org/) and this project adheres
to [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] — 2026-10-14

### Added

#### 22 CLI shortcuts (all with standardized JSON output)

| # | Shortcut | Description |
|---|----------|-------------|
| 1 | `ollama` | Chat, embeddings, list models via Ollama local |
| 2 | `osint cnpj` | CNPJ lookup: BrasilAPI + CEIS/CNEP + macro_mt |
| 3 | `osint dominio` | WHOIS + DNS + HTTP headers fingerprint |
| 4 | `osint empresa` | OSINT by company name via macro_mt + LLM |
| 5 | `osint ip` | Reverse DNS lookup |
| 6 | `due_diligence` | Full CNPJ dossier: QSA + sanctions + PGFN + macro_mt |
| 7 | `relatorio` | Markdown/HTML report generator |
| 8 | `investigar` | CodingAgent with 11 native tools |
| 9 | `sancoes` | CEIS / CNEP / CEPIM / Leniência CSV reader |
| 10 | `buscar` | Embeddings + cosine similarity search |
| 11 | `sql` | LLM-generated SQL for macro_mt.db |
| 12 | `analise` | Runs B-suite via core.analises.rodar |
| 13 | `ranking` | Supplier ranking by value / CNPJ count / cross-municipality |
| 14 | `dossie` | Mini-CNPJ dossier: identity, MT ties, sanctions, legal basis |
| 15 | `cronograma` | Monthly temporal analysis + peak detection |
| 16 | `pessoas` | TSE parquet × QSA (donors / candidate partners) |
| 17 | `shell` | Free-form CodingAgent session |
| 18 | `openwebui` | Open WebUI Docker management (check / install / restart / logs) |
| 19 | `pep_check` | Politically Exposed Person check via TSE + Portal Transparência |
| 20 | `socios` | QSA listing with CPF masking + BrasilAPI cache fallback |
| 21 | `geocode_lote` | Parallel Nominatim/OSM geocoding (8 workers) with cache |
| 22 | `metadados` | EXIF extraction via Pillow (GPS, camera, PII detection) |
| 23 | `diario` | Search in AMM-MT, TCE-SC, Querido Diário + macro_mt.db |
| 24 | `sql_qualquer` | SELECT on any SQLite with automatic schema discovery |
| 25 | `csv_diff` | CSV diff (added / removed / changed rows + schema diff) |

#### Architecture

- **`_output.py`**: `output()` + `print_json()` helpers — standardized JSON response
  format: `{ok, dados, fonte, erro, timestamp, prompt_hint}`
- **`verticals/enemy.py`**: `EnemyDisclosure` class wrapping B-suite, dossier,
  investigate, sanctions — **EnemyDisclosure as a drop-in vertical**
- **`pyproject.toml`**: 21 entry points (console_scripts), Python 3.11/3.12/3.13,
  optional deps: playwright, curl-cffi, docker, openai, anthropic, ollama
- **`SHORTCUTS.md`**: Complete catalog of 22 shortcuts with usage examples
- **`tests/test_shortcuts.py`**: 26 pytest tests — all passing

### Fixed

| Bug | File | Description |
|-----|------|-------------|
| Ollama `chat()` signature | `ollama.py` | `model` param → `messages` list |
| Typo in helper name | `sancoes.py` | `_buscar_em_csv_em` → `_buscar_em_csv` |
| BrasilAPI `email` field | `brasilapi.py` | `email` returned as `none` string → properly cached as `null` |
| `openwebui_install` syntax | `openwebui_install.py` | Syntax error + docker lazy import |
| `metadados.py` NoneType | `metadados.py` | `exif.get()` returned None for files without EXIF |
| RAIZ resolution | All shortcuts | Hardcoded `D:\Dev\EnemyDisclosure` → `INSPECTA_RAIZ` env var |

### Dependencies

- **Ollama**: `127.0.0.1:11434` (local)
- **Models**: gemma4-26b, gemma4:latest, mythos9b, llama3.1:8b, qwen2.5:1.5b, nomic-embed-text
- **BrasilAPI**: HTTP 403 on this machine → local cache fallback (`shared_data/brasilapi_cnpj.json`)
- **Docker**: Open WebUI management requires Docker Desktop running
- **Windows**: Python 3.12, PowerShell 5.1

---

## [0.0.0] — 2026-10-?? (initial commit)

Initial skeleton: llm/ollama.py, agents/coding_agent.py, tools/, shortcuts/ structure.
