"""Modo livre - passa a instrucao direto ao coding agent."""
from inspectra.agents.coding import CodingAgent


def cmd_shell(args) -> int:
    instrucao = " ".join(args.instrucao)
    print(f"=== Modo livre (coding agent) ===")
    print(f"Modelo: {args.model} | max_steps: {args.steps}\n")
    agent = CodingAgent(model=args.model, max_steps=args.steps, temperatura=0.2)
    resp = agent.run(instrucao, verbose=True)
    print("\n" + "=" * 60)
    print("RESPOSTA FINAL:")
    print("=" * 60)
    print(resp)
    return 0