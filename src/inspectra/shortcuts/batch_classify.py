"""
Roda classificar.py em todos os orgaos que tem analises_<ano>.json.

Processa em batch, com rate limiting para nao saturar Ollama.

Uso:
    python -m core.ia.batch_classify 2025 --model gemma4:latest
    python -m core.ia.batch_classify 2025 --model gemma4-26b --delay 5
    python -m core.ia.batch_classify 2025 --only prefeitura_cuiaba camara_cuiaba
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

from inspectra.shortcuts.classificar import classificar_orgaos

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))


def listar_orgaos(ano: int) -> list:
    """Retorna slug-andoor cada orgao que tem analises_<ano>.json."""
    encontrados = []
    for muni in (RAIZ / "orgaos").iterdir():
        if not muni.is_dir():
            continue
        for slug in muni.iterdir():
            if not slug.is_dir():
                continue
            jp = slug / "data" / "export" / f"analises_{ano}.json"
            if jp.exists():
                encontrados.append(slug.name)
    return sorted(encontrados)


def main():
    p = argparse.ArgumentParser(description="Classifica achados do B-suite em batch")
    p.add_argument("ano", type=int, help="Exercicio")
    p.add_argument("--model", default="gemma4:latest")
    p.add_argument("--only", nargs="+", help="Apenas estes orgaos")
    p.add_argument("--skip", nargs="+", help="Pular estes orgaos")
    p.add_argument("--temperatura", type=float, default=0.1)
    p.add_argument("--delay", type=float, default=2.0,
                    help="Delay entre orgaos em segundos (default 2)")
    p.add_argument("--force", action="store_true",
                    help="Re-classifica mesmo se _classificadas.json ja existe")
    args = p.parse_args()

    orgaos = listar_orgaos(args.ano)
    if args.only:
        orgaos = [o for o in orgaos if o in args.only]
    if args.skip:
        orgaos = [o for o in orgaos if o not in args.skip]

    print(f"Orgaos com analises_{args.ano}.json: {len(orgaos)}")
    for o in orgaos:
        print(f"  - {o}")
    print(f"\nModelo: {args.model} | Delay: {args.delay}s | Force: {args.force}")
    print(f"Temperatura: {args.temperatura}\n")

    import time
    sucessos = 0
    falhas = []
    pulados = 0
    for i, orgao in enumerate(orgaos, 1):
        # Pula se ja classificado (a menos que --force)
        jp_class = list((RAIZ / "orgaos").rglob(f"analises_{args.ano}_classificadas.json"))
        ja_feito = any(orgao in str(p) for p in jp_class)
        if ja_feito and not args.force:
            print(f"[{i}/{len(orgaos)}] {orgao}: ja classificado, pulando (use --force)")
            pulados += 1
            continue

        print(f"[{i}/{len(orgaos)}] {orgao}: classificando...")
        rc = classificar_orgaos(orgao, args.ano, args.model, args.temperatura)
        if rc == 0:
            sucessos += 1
        else:
            falhas.append(orgao)
        if i < len(orgaos):
            time.sleep(args.delay)

    print(f"\nResumo: {sucessos} ok, {len(falhas)} falhas, {pulados} pulados")
    if falhas:
        print(f"Falhas: {', '.join(falhas)}")
    return 0 if not falhas else 1


if __name__ == "__main__":
    sys.exit(main())