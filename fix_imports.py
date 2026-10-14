"""Atualiza imports nos arquivos migrados."""
import re
from pathlib import Path

RAIZ_INS = Path(r"D:\Dev\EnemyDisclosure\produto\inspectra\src\inspectra")

# Mapeamento: modulo antigo -> modulo novo
MIGRATIONS = {
    "core.ia.ollama_client": "inspectra.llm.client",
    "core.ia.coding_agent": "inspectra.agents.coding",
    "core.ia.agent": "inspectra.agents.react",
    "core.ia.audit_tools": "inspectra.tools.audit",
    "core.ia.atalhos.sancoes": "inspectra.shortcuts.sancoes",
    "core.ia.atalhos.dossie": "inspectra.shortcuts.dossie",
    "core.ia.atalhos.classificar": "inspectra.shortcuts.classificar",
    "core.ia.atalhos.cli": "inspectra.shortcuts.cli",
    "core.ia.atalhos.investigar": "inspectra.shortcuts.investigar",
    "core.ia.atalhos.analise": "inspectra.shortcuts.analise",
    "core.ia.atalhos.ranking": "inspectra.shortcuts.ranking",
    "core.ia.atalhos.buscar": "inspectra.shortcuts.buscar",
    "core.ia.atalhos.sql": "inspectra.shortcuts.sql",
    "core.ia.atalhos.shell": "inspectra.shortcuts.shell",
    "core.ia.atalhos.cronograma": "inspectra.shortcuts.cronograma",
    "core.ia.atalhos.pessoas": "inspectra.shortcuts.pessoas",
    "core.ia.classificar": "inspectra.shortcuts.classificar",
    "core.ia.cron_monitor": "inspectra.shortcuts.cron_monitor",
    "core.ia.regen_dossies": "inspectra.shortcuts.regen_dossies",
    "core.ia.batch_classify": "inspectra.shortcuts.batch_classify",
    "core.ia.openwebui_tools.enemydisclosure": "inspectra.tools.enemydisclosure",
}

ARQUIVOS_ALVO = []
for pasta in ["agents", "llm", "tools", "shortcuts", "ingestao", "verticals"]:
    arqs = list((RAIZ_INS / pasta).rglob("*.py"))
    ARQUIVOS_ALVO.extend(arqs)

mudou = 0
for arq in ARQUIVOS_ALVO:
    txt = arq.read_text(encoding="utf-8", errors="replace")
    original = txt
    for old, new in MIGRATIONS.items():
        # from X import Y -> from X import Y
        txt = re.sub(rf"\bfrom {re.escape(old)}\b", f"from {new}", txt)
        txt = re.sub(rf"\bimport {re.escape(old)}\b", f"import {new}", txt)
    if txt != original:
        arq.write_text(txt, encoding="utf-8")
        mudou += 1
        print(f"  updated: {arq.relative_to(RAIZ_INS.parent.parent)}")

print(f"\n{mudou} arquivos atualizados.")