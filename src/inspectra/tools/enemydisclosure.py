"""
Tools do EnemyDisclosure para Open WebUI.
Cole o conteúdo deste arquivo em Workspace > Tools > + > Create Tool
no Open WebUI (http://localhost:3000), depois ative em uma conversa.
"""
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Optional

RAIZ_PROJETO = Path("D:/Dev/EnemyDisclosure")


def _safe_path(rel: str) -> Optional[Path]:
    if not rel:
        return None
    try:
        p = (RAIZ_PROJETO / rel).resolve()
        if not str(p).startswith(str(RAIZ_PROJETO.resolve())):
            return None
        return p
    except Exception:
        return None


class Tools:
    def __init__(self):
        self.cwd = str(RAIZ_PROJETO)

    def listar_bancos(self) -> str:
        """
        Lista todos os bancos SQLite disponiveis no projeto EnemyDisclosure
        (todos os orgaos + macro_mt.db). Retorna JSON com path e tabelas.

        :return: JSON string
        """
        bancos = []
        for orgaos in (RAIZ_PROJETO / "orgaos").iterdir():
            if not orgaos.is_dir():
                continue
            for slug in orgaos.iterdir():
                if not slug.is_dir():
                    continue
                db_dir = slug / "data" / "db"
                if db_dir.exists():
                    for db in db_dir.glob("*.db"):
                        bancos.append({"path": str(db.relative_to(RAIZ_PROJETO)), "nome": db.stem})
        macro = RAIZ_PROJETO / "shared_data" / "macro_mt" / "macro_mt.db"
        if macro.exists():
            bancos.append({"path": str(macro.relative_to(RAIZ_PROJETO)), "nome": "macro_mt"})
        return json.dumps(bancos, ensure_ascii=False, indent=2)

    def consultar_sql(self, banco: str, query: str, limite: int = 50) -> str:
        """
        Executa SELECT read-only em um banco SQLite do projeto EnemyDisclosure.
        Use o banco 'shared_data/macro_mt/macro_mt.db' para queries cross-municipal.

        REGRAS: apenas SELECT/WITH/PRAGMA. Limite padrao 50. Para CNPJ use sempre
        WHERE length(cnpj_cpf) >= 11 AND valor > 0.

        :param banco: path do banco relativo ao projeto (ex: 'shared_data/macro_mt/macro_mt.db')
        :param query: query SQL (SELECT/WITH/PRAGMA)
        :param limite: maximo de linhas (default 50)
        :return: resultado formatado
        """
        p = _safe_path(banco)
        if not p:
            return f"ERRO: banco invalido: {banco}"
        if not p.exists():
            return f"ERRO: banco nao existe: {banco}"
        q = query.strip().rstrip(";")
        if not re.match(r"(?is)^(select|with|pragma)\b", q):
            return "ERRO: apenas SELECT/WITH/PRAGMA."
        if not (1 <= limite <= 500):
            limite = 50
        q = re.sub(r"(?i)\blimit\s+\d+", "", q).strip() + f"\nLIMIT {limite}"
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
            out.append("  " + " | ".join(str(v) if v is not None else "NULL" for v in r))
        return "\n".join(out)

    def listar_dossies(self, top_k: int = 5) -> str:
        """
        Lista os dossies e arquivos de analise mais recentes do projeto EnemyDisclosure.

        :param top_k: quantos retornar (default 5)
        :return: lista de paths relativos
        """
        arquivos = []
        for path in RAIZ_PROJETO.glob("orgaos/*/*/data/export/*.html"):
            arquivos.append((path.stat().st_mtime, path))
        for path in RAIZ_PROJETO.glob("orgaos/*/*/data/export/*.md"):
            arquivos.append((path.stat().st_mtime, path))
        arquivos.sort(reverse=True)
        return "\n".join(
            f"{datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M')}  {p.relative_to(RAIZ_PROJETO)}"
            for t, p in arquivos[:top_k]
        )

    def ler_arquivo(self, caminho: str, max_linhas: int = 200) -> str:
        """
        Le um arquivo de texto do projeto EnemyDisclosure (ate max_linhas).

        :param caminho: path relativo ao projeto (ex: 'core/analises/rodar.py')
        :param max_linhas: maximo de linhas (default 200)
        :return: conteudo do arquivo
        """
        p = self._safe(caminho)
        if not p or not p.exists() or not p.is_file():
            return f"ERRO: arquivo nao encontrado: {caminho}"
        try:
            with p.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return f"ERRO: {e}"
        txt = "".join(lines[:max_linhas])
        if len(lines) > max_linhas:
            txt += f"\n... ({len(lines) - max_linhas} linhas omitidas)"
        return txt

    def grep(self, padrao: str, diretorio: str = "core", tipo_arquivo: str = "*.py") -> str:
        """
        Procura por um regex em arquivos do projeto. Retorna ate 30 matches.

        :param padrao: regex Python
        :param diretorio: subdiretorio (default 'core')
        :param tipo_arquivo: extensao (default '*.py')
        :return: matches formato arquivo:linha:conteudo
        """
        p = self._safe(diretorio)
        if not p:
            return f"ERRO: diretorio invalido: {diretorio}"
        try:
            rx = re.compile(padrao)
        except re.error as e:
            return f"ERRO regex: {e}"
        matches = []
        for f in p.rglob(tipo_arquivo):
            if not f.is_file():
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if rx.search(line):
                    matches.append(f"{f.relative_to(RAIZ_PROJETO)}:{i}: {line.rstrip()[:200]}")
                    if len(matches) >= 30:
                        break
            if len(matches) >= 30:
                break
        return "\n".join(matches) if matches else "(nenhum match)"

    def rodar_analise_b(self, orgao: str, ano: int, nome: str) -> str:
        """
        Roda uma analise do B-suite do EnemyDisclosure.

        :param orgao: slug do orgao (prefeitura_cuiaba, camara_vg, ...)
        :param ano: exercicio (ex: 2025)
        :param nome: nome snake_case (fracionamento, benford, nepotismo, aditivos, ...)
        :return: stdout/resultado da analise
        """
        if not re.match(r"^[a-z0-9_]+$", orgao) or not re.match(r"^[a-z0-9_]+$", nome):
            return "ERRO: orgao e nome devem ser snake_case."
        if not (2000 <= ano <= 2030):
            return "ERRO: ano fora de faixa."
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "core.analises.rodar", orgao, str(ano), "--so", nome],
                cwd=str(RAIZ_PROJETO), capture_output=True, text=True, timeout=600,
            )
        except subprocess.TimeoutExpired:
            return "ERRO: timeout (>10min)."
        return f"EXITCODE={proc.returncode}\n--- stdout ---\n{proc.stdout[-2500:]}\n--- stderr ---\n{proc.stderr[-1000:]}"

    def _safe(self, rel: str) -> Optional[Path]:
        return _safe_path(rel)