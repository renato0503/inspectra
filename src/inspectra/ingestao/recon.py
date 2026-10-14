# complexo/recon.py
"""Orquestração do reconhecimento de um portal de transparência.

Fluxo (adaptado das 5 fases do api-recon do ARTEX):

  1. resolve a URL do portal (por slug em ``core.config.PERFIS`` ou URL direta);
  2. roda o harvest estático (SPA) ou o spider (MPA);
  3. faz o fingerprint do vendor a partir dos bundles/endpoints;
  4. monta o ``site_map.json`` e um relatório ``RECON.md`` legível;
  5. (opcional, se REA disponível) enriquece com a análise de bundle via CDP.

O resultado alimenta a escolha do adapter do EnemyDisclosure — sem
tentativa-e-erro.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import caminhos, fingerprint
from .artex import ApiRecon


# ──────────────────────────────────────────────────────────────────────────
@dataclass
class SiteMap:
    site: str
    slug: str | None = None
    app_type: str = "desconhecido"          # spa | mpa | desconhecido
    runtime_mode: str = "static"
    vendor: str | None = None
    vendor_nome: str | None = None
    adapter: str | None = None
    confianca: str = "nenhuma"
    apis_static: list[str] = field(default_factory=list)
    apis_runtime: list[str] = field(default_factory=list)
    frontend_routes: list[str] = field(default_factory=list)
    params: list[dict] = field(default_factory=list)
    js_downloaded: int = 0
    evidencias: list[str] = field(default_factory=list)
    links_transparencia: list[str] = field(default_factory=list)
    portal_transparencia: str | None = None
    limitacoes: str = ""
    # recon renderizado (complexo/browser.py) — preenchido com --browser
    browser_renderizado: bool = False
    browser_url_final: str | None = None
    browser_titulo: str | None = None
    tem_app_shell: bool = False
    candidatos_browser: list[dict] = field(default_factory=list)
    adapter_hint: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────────
def resolver_url(slug: str) -> str | None:
    """Pega a base do portal a partir do slug em core.config.PERFIS."""
    try:
        from core.config import PERFIS
    except Exception:
        return None
    perfil = PERFIS.get(slug)
    return perfil.get("base") if perfil else None


def _ler_html(workdir: Path) -> str:
    p = workdir / "index.html"
    if p.exists():
        try:
            return p.read_text(encoding="utf-8", errors="ignore")[:200_000]
        except OSError:
            return ""
    return ""


# ── descoberta do portal de transparência a partir do site institucional ───
_RE_HREF = re.compile(r'href=["\']([^"\']+)["\']', re.I)
_RE_TRANSP = re.compile(
    r"transparen|portal[-_ ]?transparen|contas[-_ ]?public|prestacao[-_ ]?de[-_ ]?contas"
    r"|licitac|acesso[-_ ]?a[-_ ]?informacao|elegis|fiorilli|publicsoft|atende\.net"
    r"|ipm|elp\.|equiplano|instar|e[-_ ]?publica|abaco|govbr",
    re.I,
)


def descobrir_links_transparencia(html: str, base_url: str) -> list[str]:
    """Extrai do HTML os links que apontam para o portal de transparência.

    Não faz requisição — só lê o HTML de entrada já baixado pelo harvest.
    """
    from urllib.parse import urljoin

    saida: list[str] = []
    vistos: set[str] = set()
    for m in _RE_HREF.findall(html or ""):
        if m.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
            continue
        full = urljoin(base_url, m)
        if not _RE_TRANSP.search(full):
            continue
        if full in vistos or full.rstrip("/") == base_url.rstrip("/"):
            continue
        vistos.add(full)
        saida.append(full)
    return saida


_RE_LINK_FORTE = re.compile(
    r"transparen|/transparencia|portal.?transparen|contas.?public|prestacao.?de.?contas"
    r"|fiorilli|fassil|dcfiorilli|agili|e-?publica|elotech|equiplano|abaco|publicsoft"
    r"|consultatransparencia|atende\.net|ipm|instar|:80\d\d/",
    re.I,
)


def _rank_link(link: str) -> tuple:
    """Prioriza links que apontam para o portal de transparência em si."""
    forte = 1 if _RE_LINK_FORTE.search(link) else 0
    generico = 1 if re.search(r"sic-|ouvidoria|acesso", link, re.I) else 0
    return (forte, -generico, len(link))


def _rank_fp(fp: dict) -> tuple:
    """Ordena fingerprints por qualidade (confiança -> score -> nº de evidências)."""
    ordem = {"alta": 3, "media": 2, "baixa": 1, "nenhuma": 0}
    return (
        ordem.get(fp.get("confianca", "nenhuma"), 0),
        fp.get("score", 0),
        len(fp.get("evidencias", []) or []),
    )


def _classificar_app(workdir: Path, n_endpoints: int, n_js: int) -> str:
    html = _ler_html(workdir)
    if re.search(r'<div[^>]+id=["\'](app|root)["\']', html, re.I) and n_js > 0:
        return "spa"
    if re.search(r"<form\b", html, re.I) and n_endpoints <= 3:
        return "mpa"
    if n_js > 0 and n_endpoints > 0:
        return "spa"
    if n_endpoints == 0 and n_js == 0:
        return "desconhecido"
    return "mpa"


# ──────────────────────────────────────────────────────────────────────────
class ReconPortal:
    """Executa o recon completo de um portal e emite o site_map.json."""

    def __init__(self, slug: str | None = None, url: str | None = None,
                 workdir: str | Path | None = None):
        self.slug = slug
        self.url = url or (resolver_url(slug) if slug else None)
        if not self.url:
            raise ValueError("Informe --url ou um --slug cadastrado em core.config.PERFIS.")
        if workdir is None:
            workdir = caminhos.recon_dir(slug or _slug_de_url(self.url))
        self.workdir = Path(workdir)
        self.recon = ApiRecon(self.workdir)

    # -- execução ------------------------------------------------------------
    def executar(self, mpa: bool = False, cookie: str = "",
                 com_runtime: bool = False, com_seguir: bool = False,
                 com_browser: bool = False, timeout: int = 900) -> SiteMap:
        self.workdir.mkdir(parents=True, exist_ok=True)

        if mpa:
            res = self.recon.spider_mpa(self.url, cookie=cookie, timeout=timeout)
        else:
            res = self.recon.harvest_static(self.url, timeout=timeout)

        if not res.ok:
            # Ainda assim, monta um site_map com a limitação registrada.
            sm = SiteMap(site=self.url, slug=self.slug, app_type="desconhecido",
                         limitacoes=f"harvest falhou (rc={res.returncode}): {res.stderr[:300]}")
            # mesmo com harvest vazio, o browser pode achar o portal
            if com_browser:
                sm = self._renderizar_browser(sm)
            self._escrever(sm)
            return sm

        endpoints = self.recon.endpoints()
        routes = self.recon.routes()
        n_js = len(self.recon.js_files())

        from .fingerprint import fingerprint_recon
        fp = fingerprint_recon({
            "jsdir": self.recon.js_dir(),
            "endpoints": endpoints + routes,
            "html": _ler_html(self.workdir),
        })

        sm = SiteMap(
            site=self.url,
            slug=self.slug,
            app_type=_classificar_app(self.workdir, len(endpoints), n_js),
            runtime_mode="static",
            vendor=fp.get("vendor"),
            vendor_nome=fp.get("vendor_nome"),
            adapter=fp.get("adapter"),
            confianca=fp.get("confianca", "nenhuma"),
            apis_static=endpoints,
            frontend_routes=routes,
            js_downloaded=n_js,
            evidencias=fp.get("evidencias", []) or [],
        )

        sm.links_transparencia = descobrir_links_transparencia(
            _ler_html(self.workdir), self.url
        )

        if com_browser:
            sm = self._renderizar_browser(sm)

        if com_runtime:
            sm = self._enriquecer_runtime(sm)

        # com_seguir OU com_browser: tenta harvest+fingerprint do melhor link
        if (com_seguir or com_browser) and sm.links_transparencia:
            sm = self._seguir_transparencia(sm)

        self._escrever(sm)
        return sm

    # -- descoberta renderizada (Playwright) ---------------------------------
    def _renderizar_browser(self, sm: SiteMap, espera_ms: int = 2500) -> SiteMap:
        """Renderiza o site e funde os links encontrados no SiteMap.

        Preenche ``browser_*`` e adiciona os candidatos à frente de
        ``links_transparencia`` (para o ``_seguir_transparencia`` priorizar).
        Não falha o recon se o Playwright não estiver disponível — registra a
        limitação.
        """
        from .browser import Navegador
        try:
            desc = Navegador().descobrir_portal(self.url, espera_ms=espera_ms)
        except Exception as exc:  # pragma: no cover - ambiente
            sm.limitacoes = (sm.limitacoes + " | " +
                             f"browser indisponível: {exc}").strip(" |")
            return sm

        sm.browser_renderizado = True
        sm.browser_url_final = desc.url_final or None
        sm.browser_titulo = desc.title or None
        sm.tem_app_shell = desc.tem_app_shell
        sm.candidatos_browser = desc.candidatos
        sm.adapter_hint = desc.adapter_hint

        # links do browser primeiro (mais confiáveis p/ sites JS-heavy)
        novos = [c["href"] for c in desc.candidatos]
        for l in sm.links_transparencia:
            if l not in novos:
                novos.append(l)
        sm.links_transparencia = novos

        # se o static não achou vendor/endpoint, tenta uma pista pelo href
        if not sm.adapter and desc.adapter_hint:
            from .fingerprint import fingerprint_texto_livre
            fp = fingerprint_texto_livre(
                " ".join(c["href"] for c in desc.candidatos[:6]))
            if fp.get("adapter"):
                sm.adapter = fp["adapter"]
                sm.vendor = fp.get("vendor")
                sm.confianca = fp.get("confianca", "baixa")
                sm.evidencias = fp.get("evidencias", []) or sm.evidencias
        if desc.erro:
            sm.limitacoes = (sm.limitacoes + " | " +
                             f"browser: {desc.erro[:200]}").strip(" |")
        return sm

    def _seguir_transparencia(self, sm: SiteMap, max_links: int = 5) -> SiteMap:
        """Faz o harvest dos links do portal de transparência e re-fingerprinta."""
        alvo_dir = self.workdir / "transparencia"
        melhor: dict | None = None
        # prioriza links que claramente são portal de transparência / de vendor
        links = sorted(sm.links_transparencia, key=_rank_link, reverse=True)
        for link in links[:max_links]:
            sub = ApiRecon(alvo_dir)
            res = sub.harvest_static(link, timeout=120)
            if not res.ok:
                continue
            from .fingerprint import fingerprint_recon
            fp = fingerprint_recon({
                "jsdir": sub.js_dir(),
                "endpoints": sub.endpoints() + sub.routes(),
                "html": _ler_html(alvo_dir),
            })
            cand = {"link": link, "fp": fp, "endpoints": sub.endpoints(),
                    "routes": sub.routes()}
            if fp.get("adapter") and (
                melhor is None or _rank_fp(fp) > _rank_fp(melhor["fp"])
            ):
                melhor = cand
            if melhor and melhor["fp"].get("confianca") == "alta":
                break

        if melhor:
            fp = melhor["fp"]
            sm.portal_transparencia = melhor["link"]
            sm.vendor = fp.get("vendor")
            sm.vendor_nome = fp.get("vendor_nome")
            sm.adapter = fp.get("adapter")
            sm.confianca = fp.get("confianca")
            sm.apis_static = melhor["endpoints"] or sm.apis_static
            sm.frontend_routes = melhor["routes"] or sm.frontend_routes
            sm.evidencias = fp.get("evidencias", []) or sm.evidencias
        return sm

    def _enriquecer_runtime(self, sm: SiteMap) -> SiteMap:
        cfg = self.recon.gerar_config_base(self.url)
        res = self.recon.runtime_harvest(cfg)
        rt = self.recon.runtime_api()
        if rt and isinstance(rt, dict):
            sm.apis_runtime = rt.get("uniq", []) or []
            sm.runtime_mode = "depth"
        elif not res.ok:
            sm.limitacoes = (sm.limitacoes + " | " +
                             f"runtime indisponível: {res.stderr[:200]}").strip(" |")
        return sm

    # -- escrita -------------------------------------------------------------
    def _escrever(self, sm: SiteMap) -> None:
        (self.workdir / "site_map.json").write_text(
            json.dumps(sm.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (self.workdir / "RECON.md").write_text(self._relatorio(sm), encoding="utf-8")

    def _relatorio(self, sm: SiteMap) -> str:
        linhas = [
            f"# Recon — {sm.slug or sm.site}",
            "",
            f"- **Portal:** {sm.site}",
            f"- **Portal de transparência:** {sm.portal_transparencia or '—'}",
            f"- **Tipo de app:** {sm.app_type}",
            f"- **Vendor detectado:** {sm.vendor or 'não identificado'}"
            + (f" ({sm.vendor_nome})" if sm.vendor_nome else ""),
            f"- **Adapter sugerido:** `{sm.adapter or '—'}` (confiança: {sm.confianca})",
            f"- **JS baixados:** {sm.js_downloaded}",
            f"- **Endpoints estáticos:** {len(sm.apis_static)}",
            f"- **Rotas frontend:** {len(sm.frontend_routes)}",
        ]
        if sm.browser_renderizado:
            linhas.append(f"- **Recon renderizado:** sim"
                          + (f" (final: {sm.browser_url_final})" if sm.browser_url_final else "")
                          + (f" · app shell: {'sim' if sm.tem_app_shell else 'não'}")
                          + (f" · pista de adapter: `{sm.adapter_hint}`" if sm.adapter_hint else ""))
        if sm.apis_runtime:
            linhas.append(f"- **Endpoints runtime:** {len(sm.apis_runtime)}")
        if sm.evidencias:
            linhas.append(f"- **Evidências do fingerprint:** {', '.join(sm.evidencias[:8])}")
        if sm.candidatos_browser:
            linhas += ["", "## Candidatos a portal (renderizado)", ""]
            for c in sm.candidatos_browser[:10]:
                hint = f" · `{c['adapter_hint']}`" if c.get("adapter_hint") else ""
                linhas.append(f"- [{c['score']}] {c['href']}{hint}"
                              + (f" — _{c['text']}_" if c.get("text") else ""))
        if sm.links_transparencia:
            linhas += ["", "## Links de transparência no site institucional", ""]
            linhas += [f"- {l}" for l in sm.links_transparencia[:20]]
        if sm.limitacoes:
            linhas += ["", f"> Limitação: {sm.limitacoes}"]
        if sm.apis_static:
            linhas += ["", "## Endpoints (amostra)", ""]
            linhas += [f"- `{e}`" for e in sm.apis_static[:40]]
        return "\n".join(linhas) + "\n"


def _slug_de_url(url: str) -> str:
    m = re.sub(r"^https?://", "", url).split("/")[0]
    return re.sub(r"[^a-z0-9]+", "_", m.lower()).strip("_")


# ──────────────────────────────────────────────────────────────────────────
def recomendar_adapter(site_map: SiteMap | dict) -> str | None:
    """Devolve a família de adapter recomendada para o site_map."""
    if isinstance(site_map, dict):
        return site_map.get("adapter")
    return site_map.adapter
