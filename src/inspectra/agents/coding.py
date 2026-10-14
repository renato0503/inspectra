"""
Agente de codigo com function calling NATIVO (Ollama /api/chat + tools OpenAI-compatible).

Diferencas do agent.py anterior (ReAct manual):
- Usa o protocolo nativo de tool calling do Ollama (campo `tools` na mensagem)
- Modelos suportados: gemma4:latest, llama3.1:8b, qwen2.5:* (todos com capability "tools")
- Loop mais estavel, menos alucinacao, mais rapido

Uso:
    from inspectra.agents.coding import CodingAgent
    agent = CodingAgent(model="gemma4:latest")
    agent.run("Investigue o fornecedor Costa Oeste em todos os orgaos")

CLI:
    python -m core.ia.coding_agent "Rode o B17 (Benford) na prefeitura_cuiaba 2025"
"""
from __future__ import annotations
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from inspectra.llm.client import chat

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
LOGS_DIR = RAIZ_PROJETO / "shared_data" / "agent_logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# DEFINICAO DAS TOOLS (formato OpenAI)
# ============================================================
TOOLS: List[Dict] = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Executa um comando shell no diretorio do projeto. Comando e executado com subprocess. Use para tarefas como git, ls, mover arquivos, instalar pacotes, rodar scripts, etc. NAO use para tarefas destrutivas em massa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Comando shell completo"},
                    "timeout": {"type": "integer", "description": "Timeout em segundos (default 60, max 600)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Le um arquivo de texto do projeto. Retorna conteudo + numero de linhas. Use para inspecionar codigo, JSONs, CSVs de ate 500 linhas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Caminho relativo ao projeto (ex: 'core/analises/rodar.py')"},
                    "max_lines": {"type": "integer", "description": "Maximo de linhas (default 200)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Lista arquivos em um diretorio usando glob. Retorna ate 200 caminhos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Diretorio relativo ao projeto"},
                    "pattern": {"type": "string", "description": "Padrao glob (default '*')"},
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Procura por um padrao (regex) em arquivos. Retorna ate 50 matches com arquivo:linha:conteudo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex Python"},
                    "directory": {"type": "string", "description": "Diretorio (relativo ao projeto)"},
                    "file_pattern": {"type": "string", "description": "Filtro de arquivo (default '*')"},
                },
                "required": ["pattern", "directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_sql",
            "description": "Executa SELECT em um banco SQLite do projeto (read-only). Retorna ate 'limite' linhas com colunas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "banco": {"type": "string", "description": "Path do banco relativo ao projeto (ex: 'shared_data/macro_mt/macro_mt.db')"},
                    "query": {"type": "string", "description": "Query SQL (SELECT/WITH/PRAGMA)"},
                    "limite": {"type": "integer", "description": "Limite de linhas (default 50)"},
                },
                "required": ["banco", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_databases",
            "description": "Lista todos os bancos SQLite do projeto (orgaos + macro_mt).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_analysis",
            "description": "Roda uma analise do B-suite via 'python -m core.analises.rodar <orgao> <ano> --so <nome>'. Args: nome da analise (snake_case: fracionamento, benford, nepotismo, aditivos, etc), orgao (snake_case: prefeitura_cuiaba), ano (inteiro). Pode demorar ate 10 min.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string"},
                    "orgao": {"type": "string"},
                    "ano": {"type": "integer"},
                },
                "required": ["nome", "orgao", "ano"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "python_exec",
            "description": "Executa codigo Python ad-hoc em subprocess. Use para calculos, transformacoes, testes. NAO use para tarefas destrutivas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Codigo Python"},
                    "timeout": {"type": "integer", "description": "Timeout em segundos (default 30, max 120)"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Escreve conteudo em um arquivo do projeto. Cria diretorios se necessario. Cuidado: sobrescreve arquivos existentes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "conteudo": {"type": "string"},
                },
                "required": ["path", "conteudo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_achados",
            "description": "Busca semantica em todos os arquivos de analise/dossie do projeto usando embeddings. Retorna os top_k trechos mais relevantes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string"},
                    "top_k": {"type": "integer", "description": "Numero de resultados (default 5, max 20)"},
                },
                "required": ["termo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Busca uma URL publica via curl-cffi (impersonate chrome124). Retorna texto limpo (ate 5000 chars). Use para consultar APIs (BrasilAPI, PNCP), consultar CEIS/CNEP online, baixar noticias, etc. NAO funciona em sites com captcha (TSE, CNDT).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL completa (https://...)"},
                    "timeout": {"type": "integer", "description": "Timeout em segundos (default 30, max 120)"},
                    "max_chars": {"type": "integer", "description": "Max chars a retornar (default 5000)"},
                },
                "required": ["url"],
            },
        },
    },
]


SYSTEM_PROMPT = """Voce e um agente de auditoria e engenharia de dados do projeto EnemyDisclosure (D:\\Dev\\EnemyDisclosure).
Auditoria independente de gastos publicos municipais de Mato Grosso, Brasil.

REGRAS CRITICAS:
- SEMPRE use tools para obter dados reais. NUNCA invente numeros, valores ou CNPJs.
- Quando uma tool retornar dados, COAPIE OS NUMEROS EXATAMENTE como retornados. Nao arredonde, nao troque casas decimais, nao invente.
- Se a query retornou 0 linhas, reporte "0 resultados" — nao invente um valor placeholder.
- Para queries SQL, use SEMPRE filtros para excluir dados invalidos:
  * cnpj_cpf pode estar VAZIO em municipios com portal GeneXus GP (Brasnorte, Chapada, Sinop, Varzea Grande). SEMPRE use `WHERE length(cnpj_cpf) >= 11` para pegar CNPJ/CPF reais.
  * valor pode ser NULL. Use `WHERE valor IS NOT NULL AND valor > 0`.
- Para queries SQL: use o banco `shared_data/macro_mt/macro_mt.db` (todos os municipios consolidados) OU `orgaos/<Municipio>/<slug>/data/db/enemy_disclosure_<ano>.db`.
- Tabela `despesas` tem colunas: id, orgao, municipio, exercicio, data, credor, cnpj_cpf, valor, tipo_documento, modalidade, objeto, fase, dotacao, fonte.
- Para analises B: use `run_analysis`. Para busca semantica: `search_achados`. Para APIs externas: `fetch_url` (BrasilAPI, PNCP, etc).
- Quando terminar, de uma resposta final em portugues, direta e objetiva.
- Caminhos sao sempre relativos ao projeto (ex: 'core/analises/rodar.py', NAO absolutos).

EXEMPLO DE QUERY CORRETA:
```sql
SELECT SUBSTR(cnpj_cpf, 1, 8) as raiz,
       COUNT(DISTINCT municipio) as n_mun,
       SUM(valor) as total,
       COUNT(*) as n_emps
FROM despesas
WHERE length(cnpj_cpf) >= 11 AND valor > 0
GROUP BY raiz
HAVING n_mun >= 2
ORDER BY n_mun DESC, total DESC LIMIT 10;
```
"""


# ============================================================
# IMPLEMENTACOES DAS TOOLS (safety wrappers)
# ============================================================

_DENY_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+\\",
    r"del\s+/[sf]\s+/q\s+[a-z]:\\",
    r"format\s+[a-z]:",
    r"diskpart",
    r"reg\s+delete",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",  # fork bomb
    r"curl\s+.*\|\s*bash",
    r"curl\s+.*\|\s*sh",
]


def _safe_path(rel: str) -> Optional[Path]:
    """Resolve rel ao projeto. Retorna None se escapar."""
    if not rel:
        return None
    try:
        p = (RAIZ_PROJETO / rel).resolve()
        if not str(p).startswith(str(RAIZ_PROJETO.resolve())):
            return None
        return p
    except Exception:
        return None


def _is_safe_command(cmd: str) -> Optional[str]:
    """Retorna None se ok, ou mensagem de erro se bloqueado."""
    for pat in _DENY_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            return f"ERRO: comando bloqueado por politica de seguranca (padrao '{pat}')."
    return None


def tool_bash(command: str, timeout: int = 60) -> str:
    if not (1 <= timeout <= 600):
        timeout = 60
    if (msg := _is_safe_command(command)):
        return msg
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(RAIZ_PROJETO),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return f"ERRO: timeout ({timeout}s) executando comando."
    except Exception as e:
        return f"ERRO: {type(e).__name__}: {e}"
    out = (proc.stdout or "")[-3000:]
    err = (proc.stderr or "")[-1000:]
    rc = proc.returncode
    return f"EXITCODE={rc}\n--- stdout (ultimos 3000 chars) ---\n{out}\n--- stderr (ultimos 1000 chars) ---\n{err}"


def tool_read_file(path: str, max_lines: int = 200) -> str:
    p = _safe_path(path)
    if p is None:
        return f"ERRO: caminho invalido ou fora do projeto: '{path}'"
    if not p.exists() or not p.is_file():
        return f"ERRO: arquivo nao existe: '{path}'"
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return f"ERRO leitura: {e}"
    txt = "".join(lines[:max_lines])
    if len(lines) > max_lines:
        txt += f"\n... ({len(lines)-max_lines} linhas adicionais omitidas)"
    return txt


def tool_list_files(directory: str, pattern: str = "*") -> str:
    d = _safe_path(directory)
    if d is None or not d.exists() or not d.is_dir():
        return f"ERRO: diretorio invalido: '{directory}'"
    try:
        paths = sorted(d.glob(pattern))
    except Exception as e:
        return f"ERRO glob: {e}"
    if not paths:
        return "(vazio)"
    return "\n".join(p.relative_to(RAIZ_PROJETO).as_posix() for p in paths[:200])


def tool_grep(pattern: str, directory: str, file_pattern: str = "*") -> str:
    d = _safe_path(directory)
    if d is None:
        return f"ERRO: diretorio invalido: '{directory}'"
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"ERRO regex: {e}"
    matches = []
    for f in d.rglob(file_pattern):
        if not f.is_file():
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            if rx.search(line):
                matches.append(f"{f.relative_to(RAIZ_PROJETO).as_posix()}:{i}: {line.rstrip()[:200]}")
                if len(matches) >= 50:
                    break
        if len(matches) >= 50:
            break
    if not matches:
        return "(nenhum match)"
    return "\n".join(matches)


def tool_query_sql(banco: str, query: str, limite: int = 50) -> str:
    p = _safe_path(banco)
    if p is None:
        return f"ERRO: banco invalido: '{banco}'"
    if not p.exists():
        return f"ERRO: banco nao existe: '{banco}'"
    q = query.strip().rstrip(";")
    if not re.match(r"(?is)^(select|with|pragma)\b", q):
        return "ERRO: apenas SELECT/WITH/PRAGMA."
    if not (1 <= limite <= 500):
        limite = 50
    q = re.sub(r"(?i)\blimit\s+\d+", "", q).strip()
    q += f"\nLIMIT {limite}"
    try:
        with sqlite3.connect(p) as cx:
            cur = cx.execute(q)
            rows = cur.fetchall()
            cols = [d[0] for d in (cur.description or [])] if cur.description else []
    except Exception as e:
        return f"ERRO SQL: {e}"
    if not rows:
        return f"(0 linhas)\nColunas: {cols}"
    out = [f"Linhas: {len(rows)}  Colunas: {cols}"]
    for r in rows:
        cells = [str(v) if v is not None else "NULL" for v in r]
        out.append("  " + " | ".join(cells))
    return "\n".join(out)


def tool_list_databases() -> str:
    bases = []
    for orgaos in (RAIZ_PROJETO / "orgaos").iterdir():
        if not orgaos.is_dir():
            continue
        for slug in orgaos.iterdir():
            if not slug.is_dir():
                continue
            db_dir = slug / "data" / "db"
            if db_dir.exists():
                for db in db_dir.glob("*.db"):
                    bases.append(str(db.relative_to(RAIZ_PROJETO)))
    macro = RAIZ_PROJETO / "shared_data" / "macro_mt" / "macro_mt.db"
    if macro.exists():
        bases.append(str(macro.relative_to(RAIZ_PROJETO)))
    if not bases:
        return "(nenhum banco)"
    return "\n".join(bases)


def tool_run_analysis(nome: str, orgao: str, ano: int) -> str:
    if not re.match(r"^[a-z0-9_]+$", nome) or not re.match(r"^[a-z0-9_]+$", orgao):
        return "ERRO: nome e orgao devem ser snake_case."
    if not (2000 <= ano <= 2030):
        return "ERRO: ano fora de faixa razoavel."
    cmd = [sys.executable, "-m", "core.analises.rodar", orgao, str(ano), "--so", nome]
    try:
        proc = subprocess.run(cmd, cwd=str(RAIZ_PROJETO), capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return "ERRO: timeout (>10min)."
    out = (proc.stdout or "")[-2500:]
    err = (proc.stderr or "")[-1000:]
    return f"EXITCODE={proc.returncode}\n--- stdout (ultimos 2500) ---\n{out}\n--- stderr (ultimos 1000) ---\n{err}"


def tool_python_exec(code: str, timeout: int = 30) -> str:
    if not (1 <= timeout <= 120):
        timeout = 30
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(RAIZ_PROJETO),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return f"ERRO: timeout ({timeout}s)."
    except Exception as e:
        return f"ERRO: {type(e).__name__}: {e}"
    out = (proc.stdout or "")[-2500:]
    err = (proc.stderr or "")[-1000:]
    return f"EXITCODE={proc.returncode}\n--- stdout ---\n{out}\n--- stderr ---\n{err}"


def tool_write_file(path: str, conteudo: str) -> str:
    p = _safe_path(path)
    if p is None:
        return f"ERRO: caminho invalido: '{path}'"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(conteudo, encoding="utf-8")
        return f"OK: escrito {len(conteudo)} chars em {path}"
    except Exception as e:
        return f"ERRO: {e}"


def tool_search_achados(termo: str, top_k: int = 5) -> str:
    top_k = max(1, min(top_k, 20))
    try:
        from inspectra.llm.client import embed
    except ImportError:
        return "ERRO: ollama_client indisponivel."
    candidatos = []
    for path in RAIZ_PROJETO.glob("orgaos/*/*/data/export/*.json"):
        try:
            txt = path.read_text(encoding="utf-8", errors="replace")
            if 100 < len(txt) < 50000:
                candidatos.append((path, txt))
        except Exception:
            pass
    if not candidatos:
        return "(nenhum arquivo de analise encontrado)"
    try:
        vec_query = embed(termo)
    except Exception as e:
        return f"ERRO embedding: {e}"
    chunks = []
    for path, txt in candidatos[:30]:
        for i in range(0, len(txt), 800):
            trecho = txt[i:i + 1200]
            if len(trecho.strip()) < 80:
                continue
            try:
                v = embed(trecho[:500])
                chunks.append({"path": str(path.relative_to(RAIZ_PROJETO)), "trecho": trecho, "vec": v})
            except Exception:
                pass
    if not chunks:
        return "(nenhum chunk indexado)"
    import math
    def cos(a, b):
        num = sum(x * y for x, y in zip(a, b))
        da = math.sqrt(sum(x * x for x in a))
        db = math.sqrt(sum(x * x for x in b))
        return num / (da * db) if da and db else 0.0
    chunks.sort(key=lambda c: cos(vec_query, c["vec"]), reverse=True)
    out = [f"Top {top_k} para '{termo}':"]
    for i, c in enumerate(chunks[:top_k], 1):
        out.append(f"\n--- {i}. {c['path']} (sim={cos(vec_query, c['vec']):.3f}) ---")
        out.append(c["trecho"][:600])
    return "\n".join(out)


# Allowlist para fetch_url (seguranca contra SSRF)
_FETCH_DENY = re.compile(
    r"^(https?://)?(localhost|127\.|10\.|192\.168\.|0\.|169\.254\.)",
    re.IGNORECASE,
)


def tool_fetch_url(url: str, timeout: int = 30, max_chars: int = 5000) -> str:
    if not (1 <= timeout <= 120):
        timeout = 30
    max_chars = max(100, min(max_chars, 30000))
    if not url.startswith(("http://", "https://")):
        return "ERRO: URL deve comecar com http:// ou https://"
    if _FETCH_DENY.match(url):
        return "ERRO: URL aponta para rede local/privada. Bloqueado por politica."
    try:
        try:
            from curl_cffi import requests as cffi_requests
            r = cffi_requests.get(url, impersonate="chrome124", timeout=timeout, allow_redirects=True)
        except ImportError:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return f"HTTP OK\n\n{body[:max_chars]}"
        if r.status_code >= 400:
            return f"ERRO HTTP {r.status_code} para {url}"
        texto = r.text if hasattr(r, "text") else r.content.decode("utf-8", errors="replace")
        # Limpar HTML basico se vier
        if "<html" in texto.lower()[:200]:
            texto = re.sub(r"<script[^>]*>.*?</script>", "", texto, flags=re.DOTALL | re.IGNORECASE)
            texto = re.sub(r"<style[^>]*>.*?</style>", "", texto, flags=re.DOTALL | re.IGNORECASE)
            texto = re.sub(r"<[^>]+>", " ", texto)
            texto = re.sub(r"\s+", " ", texto)
        return f"HTTP {r.status_code}\nURL: {url}\nTamanho: {len(texto)} chars\n\n{texto[:max_chars]}"
    except Exception as e:
        return f"ERRO fetch: {type(e).__name__}: {e}"


TOOL_DISPATCH: Dict[str, Callable] = {
    "bash": tool_bash,
    "read_file": tool_read_file,
    "list_files": tool_list_files,
    "grep": tool_grep,
    "query_sql": tool_query_sql,
    "list_databases": tool_list_databases,
    "run_analysis": tool_run_analysis,
    "python_exec": tool_python_exec,
    "write_file": tool_write_file,
    "search_achados": tool_search_achados,
    "fetch_url": tool_fetch_url,
}


# ============================================================
# AGENT LOOP
# ============================================================

class CodingAgent:
    def __init__(
        self,
        model: str = "gemma4:latest",
        max_steps: int = 15,
        temperatura: float = 0.2,
    ):
        self.model = model
        self.max_steps = max_steps
        self.temperatura = temperatura
        self.history: List[Dict] = []

    def _executar_tool(self, name: str, args: Dict) -> str:
        fn = TOOL_DISPATCH.get(name)
        if not fn:
            return f"ERRO: tool '{name}' nao existe."
        try:
            return fn(**args)
        except Exception as e:
            return f"ERRO executando {name}: {type(e).__name__}: {e}"

    def _log_step(self, log_file: Path, **kw) -> None:
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(kw, ensure_ascii=False, default=str) + "\n")

    def run(self, tarefa: str, verbose: bool = True) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = LOGS_DIR / f"coding_{ts}.jsonl"
        self.history = [{"role": "user", "content": tarefa}]
        self._log_step(log_file, event="start", model=self.model, tarefa=tarefa)

        for step in range(1, self.max_steps + 1):
            t0 = time.time()
            try:
                msg = chat(
                    self.model,
                    "",
                    system=SYSTEM_PROMPT,
                    temperatura=self.temperatura,
                    history=self.history,
                    tools=TOOLS,
                )
            except Exception as e:
                return f"ERRO no LLM: {e}"
            dt = time.time() - t0

            tool_calls = msg.get("tool_calls") or []
            content = msg.get("content", "") or ""

            assistant_msg = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        }
                    }
                    for tc in tool_calls
                ]
            self.history.append(assistant_msg)

            if verbose:
                print(f"\n=== Step {step} ({dt:.1f}s) ===")
                if content:
                    print(f"[conteudo] {content[:300]}")
                for tc in tool_calls:
                    fn = tc["function"]["name"]
                    args = tc["function"].get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {"raw": args}
                    print(f"[tool_call] {fn}({json.dumps(args, ensure_ascii=False)[:200]})")

            self._log_step(
                log_file, step=step, dt=round(dt, 1),
                content=content[:500],
                tool_calls=[tc["function"]["name"] for tc in tool_calls],
            )

            if not tool_calls:
                if verbose:
                    print("\n" + "=" * 60 + "\nRESPOSTA FINAL\n" + "=" * 60)
                self._log_step(log_file, event="final", answer=content)
                return content

            for tc in tool_calls:
                fn = tc["function"]["name"]
                args = tc["function"].get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                observation = self._executar_tool(fn, args)
                self.history.append({"role": "tool", "content": observation[:8000]})
                if verbose:
                    preview = observation[:300].replace("\n", "\n    ")
                    print(f"[observation {fn}]\n    {preview}")
                self._log_step(log_file, tool=fn, observation=observation[:500])

        return "Limite de etapas atingido sem finalizacao explicita."


def main():
    import argparse
    p = argparse.ArgumentParser(description="Coding agent (Ollama function calling nativo)")
    p.add_argument("tarefa", nargs="*")
    p.add_argument("--model", default="gemma4:latest")
    p.add_argument("--steps", type=int, default=15)
    p.add_argument("--stdin", action="store_true")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    if args.stdin:
        tarefa = sys.stdin.read().strip()
    elif args.tarefa:
        tarefa = " ".join(args.tarefa)
    else:
        tarefa = input("Tarefa> ")
    agent = CodingAgent(model=args.model, max_steps=args.steps)
    resp = agent.run(tarefa, verbose=not args.quiet)
    print("\n" + "=" * 60)
    print("RESPOSTA FINAL:")
    print("=" * 60)
    print(resp)


if __name__ == "__main__":
    main()