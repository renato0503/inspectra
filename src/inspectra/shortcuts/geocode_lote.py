"""
Geocodifica lote de CNPJs em paralelo (ThreadPoolExecutor).

Cada CNPJ e geocodificado: endereco -> lat/lon via Nominatim/OSM.
Usa cache local para evitar requests repetidos.

Uso:
    python -m inspectra.shortcuts.cli geocode_lote cnpjs.csv
    python -m inspectra.shortcuts.cli geocode_lote cnpjs.csv --max-workers 8
    python -m inspectra.shortcuts.cli geocode_lote --lista 07192414000109 12345678000199
    python -m inspectra.shortcuts.cli geocode_lote cnpjs.csv --json
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Optional

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(RAIZ / "src"))

from inspectra.shortcuts._output import output

CACHE_FILE = RAIZ / "shared_data" / "geocode_cache.json"

# Nominatim: 1 req/s
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def _load_cache() -> Dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(cache: Dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _norm_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def _endereco_from_brasilapi(cnpj: str) -> Optional[str]:
    """Constrói endereco a partir do cache BrasilAPI."""
    cache = RAIZ / "shared_data" / "brasilapi_cnpj.json"
    if not cache.exists():
        return None
    try:
        db = json.loads(cache.read_text())
        cnpj_limpo = _norm_cnpj(cnpj)
        if cnpj_limpo not in db:
            return None
        d = db[cnpj_limpo]
        partes = []
        if d.get("logradouro"):
            partes.append(d["logradouro"])
        if d.get("numero") and d["numero"] != "S/N":
            partes[-1] += f", {d['numero']}"
        if d.get("bairro"):
            partes.append(d["bairro"])
        if d.get("municipio"):
            partes.append(d["municipio"])
        if d.get("uf"):
            partes.append(d["uf"])
            partes.append("Brasil")
        return ", ".join(partes) if partes else None
    except Exception:
        return None


def _geocode_nominatim(endereco: str, cache: Dict) -> Optional[Dict]:
    """Geocodifica via Nominatim com cache."""
    if endereco in cache:
        return cache[endereco]
    try:
        import urllib.parse
        import urllib.request
        params = urllib.parse.urlencode({
            "q": endereco,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
        })
        req = urllib.request.Request(
            f"{NOMINATIM_URL}?{params}",
            headers={"User-Agent": "Inspectra/1.0 (gestor.renatorosa@gmail.com)"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data:
            resultado = {
                "lat": float(data[0]["lat"]),
                "lon": float(data[0]["lon"]),
                "tipo_zona": data[0].get("type", "?"),
                "display_name": data[0].get("display_name", "")[:200],
            }
            cache[endereco] = resultado
            return resultado
    except Exception:
        pass
    cache[endereco] = None
    return None


def _geocode_cnpj(cnpj: str, cache: Dict) -> Dict:
    """Geocodifica um CNPJ. Retorna dict com resultado."""
    cnpj_limpo = _norm_cnpj(cnpj)
    endereco = _endereco_from_brasilapi(cnpj_limpo)
    if not endereco:
        return {"cnpj": cnpj_limpo, "geocodificado": False, "erro": "Endereco nao encontrado no cache BrasilAPI"}
    resultado = _geocode_nominatim(endereco, cache)
    if resultado:
        return {
            "cnpj": cnpj_limpo,
            "endereco": endereco,
            "lat": resultado["lat"],
            "lon": resultado["lon"],
            "tipo_zona": resultado["tipo_zona"],
            "geocodificado": True,
        }
    return {
        "cnpj": cnpj_limpo,
        "endereco": endereco,
        "geocodificado": False,
        "erro": "Nominatim nao encontrou coordenadas",
    }


def geocode_lote(
    cnpjs: List[str],
    max_workers: int = 4,
    cache: Optional[Dict] = None,
) -> dict:
    """Geocodifica lista de CNPJs em paralelo. Retorna JSON estruturado."""
    inicio = time.time()

    if not cnpjs:
        return output(True, {"total": 0, "sucessos": 0, "falhas": 0, "resultados": []},
                     "Nominatim + BrasilAPI", prompt_hint="Lista vazia.")

    cache = cache or _load_cache()
    resultados = []
    sucessos = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_geocode_cnpj, cnpj, cache): cnpj for cnpj in cnpjs}
        for i, future in enumerate(as_completed(futures), 1):
            r = future.result()
            if r["geocodificado"]:
                sucessos += 1
            resultados.append(r)
            if i % 20 == 0:
                _save_cache(cache)

    _save_cache(cache)

    dados = {
        "total": len(cnpjs),
        "sucessos": sucessos,
        "falhas": len(cnpjs) - sucessos,
        "resultados": resultados,
    }
    hint = f"{sucessos}/{len(cnpjs)} geocodificados. Cache salvo em geocode_cache.json."
    tempo = round((time.time() - inicio) * 1000)
    resultado = output(True, dados, "Nominatim + BrasilAPI", prompt_hint=hint)
    resultado["meta"]["tempo_ms"] = tempo
    return resultado


def _ler_csv_cnpjs(arquivo: str) -> List[str]:
    """Extrai CNPJs de CSV (coluna 'cnpj' ou primeira coluna)."""
    cnpjs = []
    try:
        with open(arquivo, encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            cnpj_col = None
            for i, h in enumerate(headers):
                if "cnpj" in h.lower() or "cpf" in h.lower():
                    cnpj_col = i
                    break
            if cnpj_col is None:
                cnpj_col = 0
            for row in reader:
                if len(row) > cnpj_col:
                    cnpj = row[cnpj_col].strip()
                    cnpj_limpo = re.sub(r"\D", "", cnpj)
                    if 11 <= len(cnpj_limpo) <= 14:
                        cnpjs.append(cnpj)
    except Exception as e:
        return []
    return cnpjs


def main():
    p = argparse.ArgumentParser(prog="geocode_lote")
    p.add_argument("arquivo", nargs="?", help="CSV com CNPJs")
    p.add_argument("--lista", nargs="*", help="CNPJs diretamente (espacos)")
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if args.lista:
        cnpjs = args.lista
    elif args.arquivo:
        cnpjs = _ler_csv_cnpjs(args.arquivo)
    else:
        p.print_help()
        return 1

    resultado = geocode_lote(cnpjs, max_workers=args.max_workers)

    if args.json:
        print_json(resultado)
    else:
        dados = resultado["dados"]
        print(f"\n=== Geocodificacao: {dados['sucessos']}/{dados['total']} OK ===")
        print(f"Tempo: {resultado['meta']['tempo_ms']:.0f}ms")
        print(f"\nSucessos:")
        for r in dados["resultados"]:
            if r.get("geocodificado"):
                print(f"  {r['cnpj']}: ({r['lat']}, {r['lon']}) [{r['tipo_zona']}]")
        print(f"\nFalhas ({dados['falhas']}):")
        for r in dados["resultados"]:
            if not r.get("geocodificado"):
                print(f"  {r['cnpj']}: {r.get('erro', '?')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
