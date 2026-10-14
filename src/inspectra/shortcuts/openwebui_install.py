"""
Instala as custom tools do Inspectra no container Docker do Open WebUI.

O script copia os arquivos de tools para o diretorio de volume mountado
do container (`/app/backend/open_webui/tools/custom`) e reinicia o container.

Uso:
    python -m inspectra.shortcuts.openwebui_install          # instalacao padrao
    python -m inspectra.shortows.openwebui_install --check   # mostra status
    python -m inspectra.shortcuts.openwebui_install --restart  # reinicia container
    python -m inspectra.shortcuts.openwebui_install --logs  # logs do container
"""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
import sys
import os
from pathlib import Path

try:
    import docker
    HAS_DOCKER = True
except ImportError:
    HAS_DOCKER = False

CONTAINER_NAME = "open-webui"
TOOLS_SOURCE = Path(__file__).resolve().parents[2] / "tools"
TOOLS_DEST_INSIDE_CONTAINER = "/app/backend/open_webui/tools/custom"


def _get_container():
    """Retorna o cliente Docker e o container do Open WebUI."""
    if not HAS_DOCKER:
        raise RuntimeError(
            "Biblioteca 'docker' nao instalada. Instale com: pip install docker"
        )
    try:
        client = docker.from_env()
    except Exception as e:
        raise RuntimeError(f"Docker nao esta rodando: {e}") from e
    try:
        container = client.containers.get(CONTAINER_NAME)
    except docker.errors.NotFound:
        raise RuntimeError(
            f"Container '{CONTAINER_NAME}' nao encontrado. "
            "Verifique se o Open WebUI esta rodando com: docker ps"
        ) from None
    return client, container


def cmd_check(args) -> int:
    """Mostra status atual."""
    print(f"Container: {CONTAINER_NAME}")
    try:
        _, container = _get_container()
        print(f"Status: {container.status}")
        print(f"Image: {container.image.tags}")
        # Verifica volume mount
        mounts = {m["Destination"]: m["Source"] for m in container.attrs.get("Mounts", [])}
        print(f"\nMounts relevantes:")
        for dest, src in mounts.items():
            if "open_webui" in dest or "custom" in dest:
                print(f"  {dest} -> {src}")
        # Lista tools no container
        result = container.exec_run("ls", "-la", TOOLS_DEST_INSIDE_CONTAINER)
        if result.exit_code == 0:
            print(f"\nTools no container ({TOOLS_DEST_INSIDE_CONTAINER}):")
            for line in result.output.decode().split("\n"):
                print(f"  {line}")
        else:
            print(f"\n[AVISO] Diretorio de tools nao encontrado no container (exit {result.exit_code})")
        return 0
    except RuntimeError as e:
        print(f"[ERRO] {e}")
        return 1


def cmd_install(args) -> int:
    """Copia tools para o container."""
    print(f"Fonte: {TOOLS_SOURCE}")
    if not TOOLS_SOURCE.exists():
        print(f"[ERRO] Pasta de tools nao encontrada: {TOOLS_SOURCE}")
        return 1
    try:
        _, container = _get_container()
    except RuntimeError as e:
        print(f"[ERRO] {e}")
        return 1

    print(f"Container: {container.name} ({container.status})")

    # Copia via docker cp
    import tempfile, tarfile, io
    tools_tmp = Path(tempfile.gettempdir()) / "inspectra_tools"
    shutil.copytree(TOOLS_SOURCE, tools_tmp, dirs_exist_ok=True)
    print(f"Copiando tools para container...")
    try:
        container.put_archive("/", [(str(tools_tmp), ".")])
        print("[OK] Tools copiados para o container")
    except Exception as e:
        print(f"[ERRO] Falha ao copiar: {e}")
        return 1
    finally:
        shutil.rmtree(tools_tmp, ignore_errors=True)

    # Tambem copia para o host (volume mount)
    mount_path = Path(os.environ.get("USERPROFILE", "")) / "open_webui_tools_custom"
    # Procura o volume mount no host
    try:
        mounts = {m["Destination"]: m["Source"] for m in container.attrs.get("Mounts", [])}
    except Exception:
        mounts = {}
    dest_host = None
    for dest in mounts:
        if "open_webui" in dest.lower() and "custom" in dest.lower():
            dest_host = Path(mounts[dest])
            break
    if dest_host and dest_host.exists():
        shutil.copytree(TOOLS_SOURCE, dest_host, dirs_exist_ok=True)
        print(f"[OK] Tools tambem copiados para volume mount: {dest_host}")
    else:
        print(f"[INFO] Volume mount nao detectado — reinicie o container com --restart")

    print("\nTools instalados:")
    for f in TOOLS_SOURCE.glob("*.py"):
        print(f"  - {f.name}")
    print("\nAcesse http://localhost:3000/workspace/tools para ativar.")
    return 0


def cmd_restart(args) -> int:
    """Reinicia o container."""
    try:
        _, container = _get_container()
    except RuntimeError as e:
        print(f"[ERRO] {e}")
        return 1
    print(f"Reiniciando {container.name}...")
    container.restart()
    print("[OK] Container reiniciado. Aguarde 10 segundos...")
    import time; time.sleep(10)
    return 0


def cmd_logs(args) -> int:
    """Mostra logs do container."""
    try:
        _, container = _get_container()
    except RuntimeError as e:
        print(f"[ERRO] {e}")
        return 1
    print(f"=== Logs de {container.name} (ultimas {args.lines} linhas) ===")
    logs = container.logs(tail=args.lines).decode()
    print(logs[-3000:] if len(logs) > 3000 else logs)
    return 0


def main():
    p = argparse.ArgumentParser(prog="openwebui_install")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("install", help="Instala custom tools no container Open WebUI")
    sub.add_parser("check", help="Mostra status atual do container e tools")
    sub.add_parser("restart", help="Reinicia o container do Open WebUI")
    sp = sub.add_parser("logs", help="Mostra logs do container")
    sp.add_argument("--lines", type=int, default=50)

    args = p.parse_args()
    if args.cmd == "install":
        return cmd_install(args)
    elif args.cmd == "check":
        return cmd_check(args)
    elif args.cmd == "restart":
        return cmd_restart(args)
    elif args.cmd == "logs":
        return cmd_logs(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
