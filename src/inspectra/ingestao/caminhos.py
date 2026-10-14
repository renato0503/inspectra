# complexo/caminhos.py
"""Resolução de caminhos e dependências da integração ARTEX + REA.

Nada aqui é hard-coded em relação ao diretório de origem: tudo pode ser
apontado por variável de ambiente. Os scripts do *api-recon* já vêm
vendorizados dentro do projeto (``complexo/vendor/api-recon/scripts``), então
o recon estático/runtime funciona mesmo sem o diretório ``D:\\Dev\\Complexo``.
As ferramentas REA e playwright-cli são externas e detectadas em runtime.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# ── Raiz do repositório EnemyDisclosure e desta pasta ──────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
COMPLEXO_DIR = Path(__file__).resolve().parent

# ── Scripts vendorizados do api-recon (ARTEX) ──────────────────────────────
VENDOR_DIR = COMPLEXO_DIR / "vendor"
API_RECON_DIR = VENDOR_DIR / "api-recon"
API_RECON_SCRIPTS = API_RECON_DIR / "scripts"

HARVEST_STATIC = API_RECON_SCRIPTS / "harvest_static.py"
SPIDER_MPA = API_RECON_SCRIPTS / "spider_mpa.py"
RUNTIME_HARVEST = API_RECON_SCRIPTS / "runtime_harvest.js"
PRELOAD_JS = API_RECON_SCRIPTS / "preload.js"
EXTRACT_ROUTE_MAP = API_RECON_SCRIPTS / "extract_route_map.py"
BUILD_PERM_TREE = API_RECON_SCRIPTS / "build_perm_tree.py"

# Onde o api-recon guarda o output por defeito (quando nenhum outdir é dado)
RECON_RAIZ = REPO_ROOT / "shared_data" / "recon"


def _env_path(nome: str) -> Path | None:
    v = os.getenv(nome, "").strip()
    return Path(v) if v else None


# ── Diretórios-fonte do Complexo (opcionais) ───────────────────────────────
def artex_home() -> Path:
    """Diretório do ARTEX (env ENEMY_ARTEX_HOME, senão D:\\Dev\\Complexo\\ARTEX)."""
    return _env_path("ENEMY_ARTEX_HOME") or Path(r"D:\Dev\Complexo\ARTEX")


def rea_home() -> Path:
    """Diretório do REA (env ENEMY_REA_HOME, senão D:\\Dev\\Complexo\\REA)."""
    return _env_path("ENEMY_REA_HOME") or Path(r"D:\Dev\Complexo\REA")


# ── Executáveis ────────────────────────────────────────────────────────────
def python_bin() -> str:
    """Intérprete Python atual (para rodar os scripts vendorizados)."""
    return sys.executable or "python"


def node_bin() -> str:
    """Executável Node.js, se disponível no PATH."""
    return shutil.which("node") or "node"


def rea_entry() -> list[str] | None:
    """Comando para invocar o REA.

    Ordem de resolução:
      1. ENEMY_REA_BIN (comando ou caminho completo)
      2. `rea` no PATH (instalação via npm i -g rea-agents)
      3. `<rea_home>/scripts/rea.mjs` (checkout local — precisa de build)
    Devolve a lista de argv inicial ou ``None`` se nada for encontrado.
    """
    env = os.getenv("ENEMY_REA_BIN", "").strip()
    if env:
        return [env]

    exe = shutil.which("rea")
    if exe:
        return [exe]

    entry = rea_home() / "scripts" / "rea.mjs"
    if entry.exists():
        return [node_bin(), str(entry)]

    return None


def playwright_cli_entry() -> list[str] | None:
    """Comando para invocar o playwright-cli.

    Ordem: ENEMY_PLAYWRIGHT_CLI -> `playwright-cli` no PATH.
    """
    env = os.getenv("ENEMY_PLAYWRIGHT_CLI", "").strip()
    if env:
        return [env]
    exe = shutil.which("playwright-cli")
    if exe:
        return [exe]
    return None


def playwright_python_ok() -> bool:
    """True se a lib Python `playwright` está importável (recon renderizado)."""
    try:
        import playwright  # noqa: F401
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False
    return True


# ── Config MCP (REA é um servidor MCP) ─────────────────────────────────────
def mcp_config() -> dict:
    """Bloco pronto para registrar o REA como servidor MCP num cliente.

    O REA é um MCP server oficial (``npx rea-agents setup`` registra sozinho,
    mas este helper permite registrar à mão num ``.mcp.json``/``opencode.json``).
    Devolve o dict ``mcpServers`` com o comando resolvido (``rea`` no PATH,
    ``npx rea-agents`` ou o checkout local via ``scripts/rea.mjs``).
    """
    entry = rea_entry()
    if entry and entry[0].lower().endswith(("node", "node.exe")):
        comando = entry[0]
        args = [*entry[1:], "mcp"]
    elif entry:
        comando = entry[0]
        args = ["mcp"]
    else:
        comando = "npx"
        args = ["-y", "rea-agents@latest", "mcp"]
    return {"mcpServers": {"rea": {"command": comando, "args": args}}}


# ── Saídas de recon por órgão/slug ─────────────────────────────────────────
def recon_dir(slug: str, exercicio: str | int | None = None) -> Path:
    """Diretório de recon dentro do órgão, se o slug existir em orgaos/.

    Estrutura do EnemyDisclosure: ``orgaos/<Municipio>/<slug>/recon``.
    Se o slug não for encontrado, cai em ``shared_data/recon/<slug>``.
    """
    if slug:
        for municipio in (REPO_ROOT / "orgaos").glob("*"):
            alvo = municipio / slug / "recon"
            if alvo.parent.exists():
                return alvo
    base = RECON_RAIZ / slug if slug else RECON_RAIZ
    if exercicio:
        base = base / str(exercicio)
    return base


# ── Diagnóstico de disponibilidade ─────────────────────────────────────────
def diagnostico() -> dict:
    """Verifica o que está disponível para as duas ferramentas."""
    rea = rea_entry()
    pwc = playwright_cli_entry()

    rea_dist = rea_home() / "dist"
    info = {
        "python": {"ok": True, "bin": python_bin(), "versao": sys.version.split()[0]},
        "node": {"ok": shutil.which("node") is not None, "bin": node_bin()},
        "npm": {"ok": shutil.which("npm") is not None, "bin": shutil.which("npm") or ""},
        "recon_vendorizado": {
            "ok": all(
                p.exists()
                for p in (HARVEST_STATIC, SPIDER_MPA, RUNTIME_HARVEST, PRELOAD_JS)
            ),
            "dir": str(API_RECON_SCRIPTS),
        },
        "puppeteer_core": {
            "ok": (API_RECON_SCRIPTS / "node_modules" / "puppeteer-core").exists(),
            "dir": str(API_RECON_SCRIPTS),
            "obs": "necessário só para runtime_harvest.js (depth mode)",
        },
        "rea": {
            "ok": bool(rea),
            "entry": " ".join(rea) if rea else "",
            "build_ok": rea_dist.exists(),
            "home": str(rea_home()),
            "obs": "se apontar para scripts/rea.mjs sem dist/, rode npm install && npm run build",
        },
        "playwright_cli": {
            "ok": bool(pwc),
            "entry": " ".join(pwc) if pwc else "",
        },
        "playwright_python": {
            "ok": playwright_python_ok(),
            "obs": "usado pelo recon renderizado (complexo/browser.py)",
        },
    }
    return info


if __name__ == "__main__":  # pragma: no cover - utilitário
    import json

    print(json.dumps(diagnostico(), indent=2, ensure_ascii=False))
