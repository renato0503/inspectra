"""
Extrai metadados EXIF de imagens (GPS, camera, software, data).

Uso:
    python -m inspectra.shortcuts.cli metadados foto.jpg
    python -m inspectra.shortcuts.cli metadados foto.jpg --json
    python -m inspectra.shortcuts.cli metadados *.jpg --diretorio ./fotos
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(RAIZ / "src"))

from inspectra.shortcuts._output import output


def _tem_pillow() -> bool:
    try:
        from PIL import Image
        return True
    except ImportError:
        return False


def _tem_exif(img_path: Path) -> dict:
    """Extrai EXIF de imagem. Retorna dict."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS
    except ImportError:
        return {"erro": "Pillow nao instalado (pip install Pillow)"}

    try:
        img = Image.open(img_path)
        exif_data = img._getexif()
        if not exif_data:
            return {"exif": None, "tem_exif": False}
    except Exception as e:
        return {"erro": f"Falha ao ler EXIF: {e}"}

    resultado = {"exif": {}, "tem_exif": True}
    gps_info = {}

    for tag_id, value in exif_data.items():
        tag = TAGS.get(tag_id, tag_id)
        if tag == "GPSInfo":
            for gps_tag in value:
                gps_tag_name = GPSTAGS.get(gps_tag, gps_tag)
                gps_info[gps_tag_name] = str(value[gps_tag])
        else:
            resultado["exif"][str(tag)] = str(value)[:200]

    if gps_info:
        resultado["gps"] = gps_info
        lat = gps_info.get("GPSLatitude")
        lon = gps_info.get("GPSLongitude")
        if lat and lon:
            resultado["gps_str"] = f"{lat}, {lon}"

    return resultado


def _tem_pii(exif: dict) -> bool:
    """Detecta se EXIF contem PII (GPS, CPF de photographer)."""
    if exif.get("gps"):
        return True
    exif_data = exif.get("exif") or {}
    for v in exif_data.values():
        vlow = str(v).lower()
        if any(x in vlow for x in ["cpf", "documento", "passaporte"]):
            return True
    return False


def extrair_metadados(caminho: str) -> dict:
    """Extrai metadados de uma imagem. Retorna JSON estruturado."""
    inicio = time.time()
    img_path = Path(caminho)

    if not img_path.exists():
        return output(False, None, "Pillow/EXIF", erro=f"Arquivo nao encontrado: {caminho}")

    tamanho = img_path.stat().st_size
    nome, ext = os.path.splitext(img_path.name)
    ext = ext.lower()

    if ext not in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".heic", ".heif"):
        return output(False, None, "Pillow/EXIF", erro=f"Formato nao suportado: {ext}")

    exif = _tem_exif(img_path)
    if "erro" in exif:
        return output(False, None, "Pillow/EXIF", erro=exif["erro"])

    tem_pii = _tem_pii(exif)

    dados = {
        "arquivo": str(img_path.name),
        "tamanho_bytes": tamanho,
        "tamanho_formatado": _format_size(tamanho),
        "formato": ext,
        "tem_exif": exif.get("tem_exif", False),
        "exif": exif.get("exif"),
        "gps": exif.get("gps"),
        "gps_str": exif.get("gps_str"),
        "tem_pii": tem_pii,
        "pii_flags": _pii_flags(exif),
    }

    hint = f"{'TEM GPS - cuidado com PII' if tem_pii else 'Sem GPS/PII'}. " \
           f"{len(exif.get('exif') or {})} campos EXIF."

    tempo = round((time.time() - inicio) * 1000)
    resultado = output(True, dados, "Pillow/EXIF", prompt_hint=hint)
    resultado["meta"]["tempo_ms"] = tempo
    return resultado


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _pii_flags(exif: dict) -> list:
    flags = []
    if exif.get("gps"):
        flags.append("GPS")
    exif_data = exif.get("exif") or {}
    exif_vals = str(exif_data)
    if "cpf" in exif_vals.lower():
        flags.append("CPF")
    if "documento" in exif_vals.lower():
        flags.append("DOCUMENTO")
    if "author" in exif_vals.lower() or "artist" in exif_vals.lower():
        flags.append("AUTOR")
    return flags


def _processar_diretorio(diretorio: str, extensao: str = ".jpg") -> list:
    """Processa todas as imagens de um diretorio."""
    dir_path = Path(diretorio)
    if not dir_path.is_dir():
        return []
    resultados = []
    for img in dir_path.glob(f"*{extensao}"):
        r = extrair_metadados(str(img))
        resultados.append(r["dados"])
    return resultados


def main():
    p = argparse.ArgumentParser(prog="metadados")
    p.add_argument("arquivo", nargs="?", help="Arquivo de imagem")
    p.add_argument("--diretorio", help="Processar todos os arquivos de um diretorio")
    p.add_argument("--extensao", default=".jpg", help="Extensao a filtrar no diretorio")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if args.diretorio:
        resultados = _processar_diretorio(args.diretorio, args.extensao)
        resultado = output(True, {"total": len(resultados), "resultados": resultados},
                          "Pillow/EXIF", prompt_hint=f"{len(resultados)} imagens processadas.")
    elif args.arquivo:
        resultado = extrair_metadados(args.arquivo)
    else:
        p.print_help()
        return 1

    if args.json:
        print_json(resultado)
    else:
        dados = resultado["dados"]
        if isinstance(dados, dict) and "resultados" in dados:
            print(f"\n=== {dados['total']} imagens processadas ===")
            for r in dados["resultados"]:
                pii = "[PII]" if r.get("tem_pii") else ""
                gps = f"[GPS: {r.get('gps_str', '?')}]" if r.get("gps") else ""
                print(f"  {r['arquivo']} {pii}{gps}")
        else:
            print(f"\n=== {dados['arquivo']} ===")
            print(f"Tamanho: {dados['tamanho_formatado']} | Formato: {dados['formato']}")
            print(f"EXIF: {dados['tem_exif']} | PII: {dados['tem_pii']}")
            if dados.get("gps_str"):
                print(f"GPS: {dados['gps_str']}")
            if dados.get("exif"):
                print(f"\nCampos EXIF ({len(dados['exif'])}):")
                for k, v in list(dados["exif"].items())[:10]:
                    print(f"  {k}: {v}")
            if dados.get("tem_pii"):
                print(f"\n[ALERTA] Esta imagem contem PII: {', '.join(dados.get('pii_flags', []))}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
