# complexo/browser.py
"""Descoberta renderizada de portal de transparência (Playwright).

O harvest estático do api-recon só vê o HTML de entrada. Em portais
institucionais JS-heavy (SPA/menus montados por JavaScript) o link do portal de
transparência **não está no HTML** — é por isso que o scanner macro MT devolveu
um mar de "Desconhecido". Este módulo renderiza a página num Chromium real,
espera o JS montar o menu, e extrai:

  * os links visíveis (texto + href), inclusive os criados por JS;
  * os candidatos a portal de transparência, pontuados por palavra-chave e
    por ruído de framework (Fiorilli, GeneXus, e-Pública, Ábaco, etc.);
  * uma pista de adapter (família de portal) por candidato.

Não é teste de intrusão: só renderiza páginas públicas e lê o DOM. Para sites
que exigem sessão institucional, use ``playwright-cli`` com autorização formal.

Uso:

    from complexo.browser import Navegador
    nv = Navegador()
    ok, motivo = nv.disponivel()
    desc = nv.descobrir_portal("https://prefeitura.x.mt.gov.br")
    for c in desc.candidatos:
        print(c["score"], c.get("adapter_hint"), c["href"])
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from urllib.parse import urljoin, urlsplit, urlunsplit

UA_PADRAO = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Palavras fortes no TEXTO ou no HREF de um link candidato a transparência.
_RE_TEXTO_TRANSP = re.compile(
    r"transpar[êe]nc|portal da transpar|presta[çc][aã]o de contas|contas p[úu]blic"
    r"|acesso [àa] informa|lei de acesso|lc ?131|governo aberto|dados abertos"
    r"|despesas? e receitas?|execu[çc][ãa]o (or[çc]ament|financeir)|licita[çc]"
    r"|di[áa]rio oficial|e-?sic|servi[çc]o de informa[çc][ãa]o ao cidad"
    r"|or[çc]amento|empenhos?|folha de pagamento|recurso humano",
    re.I,
)
_RE_HREF_TRANSP = re.compile(
    r"transparen|prestacao|presta[çc]ao|contas|licitac|portal-?transparen|acesso.?informac"
    r"|fiorilli|fassil|dcfiorilli|agili|e-?publica|elotech|equiplano|abaco|publicsoft"
    r"|consultatransparencia|ipm|instar|/sic|:80\d\d/",
    re.I,
)

# Tokens de vendor no HREF/TEXTO -> pista de família (não substitui o
# fingerprint dos bundles; é só uma heurística para priorizar candidatos).
_HINTS_VENDOR: list[tuple[re.Pattern, str]] = [
    (re.compile(r"versaojson|scpiwebservices|dcfiorilli|fassilcloud", re.I), "fiorilli"),
    (re.compile(r"gp\.srv\.br|transparencia_gp|/transparencia_[a-z]", re.I), "genexus_gp"),
    (re.compile(r"servlet/a[A-Z]|genexus", re.I), "genexus_cuiaba"),
    (re.compile(r"e-?publica|agilicloud|transparencia\.e-publica", re.I), "epublica"),
    (re.compile(r"elotech|oxy\.elotech|atricon", re.I), "elotech_oxy"),
    (re.compile(r"consultatransparencia", re.I), "consulta_transparencia"),
    (re.compile(r"vg\.abaco|abaco\.com\.br|X-SPA-REQUEST", re.I), "abaco_wm"),
    (re.compile(r"agili|urlStore", re.I), "agili_blue"),
]


# ──────────────────────────────────────────────────────────────────────────
@dataclass
class LinksPagina:
    """Resultado da extração de links de uma página renderizada."""

    url: str
    url_final: str = ""
    title: str = ""
    links: list[dict] = field(default_factory=list)       # {text, href}
    iframes: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    texto: str = ""
    tem_app_shell: bool = False
    erro: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["texto"] = self.texto[:2000]
        return d


@dataclass
class DescobertaBrowser:
    """Resultado da busca renderizada pelo portal de transparência."""

    url: str
    url_final: str = ""
    title: str = ""
    candidatos: list[dict] = field(default_factory=list)  # ordenados por score
    links_transparencia: list[str] = field(default_factory=list)
    adapter_hint: str | None = None
    adapter_hint_url: str | None = None
    tem_app_shell: bool = False
    erro: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────────
def _normalizar_href(base: str, href: str) -> str | None:
    """Resolve href relativo, descarta javascript/mailto/âncoras."""
    if not href:
        return None
    h = href.strip()
    if h.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
        return None
    full = urljoin(base, h)
    if not full.startswith(("http://", "https://")):
        return None
    # remove fragmento, mantém query (alguns portais usam ?)
    sp = urlsplit(full)
    return urlunsplit((sp.scheme, sp.netloc, sp.path, sp.query, ""))


def pontuar_candidato(texto: str, href: str) -> int:
    """Pontua um link como candidato a portal de transparência."""
    score = 0
    if texto and _RE_TEXTO_TRANSP.search(texto):
        score += 4
    if href and _RE_TEXTO_TRANSP.search(href):
        score += 2
    if href and _RE_HREF_TRANSP.search(href):
        score += 3
    # penaliza ruído de navegação
    if re.search(r"facebook|instagram|whatsapp|youtube|twitter|/login|^#$", href or "", re.I):
        score -= 3
    return score


def pista_adapter(texto: str, href: str) -> str | None:
    """Pista de família de portal a partir do texto/href (heurística)."""
    alvo = f"{texto or ''} {href or ''}"
    for pat, familia in _HINTS_VENDOR:
        if pat.search(alvo):
            return familia
    return None


def classificar_candidatos(links: list[dict], base_url: str) -> list[dict]:
    """Dedup + pontuação + pista de adapter. Ordena por score desc.

    ``links`` é uma lista de ``{text, href}``. Não faz rede.
    """
    vistos: set[str] = set()
    saida: list[dict] = []
    for l in links or []:
        href = l.get("href") or ""
        norm = _normalizar_href(base_url, href)
        if not norm or norm in vistos:
            continue
        # dedup também pela chave path+query sem barra final
        chave = norm.rstrip("/")
        if chave in vistos:
            continue
        texto = (l.get("text") or "").strip()
        score = pontuar_candidato(texto, norm)
        if score <= 0:
            continue
        vistos.add(norm)
        vistos.add(chave)
        saida.append({
            "href": norm,
            "text": texto[:120],
            "score": score,
            "adapter_hint": pista_adapter(texto, norm),
        })
    saida.sort(key=lambda d: (d["score"], -len(d["href"])), reverse=True)
    return saida


# ──────────────────────────────────────────────────────────────────────────
class Navegador:
    """Wrapper fino do Playwright (Chromium) para recon renderizado."""

    class Indisponivel(RuntimeError):
        pass

    def __init__(self, timeout_ms: int = 25_000, user_agent: str = UA_PADRAO,
                 headless: bool = True):
        self.timeout_ms = timeout_ms
        self.user_agent = user_agent
        self.headless = headless

    # -- disponibilidade -----------------------------------------------------
    @staticmethod
    def disponivel() -> tuple[bool, str]:
        try:
            import playwright  # noqa: F401
            from playwright.sync_api import sync_playwright  # noqa: F401
        except Exception as exc:  # pragma: no cover - depende do ambiente
            return (False, f"playwright não instalado ({exc}). "
                           f"Rode: pip install playwright && playwright install chromium")
        return (True, "ok")

    def _contexto(self):
        """Context manager que devolve (playwright, browser) com cleanup."""
        ok, motivo = self.disponivel()
        if not ok:
            raise self.Indisponivel(motivo)
        from playwright.sync_api import sync_playwright  # import tardio

        return sync_playwright()

    # -- render --------------------------------------------------------------
    def render(self, url: str, espera_ms: int = 2500,
               wait_until: str = "networkidle") -> LinksPagina:
        """Renderiza a página e extrai links/iframes/scripts/texto."""
        ok, motivo = self.disponivel()
        if not ok:
            return LinksPagina(url=url, erro=motivo)

        with self._contexto() as p:
            browser = p.chromium.launch(headless=self.headless, args=["--no-sandbox"])
            ctx = browser.new_context(user_agent=self.user_agent)
            page = ctx.new_page()
            try:
                page.goto(url, wait_until=wait_until, timeout=self.timeout_ms)
                page.wait_for_timeout(espera_ms)
                links = []
                for a in page.query_selector_all("a[href]"):
                    href = a.get_attribute("href") or ""
                    try:
                        text = (a.inner_text() or "").strip()
                    except Exception:
                        text = ""
                    if href:
                        links.append({"text": text, "href": href})
                iframes = [f for f in page.eval_on_selector_all(
                    "iframe[src]", "els => els.map(e => e.getAttribute('src'))") if f]
                scripts = [s for s in page.eval_on_selector_all(
                    "script[src]", "els => els.map(e => e.getAttribute('src'))") if s]
                body = ""
                try:
                    body = page.inner_text("body")
                except Exception:
                    body = ""
                html = ""
                try:
                    html = page.content()
                except Exception:
                    html = ""
                tem_shell = bool(re.search(
                    r'<div[^>]+id=["\'](app|root|__next|__nuxt)["\']', html, re.I))
                return LinksPagina(
                    url=url, url_final=page.url, title=page.title() or "",
                    links=links, iframes=iframes, scripts=scripts,
                    texto=body, tem_app_shell=tem_shell,
                )
            except Exception as exc:  # pragma: no cover - rede/CDN
                return LinksPagina(url=url, erro=f"{type(exc).__name__}: {exc}")
            finally:
                try:
                    ctx.close()
                    browser.close()
                except Exception:
                    pass

    # -- descoberta ----------------------------------------------------------
    def descobrir_portal(self, url: str, espera_ms: int = 2500,
                         max_candidatos: int = 8) -> DescobertaBrowser:
        """Renderiza a home institucional e devolve os candidatos a portal."""
        pg = self.render(url, espera_ms=espera_ms)
        if pg.erro and not pg.links:
            return DescobertaBrowser(url=url, url_final=pg.url_final,
                                     title=pg.title, erro=pg.erro)

        base = pg.url_final or url
        candidatos = classificar_candidatos(pg.links, base)[:max_candidatos]
        # se a própria página já é o portal, ele aparece no topo
        desc = DescobertaBrowser(
            url=url, url_final=pg.url_final, title=pg.title,
            candidatos=candidatos,
            links_transparencia=[c["href"] for c in candidatos],
            tem_app_shell=pg.tem_app_shell,
        )
        for c in candidatos:
            if c.get("adapter_hint"):
                desc.adapter_hint = c["adapter_hint"]
                desc.adapter_hint_url = c["href"]
                break
        return desc


def renderizar(url: str, espera_ms: int = 2500) -> LinksPagina:
    """Atalho funcional para :meth:`Navegador.render`."""
    return Navegador().render(url, espera_ms=espera_ms)


if __name__ == "__main__":  # pragma: no cover - utilitário
    import json
    import sys

    if len(sys.argv) < 2:
        print("uso: python -m complexo.browser <url>")
        raise SystemExit(2)
    print(json.dumps(Navegador().descobrir_portal(sys.argv[1]).to_dict(),
                     ensure_ascii=False, indent=2))
