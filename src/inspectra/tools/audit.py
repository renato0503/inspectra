"""
Ferramentas audit-specific para o agente ReAct.

Cada tool é registrada com nome, descrição e callable. O agente usa o nome
+ descrição para decidir quando chamar.

Princípios:
- Read-only por padrão. Escritas exigem confirm.
- Retornam string (texto) para o LLM consumir.
- Logging automático em shared_data/agent_logs/.
"""
from __future__ import annotations
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
LOGS_DIR = RAIZ_PROJETO / "shared_data" / "agent_logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _log(tool: str, args: Any, result: str) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    entry = {"ts": ts, "tool": tool, "args": str(args)[:500], "result": result[:2000]}
    line = json.dumps(entry, ensure_ascii=False)
    log_file = LOGS_DIR / f"agent_{datetime.now().strftime('%Y%m%d')}.jsonl"
    with log_file.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def registrar(self, nome: str, descricao: str, fn: Callable, *, args_schema: str = ""):
        self._tools[nome] = {
            "nome": nome,
            "descricao": descricao,
            "fn": fn,
            "args_schema": args_schema,
        }

    def tem(self, nome: str) -> bool:
        return nome in self._tools

    def listar(self) -> List[Dict[str, str]]:
        return [
            {"nome": t["nome"], "descricao": t["descricao"], "args": t["args_schema"]}
            for t in self._tools.values()
        ]

    def executar(self, nome: str, **kwargs) -> str:
        if nome not in self._tools:
            return f"ERRO: ferramenta '{nome}' nao existe. Disponiveis: {list(self._tools)}"
        try:
            result = self._tools[nome]["fn"](**kwargs)
            result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            result_str = f"ERRO executando {nome}: {type(e).__name__}: {e}"
        _log(nome, kwargs, result_str)
        return result_str


# ============================================================
# FERRAMENTAS READ-ONLY (seguras, sempre permitidas)
# ============================================================

def _listar_bancos() -> List[Path]:
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
                    bases.append(db)
    macro = RAIZ_PROJETO / "shared_data" / "macro_mt" / "macro_mt.db"
    if macro.exists():
        bases.append(macro)
    return bases


def tool_listar_bancos():
    """Lista os bancos SQLite disponiveis no projeto (todos os orgaos + macro_mt)."""
    bancos = []
    for db in _listar_bancos():
        rel = db.relative_to(RAIZ_PROJETO)
        try:
            with sqlite3.connect(db) as cx:
                tables = [r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            bancos.append({"path": str(rel), "tabelas": tables})
        except Exception as e:
            bancos.append({"path": str(rel), "erro": str(e)})
    return json.dumps(bancos, ensure_ascii=False, indent=2)


def tool_esquema_tabela(banco: str, tabela: str):
    """Mostra CREATE TABLE/VIEW e 5 primeiras linhas de uma tabela. banco = path relativo (ex: 'shared_data/macro_mt/macro_mt.db')."""
    db_path = (RAIZ_PROJETO / banco).resolve()
    if not db_path.exists():
        return f"ERRO: banco {banco} nao encontrado."
    if not str(db_path.resolve()).startswith(str(RAIZ_PROJETO.resolve())):
        return "ERRO: caminho fora do projeto."
    with sqlite3.connect(db_path) as cx:
        try:
            schema = cx.execute(
                "SELECT sql, type FROM sqlite_master WHERE name=? AND type IN ('table','view')",
                (tabela,),
            ).fetchone()
            if not schema:
                tables = [r[0] for r in cx.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                ).fetchall()]
                return f"ERRO: '{tabela}' nao existe. Disponiveis: {tables}"
            cur = cx.execute(f'SELECT * FROM "{tabela}" LIMIT 5')
            sample = cur.fetchall()
            cols = [d[0] for d in (cur.description or [])]
        except Exception as e:
            return f"ERRO: {e}"
    out = [f"CREATE ({schema[1].upper()}):\n{schema[0] or '(sem SQL)'}\n", f"COLUNAS: {cols}", "5 PRIMEIRAS LINHAS:"]
    for row in sample:
        out.append("  " + " | ".join(str(c) if c is not None else "NULL" for c in row))
    return "\n".join(out)


def tool_consultar_sql(banco: str, query: str, limite: int = 50):
    """Executa SELECT em um banco do projeto (read-only). Retorna ate 'limite' linhas. banco = path relativo ao projeto."""
    db_path = (RAIZ_PROJETO / banco).resolve()
    if not db_path.exists():
        return f"ERRO: banco {banco} nao encontrado."
    if not str(db_path.resolve()).startswith(str(RAIZ_PROJETO.resolve())):
        return "ERRO: caminho fora do projeto."
    q = query.strip().rstrip(";")
    if not re.match(r"(?is)^(select|with|pragma)\b", q):
        return "ERRO: apenas SELECT/WITH/PRAGMA sao permitidos."
    q = re.sub(r"(?i)\blimit\s+\d+", "", q).strip()
    q += f"\nLIMIT {limite}"
    try:
        with sqlite3.connect(db_path) as cx:
            cur = cx.execute(q)
            rows = cur.fetchall()
            cols = [d[0] for d in (cur.description or [])] if cur.description else []
    except Exception as e:
        return f"ERRO SQL: {e}"
    if not rows:
        return f"(0 linhas)\nColunas: {cols}"
    out = [f"Linhas: {len(rows)}  Colunas: {cols}"]
    for r in rows[:limite]:
        cells = [str(r[idx]) if r[idx] is not None else "NULL" for idx in range(len(cols))]
        out.append("  " + " | ".join(cells))
    if len(rows) >= limite:
        out.append(f"  ... (truncado em {limite} linhas)")
    return "\n".join(out)


def tool_listar_arquivos(diretorio: str, padrao: str = "*"):
    """Lista arquivos em um diretorio do projeto (recursivo opcional via padrao glob)."""
    d = (RAIZ_PROJETO / diretorio).resolve()
    if not d.exists() or not d.is_dir():
        return f"ERRO: diretorio '{diretorio}' nao existe."
    if not str(d).startswith(str(RAIZ_PROJETO.resolve())):
        return "ERRO: caminho fora do projeto."
    try:
        paths = sorted(d.glob(padrao))
    except Exception as e:
        return f"ERRO glob: {e}"
    if not paths:
        return "(vazio)"
    return "\n".join(p.relative_to(RAIZ_PROJETO).as_posix() for p in paths[:200])


def tool_ler_arquivo(caminho: str, max_linhas: int = 200):
    """Le um arquivo de texto do projeto (ate max_linhas)."""
    p = (RAIZ_PROJETO / caminho).resolve()
    if not p.exists() or not p.is_file():
        return f"ERRO: '{caminho}' nao existe."
    if not str(p).startswith(str(RAIZ_PROJETO.resolve())):
        return "ERRO: caminho fora do projeto."
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return f"ERRO leitura: {e}"
    txt = "".join(lines[:max_linhas])
    if len(lines) > max_linhas:
        txt += f"\n... ({len(lines) - max_linhas} linhas adicionais omitidas)"
    return txt


# ============================================================
# FERRAMENTAS DE ANALISE (side-effect: gravam JSON em disco)
# ============================================================

def tool_executar_analise_b(nome: str, orgao: str, ano: int):
    """Roda uma analise do B-suite. Ex: nome='fracionamento', orgao='prefeitura_cuiaba', ano=2025."""
    if not re.match(r"^[a-z0-9_]+$", nome):
        return "ERRO: nome deve ser snake_case (letras, numeros, underscore)."
    if not re.match(r"^[a-z0-9_]+$", orgao):
        return "ERRO: orgao deve ser snake_case."
    cmd = [sys.executable, "-m", "core.analises.rodar", orgao, str(ano), "--so", nome]
    try:
        proc = subprocess.run(cmd, cwd=str(RAIZ_PROJETO), capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return "ERRO: timeout (>10min) executando a analise."
    out = (proc.stdout or "")[-2000:]
    err = (proc.stderr or "")[-1000:]
    return f"EXITCODE={proc.returncode}\n--- stdout (ultimas 2000 chars) ---\n{out}\n--- stderr (ultimas 1000 chars) ---\n{err}"


def tool_buscar_achados(termo: str, top_k: int = 10):
    """Busca semantica em todos os arquivos de analise/dossie do projeto. Retorna os top_k trechos mais relevantes."""
    try:
        from inspectra.llm.client import embed
    except ImportError:
        return "ERRO: nao foi possivel carregar o cliente Ollama."

    candidatos = []
    for path in RAIZ_PROJETO.glob("orgaos/*/*/data/export/*.json"):
        try:
            txt = path.read_text(encoding="utf-8", errors="replace")
            if len(txt) < 50 or len(txt) > 50000:
                continue
            candidatos.append((path, txt))
        except Exception:
            pass
    for path in RAIZ_PROJETO.glob("orgaos/*/*/data/export/*.md"):
        try:
            txt = path.read_text(encoding="utf-8", errors="replace")
            if len(txt) < 50 or len(txt) > 50000:
                continue
            candidatos.append((path, txt))
        except Exception:
            pass
    if not candidatos:
        return "Nenhum arquivo de analise encontrado."

    try:
        vec_query = embed(termo)
    except Exception as e:
        return f"ERRO embedding: {e}"

    chunks: List[Dict[str, Any]] = []
    for path, txt in candidatos:
        for i in range(0, len(txt), 800):
            trecho = txt[i:i + 1200]
            if len(trecho.strip()) < 50:
                continue
            try:
                v = embed(trecho[:500])
                chunks.append({"path": str(path.relative_to(RAIZ_PROJETO)), "trecho": trecho, "vec": v})
            except Exception:
                pass
    if not chunks:
        return "Nenhum chunk indexado."

    def cos(a, b):
        import math
        num = sum(x * y for x, y in zip(a, b))
        da = math.sqrt(sum(x * x for x in a))
        db = math.sqrt(sum(x * x for x in b))
        return num / (da * db) if da and db else 0.0

    chunks.sort(key=lambda c: cos(vec_query, c["vec"]), reverse=True)
    out = [f"Top {top_k} trechos para '{termo}':"]
    for i, c in enumerate(chunks[:top_k], 1):
        out.append(f"\n--- {i}. {c['path']} (sim={cos(vec_query, c['vec']):.3f}) ---")
        out.append(c["trecho"][:600])
    return "\n".join(out)


# ============================================================
# REGISTRO PADRÃO
# ============================================================

def registrar_padrao(reg: ToolRegistry) -> None:
    reg.registrar("listar_bancos", "Lista todos os bancos SQLite disponiveis (orgaos + macro_mt) com suas tabelas.", tool_listar_bancos, args_schema="()")
    reg.registrar("esquema_tabela", "Mostra CREATE TABLE + 5 primeiras linhas. Args: banco (path relativo), tabela.", tool_esquema_tabela, args_schema="(banco: str, tabela: str)")
    reg.registrar("consultar_sql", "Executa SELECT read-only num banco. Args: banco (path relativo), query (SQL). Retorna ate 50 linhas.", tool_consultar_sql, args_schema="(banco: str, query: str, limite?: int=50)")
    reg.registrar("listar_arquivos", "Lista arquivos em um diretorio. Args: diretorio, padrao glob (default '*').", tool_listar_arquivos, args_schema="(diretorio: str, padrao?: str='*')")
    reg.registrar("ler_arquivo", "Le um arquivo de texto. Args: caminho, max_linhas (default 200).", tool_ler_arquivo, args_schema="(caminho: str, max_linhas?: int=200)")
    reg.registrar("executar_analise_b", "Roda uma analise do B-suite. Args: nome (snake_case), orgao, ano. Ex: nome='fracionamento', orgao='prefeitura_cuiaba', ano=2025.", tool_executar_analise_b, args_schema="(nome: str, orgao: str, ano: int)")
    reg.registrar("buscar_achados", "Busca semantica em todos os arquivos de analise/dossie. Args: termo, top_k (default 10).", tool_buscar_achados, args_schema="(termo: str, top_k?: int=10)")