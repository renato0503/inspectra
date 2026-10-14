# complexo/fingerprint.py
"""Fingerprinting de portal de transparência -> família de adapter.

Cruza sinais coletados do portal (texto dos bundles JS, lista de endpoints,
nome do servidor HTTP) com uma tabela de indicadores por vendor e devolve a
família de adapter do EnemyDisclosure mais provável (``core/adapters.py``).

Isso é o que permite, para um portal novo/desconhecido, escolher o adapter sem
tentativa-e-erro: o recon do api-recon alimenta este módulo.
"""

from __future__ import annotations

import re
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────
# Tabela de indicadores. Cada entrada: família (chave de core/adapters.py),
# nome legível, e uma lista de sinais. Sinal = (tipo, padrão, peso).
#   tipo "js"    -> busca no texto dos bundles JS
#   tipo "api"   -> busca na lista de endpoints/paths
#   tipo "serv"  -> busca no header Server
#   tipo "html"  -> busca no HTML de entrada
# ──────────────────────────────────────────────────────────────────────────
INDICADORES: dict[str, dict] = {
    "fiorilli": {
        "nome": "Fiorilli SCPI",
        "sinais": [
            ("api", r"/versaoJson/", 5),
            ("api", r"scpiwebservices", 5),
            ("api", r"/servicosfiorilli", 4),
            ("js",  r"versaoJson", 3),
            ("js",  r"fiorilli", 3),
            ("js",  r"SCPI", 2),
            ("html", r"fiorilli", 2),
        ],
    },
    "genexus_cuiaba": {
        "nome": "GeneXus + Angular (Cuiabá)",
        "sinais": [
            ("api", r"/servlet/a[A-Z]", 4),
            ("api", r"pagination", 3),
            ("js",  r"GXState", 3),
            ("js",  r"gxValues", 3),
            ("js",  r"ng-version", 2),
            ("js",  r"__ngContext__", 2),
            ("js",  r"gxAJax", 2),
        ],
    },
    "genexus_gp": {
        "nome": "GeneXus legado GP (gp.srv.br)",
        "sinais": [
            ("api", r"/servlet/", 3),
            ("js",  r"gx-invisible", 4),
            ("js",  r"TB_PROXIMO", 4),
            ("js",  r"gxValues", 3),
            ("js",  r"GX_AJAX_KEY", 4),
            ("js",  r"GXState", 3),
            ("html", r"gp\.srv\.br", 3),
        ],
    },
    "agili_blue": {
        "nome": "ÁGILIBlue / Ábaco",
        "sinais": [
            ("js",  r"agili", 3),
            ("api", r"/api/filtro/get", 4),
            ("js",  r"Bearer null", 3),
            ("api", r"/urlStore", 3),
        ],
    },
    "elotech_oxy": {
        "nome": "Elotech Oxy",
        "sinais": [
            ("js",  r"elotech", 4),
            ("html", r"oxy\.elotech", 5),
            ("js",  r"entidade", 1),
            ("js",  r"modulo", 1),
        ],
    },
    "epublica": {
        "nome": "e-Pública Sistemas",
        "sinais": [
            ("api", r"/rest/[a-z0-9_]+/portal/loadData/", 5),
            ("js",  r"epublica", 4),
            ("html", r"e-publica", 5),
            ("js",  r"angular", 1),
        ],
    },
    "consulta_transparencia": {
        "nome": "Consulta Transparência (ASP.NET)",
        "sinais": [
            ("html", r"consultatransparencia\.com\.br", 5),
            ("api", r"/Transparencia/", 4),
            ("serv", r"ASP\.NET", 2),
        ],
    },
    "abaco_wm": {
        "nome": "Ábaco / GeneXus SPA (wm*)",
        "sinais": [
            ("js",  r"W00XXGrid1ContainerTbl", 5),
            ("js",  r"vNPAGINAATUAL", 5),
            ("js",  r"X-SPA-REQUEST", 4),
            ("html", r"abaco\.com\.br", 4),
        ],
    },
}

# Framework genérico -> não é um adapter do projeto, mas ajuda a classificar
FRAMEWORKS = {
    "angular": [r"ng-version", r"__ngContext__", r"ɵɵdefineComponent"],
    "react":   [r"__REACT_DEVTOOLS_GLOBAL_HOOK__", r"React\.createElement"],
    "vue":     [r"__VUE__", r"data-v-app", r"createApp\("],
    "php":     [r"\.php\?", r"PHPSESSID"],
    "wordpress": [r"wp-content", r"wp-includes"],
}

# Sinais de que o portal usa o SPA framework genérico mas não um vendor conhecido
GENERICOS = {"angular": "genexus_cuiaba"}  # Angular genérico costuma ser GeneXus


def _pontuar_texto(texto: str, tipo: str, resultados: dict) -> None:
    for familia, meta in INDICADORES.items():
        score = resultados.setdefault(
            familia, {"familia": familia, "nome": meta["nome"], "score": 0, "evidencias": []}
        )
        for t, padrao, peso in meta["sinais"]:
            if t != tipo:
                continue
            try:
                if re.search(padrao, texto, re.I):
                    score["score"] += peso
                    score["evidencias"].append(f"{t}:{padrao}")
            except re.error:
                continue


def fingerprint_jsdir(jsdir: str | Path, limite_bytes: int = 4_000_000) -> dict:
    """Pontua vendors a partir dos bundles JS baixados pelo api-recon."""
    jsdir = Path(jsdir)
    resultados: dict[str, dict] = {}
    if not jsdir.exists():
        return {"vendor": None, "resultados": {}, "frameworks": [], "motivo": "jsdir inexistente"}

    texto_total = []
    lidos = 0
    for js in sorted(jsdir.glob("*.js")):
        try:
            txt = js.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lidos += len(txt)
        texto_total.append(txt)
        if lidos >= limite_bytes:
            break
    texto = "\n".join(texto_total)
    _pontuar_texto(texto, "js", resultados)

    frameworks = []
    for fw, padroes in FRAMEWORKS.items():
        if any(re.search(p, texto, re.I) for p in padroes):
            frameworks.append(fw)

    return _consolidar(resultados, frameworks, n_js=len(texto_total))


def fingerprint_endpoints(endpoints: list[str], resultados: dict | None = None) -> dict:
    """Pontua vendors a partir da lista de endpoints/rotas descobertos."""
    resultados = resultados or {}
    texto = "\n".join(endpoints)
    _pontuar_texto(texto, "api", resultados)
    return resultados


def fingerprint_texto_livre(texto: str, consolidar: bool = True) -> dict:
    """Fingerprint a partir de qualquer texto (URL, título, trecho de HTML).

    Aplica TODOS os tipos de sinal (js/api/html/serv) contra o texto — útil
    quando só se tem o href/texto de um link (recon renderizado) e não os
    bundles baixados. Com ``consolidar=True`` devolve o mesmo shape de
    :func:`fingerprint_jsdir`; senão devolve o dict bruto de scores.
    """
    resultados: dict[str, dict] = {}
    for tipo in ("js", "api", "html", "serv"):
        _pontuar_texto(texto or "", tipo, resultados)
    if not consolidar:
        return resultados
    return _consolidar(resultados, frameworks=[], n_js=0)


def fingerprint_http(html: str = "", server: str = "") -> dict:
    """Pontua vendors a partir de HTML de entrada e header Server."""
    resultados: dict[str, dict] = {}
    if html:
        _pontuar_texto(html, "html", resultados)
    if server:
        _pontuar_texto(server, "serv", resultados)
    return resultados


def _consolidar(resultados: dict, frameworks: list[str], n_js: int = 0) -> dict:
    if not resultados:
        return {"vendor": None, "adapter": None, "confianca": "nenhuma",
                "resultados": {}, "frameworks": frameworks}

    ordenado = sorted(resultados.values(), key=lambda d: d["score"], reverse=True)
    top = ordenado[0]
    segundo = ordenado[1] if len(ordenado) > 1 else {"score": 0}

    if top["score"] <= 0:
        # Sem vendor conhecido — tenta o genérico por framework
        for fw in frameworks:
            if fw in GENERICOS:
                adapter = GENERICOS[fw]
                return {
                    "vendor": f"generico/{fw}",
                    "adapter": adapter,
                    "confianca": "baixa",
                    "resultados": resultados,
                    "frameworks": frameworks,
                    "nota": f"nenhum vendor forte; framework {fw} sugere {adapter}",
                }
        return {"vendor": None, "adapter": None, "confianca": "nenhuma",
                "resultados": resultados, "frameworks": frameworks}

    # confiança: forte se top domina o segundo e tem score relevante
    if top["score"] >= 8 and top["score"] >= segundo["score"] + 3:
        conf = "alta"
    elif top["score"] >= 4 and top["score"] > segundo["score"]:
        conf = "media"
    else:
        conf = "baixa"

    return {
        "vendor": top["familia"],
        "vendor_nome": top["nome"],
        "adapter": top["familia"],
        "confianca": conf,
        "score": top["score"],
        "evidencias": top["evidencias"],
        "resultados": resultados,          # detalhe completo (acumulável)
        "scores": {k: v["score"] for k, v in resultados.items()},
        "frameworks": frameworks,
        "n_js": n_js,
    }


def fingerprint_recon(recon: dict) -> dict:
    """Fingerprint completo a partir dos artefatos do api-recon.

    ``recon`` é um dicionário com chaves opcionais: ``jsdir``, ``endpoints``,
    ``html``, ``server`` (ver :func:`complexo.recon.ReconPortal.coletar`).
    """
    resultados: dict[str, dict] = {}

    js = fingerprint_jsdir(recon["jsdir"]) if recon.get("jsdir") else {}
    resultados = js.get("resultados", {}) or {}
    frameworks = js.get("frameworks", [])

    if recon.get("endpoints"):
        fingerprint_endpoints(recon["endpoints"], resultados)

    extra = fingerprint_http(recon.get("html", ""), recon.get("server", ""))
    for k, v in extra.items():
        cur = resultados.setdefault(k, {"familia": k, "nome": v["nome"], "score": 0, "evidencias": []})
        cur["score"] += v["score"]
        cur["evidencias"] += v["evidencias"]

    return _consolidar(resultados, frameworks, n_js=js.get("n_js", 0))
