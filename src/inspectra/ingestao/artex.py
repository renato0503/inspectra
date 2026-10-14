# complexo/artex.py
"""Wrapper Python para o ARTEX adaptado ao EnemyDisclosure.

Duas frentes:

  * :class:`ApiRecon` — executa os scripts do ``api-recon`` (vendorizados em
    ``complexo/vendor/api-recon/scripts``) para descobrir endpoints, rotas e
    parâmetros de um portal de transparência (SPA ou MPA).
  * :class:`PlaywrightCLI` — ponte para o ``playwright-cli`` quando instalado,
    para automação/extração e captura de evidência visual.

Nada aqui faz requisições por conta própria: tudo é delegado aos scripts do
ARTEX. O objetivo é dar uma API Python estável para o pipeline do projeto.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from . import caminhos


# ──────────────────────────────────────────────────────────────────────────
# Resultado de um comando externo
# ──────────────────────────────────────────────────────────────────────────
class Resultado:
    """Resultado de um processo externo (script ARTEX/Node)."""

    def __init__(self, argv: list[str], returncode: int, stdout: str, stderr: str):
        self.argv = argv
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Resultado rc={self.returncode} {' '.join(self.argv[:3])}...>"

    def to_dict(self) -> dict:
        return {
            "argv": self.argv,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def _run(argv: list[str], cwd: Path | None = None, timeout: int | None = None) -> Resultado:
    proc = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return Resultado(argv, proc.returncode, proc.stdout or "", proc.stderr or "")


# ──────────────────────────────────────────────────────────────────────────
# api-recon
# ──────────────────────────────────────────────────────────────────────────
class ApiRecon:
    """Executa o api-recon (ARTEX) para um portal.

    Cada instância é dona de um ``workdir`` (o OUTDIR do api-recon), onde todos
    os artefatos do recon são gravados: ``js/``, ``api_static.txt``,
    ``routes.txt``, ``chunkmap.txt``, ``config.json``, ``runtime_api.json``,
    ``site_map.json`` etc.
    """

    def __init__(self, workdir: str | Path):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

    # -- Phase 0/1: classificação + harvest estático -------------------------
    def harvest_static(self, url: str, timeout: int = 900) -> Resultado:
        """Baixa o HTML, expande os bundles JS e extrai endpoints + rotas.

        Equivale a: ``python harvest_static.py <url> <workdir>``
        """
        return _run(
            [caminhos.python_bin(), str(caminhos.HARVEST_STATIC), url, str(self.workdir)],
            timeout=timeout,
        )

    def spider_mpa(
        self,
        url: str,
        cookie: str = "",
        max_paginas: int = 200,
        depth: int = 4,
        exclude: str = "logout|signout|delete|remove|destroy",
        delay: float = 0.1,
        timeout: int = 900,
    ) -> Resultado:
        """Crawl BFS para portais server-rendered (MPA)."""
        argv = [
            caminhos.python_bin(),
            str(caminhos.SPIDER_MPA),
            url,
            str(self.workdir),
            "--max", str(max_paginas),
            "--depth", str(depth),
            "--delay", str(delay),
        ]
        if cookie:
            argv += ["--cookie", cookie]
        if exclude:
            argv += ["--exclude", exclude]
        return _run(argv, timeout=timeout)

    # -- Phase 3: runtime (depth mode, precisa Node + puppeteer-core) --------
    def runtime_harvest(self, config_path: str | Path | None = None,
                        timeout: int = 600, runtime_mode: str | None = None) -> Resultado:
        """Roda o runtime_harvest.js contra o config.json.

        ``runtime_mode`` (opcional) sobrescreve o ``runtimeMode`` do config
        antes de rodar — útil para alternar ``depth``/``coverage``/``both``
        sem reescrever o arquivo.
        """
        cfg = Path(config_path) if config_path else (self.workdir / "config.json")
        if not cfg.exists():
            raise FileNotFoundError(
                f"config.json não encontrado em {cfg}. "
                "Gere com ApiRecon.gerar_config() (ver reference.md do api-recon)."
            )
        if runtime_mode:
            dados = json.loads(cfg.read_text(encoding="utf-8", errors="replace"))
            dados["runtimeMode"] = runtime_mode
            cfg.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        return _run(
            [caminhos.node_bin(), str(caminhos.RUNTIME_HARVEST), str(cfg)],
            cwd=caminhos.API_RECON_SCRIPTS,
            timeout=timeout,
        )

    # -- Phase 4: árvore de permissões ---------------------------------------
    def extract_route_map(self, timeout: int = 120) -> Resultado:
        return _run(
            [caminhos.python_bin(), str(caminhos.EXTRACT_ROUTE_MAP),
             str(self.workdir / "js"), str(self.workdir)],
            timeout=timeout,
        )

    def build_perm_tree(self, config_path: str | Path | None = None,
                        role: str = "SUPER_ADMIN", timeout: int = 120) -> Resultado:
        argv = [caminhos.python_bin(), str(caminhos.BUILD_PERM_TREE),
                str(self.workdir / "js"), str(self.workdir), "--role", role]
        cfg = Path(config_path) if config_path else (self.workdir / "config.json")
        if cfg.exists():
            argv += ["--config", str(cfg)]
        return _run(argv, timeout=timeout)

    # -- Leitura dos artefatos ------------------------------------------------
    def js_dir(self) -> Path:
        return self.workdir / "js"

    def js_files(self) -> list[Path]:
        return sorted(self.js_dir().glob("*.js")) if self.js_dir().exists() else []

    def _read_lines(self, nome: str) -> list[str]:
        p = self.workdir / nome
        if not p.exists():
            return []
        return [ln.strip() for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()
                if ln.strip()]

    def endpoints(self) -> list[str]:
        """Endpoints estáticos (api_static.txt) ou merged se já existir."""
        merged = self._read_lines("api_merged.txt")
        return merged if merged else self._read_lines("api_static.txt")

    def routes(self) -> list[str]:
        return self._read_lines("routes.txt")

    def paths_other(self) -> list[str]:
        return self._read_lines("paths_other.txt")

    def chunkmap(self) -> list[str]:
        return self._read_lines("chunkmap.txt")

    def read_json(self, nome: str) -> Any:
        p = self.workdir / nome
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return None

    def runtime_api(self) -> Any:
        return self.read_json("runtime_api.json")

    def site_map(self) -> Any:
        return self.read_json("site_map.json")

    def config(self) -> Any:
        return self.read_json("config.json")

    # -- Template de config.json ---------------------------------------------
    def gerar_config(
        self,
        url: str,
        runtime_mode: str = "depth",
        api_pattern: str = "/api/|/rest/|/servlet/|/service/|/graphql",
        routes: list[str] | None = None,
        stubs: list[dict] | None = None,
        cookies: list[dict] | None = None,
        local_storage: dict | None = None,
        neutralize: dict | None = None,
        forward: bool = True,
        mock_tier: str = "L1+L2",
        headless: bool = True,
        wait_until: str = "domcontentloaded",
        per_route_ms: int = 900,
        wait_ms: int = 1500,
        route_timeout: int = 12000,
        record_ws: bool = True,
        capture_responses: bool = True,
        proxy: str = "",
        destino: str | Path | None = None,
    ) -> Path:
        """Gera um ``config.json`` completo para o runtime_harvest (ARTEX).

        ``runtime_mode``:
          * ``"depth"``    — Puppeteer percorre as rotas e grava METHOD/params/resp;
          * ``"coverage"`` — preload.js injetado no document-start stuba auth e
            enumera a UI (requer browser MCP/Chat dev; ver C do reference.md);
          * ``"both"``     — depth e depois coverage (mais completo, mais lento).

        ``mock_tier`` só se aplica ao coverage: ``"L1"``, ``"L1+L2"``,
        ``"L1+L2+L3"``. ``neutralize`` reaproveita o default do ARTEX se None.
        Portais de transparência são públicos: por padrão não há cookies/login.
        """
        cfg = {
            "baseUrl": url if url.startswith("http") else "https://" + url,
            "runtimeMode": runtime_mode,
            "apiPattern": api_pattern,
            "forward": forward,
            "loginUrlPattern": "/login",
            "neutralize": neutralize or {
                "fields": ["response_code", "code", "errno", "ret", "status"],
                "success": 0,
                "flags": {"success": True, "message": "ok"},
            },
            "mockTier": mock_tier,
            "stubs": stubs or [],
            "routes": routes or self.routes() or ["/"],
            "waitMs": wait_ms,
            "perRouteMs": per_route_ms,
            "headless": headless,
            "waitUntil": wait_until,
            "routeTimeout": route_timeout,
            "captureResponses": capture_responses,
            "recordWs": record_ws,
            "proxy": proxy,
        }
        if cookies:
            cfg["cookies"] = cookies
        if local_storage:
            cfg["localStorage"] = local_storage

        alvo = Path(destino) if destino else (self.workdir / "config.json")
        alvo.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return alvo

    def gerar_config_base(self, url: str,
                          api_pattern: str = "/api/|/rest/|/servlet/|/service/|/graphql") -> Path:
        """Compatibilidade: config mínimo de depth (sem auth, portal público)."""
        return self.gerar_config(url, runtime_mode="depth", api_pattern=api_pattern)

    # -- Leitura das saídas do coverage (3b / 5) -----------------------------
    def coverage_artifacts(self) -> dict:
        """Lê os artefatos que o coverage/preload gravam no workdir.

        O preload exporta ``__API_RECON_LOG__``, ``__API_RECON_DETAIL__``,
        ``__API_RECON_ROUTES__`` e ``__API_RECON_OBSERVE__`` (ver C do
        reference.md); o harness 3b grava ``scan_raw.json`` e
        ``param_samples.json``. Devolve tudo que existir, sem exigir presença.
        """
        return {
            "scan_raw": self.read_json("scan_raw.json"),
            "param_samples": self.read_json("param_samples.json"),
            "api_detail": self.read_json("api_detail.json"),
            "params_merged": self.read_json("params_merged.json"),
            "api_merged": self._read_lines("api_merged.txt"),
            "route_map": self.read_json("route_map.json"),
        }

    def endpoints_merged(self) -> list[str]:
        """Endpoints finais (METHOD path) do Phase 5, se houver api_merged.txt."""
        return self._read_lines("api_merged.txt")

    # -- Relatório resumido ---------------------------------------------------
    def resumo(self) -> dict:
        """Resumo dos artefatos disponíveis no workdir."""
        return {
            "workdir": str(self.workdir),
            "js_downloaded": len(self.js_files()),
            "endpoints": len(self.endpoints()),
            "routes": len(self.routes()),
            "chunks": len(self.chunkmap()),
            "tem_index": (self.workdir / "index.html").exists(),
            "tem_config": (self.workdir / "config.json").exists(),
            "tem_runtime": (self.workdir / "runtime_api.json").exists(),
            "tem_site_map": (self.workdir / "site_map.json").exists(),
            "arquivos": sorted(p.name for p in self.workdir.iterdir() if p.is_file()),
        }


# ──────────────────────────────────────────────────────────────────────────
# playwright-cli (opcional)
# ──────────────────────────────────────────────────────────────────────────
class PlaywrightCLI:
    """Ponte fina para o ``playwright-cli`` do ARTEX, quando instalado.

    Se o binário não estiver disponível, os métodos levantam
    :class:`Indisponivel` com instruções — o resto do EnemyDisclosure continua
    funcionando sem ele.
    """

    class Indisponivel(RuntimeError):
        pass

    def __init__(self, timeout: int = 120):
        self.entry = caminhos.playwright_cli_entry()
        self.timeout = timeout

    def disponivel(self) -> bool:
        return self.entry is not None

    def _argv(self, *args: str) -> list[str]:
        if not self.entry:
            raise self.Indisponivel(
                "playwright-cli não encontrado. Defina ENEMY_PLAYWRIGHT_CLI ou "
                "instale o playwright-cli no PATH."
            )
        return [*self.entry, *args]

    def run(self, *args: str) -> Resultado:
        return _run(self._argv(*args), timeout=self.timeout)

    # Atalhos mais usados na auditoria
    def open(self, url: str = "") -> Resultado:
        return self.run("open", *([url] if url else []))

    def goto(self, url: str) -> Resultado:
        return self.run("goto", url)

    def click(self, ref: str) -> Resultado:
        return self.run("click", ref)

    def fill(self, ref: str, texto: str) -> Resultado:
        return self.run("fill", ref, texto)

    def snapshot(self) -> Resultado:
        return self.run("snapshot")

    def screenshot(self, saida: str = "") -> Resultado:
        return self.run("screenshot", *([saida] if saida else []))

    def requests(self) -> Resultado:
        return self.run("requests")

    def state_save(self, nome: str) -> Resultado:
        return self.run("state-save", nome)

    def state_load(self, nome: str) -> Resultado:
        return self.run("state-load", nome)

    def eval(self, script: str, ref: str = "") -> Resultado:
        return self.run("eval", script, *([ref] if ref else []))
