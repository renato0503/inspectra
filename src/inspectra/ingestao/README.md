# `complexo/` — ARTEX + REA dentro do EnemyDisclosure

Esta pasta integra ao EnemyDisclosure as duas ferramentas de segurança do
diretório `D:\Dev\Complexo`, adaptadas ao fluxo de auditoria de gastos
públicos:

| Ferramenta | O que faz aqui | Vem de |
|---|---|---|
| **ARTEX · api-recon** | Descobre **endpoints, rotas e vendor de um portal de transparência** (SPA ou MPA) sem precisar de adapter pronto. Scripts **vendorizados** nesta pasta. | `D:\Dev\Complexo\ARTEX\skills\api-recon` (AGPL-3.0) |
| **ARTEX · playwright-cli** | Automação de browser (extração, replay de sessão, evidência visual). **Externo/opcional.** | `D:\Dev\Complexo\ARTEX\skills\playwright-cli` |
| **REA** | Reverse engineering: **inspeção de bases SQLite locais**, análise de **bundles/aplicações JS** (graph, trace de feature, comparação de versões), inspeção de **página via CDP**, **HAR/capturas de rede**, binários **.NET/Go/WASM**. **Externo/opcional.** | `D:\Dev\Complexo\REA` (MIT) |
| **ARTEX · proxy de tráfego** | Gravação MITM de sessão de portal (HAR) para alimentar o REA (`inspect-web-network-capture`). **Externo (Docker/plataforma ARTEX).** | `D:\Dev\Complexo\ARTEX` |

Além do `api-recon`, o **ARTEX completo** (Go + Next.js + PostgreSQL) é uma
plataforma de agentes de segurança com grafos de ativos/exploração, findings,
tráfego e MCP. Aqui só usamos o que serve à auditoria de gastos: recon de portal,
automação de browser e o proxy de gravação. Rodá-lo inteiro é opcional
(`D:\Dev\Complexo\ARTEX` via Docker).

### Matriz de capacidades (o que dá para fazer, hoje)

| Objetivo na auditoria | Ferramenta | Como (nesta pasta) |
|---|---|---|
| Achar o **portal de transparência** escondido em site JS-heavy | ARTEX browser render | `python -m complexo recon <url> --browser` ou `browser <url>` |
| **Identificar o vendor** (Fiorilli, GeneXus, e-Pública, Ábaco…) | ARTEX api-recon + fingerprint | `recon`, `fingerprint <jsdir>` |
| Enumerar **endpoints, rotas e parâmetros** de um portal SPA | ARTEX api-recon (depth + coverage) | `harvest`, `runtime`, `Config(coverage)` |
| Atravessar o **login de cliente** de um portal (stub/mock) | ARTEX coverage (`preload.js`) | `ApiRecon.gerar_config(runtime_mode="coverage")` |
| Automatizar browser, capturar **evidência visual/PDF** | ARTEX playwright-cli | `playwright ...` |
| Ler a estrutura de um **sistema municipal local** (SQLite) | REA | `rea-sqlite <db>` |
| Entender um **app/bundle JS** (módulos, IPC, rotas) | REA | `rea-js <path>` |
| **Traçar uma feature** dentro do app (ex.: "como sai a despesa") | REA | `rea-trace <input>` |
| **Comparar duas versões** de um app (release X vs Y) | REA | `rea-compare <left> <right>` |
| Auditar uma **sessão de portal** (HAR do DevTools) | REA | `rea-har <captura.har>` + `rea-view` (api-surface) |
| Inspecionar **binário .NET / Go / WASM** de sistema de RH/contábil | REA | `rea-managed`, `rea-go`, `rea-wasm` |
| Ver/editar **Evidence** e exportar para terceiro | REA | `rea-evidence` |
| Registrar o **REA como MCP** para o agente | REA | `python -m complexo mcp-config` |
| Grafo de **asset + exploração** (portais, fornecedores, achados) | adaptação do dual-graph do ARTEX | `grafo-resumo`, `grafo-graphml` |

> **Regra de ouro do projeto continua valendo:** indício ≠ prova; todo número
> tem fonte; uso apenas em portais/sistemas **públicos** ou cuja auditoria é
> **autorizada**.

---

## Instalação e diagnóstico

Nada precisa ser instalado para o **recon estático** — os scripts do api-recon
já estão vendorizados em `complexo/vendor/api-recon/scripts` e usam só a stdlib
do Python.

Opcionais:

```powershell
# 1) runtime (depth mode) — Puppeteer para navavegar o portal e gravar as chamadas
cd complexo\vendor\api-recon\scripts
npm install                # instala puppeteer-core (usa o Node do sistema)

# 2) playwright-cli (extração/evidência) — se for usar
#    npm i -g <playwright-cli>   ou definir ENEMY_PLAYWRIGHT_CLI

# 3) REA — se for usar inspeção de SQLite/JS/web
#    npm i -g rea-agents                          (instalação global)
#    # OU usar o checkout local (precisa de build):
#    cd D:\Dev\Complexo\REA; npm install; npm run build
```

Diagnóstico do que está pronto:

```powershell
python -m complexo doctor
```

### Variáveis de ambiente (opcionais)

| Variável | Para quê | Default |
|---|---|---|
| `ENEMY_ARTEX_HOME` | diretório do ARTEX | `D:\Dev\Complexo\ARTEX` |
| `ENEMY_REA_HOME` | diretório do REA | `D:\Dev\Complexo\REA` |
| `ENEMY_REA_BIN` | comando/caminho do REA | `rea` no PATH → `<REA_HOME>\scripts\rea.mjs` |
| `ENEMY_PLAYWRIGHT_CLI` | comando do playwright-cli | `playwright-cli` no PATH |

---

## Uso — linha de comando

```powershell
# Recon completo de um portal (por URL): harvest + fingerprint + site_map
python -m complexo recon https://transparencia.x.mt.gov.br

# Recon de um órgão já cadastrado (usa a base de core.config.PERFIS)
python -m complexo recon --slug camara_vg

# Site institucional JS-heavy: REPENSAR a home no Chromium e achar o portal
python -m complexo recon https://prefeitura.x.mt.gov.br --browser
python -m complexo browser https://prefeitura.x.mt.gov.br          # só a descoberta

# Portal server-rendered (MPA) — crawl BFS
python -m complexo recon https://portal.x.gov.br --mpa

# Com runtime (depth mode) — precisa de puppeteer-core
python -m complexo recon https://portal.x.gov.br --runtime

# Só o harvest estático
python -m complexo harvest https://portal.x.gov.br --outdir shared_data\recon\portal_x

# Fingerprint de vendor a partir dos bundles já baixados
python -m complexo fingerprint shared_data\recon\portal_x\js

# Listar endpoints/rotas de um recon já feito
python -m complexo endpoints shared_data\recon\portal_x

# REA — inspeção de base SQLite local (sem executar SQL arbitrário)
python -m complexo rea-sqlite caminho\sistema.db --schema-scope database
python -m complexo rea-sqlite caminho\sistema.db --table despesas --column credor --column valor --row-limit 100

# REA — browser via CDP (abra o Chrome com --remote-debugging-port=9222 antes)
python -m complexo rea-targets http://127.0.0.1:9222
python -m complexo rea-web     http://127.0.0.1:9222 <target-id> --sources
python -m complexo rea-bundle  http://127.0.0.1:9222 <target-id> --sourcemaps

# REA — binário .NET de sistema municipal
python -m complexo rea-managed caminho\SistemaContabilidade.exe --members --type Dados.Financeiros
python -m complexo rea-go caminho\sistema_go.exe            # metadados de build Go
python -m complexo rea-wasm caminho\modulo.wasm             # artefato WASM

# REA — sessão de portal gravada (HAR do DevTools / proxy ARTEX)
python -m complexo rea-har sessao.har --record 0 --record 2
# ... e a superfície de API da captura (method+origin+path template):
python -m complexo rea-view '{"source":{"kind":"inline","evidence":{}},"view":{"kind":"api-surface"}}'

# REA — traçar uma feature e comparar versões de app
python -m complexo rea-trace trace-input.json
python -m complexo rea-compare ev-versao-a.json ev-versao-b.json
python -m complexo rea-reconcile reconciliation-input.json

# REA — prontidão e providers nativos
python -m complexo rea-providers
python -m complexo rea-doctor --provider ghidra

# Registrar o REA como servidor MCP (para o agente usar as ferramentas)
python -m complexo mcp-config

# playwright-cli (repassa os argumentos)
python -m complexo playwright open https://portal.x.gov.br

# Grafo de auditoria
python -m complexo grafo-resumo shared_data\recon\grafo.json
python -m complexo grafo-graphml shared_data\recon\grafo.json saida.graphml
```

---

## Uso — API Python

```python
from complexo import ReconPortal, fingerprint
from complexo.rea import REA
from complexo.grafo import GrafoAuditoria

# 1) recon de um portal novo -> escolhe o adapter automaticamente
rp = ReconPortal(slug=None, url="https://transparencia.x.mt.gov.br")
sm = rp.executar()
print(sm.vendor, sm.adapter, sm.confianca)   # ex.: "genexus_gp" "genexus_gp" "alta"

# 1b) descoberta renderizada (sites JS-heavy) — não faz rede além do portal
from complexo.browser import Navegador
desc = Navegador().descobrir_portal("https://prefeitura.x.mt.gov.br")
for c in desc.candidatos:            # já ordenados por score
    print(c["score"], c.get("adapter_hint"), c["href"])

# 2) fingerprint avulso
fp = fingerprint.fingerprint_jsdir("shared_data/recon/portal_x/js")

# 3) REA: auditar uma base SQLite local
rea = REA()
ok, motivo = rea.disponivel()
if ok:
    info = rea.inspect_sqlite("sistema.db", table="despesas", row_limit=50)

# 4) grafo de auditoria (asset + exploration)
g = GrafoAuditoria()
g.add_portal("https://portal.x.gov.br", vendor="genexus_gp", municipio="Sinop")
g.add_orgao("prefeitura_sinop", "Pref. Sinop", "https://portal.x.gov.br")
g.add_fornecedor("07192414000109", "Costa Oeste", sancionado=True)
g.ligar_fornecedor_orgao("07192414000109", "prefeitura_sinop", valor=16_400_000)

meta = g.nova_investigacao("Sinop", "mapear portal")
intent = g.registrar_intent(meta, "harvest_static")
g.concluir_intent(intent, fatos=["vendor=genexus_gp"],
                  achados=[{"titulo": "Costa Oeste está no CEIS"}],
                  assets_tocados=["cnpj:07192414000109"])
g.salvar("shared_data/recon/grafo.json")
print(g.fornecedores_multi_orgao())
```

---

## O que cada módulo faz

| Módulo | Responsabilidade |
|---|---|
| `caminhos.py` | resolve caminhos/executáveis; `diagnostico()`; `mcp_config()` |
| `artex.py` | `ApiRecon` (harvest/spider/runtime/perm-tree) + `gerar_config` (depth/coverage/both) + `PlaywrightCLI` |
| `browser.py` | `Navegador` (Playwright) — descoberta renderizada de portal JS-heavy |
| `rea.py` | `REA` (sqlite, js app, web CDP, managed, go, wasm, HAR, trace, compare, evidence, providers, doctor) |
| `fingerprint.py` | tabela de indicadores vendor → família de adapter |
| `grafo.py` | `GrafoAuditoria` (asset graph + exploration graph) |
| `recon.py` | `ReconPortal` → `site_map.json` + `RECON.md` (estático + renderizado) |
| `cli.py` | CLI unificada (`python -m complexo ...`) |
| `vendor/api-recon/` | scripts do api-recon do ARTEX (vendorizados) |

Para detalhes da metodologia das 5 fases do api-recon, ver
`vendor/api-recon/SKILL.md` e `vendor/api-recon/reference.md`.

### Recon renderizado (`--browser`)

O harvest estático só vê o HTML inicial. Em muitos portais municipais o menu
(com o link do portal) é montado por JavaScript, então o link não aparece no
HTML — daí o mar de "Desconhecido" no scanner macro MT. Com `--browser`, o
`ReconPortal`:

1. roda o harvest estático (como sempre);
2. **renderiza a home no Chromium** (`complexo/browser.py`) e coleta os links
   visíveis, inclusive os criados por JS;
3. pontua os candidatos a portal (texto + href) e dá uma **pista de adapter**
   pelo href/título;
4. faz harvest+fingerprint do melhor candidato e reescreve o `site_map.json`.

Requisitos: `pip install playwright && playwright install chromium`. Se faltar,
o recon **não falha** — registra a limitação e segue com o estático.

### Modos de runtime do api-recon (depth / coverage / both)

`ApiRecon.gerar_config(url, runtime_mode=...)` gera o `config.json` do ARTEX:

* **depth** — o Puppeteer percorre as rotas e grava método/params/resposta;
* **coverage** — injeta `preload.js` no document-start, **stuba a autenticação
  de cliente** e enumera a UI (páginas "escondidas" atrás de login de cliente);
* **both** — os dois (mais completo, mais lento).

Para coverage é preciso um browser MCP/DevTools que injete o preload (a lib
`preload.js` está em `vendor/api-recon/scripts`). As saídas
(`scan_raw.json`, `param_samples.json`, `api_merged.txt`, `params_merged.json`)
são lidas por `ApiRecon.coverage_artifacts()`.

> **Limite legal:** o coverage stuba apenas o gate **do cliente** para revelar
> rotas/endpoints públicos — comportamento previsto pela própria skill
> (`vendor/api-recon/SKILL.md`, seção "边界与禁止"). O backend continua
> respondendo o que é público. Nunca use para acessar dado sigiloso de sistema
> que exija credencial institucional.

---

## Saídas do recon

Em `--outdir` (default: `shared_data/recon/<slug>` ou `orgaos/<M>/<slug>/recon`):

| Arquivo | Conteúdo |
|---|---|
| `index.html` | HTML de entrada do portal |
| `js/` | bundles JS baixados |
| `api_static.txt` | endpoints encontrados nos bundles |
| `routes.txt` | rotas de frontend |
| `paths_other.txt` | outros paths |
| `chunkmap.txt` | chunks do manifesto webpack/vite |
| `config.json` | template p/ o runtime (gerado sob demanda) |
| `runtime_api.json` | chamadas reais (depth mode) |
| `site_map.json` | **resultado consolidado**: vendor, adapter, endpoints, rotas |
| `RECON.md` | relatório legível do recon |

---

## Fluxo recomendado (portal novo → dossiê)

1. `python -m complexo recon <url>` → identifica o **vendor** e o **adapter**.
   Se o site for JS-heavy, acrescente `--browser` (o link do portal pode não
   estar no HTML).
2. Se o adapter já existir em `core/adapters.py`, use o pipeline normal
   (`python run.py <slug>`). Se **não** existir, o `site_map.json` já traz os
   endpoints e rotas que o novo adapter precisa implementar.
3. Para portais com **login de cliente**, gere um `config.json` em modo
   `coverage` (`ApiRecon.gerar_config(runtime_mode="coverage")`) e rode com o
   `preload.js`; para só mapear API, use `runtime` (depth).
4. Para sistemas legados locais (SQLite, .NET, Go), use o REA antes de escrever
   ETL; para auditar uma sessão de portal já gravada, `rea-har` + `rea-view`.
5. Registre o REA como MCP (`python -m complexo mcp-config`) se quiser que o
   agente use a análise sob demanda.

---

## Limites legais (leia)

- **ARTEX** é AGPL-3.0 e destina-se a pesquisa/validação **local e autorizada**.
- **REA** é MIT, para análise **lícita** (pesquisa, disclosure coordenado,
  auditoria de software próprio/autorizado).
- O EnemyDisclosure trabalha com **dados públicos** de portais de
  transparência (LC 131/2009, Lei 12.527/2011). **Nunca** use esta pasta para
  acessar sistemas que exijam autenticação institucional sem autorização
  formal, nem para teste intrusivo de terceiros.

Ver `ATTRIBUTION.md` para créditos e licenças das ferramentas vendorizadas.
