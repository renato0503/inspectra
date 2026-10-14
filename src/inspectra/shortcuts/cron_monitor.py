"""
Job de monitoramento diario: roda cronograma em todos os municipios,
detecta picos atipicos e grava log de alertas.

Uso manual:
    python -m core.ia.cron_monitor [--dias 30] [--zscore 2.0]

Para agendar no Windows Task Scheduler:
    1. Abra "Task Scheduler" (taskschd.msc)
    2. Create Basic Task
    3. Trigger: Daily, 06:00
    4. Action: Start a program
       Program: python
       Arguments: -m core.ia.cron_monitor
       Start in: D:\\Dev\\EnemyDisclosure
    5. Marcar "Run whether user is logged in or not"

Saidas em `shared_data/cron_alerts/`:
- YYYY-MM-DD_alertas.md  (relatorio diario)
- YYYY-MM-DD_alertas.json (dados estruturados)
"""
from __future__ import annotations
import json
import os
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

from inspectra.llm.client import chat

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))
MACRO_DB = RAIZ / "shared_data" / "macro_mt" / "macro_mt.db"
ALERTAS_DIR = RAIZ / "shared_data" / "cron_alerts"
ALERTAS_DIR.mkdir(parents=True, exist_ok=True)


def detectar_picos(limite_zscore: float = 2.0, dias: int = 30) -> dict:
    """Detecta picos atipicos de gasto por municipio nos ultimos N dias."""
    if not MACRO_DB.exists():
        return {"erro": "macro_mt.db nao encontrado"}
    hoje = datetime.now().date()
    inicio = hoje - timedelta(days=dias)
    cx = sqlite3.connect(MACRO_DB)
    alertas = []
    try:
        # Agrupa por municipio + mes (independente de formato)
        rows = cx.execute("""
            SELECT municipio,
                   CASE WHEN length(data) = 10
                        THEN substr(data, 7, 4) || '-' || substr(data, 4, 2)
                        ELSE substr(data, 1, 7)
                   END as mes,
                   SUM(valor) as total,
                   COUNT(*) as n
            FROM despesas
            WHERE valor > 0 AND data IS NOT NULL AND data != '' AND length(data) >= 7
            GROUP BY municipio, mes
            ORDER BY municipio, mes
        """).fetchall()
    finally:
        cx.close()

    # Para cada municipio: calcula mediana + z-score
    por_municipio = {}
    for muni, mes, total, n in rows:
        por_municipio.setdefault(muni, []).append({"mes": mes, "total": total, "n": n})

    for muni, serie in por_municipio.items():
        if len(serie) < 6:
            continue
        valores = [s["total"] for s in serie]
        mediana = statistics.median(valores)
        media = statistics.mean(valores)
        stdev = statistics.stdev(valores) if len(valores) > 1 else 0
        if stdev == 0:
            continue
        for s in serie:
            z = (s["total"] - media) / stdev
            if z > limite_zscore:
                alertas.append({
                    "tipo": "pico_zscore",
                    "municipio": muni,
                    "mes": s["mes"],
                    "total": s["total"],
                    "n_empenhos": s["n"],
                    "mediana_municipio": mediana,
                    "media_municipio": media,
                    "z_score": round(z, 2),
                    "limite_zscore": limite_zscore,
                })

    # Detecta concentracao em dezembro
    cx = sqlite3.connect(MACRO_DB)
    try:
        dezembro = cx.execute("""
            SELECT municipio, SUM(valor) as total_dez
            FROM despesas
            WHERE valor > 0
              AND (
                  (length(data) = 10 AND substr(data, 4, 2) = '12')
                  OR (length(data) > 7 AND substr(data, 6, 2) = '12')
              )
            GROUP BY municipio
            ORDER BY total_dez DESC LIMIT 5
        """).fetchall()
    finally:
        cx.close()

    return {
        "data_execucao": hoje.isoformat(),
        "periodo_analisado_dias": dias,
        "limite_zscore": limite_zscore,
        "alertas_pico": alertas,
        "top_dezembro": [{"municipio": m, "total_dezembro": t} for m, t in dezembro],
        "total_alertas": len(alertas),
    }


def classificar_alertas(dados: dict, model: str = "gemma4:latest") -> str:
    """Usa LLM para classificar e resumir os alertas."""
    if dados["total_alertas"] == 0:
        return "Nenhum alerta significativo detectado no periodo."
    prompt = f"""\
Analise os seguintes alertas de gastos publicos municipais de Mato Grosso.
Para cada alerta, indique:
1. SEVERIDADE (critico / atencao / informativo)
2. RESUMO DE 1 FRASE
3. ACAO SUGERIDA (qual B-suite rodar, qual municipio investigar primeiro)

ALERTAS:
{json.dumps(dados['alertas_pico'][:10], ensure_ascii=False, indent=2)}

TOP DEZEMBRO (concentracao de fim de ano):
{json.dumps(dados['top_dezembro'], ensure_ascii=False, indent=2)}

Responda em portugues, formato markdown.
"""
    try:
        msg = chat(
            model,
            prompt,
            system="Voce e um auditor que monitora gastos publicos. Seja conciso.",
            temperatura=0.2,
        )
        return msg.get("content", "") if isinstance(msg, dict) else str(msg)
    except Exception as e:
        return f"(LLM indisponivel: {e})"


def main():
    import argparse
    p = argparse.ArgumentParser(description="Monitor diario de picos de gasto publico")
    p.add_argument("--dias", type=int, default=180, help="Periodo retroativo (default 180)")
    p.add_argument("--zscore", type=float, default=2.0, help="Z-score minimo para alerta (default 2.0)")
    p.add_argument("--model", default="gemma4:latest", help="Modelo Ollama")
    p.add_argument("--no-llm", action="store_true", help="Pula classificacao LLM")
    args = p.parse_args()

    hoje = datetime.now()
    print(f"[{hoje.isoformat(timespec='seconds')}] Monitor diario de gastos publicos")
    print(f"Periodo: {args.dias} dias | Z-score minimo: {args.zscore}\n")

    dados = detectar_picos(limite_zscore=args.zscore, dias=args.dias)

    print(f"Picos detectados (z>{args.zscore}): {dados['total_alertas']}")
    if dados.get("top_dezembro"):
        print(f"Top 5 municipios por gasto em dezembro:")
        for item in dados["top_dezembro"]:
            print(f"  {item['municipio']:25s} R$ {item['total_dezembro']:>15,.2f}")

    # Classificacao LLM
    classificacao = ""
    if not args.no_llm:
        print("\nClassificando com LLM...")
        classificacao = classificar_alertas(dados, model=args.model)

    # Salva
    json_path = ALERTAS_DIR / f"{hoje.date().isoformat()}_alertas.json"
    json_path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = ALERTAS_DIR / f"{hoje.date().isoformat()}_alertas.md"
    md_content = f"""# Alertas Diarios de Gasto Publico — {hoje.date().isoformat()}

_Periodo: ultimos {args.dias} dias | Z-score minimo: {args.zscore} | Modelo: {args.model if not args.no_llm else 'sem LLM'}_

## Resumo automatico

{classificacao or '_classificacao LLM nao rodada_'}

## Dados brutos

### Picos detectados: {dados['total_alertas']}

"""
    for a in dados.get("alertas_pico", []):
        md_content += (
            f"- **{a['municipio']}** ({a['mes']}): R$ {a['total']:,.2f} "
            f"(z={a['z_score']:.2f}, mediana=R$ {a['mediana_municipio']:,.2f}, "
            f"n={a['n_empenhos']})\n"
        )
    md_content += "\n### Top 5 municipios por gasto em dezembro:\n\n"
    for item in dados.get("top_dezembro", []):
        md_content += f"- {item['municipio']}: R$ {item['total_dezembro']:,.2f}\n"
    md_path.write_text(md_content, encoding="utf-8")

    print(f"\nSalvos:")
    print(f"  {json_path.relative_to(RAIZ)}")
    print(f"  {md_path.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())