"""
Auto-classificação de indícios via LLM (Ollama local).

Lê `analises_<ano>.json` (saída do B-suite), classifica cada achado com
severidade (forte / moderada / atenção / ok), justifica e adiciona
sugestões de aprofundamento.

Saída: `analises_<ano>_classificadas.json` no mesmo diretório.

Uso:
    python -m core.ia.classificar prefeitura_cuiaba 2025
    python -m core.ia.classificar camara_vg 2025 --model gemma4-26b
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from inspectra.llm.client import chat

RAIZ = Path(__file__).resolve().parents[2]


SYSTEM_PROMPT = """\
Voce e um auditor senior do TCE/MT classificando indicios de irregularidade
em gastos publicos municipais.

TAREFA: Para cada achado fornecido, classifique a SEVERIDADE em uma de:
- "forte": evidencia robusta de irregularidade (ex: >= 50% sobrepreco,
  vinculo socio=gestor, sancao federal vigente, aditivos > 100%)
- "moderada": indicios consistentes mas nao definitivos (ex: 20-50%
  sobrepreco, fracionamento provavel, concentracao em fim de ano)
- "atencao": alerta amarelo - merece monitoramento (ex: outliers
  estatisticos isolados, valores redondos, poucas transacoes)
- "ok": nao ha indicio relevante

Responda EXCLUSIVAMENTE em JSON no formato:
[
  {
    "indice": <int>,
    "severidade": "forte" | "moderada" | "atencao" | "ok",
    "justificativa": "<1-2 frases objetivas>",
    "acoes_sugeridas": ["<acao 1>", "<acao 2>", ...],
    "base_legal": ["<lei/artigo 1>", ...]
  },
  ...
]

REGRAS:
- Use apenas o contexto fornecido. NAO invente dados.
- Se o achado for muito vago, severidade="atencao".
- Base legal: cite a LEI FEDERAL aplicavel (ex: Lei 14.133/2021 art. 75 para
  fracionamento, Lei 8.429/92 para improbidade).
- Seja conservador: nao classifique como "forte" sem evidencia clara.
- Retorne APENAS o JSON, sem markdown, sem texto adicional.
"""


def _parse_achados(analises: List[Dict]) -> List[Dict]:
    """Extrai lista flat de achados com identificadores."""
    achados = []
    for idx_a, bloco in enumerate(analises):
        titulo = bloco.get("titulo", f"Bloco {idx_a}")
        for idx_b, achado in enumerate(bloco.get("achados", [])):
            achados.append({
                "_indice_global": len(achados),
                "_titulo_bloco": titulo,
                "_idx_bloco": idx_a,
                "_idx_achado": idx_b,
                "dados_originais": achado,
            })
    return achados


def _formatar_para_llm(achados: List[Dict]) -> str:
    linhas = []
    for a in achados:
        linhas.append(f"--- Achado #{a['_indice_global']} (Bloco: {a['_titulo_bloco']}) ---")
        linhas.append(json.dumps(a["dados_originais"], ensure_ascii=False, indent=2))
        linhas.append("")
    return "\n".join(linhas)


def _parse_resposta_json(texto: str) -> Optional[List[Dict]]:
    """Tenta extrair JSON valido da resposta (com ou sem fences)."""
    texto = texto.strip()
    # Remover fences markdown
    texto = re.sub(r"^```(?:json)?\s*", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"\s*```$", "", texto, flags=re.MULTILINE)
    texto = texto.strip()
    # Tentar parse direto
    try:
        data = json.loads(texto)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    # Tentar extrair primeiro JSON array do texto
    m = re.search(r"\[\s*\{.*\}\s*\]", texto, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def classificar_orgaos(orgao: str, ano: int, model: str = "gemma4-26b", temperatura: float = 0.1) -> int:
    """Classifica todos os achados de um orgao/ano. Retorna 0 ok, 1 erro."""
    orgaos_dir = RAIZ / "orgaos"
    encontrado = None
    for muni in orgaos_dir.iterdir():
        if not muni.is_dir():
            continue
        slug_dir = muni / orgao
        if not slug_dir.exists():
            continue
        export_dir = slug_dir / "data" / "export"
        json_path = export_dir / f"analises_{ano}.json"
        if json_path.exists():
            encontrado = json_path
            break

    if not encontrado:
        print(f"ERRO: nao encontrei analises_{ano}.json para orgao '{orgao}'")
        print(f"  Procurado em: {orgaos_dir}/*/{orgao}/data/export/")
        return 1

    print(f"Lendo: {encontrado.relative_to(RAIZ)}")
    try:
        data = json.loads(encontrado.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERRO lendo JSON: {e}")
        return 1

    analises = data.get("analises", [])
    if not analises:
        print("  (sem achados para classificar)")
        return 0

    achados = _parse_achados(analises)
    print(f"Encontrados {len(achados)} achados em {len(analises)} blocos\n")
    print(f"Modelo: {model} | Temperatura: {temperatura}")
    print(f"Enviando para classificacao...\n")

    prompt = (
        f"Classifique os {len(achados)} achados abaixo conforme o sistema.\n\n"
        + _formatar_para_llm(achados)
    )

    try:
        resposta_msg = chat(model, prompt, system=SYSTEM_PROMPT, temperatura=temperatura)
        resposta = resposta_msg.get("content", "") if isinstance(resposta_msg, dict) else str(resposta_msg)
    except Exception as e:
        print(f"ERRO no LLM: {e}")
        return 1

    classificacoes = _parse_resposta_json(resposta)
    if not classificacoes:
        print(f"ERRO: LLM nao retornou JSON parseavel. Resposta:")
        print(resposta[:1500])
        # Salva mesmo assim a resposta bruta
        debug_path = encontrado.parent / f"analises_{ano}_llm_raw.txt"
        debug_path.write_text(resposta, encoding="utf-8")
        print(f"\nResposta bruta salva em: {debug_path.relative_to(RAIZ)}")
        return 1

    # Merge: adiciona classificacao ao achado original
    counts = {"forte": 0, "moderada": 0, "atencao": 0, "ok": 0}
    for cls in classificacoes:
        try:
            idx = int(cls.get("indice", -1))
            if idx < 0 or idx >= len(achados):
                continue
            sev = cls.get("severidade", "atencao").lower()
            if sev not in counts:
                sev = "atencao"
            counts[sev] += 1
            achado = achados[idx]
            bloco = analises[achado["_idx_bloco"]]
            if "achados" in bloco and achado["_idx_achado"] < len(bloco["achados"]):
                bloco["achados"][achado["_idx_achado"]]["_classificacao_llm"] = {
                    "severidade": sev,
                    "justificativa": cls.get("justificativa", ""),
                    "acoes_sugeridas": cls.get("acoes_sugeridas", []),
                    "base_legal": cls.get("base_legal", []),
                    "modelo": model,
                }
        except Exception as e:
            print(f"  [!] erro aplicando classificacao #{cls.get('indice')}: {e}")

    # Adiciona sumario no JSON
    data["_classificacao_resumo"] = counts
    data["_classificacao_modelo"] = model
    data["_classificacao_data"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")

    out_path = encontrado.parent / f"analises_{ano}_classificadas.json"
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nClassificacao salva em: {out_path.relative_to(RAIZ)}")
    print(f"\nResumo:")
    for sev, qtd in counts.items():
        print(f"  {sev:10s}: {qtd}")
    print(f"  {'TOTAL':10s}: {sum(counts.values())}")
    return 0


def main():
    import argparse
    p = argparse.ArgumentParser(description="Auto-classifica achados do B-suite via LLM")
    p.add_argument("orgao", help="Slug do orgao (prefeitura_cuiaba, camara_vg, ...)")
    p.add_argument("ano", type=int, help="Exercicio")
    p.add_argument("--model", default="gemma4-26b", help="Modelo Ollama")
    p.add_argument("--temperatura", type=float, default=0.1)
    args = p.parse_args()
    raise SystemExit(classificar_orgaos(args.orgao, args.ano, args.model, args.temperatura))


if __name__ == "__main__":
    main()