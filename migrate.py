"""Copia atalhos, complexo e openwebui_tools do EnemyDisclosure para Inspectra."""
import shutil
from pathlib import Path

RAIZ_ED = Path(r"D:\Dev\EnemyDisclosure")
RAIZ_INS = RAIZ_ED / "produto" / "inspectra"

ATALHOS = [
    "investigar.py", "analise.py", "ranking.py", "sancoes.py",
    "buscar.py", "sql.py", "shell.py", "dossie.py", "cronograma.py",
    "pessoas.py", "classificar.py", "cron_monitor.py", "regen_dossies.py",
    "batch_classify.py", "cli.py", "__main__.py", "__init__.py", "README.md",
]

for nome in ATALHOS:
    src = RAIZ_ED / "core" / "ia" / "atalhos" / nome
    dst = RAIZ_INS / "src" / "inspectra" / "shortcuts" / nome
    if src.exists():
        shutil.copy(src, dst)
        print(f"copied: {nome}")
    else:
        print(f"missing: {nome}")

src = RAIZ_ED / "complexo"
dst = RAIZ_INS / "src" / "inspectra" / "ingestao"
if src.exists():
    for arq in src.rglob("*"):
        if arq.is_file():
            rel = arq.relative_to(src)
            destino = dst / rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(arq, destino)
    print(f"copied: complexo/ ({len(list(dst.rglob('*')))} arquivos)")

for py in (RAIZ_ED / "core" / "ia" / "openwebui_tools").glob("*.py"):
    shutil.copy(py, RAIZ_INS / "src" / "inspectra" / "tools" / py.name)
    print(f"copied: openwebui_tools/{py.name}")