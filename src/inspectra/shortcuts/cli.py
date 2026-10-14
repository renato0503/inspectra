"""
CLI unificada para tarefas comuns de auditoria.

Subcomandos:
    investigar <nome/cnpj> [-m modelo]
    analise    <nome_b> <orgao> <ano> [-m modelo]
    ranking    [--top N] [--por valor|cnpj|cross]
    sancoes    <cnpj>            (direto, rapido)
    buscar     <termo> [--top K]  (direto, embeddings)
    sql        "<pergunta>"      (gera SQL via LLM + executa)
    dossie     <cnpj> [--save path]   (gera mini-dossie markdown)
    cronograma <orgao|all>           (analise temporal mensal)
    pessoas    --cpf X --nome Y      (cruza TSE + QSA)
    shell      "<instrucao>"     (modo livre, abre o coding agent)

Uso:
    python -m core.ia.atalhos investigar "COSTA OESTE"
    python -m core.ia.atalhos analise benford camara_cuiaba 2025
    python -m core.ia.atalhos ranking --top 10
    python -m core.ia.atalhos sancoes 07.192.414/0001-09
    python -m core.ia.atalhos buscar "fracionamento combustivel 2024"
    python -m core.ia.atalhos dossie 07.192.414/0001-09
    python -m core.ia.atalhos cronograma prefeitura_sinop
    python -m core.ia.atalhos pessoas --cpf 12345678900
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from .investigar import cmd_investigar
from .analise import cmd_analise
from .ranking import cmd_ranking
from .sancoes import cmd_sancoes
from .buscar import cmd_buscar
from .sql import cmd_sql
from .shell import cmd_shell
from .dossie import cmd_dossie
from .cronograma import cmd_cronograma
from .pessoas import cmd_pessoas
import os

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))


def main():
    p = argparse.ArgumentParser(
        prog="atalhos",
        description="Atalhos de auditoria do EnemyDisclosure (via Ollama local).",
    )
    p.add_argument("--model", default="gemma4:latest",
                    help="Modelo Ollama a usar (default: gemma4:latest)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # investigar
    sp = sub.add_parser("investigar", help="Investiga fornecedor (nome parcial ou CNPJ) em todos os municipios")
    sp.add_argument("termo", help="Nome parcial ou CNPJ (com ou sem formatacao)")
    sp.add_argument("--steps", type=int, default=8)

    # analise
    sp = sub.add_parser("analise", help="Roda uma analise do B-suite e le o resultado")
    sp.add_argument("nome", help="Nome snake_case (fracionamento, benford, nepotismo, aditivos, ...)")
    sp.add_argument("orgao", help="Slug do orgao (prefeitura_cuiaba, camara_vg, ...)")
    sp.add_argument("ano", type=int, help="Exercicio")
    sp.add_argument("--steps", type=int, default=8)

    # ranking
    sp = sub.add_parser("ranking", help="Ranking cross-municipal por valor ou por CNPJ raiz")
    sp.add_argument("--top", type=int, default=10, help="Quantos (default 10)")
    sp.add_argument("--por", choices=["valor", "cnpj", "cross"], default="valor",
                    help="valor = top por valor total; cnpj = top credores distintos; cross = 2+ municipios")
    sp.add_argument("--steps", type=int, default=5)

    # sancoes
    sp = sub.add_parser("sancoes", help="Consulta direta (sem LLM) nas sancoes federais (CEIS/CNEP/CEPIM)")
    sp.add_argument("cnpj", help="CNPJ raiz (8 digitos) ou CNPJ completo (com pontuacao)")

    # buscar (semantica)
    sp = sub.add_parser("buscar", help="Busca semantica em todos os dossies (sem LLM)")
    sp.add_argument("termo", help="Termo de busca em PT-BR")
    sp.add_argument("--top", type=int, default=5)

    # sql (gera SQL via LLM e executa)
    sp = sub.add_parser("sql", help="Pergunta em linguagem natural -> SQL -> executa no macro_mt.db")
    sp.add_argument("pergunta", help="Pergunta em portugues")
    sp.add_argument("--banco", default="shared_data/macro_mt/macro_mt.db")
    sp.add_argument("--steps", type=int, default=4)

    # dossie
    sp = sub.add_parser("dossie", help="Gera mini-dossie markdown de um CNPJ")
    sp.add_argument("cnpj", help="CNPJ (com ou sem pontuacao)")
    sp.add_argument("--save", nargs="?", const=True, default=False,
                    help="Salva em arquivo (default NAO salva, a menos que voce passe --save ou um path)")
    sp.add_argument("--no-save", dest="save", action="store_false",
                    help="Nao salva em arquivo (padrao)")

    # cronograma
    sp = sub.add_parser("cronograma", help="Analise temporal (mes a mes) de um orgao ou todos")
    sp.add_argument("orgao", nargs="?", default="todos", help="Slug do orgao ou 'todos' (default)")
    sp.add_argument("--steps", type=int, default=6)

    # pessoas
    sp = sub.add_parser("pessoas", help="Investiga politico/socio cruzando TSE + QSA (sem LLM)")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--cpf", help="CPF (11 digitos)")
    g.add_argument("--nome", help="Nome parcial para buscar")

    # shell (modo livre)
    sp = sub.add_parser("shell", help="Modo livre - passa a instrucao direto ao coding agent")
    sp.add_argument("instrucao", nargs="+")
    sp.add_argument("--steps", type=int, default=12)

    args = p.parse_args()

    cmd = args.cmd
    if cmd == "investigar":
        sys.exit(cmd_investigar(args))
    elif cmd == "analise":
        sys.exit(cmd_analise(args))
    elif cmd == "ranking":
        sys.exit(cmd_ranking(args))
    elif cmd == "sancoes":
        sys.exit(cmd_sancoes(args))
    elif cmd == "buscar":
        sys.exit(cmd_buscar(args))
    elif cmd == "sql":
        sys.exit(cmd_sql(args))
    elif cmd == "dossie":
        sys.exit(cmd_dossie(args))
    elif cmd == "cronograma":
        sys.exit(cmd_cronograma(args))
    elif cmd == "pessoas":
        sys.exit(cmd_pessoas(args))
    elif cmd == "shell":
        sys.exit(cmd_shell(args))


if __name__ == "__main__":
    main()