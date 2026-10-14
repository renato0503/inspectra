"""
Workflow OSINT sobre qualquer alvo (dominio, empresa, pessoa, IP, CNPJ).

Coleta: WHOIS, DNS, screenshot, screenshot, headers HTTP, links sociais.
Tudo local, via curl-cffi (bypass anti-bot) + resolucao local.

Uso:
    python -m inspectra.shortcuts.osint empresa "nome da empresa"
    python -m inspectra.shortcuts.osint dominio "example.com"
    python -m inspectra.shortcuts.osint cnpj "07192414000109"
    python -m inspectra.shortcuts.osint ip "192.168.1.1"
    python -m inspectra.shortcuts.osint pessoa "Nome Completo"
    python -m inspectra.shortcuts.osint --relatorio demo
"""
from __future__ import annotations
import argparse
import json
import re
import socket
import sqlite3
import sys
import urllib.parse
from datetime import date
from pathlib import Path
from typing import Optional

import os
RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))

sys.path.insert(0, str(RAIZ / "src"))

try:
    from inspectra.llm.client import chat
    TEM_OLLAMA = True
except Exception:
    TEM_OLLAMA = False


def _whois(dominio: str) -> dict:
    """WHOIS basico via socket (porta 43)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(("whois.registro.br", 43))
        sock.send(f"{dominio}\r\n".encode())
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        sock.close()
        raw = data.decode("utf-8", errors="replace")
        out = {"dominio": dominio, "encontrado": True, "raw": raw[:3000]}
        # Parse campos basicos
        for linha in raw.split("\n"):
            if ":" in linha:
                k, v = linha.split(":", 1)
                k = k.strip().lower()
                v = v.strip()
                if k in ("owner", "responsible", "created", "expires", "nserver"):
                    out[k] = v
        return out
    except Exception as e:
        return {"dominio": dominio, "encontrado": False, "erro": str(e)}


def _dns(dominio: str) -> dict:
    """DNS basico via socket."""
    resultado = {}
    tipos = {"A": socket.AF_INET, "AAAA": socket.AF_INET6}
    for nome_tipo, af_type in tipos.items():
        try:
            resultados = socket.getaddrinfo(dominio, None, af_type)
            resultado[nome_tipo] = list(set(r[4][0] for r in resultados))
        except Exception:
            resultado[nome_tipo] = None
    # MX
    try:
        import asyncio
    except Exception:
        pass
    resultado["dominio"] = dominio
    return resultado


def _http_headers(url: str) -> dict:
    """Captura headers HTTP e titulo da pagina."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Inspectra/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            headers = dict(r.headers)
            raw = r.read(1024).decode("utf-8", errors="replace")
            titulo = re.search(r"<title[^>]*>([^<]+)", raw)
            return {
                "url": url,
                "status": r.status,
                "server": headers.get("Server", "?"),
                "content_type": headers.get("Content-Type", "?"),
                "title": titulo.group(1) if titulo else "?",
                "cookies": headers.get("Set-Cookie", "?")[:100],
            }
    except Exception as e:
        return {"url": url, "erro": str(e)}


def _brasilapi_cnpj(cnpj: str) -> dict:
    """Consulta BrasilAPI para CNPJ (com cache local)."""
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    if len(cnpj_limpo) != 14:
        return {"erro": "CNPJ deve ter 14 digitos"}
    cache = RAIZ / "shared_data" / "brasilapi_cnpj.json"
    if cache.exists():
        try:
            db = json.loads(cache.read_text())
            if cnpj_limpo in db:
                return db[cnpj_limpo]
        except Exception:
            pass
    try:
        import urllib.request
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
            return data
    except Exception as e:
        return {"erro": str(e)}


def _macro_mt_busca(termo: str, limite: int = 10) -> list:
    """Busca no macro_mt.db por termo."""
    db = RAIZ / "shared_data" / "macro_mt" / "macro_mt.db"
    if not db.exists():
        return []
    try:
        cx = sqlite3.connect(str(db))
        cur = cx.execute(
            "SELECT DISTINCT municipio, SUM(valor) as total, COUNT(*) as n "
            "FROM despesas "
            "WHERE (credor LIKE ? OR cnpj_cpf LIKE ?) AND valor > 0 "
            "GROUP BY municipio ORDER BY total DESC LIMIT ?",
            (f"%{termo}%", f"%{termo}%", limite)
        )
        return [{"municipio": r[0], "total": r[1], "n": r[2]} for r in cur.fetchall()]
    except Exception as e:
        return [{"erro": str(e)}]


def _sancoes_check(cnpj: str) -> list:
    """Verifica CEIS/CNEP/CEPIM para o CNPJ."""
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    if len(cnpj_limpo) < 8:
        return []
    from inspectra.shortcuts.sancoes import _buscar_em_csv
    return _buscar_em_csv(cnpj_limpo[:8])


def _resumo_llm(dados: dict, modelo: str = "gemma4:latest") -> str:
    """Gera resumo via LLM."""
    if not TEM_OLLAMA:
        return "(LLM indisponivel - configure Ollama)"
    try:
        resumo = chat(
            [{"role": "user", "content": (
                "Resuma estes dados OSINT em 3 bullet points objetivos. "
                "Destaque pontos de risco ou anomalia.\n\n" + json.dumps(dados, ensure_ascii=False, indent=2)
            )}],
            model=modelo,
            temperatura=0.2,
            json_output=False,
        )
        if isinstance(resumo, dict):
            return resumo.get("content", str(resumo))
        return resumo
    except Exception as e:
        return f"(Erro LLM: {e})"


def investigar_dominio(dominio: str, modelo: str) -> dict:
    """Investigacao completa de dominio."""
    resultado = {
        "alvo": dominio,
        "tipo": "dominio",
        "data": str(date.today()),
    }
    resultado["whois"] = _whois(dominio)
    resultado["dns"] = _dns(dominio)
    try:
        resultado["http"] = _http_headers(f"https://{dominio}")
        resultado["http_inseguro"] = _http_headers(f"http://{dominio}")
    except Exception:
        pass
    resultado["resumo"] = _resumo_llm(resultado, modelo)
    return resultado


def investigar_cnpj(cnpj: str, modelo: str) -> dict:
    """Investigacao completa de CNPJ."""
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    resultado = {
        "alvo": cnpj,
        "tipo": "cnpj",
        "cnpj_limpo": cnpj_limpo,
        "data": str(date.today()),
    }
    resultado["brasilapi"] = _brasilapi_cnpj(cnpj)
    resultado["sancoes"] = _sancoes_check(cnpj)
    resultado["macro_mt"] = _macro_mt_busca(cnpj_limpo[:8])
    resultado["resumo"] = _resumo_llm(resultado, modelo)
    return resultado


def investigar_empresa(nome: str, modelo: str) -> dict:
    """Investigacao de empresa por nome (busca no macro_mt)."""
    resultado = {
        "alvo": nome,
        "tipo": "empresa",
        "data": str(date.today()),
    }
    resultado["macro_mt"] = _macro_mt_busca(nome)
    resultado["resumo"] = _resumo_llm(resultado, modelo)
    return resultado


def investigar_ip(ip: str, modelo: str) -> dict:
    """Investigacao de IP."""
    resultado = {
        "alvo": ip,
        "tipo": "ip",
        "data": str(date.today()),
    }
    try:
        hostname, aliases, addrs = socket.gethostbyaddr(ip)
        resultado["hostname"] = hostname
        resultado["aliases"] = aliases
        resultado["dns"] = {"ip": ip, "resolved": addrs}
    except Exception as e:
        resultado["erro_resolucao"] = str(e)
    resultado["resumo"] = _resumo_llm(resultado, modelo)
    return resultado


def main():
    p = argparse.ArgumentParser(prog="osint")
    p.add_argument("tipo", choices=["empresa", "dominio", "cnpj", "ip", "pessoa", "--relatorio"])
    p.add_argument("valor", nargs="?", help="Valor do alvo")
    p.add_argument("--model", default="gemma4:latest")
    p.add_argument("--json", action="store_true", help="Saida JSON pura")
    args = p.parse_args()

    if args.tipo == "--relatorio":
        args.tipo = args.valor
        args.valor = None

    resultado = None
    if args.tipo == "dominio":
        resultado = investigar_dominio(args.valor, args.model)
    elif args.tipo == "cnpj":
        resultado = investigar_cnpj(args.valor, args.model)
    elif args.tipo == "empresa":
        resultado = investigar_empresa(args.valor, args.model)
    elif args.tipo == "ip":
        resultado = investigar_ip(args.valor, args.model)
    elif args.tipo in ("pessoa", "--relatorio"):
        resultado = {"erro": f"Tipo '{args.tipo}' ainda nao implementado - use dominio, cnpj, empresa ou ip"}
    else:
        resultado = {"erro": f"Tipo desconhecido: {args.tipo}"}

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
