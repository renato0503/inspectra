"""
Agente ReAct minimalista usando Ollama local.

Loop: Thought -> Action -> Observation -> ... -> Final Answer

Uso:
    from inspectra.agents.react import Agent
    agent = Agent(model="gemma4:latest")
    resp = agent.run("Quais municipios tem Costa Oeste no CEIS?")
"""
from __future__ import annotations
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from inspectra.tools.audit import ToolRegistry, registrar_padrao
from inspectra.llm.client import chat

LOGS_DIR = Path(__file__).resolve().parents[2] / "shared_data" / "agent_logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


SYSTEM_PROMPT = """Voce e um agente de auditoria independente que analisa gastos publicos municipais brasileiros.

FORMATO OBRIGATORIO (siga rigorosamente):

Thought: <seu raciocinio>
Action: <nome_da_tool>
Action Input: <json com argumentos>

OU, apenas quando ja tiver dados reais de Observation anteriores:

Thought: agora tenho dados suficientes
Final Answer: <sua resposta em portugues, com numeros concretos>

REGRAS CRITICAS:
- Uma tool por turno. Espere SEMPRE o resultado (Observation) antes de chamar outra.
- NAO finalize sem ter visto pelo menos um Observation com dados reais.
- NAO invente numeros. Se nao viu dados, ainda nao pode finalizar.
- Respostas finais: maximo 8 linhas, em portugues.
- SQL: apenas SELECT/WITH/PRAGMA, max 50 linhas.
- Banco cross-municipio: `shared_data/macro_mt/macro_mt.db`, tabela `despesas` (municipio, ano, cnpj, cnpj_raiz, fornecedor, valor, data_empenho, modalidade).
"""


def _tools_react_to_text(tools: List[Dict]) -> str:
    out = ["Ferramentas disponiveis:"]
    for t in tools:
        out.append(f"- {t['nome']}({t['args']}): {t['descricao']}")
    return "\n".join(out)


class Agent:
    def __init__(
        self,
        model: str = "gemma4:latest",
        max_steps: int = 8,
        temperature: float = 0.2,
    ):
        self.model = model
        self.max_steps = max_steps
        self.temperature = temperature
        self.tools = ToolRegistry()
        registrar_padrao(self.tools)

    def _parse_action(self, text: str) -> Optional[Dict]:
        m_action = re.search(r"(?im)^Action:\s*([a-z0-9_]+)\s*$", text)
        m_input = re.search(r"(?is)Action\s*Input:\s*(.+?)(?:\n\s*\n|\Z)", text)
        if not m_action:
            return None
        nome = m_action.group(1).strip()
        raw = (m_input.group(1).strip() if m_input else "{}").strip()
        try:
            args = json.loads(raw) if raw.startswith("{") else {"query": raw}
        except json.JSONDecodeError:
            args = {"query": raw}
        return {"nome": nome, "args": args}

    def _extract_final(self, text: str) -> Optional[str]:
        m = re.search(r"(?is)Final\s*Answer:\s*(.+?)\Z", text)
        return m.group(1).strip() if m else None

    def run(self, pergunta: str, verbose: bool = True) -> str:
        tools_list = self.tools.listar()
        system = SYSTEM_PROMPT + "\n\n" + _tools_react_to_text(tools_list)
        history: List[Dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": pergunta},
        ]

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = LOGS_DIR / f"run_{ts}.jsonl"
        with log_file.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"event": "start", "model": self.model, "pergunta": pergunta}, ensure_ascii=False) + "\n")

        for step in range(1, self.max_steps + 1):
            t0 = time.time()
            try:
                resp_text = chat(
                    self.model,
                    "\n".join(f"[{m['role']}] {m['content']}" for m in history[1:]),
                    system=system,
                    temperatura=self.temperature,
                )
            except Exception as e:
                return f"ERRO no LLM: {e}"
            dt = time.time() - t0

            history.append({"role": "assistant", "content": resp_text})
            with log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"step": step, "dt": round(dt, 1), "response": resp_text}, ensure_ascii=False) + "\n")

            if verbose:
                print(f"\n=== Step {step} ({dt:.1f}s) ===")
                print(resp_text[:1500])

            final = self._extract_final(resp_text)
            if final:
                with log_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"event": "final", "answer": final}, ensure_ascii=False) + "\n")
                return final

            action = self._parse_action(resp_text)
            if not action:
                history.append({
                    "role": "user",
                    "content": "Formato invalido. Responda EXATAMENTE com Thought/Action/Action Input OU Final Answer.",
                })
                continue

            observation = self.tools.executar(action["nome"], **action["args"])
            history.append({
                "role": "user",
                "content": f"Observation ({action['nome']}):\n{observation}",
            })

        return (
            "Limite de etapas atingido sem Final Answer. Ultima saida do agente:\n\n"
            + history[-1]["content"][:2000]
        )


def main():
    import argparse
    p = argparse.ArgumentParser(description="Agente de auditoria (Ollama local)")
    p.add_argument("pergunta", nargs="*", default=None, help="Pergunta (ou use --stdin)")
    p.add_argument("--model", default="gemma4:latest")
    p.add_argument("--steps", type=int, default=8)
    p.add_argument("--stdin", action="store_true")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    if args.stdin:
        pergunta = sys.stdin.read().strip()
    elif args.pergunta:
        pergunta = " ".join(args.pergunta)
    else:
        pergunta = input("Pergunta> ")
    agent = Agent(model=args.model, max_steps=args.steps)
    resp = agent.run(pergunta, verbose=not args.quiet)
    print("\n" + "=" * 60)
    print("RESPOSTA FINAL:")
    print("=" * 60)
    print(resp)


if __name__ == "__main__":
    main()