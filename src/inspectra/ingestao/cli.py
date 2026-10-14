# complexo/cli.py
"""CLI unificada da integração ARTEX + REA.

Uso:
    python -m complexo <comando> [args]

Comandos principais:
    doctor                         Diagnóstico do que está disponível
    recon <url|--slug slug>        Recon completo -> site_map.json + RECON.md
    harvest <url>                  Só o harvest estático (SPA)
    spider <url>                   Crawl BFS (MPA server-rendered)
    fingerprint <jsdir>            Fingerprint de vendor a partir dos bundles
    endpoints <outdir>             Lista endpoints/rotas de um recon já feito
    runtime <config.json>          Roda o runtime_harvest.js (depth mode)
    rea-sqlite <db>                Inspeciona snapshot SQLite (REA)
    rea-js <path>                  Analisa app JavaScript (REA)
    rea-targets <cdp>              Lista alvos do browser via CDP (REA)
    rea-web <cdp> <target>         Inspeciona página web via CDP (REA)
    rea-bundle <cdp> <target>      Analisa bundle web via CDP (REA)
    rea-managed <path>             Inspeção de binário .NET (REA)
    rea-go <path>                  Metadados de build de binário Go (REA)
    rea-wasm <path>                Validação/seções de artefato WASM (REA)
    rea-har <path>                 Inspeção offline de captura HAR (REA)
    rea-view <json|arquivo>        Projeta summary/API-surface de Evidence (REA)
    rea-trace <json|arquivo>       Traça feature na Application Graph (REA)
    rea-reconcile <json|arquivo>   Funde graph estático + runtime (REA)
    rea-compare <left> <right>     Compara duas versões/Evidence (REA)
    rea-evidence <in> [--out f]    Importa/exporta bundle de evidência (REA)
    rea-providers                  Lista providers nativos do REA
    rea-doctor [--provider P]      Diagnóstico de prontidão do REA
    browser <url>                  Descoberta renderizada (Playwright)
    mcp-config                     Bloco .mcp.json para registrar o REA
    playwright <args...>           Repassa para o playwright-cli
    grafo-resumo <grafo.json>      Resumo de um grafo de auditoria
    grafo-graphml <in.json> <out>  Exporta o asset graph para GraphML
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import caminhos, fingerprint
from .artex import ApiRecon, PlaywrightCLI
from .browser import Navegador
from .grafo import GrafoAuditoria
from .rea import REA
from .recon import ReconPortal


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ── comandos ───────────────────────────────────────────────────────────────
def cmd_doctor(_args) -> int:
    info = caminhos.diagnostico()
    rea_ok, rea_motivo = REA().disponivel()
    info["rea"]["motivo"] = "" if rea_ok else rea_motivo
    pwc = PlaywrightCLI()
    info["playwright_cli"]["disponivel"] = pwc.disponivel()
    _print_json(info)

    print("\n== Resumo ==")
    print(f"  recon vendorizado : {'OK' if info['recon_vendorizado']['ok'] else 'FALTA'}")
    print(f"  node              : {'OK' if info['node']['ok'] else 'FALTA'}")
    print(f"  puppeteer-core    : {'OK' if info['puppeteer_core']['ok'] else 'opcional (runtime depth)'}")
    print(f"  playwright (py)   : {'OK' if info.get('playwright_python', {}).get('ok') else 'FALTA (recon renderizado)'}")
    print(f"  REA               : {'OK' if rea_ok else 'indisponível'}"
          + (f" — {rea_motivo}" if not rea_ok else ""))
    print(f"  playwright-cli    : {'OK' if pwc.disponivel() else 'indisponível (opcional)'}")
    return 0


def cmd_recon(args) -> int:
    rp = ReconPortal(slug=args.slug, url=args.url, workdir=args.outdir)
    sm = rp.executar(mpa=args.mpa, cookie=args.cookie or "",
                     com_runtime=args.runtime, com_seguir=args.seguir,
                     com_browser=args.browser)
    print(f"[+] site_map: {rp.workdir / 'site_map.json'}")
    print(f"[+] relatório: {rp.workdir / 'RECON.md'}")
    print(f"[+] vendor={sm.vendor} adapter={sm.adapter} confianca={sm.confianca} "
          f"endpoints={len(sm.apis_static)} rotas={len(sm.frontend_routes)} js={sm.js_downloaded}")
    if sm.browser_renderizado:
        print(f"[+] render: final={sm.browser_url_final} candidatos={len(sm.candidatos_browser)}"
              + (f" pista_adapter={sm.adapter_hint}" if sm.adapter_hint else ""))
    if sm.portal_transparencia:
        print(f"[+] portal de transparência: {sm.portal_transparencia}")
    if sm.limitacoes:
        print(f"[!] {sm.limitacoes}")
    return 0


def cmd_browser(args) -> int:
    ok, motivo = Navegador.disponivel()
    if not ok:
        print(f"[!] {motivo}", file=sys.stderr)
        return 127
    desc = Navegador(timeout_ms=args.timeout * 1000).descobrir_portal(
        args.url, espera_ms=args.espera, max_candidatos=args.limite)
    _print_json(desc.to_dict())
    return 0


def cmd_harvest(args) -> int:
    recon = ApiRecon(args.outdir)
    res = recon.harvest_static(args.url)
    print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)
    print(f"[+] resumo: {json.dumps(recon.resumo(), ensure_ascii=False)}")
    return res.returncode


def cmd_spider(args) -> int:
    recon = ApiRecon(args.outdir)
    res = recon.spider_mpa(args.url, cookie=args.cookie or "", max_paginas=args.max,
                           depth=args.depth)
    print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)
    return res.returncode


def cmd_fingerprint(args) -> int:
    fp = fingerprint.fingerprint_jsdir(args.jsdir)
    _print_json(fp)
    return 0


def cmd_endpoints(args) -> int:
    recon = ApiRecon(args.outdir)
    _print_json({
        "workdir": str(recon.workdir),
        "endpoints": recon.endpoints(),
        "routes": recon.routes(),
        "paths_other": recon.paths_other(),
        "resumo": recon.resumo(),
    })
    return 0


def cmd_runtime(args) -> int:
    workdir = Path(args.config).parent
    recon = ApiRecon(workdir)
    res = recon.runtime_harvest(args.config)
    print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)
    return res.returncode


def cmd_rea_sqlite(args) -> int:
    _print_json(REA().inspect_sqlite(
        args.db, table=args.table, columns=args.column,
        row_limit=args.row_limit, schema_scope=args.schema_scope))
    return 0


def cmd_rea_js(args) -> int:
    _print_json(REA().analyze_javascript_application(args.path))
    return 0


def cmd_rea_targets(args) -> int:
    _print_json(REA().list_browser_targets(args.cdp))
    return 0


def cmd_rea_web(args) -> int:
    _print_json(REA().inspect_web_page(
        args.cdp, args.target,
        include_script_sources=args.sources,
        include_json_body_shapes=args.body_shapes,
        observation_ms=args.observation_ms))
    return 0


def cmd_rea_bundle(args) -> int:
    _print_json(REA().analyze_web_bundle(
        args.cdp, args.target, fetch_source_maps=args.sourcemaps,
        observation_ms=args.observation_ms))
    return 0


def cmd_rea_managed(args) -> int:
    if args.members:
        _print_json(REA().inspect_managed_members(args.path, tipo=args.type))
    else:
        _print_json(REA().inspect_managed_artifact(args.path))
    return 0


def _arg_payload(valor: str):
    """Aceita um caminho de arquivo OU uma string JSON inline."""
    p = Path(valor)
    if p.exists():
        return p
    return valor  # JSON inline — o REA parseia


def cmd_rea_go(args) -> int:
    _print_json(REA().inspect_go_binary(args.path))
    return 0


def cmd_rea_wasm(args) -> int:
    _print_json(REA().inspect_wasm_artifact(args.path))
    return 0


def cmd_rea_har(args) -> int:
    _print_json(REA().inspect_web_network_capture(
        args.path, fmt=args.formato, records=args.record))
    return 0


def cmd_rea_view(args) -> int:
    _print_json(REA().inspect_analysis_view(_arg_payload(args.entrada)))
    return 0


def cmd_rea_trace(args) -> int:
    _print_json(REA().trace_application_feature(_arg_payload(args.entrada)))
    return 0


def cmd_rea_reconcile(args) -> int:
    _print_json(REA().reconcile_javascript_runtime(_arg_payload(args.entrada)))
    return 0


def cmd_rea_compare(args) -> int:
    _print_json(REA().compare_application_versions(args.left, args.right))
    return 0


def cmd_rea_evidence(args) -> int:
    if args.out:
        _print_json(REA().evidence_export(args.entrada, args.out))
    else:
        _print_json(REA().evidence_import(args.entrada))
    return 0


def cmd_rea_providers(args) -> int:
    _print_json(REA().providers())
    return 0


def cmd_rea_doctor(args) -> int:
    _print_json(REA().doctor(provider=args.provider, scope=args.scope))
    return 0


def cmd_mcp_config(args) -> int:
    _print_json(caminhos.mcp_config())
    return 0


def cmd_playwright(args) -> int:
    pwc = PlaywrightCLI()
    if not pwc.disponivel():
        print("[!] playwright-cli indisponível. Defina ENEMY_PLAYWRIGHT_CLI ou "
              "instale no PATH.", file=sys.stderr)
        return 127
    res = pwc.run(*args.playwright_args)
    print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)
    return res.returncode


def cmd_grafo_resumo(args) -> int:
    g = GrafoAuditoria.carregar(args.grafo)
    _print_json({
        "resumo": g.resumo(),
        "fornecedores_multi_orgao": g.fornecedores_multi_orgao()[:20],
        "operadores": g.operadores()[:20],
    })
    return 0


def cmd_grafo_graphml(args) -> int:
    g = GrafoAuditoria.carregar(args.entrada)
    out = g.exportar_graphml(args.saida)
    if out is None:
        print("[!] networkx não instalado — GraphML não gerado.", file=sys.stderr)
        return 1
    print(f"[+] GraphML: {out}")
    return 0


# ── parser ─────────────────────────────────────────────────────────────────
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m complexo",
        description="Integração ARTEX (recon/browser) + REA (reverse) no EnemyDisclosure.",
    )
    sub = p.add_subparsers(dest="comando", required=True)

    sub.add_parser("doctor", help="diagnóstico do ambiente").set_defaults(func=cmd_doctor)

    r = sub.add_parser("recon", help="recon completo de um portal")
    r.add_argument("url", nargs="?", help="URL do portal")
    r.add_argument("--slug", help="slug do órgão em core.config.PERFIS")
    r.add_argument("--outdir", help="diretório de saída")
    r.add_argument("--mpa", action="store_true", help="crawl MPA (server-rendered)")
    r.add_argument("--runtime", action="store_true", help="também roda o runtime (depth)")
    r.add_argument("--seguir", action="store_true",
                   help="seguir os links do portal de transparência e re-fingerprintar")
    r.add_argument("--browser", action="store_true",
                   help="renderizar com Playwright p/ achar o portal em sites JS-heavy")
    r.add_argument("--cookie", help="cookie de sessão (MPA)")
    r.set_defaults(func=cmd_recon)

    h = sub.add_parser("harvest", help="harvest estático (SPA)")
    h.add_argument("url")
    h.add_argument("--outdir", required=True)
    h.set_defaults(func=cmd_harvest)

    s = sub.add_parser("spider", help="crawl BFS (MPA)")
    s.add_argument("url")
    s.add_argument("--outdir", required=True)
    s.add_argument("--cookie", default="")
    s.add_argument("--max", type=int, default=200)
    s.add_argument("--depth", type=int, default=4)
    s.set_defaults(func=cmd_spider)

    f = sub.add_parser("fingerprint", help="fingerprint de vendor pelos bundles JS")
    f.add_argument("jsdir")
    f.set_defaults(func=cmd_fingerprint)

    e = sub.add_parser("endpoints", help="lista endpoints/rotas de um recon")
    e.add_argument("outdir")
    e.set_defaults(func=cmd_endpoints)

    rt = sub.add_parser("runtime", help="runtime_harvest.js (depth mode)")
    rt.add_argument("config")
    rt.set_defaults(func=cmd_runtime)

    rs = sub.add_parser("rea-sqlite", help="inspeciona snapshot SQLite (REA)")
    rs.add_argument("db")
    rs.add_argument("--table")
    rs.add_argument("--column", action="append")
    rs.add_argument("--row-limit", type=int)
    rs.add_argument("--schema-scope", choices=["inventory", "selected_table", "database"])
    rs.set_defaults(func=cmd_rea_sqlite)

    rj = sub.add_parser("rea-js", help="analisa app JavaScript (REA)")
    rj.add_argument("path")
    rj.set_defaults(func=cmd_rea_js)

    rtar = sub.add_parser("rea-targets", help="lista alvos do browser via CDP (REA)")
    rtar.add_argument("cdp", nargs="?", default="http://127.0.0.1:9222")
    rtar.set_defaults(func=cmd_rea_targets)

    rw = sub.add_parser("rea-web", help="inspeciona página web via CDP (REA)")
    rw.add_argument("cdp")
    rw.add_argument("target")
    rw.add_argument("--sources", action="store_true")
    rw.add_argument("--body-shapes", action="store_true")
    rw.add_argument("--observation-ms", type=int)
    rw.set_defaults(func=cmd_rea_web)

    rb = sub.add_parser("rea-bundle", help="analisa bundle web via CDP (REA)")
    rb.add_argument("cdp")
    rb.add_argument("target")
    rb.add_argument("--sourcemaps", action="store_true")
    rb.add_argument("--observation-ms", type=int)
    rb.set_defaults(func=cmd_rea_bundle)

    rm = sub.add_parser("rea-managed", help="inspeção de binário .NET (REA)")
    rm.add_argument("path")
    rm.add_argument("--members", action="store_true")
    rm.add_argument("--type")
    rm.set_defaults(func=cmd_rea_managed)

    rg = sub.add_parser("rea-go", help="metadados de build de binário Go (REA)")
    rg.add_argument("path")
    rg.set_defaults(func=cmd_rea_go)

    rwa = sub.add_parser("rea-wasm", help="validação de artefato WASM (REA)")
    rwa.add_argument("path")
    rwa.set_defaults(func=cmd_rea_wasm)

    rh = sub.add_parser("rea-har", help="inspeção offline de captura HAR (REA)")
    rh.add_argument("path")
    rh.add_argument("--formato", default="har")
    rh.add_argument("--record", action="append", type=int,
                    help="ordinal do registro (pode repetir; omitir = todos)")
    rh.set_defaults(func=cmd_rea_har)

    rv = sub.add_parser("rea-view", help="projeta summary/API-surface de Evidence (REA)")
    rv.add_argument("entrada", help="arquivo JSON ou JSON inline")
    rv.set_defaults(func=cmd_rea_view)

    rt = sub.add_parser("rea-trace", help="traça feature na Application Graph (REA)")
    rt.add_argument("entrada", help="arquivo JSON ou JSON inline")
    rt.set_defaults(func=cmd_rea_trace)

    rr = sub.add_parser("rea-reconcile", help="funde graph estático + runtime (REA)")
    rr.add_argument("entrada", help="arquivo JSON ou JSON inline")
    rr.set_defaults(func=cmd_rea_reconcile)

    rc = sub.add_parser("rea-compare", help="compara duas versões/Evidence (REA)")
    rc.add_argument("left")
    rc.add_argument("right")
    rc.set_defaults(func=cmd_rea_compare)

    rev = sub.add_parser("rea-evidence", help="importa/exporta bundle de evidência (REA)")
    rev.add_argument("entrada")
    rev.add_argument("--out", help="se dado, exporta para este caminho")
    rev.set_defaults(func=cmd_rea_evidence)

    rp = sub.add_parser("rea-providers", help="lista providers nativos do REA")
    rp.set_defaults(func=cmd_rea_providers)

    rd = sub.add_parser("rea-doctor", help="diagnóstico de prontidão do REA")
    rd.add_argument("--provider")
    rd.add_argument("--scope")
    rd.set_defaults(func=cmd_rea_doctor)

    br = sub.add_parser("browser", help="descoberta renderizada de portal (Playwright)")
    br.add_argument("url")
    br.add_argument("--espera", type=int, default=2500, help="ms após o goto")
    br.add_argument("--timeout", type=int, default=25, help="timeout do goto (s)")
    br.add_argument("--limite", type=int, default=8, help="nº máx. de candidatos")
    br.set_defaults(func=cmd_browser)

    mc = sub.add_parser("mcp-config", help="bloco .mcp.json para registrar o REA")
    mc.set_defaults(func=cmd_mcp_config)

    pw = sub.add_parser("playwright", help="repassa para o playwright-cli")
    pw.add_argument("playwright_args", nargs=argparse.REMAINDER)
    pw.set_defaults(func=cmd_playwright)

    gr = sub.add_parser("grafo-resumo", help="resumo de um grafo de auditoria")
    gr.add_argument("grafo")
    gr.set_defaults(func=cmd_grafo_resumo)

    gg = sub.add_parser("grafo-graphml", help="exporta asset graph p/ GraphML")
    gg.add_argument("entrada")
    gg.add_argument("saida")
    gg.set_defaults(func=cmd_grafo_graphml)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (REA.Indisponivel, PlaywrightCLI.Indisponivel, Navegador.Indisponivel) as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 127
    except FileNotFoundError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
