"""
CLI unificada do Inspectra — plataforma de IA local para analise forense.

Subcomandos (atalhos prontos para agentes LLMs chamarem):
    investigar <nome/cnpj>       Investiga fornecedor cross-municipal
    analise    <nome_b> <orgao> <ano>   Roda analise B-suite
    ranking    [--top N] [--por valor|cnpj|cross]  Rankings
    sancoes    <cnpj>            CEIS/CNEP/CEPIM direto
    buscar     <termo>            Busca semantica em dossies
    sql        "<pergunta>"       Natural language -> SQL
    dossie     <cnpj>             Mini-dossie de CNPJ
    cronograma <orgao|all>         Analise temporal mensal
    pessoas    --cpf|--nome       TSE x QSA
    shell      "<instrucao>"      Modo livre (coding agent)
    ollama     chat|embed|models  Wrapper direto no Ollama
    relatorio  <arquivo.json>     Gerador de relatorios
    osint      dominio|cnpj|empresa|ip  OSINT completo
    due_diligence <cnpj>          Due diligence de empresa
    openwebui  install|check|restart|logs  Gerencia container Docker

Uso:
    set INSPECTA_RAIZ=D:\\Dev\\EnemyDisclosure
    python -m inspectra.shortcuts.cli investigar "COSTA OESTE"
    python -m inspectra.shortcuts.cli ollama chat "Qual a situacao do Brasil?"
    python -m inspectra.shortcuts.cli relatorio achados.json --saida relatorio.html
    python -m inspectra.shortcuts.cli osint cnpj 07192414000109
    python -m inspectra.shortcuts.cli due_diligence cnpj 07192414000109
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(os.environ.get("INSPECTA_RAIZ", Path(__file__).resolve().parents[3]))

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
from .ollama import cmd_chat, cmd_embed, cmd_models, cmd_complete
from . import relatorio, osint, due_diligence, openwebui_install


def main():
    p = argparse.ArgumentParser(
        prog="inspectra",
        description="Plataforma Inspectra — IA local para analise forense.",
    )
    p.add_argument("--model", default="gemma4:latest",
                   help="Modelo Ollama padrao (default: gemma4:latest)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # investigar
    sp = sub.add_parser("investigar", help="Investiga fornecedor em todos os municipios")
    sp.add_argument("termo", help="Nome parcial ou CNPJ")
    sp.add_argument("--steps", type=int, default=8)

    # analise
    sp = sub.add_parser("analise", help="Roda uma analise do B-suite")
    sp.add_argument("nome", help="Nome snake_case (fracionamento, benford, ...)")
    sp.add_argument("orgao", help="Slug do orgao")
    sp.add_argument("ano", type=int, help="Exercicio")
    sp.add_argument("--steps", type=int, default=8)

    # ranking
    sp = sub.add_parser("ranking", help="Ranking cross-municipal")
    sp.add_argument("--top", type=int, default=10)
    sp.add_argument("--por", choices=["valor", "cnpj", "cross"], default="valor")

    # sancoes
    sp = sub.add_parser("sancoes", help="Consulta direta CEIS/CNEP/CEPIM")
    sp.add_argument("cnpj", help="CNPJ (8 ou 14 digitos)")

    # buscar
    sp = sub.add_parser("buscar", help="Busca semantica em dossies")
    sp.add_argument("termo", help="Termo em PT-BR")
    sp.add_argument("--top", type=int, default=5)

    # sql
    sp = sub.add_parser("sql", help="Pergunta em portugues -> SQL")
    sp.add_argument("pergunta", help="Pergunta em portugues")
    sp.add_argument("--steps", type=int, default=4)

    # dossie
    sp = sub.add_parser("dossie", help="Mini-dossie de um CNPJ")
    sp.add_argument("cnpj", help="CNPJ")
    sp.add_argument("--save", nargs="?", const=True, default=False)

    # cronograma
    sp = sub.add_parser("cronograma", help="Analise temporal mensal")
    sp.add_argument("orgao", nargs="?", default="todos")
    sp.add_argument("--steps", type=int, default=6)

    # pessoas
    sp = sub.add_parser("pessoas", help="Cruza TSE + QSA")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--cpf", help="CPF")
    g.add_argument("--nome", help="Nome parcial")

    # shell
    sp = sub.add_parser("shell", help="Modo livre com coding agent")
    sp.add_argument("instrucao", nargs="+")
    sp.add_argument("--steps", type=int, default=12)

    # ollama
    sp = sub.add_parser("ollama", help="Wrapper direto no Ollama (chat/embed/models)")
    ollama_sub = sp.add_subparsers(dest="ollama_cmd", required=True)
    o = ollama_sub.add_parser("chat", help="Conversa")
    o.add_argument("mensagem")
    o.add_argument("--model", default="gemma4:latest")
    o.add_argument("--system")
    o.add_argument("--temperatura", type=float, default=0.3)
    o.add_argument("--json", action="store_true")
    o = ollama_sub.add_parser("embed", help="Embedding")
    o.add_argument("texto")
    o.add_argument("--embed-model")
    o.add_argument("--raw", action="store_true")
    ollama_sub.add_parser("models", help="Lista modelos")
    o = ollama_sub.add_parser("complete", help="Completion unico")
    o.add_argument("prompt")
    o.add_argument("--model", default="gemma4:latest")
    o.add_argument("--temperatura", type=float, default=0.3)
    o.add_argument("--json", action="store_true")

    # relatorio
    sp = sub.add_parser("relatorio", help="Gerador de relatorios")
    sp.add_argument("arquivo", nargs="?", help="JSON de entrada (stdin se omitido)")
    sp.add_argument("--formato", choices=["md", "html"], default="md")
    sp.add_argument("--saida", help="Arquivo de saida")
    sp.add_argument("--demo", action="store_true")

    # osint
    sp = sub.add_parser("osint", help="OSINT: dominio|cnpj|empresa|ip")
    sp.add_argument("tipo", choices=["dominio", "cnpj", "empresa", "ip"])
    sp.add_argument("valor", nargs="?", help="Alvo")
    sp.add_argument("--json", action="store_true")

    # due_diligence
    sp = sub.add_parser("due_diligence", help="Due diligence de CNPJ")
    sp.add_argument("cnpj", nargs="?", help="CNPJ")
    sp.add_argument("--model", default="gemma4:latest")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--demo", action="store_true")

    # pep_check
    sp = sub.add_parser("pep_check", help="Verifica se pessoa e PEP (politicamente exposta)")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("nome", nargs="?", help="Nome da pessoa")
    g.add_argument("--cpf", help="CPF (11 digitos)")

    # socios
    sp = sub.add_parser("socios", help="Lista socios de um CNPJ com qualificacao e data")
    sp.add_argument("cnpj", nargs="?", help="CNPJ")
    sp.add_argument("--cnpj", dest="cnpj_opt", help="CNPJ via flag")

    # geocode_lote
    sp = sub.add_parser("geocode_lote", help="Geocodifica lote de CNPJs em paralelo (Nominatim)")
    sp.add_argument("arquivo", nargs="?", help="CSV com CNPJs")
    sp.add_argument("--lista", nargs="*", help="CNPJs diretamente")
    sp.add_argument("--max-workers", type=int, default=4)

    # metadados
    sp = sub.add_parser("metadados", help="Extrai metadados EXIF de imagens (GPS, camera, PII)")
    sp.add_argument("arquivo", nargs="?", help="Arquivo de imagem")
    sp.add_argument("--diretorio", help="Processar todos os arquivos de um diretorio")
    sp.add_argument("--extensao", default=".jpg")

    # diario
    sp = sub.add_parser("diario", help="Busca em diarios oficiais (MT, SC, federal)")
    sp.add_argument("termo", nargs="?", help="Termo de busca")
    sp.add_argument("--uf", default=None)
    sp.add_argument("--periodo", type=int, default=365)

    # sql_qualquer
    sp = sub.add_parser("sql_qualquer", help="Executa SQL em qualquer banco SQLite (apenas SELECT)")
    sp.add_argument("db", help="Caminho do banco SQLite")
    sp.add_argument("query", nargs="?", help="Query SQL")
    sp.add_argument("--schema", action="store_true")
    sp.add_argument("--tabela", dest="tabela")
    sp.add_argument("--limite", type=int, default=1000)

    # csv_diff
    sp = sub.add_parser("csv_diff", help="Diff entre dois CSVs (adicionados, removidos, alterados)")
    sp.add_argument("arquivo_a", help="Primeiro CSV (antes)")
    sp.add_argument("arquivo_b", help="Segundo CSV (depois)")
    sp.add_argument("--chave", default="cnpj")
    sp.add_argument("--saida", help="Salvar resultado em JSON")

    # openwebui
    sp = sub.add_parser("openwebui", help="Gerencia Open WebUI Docker")
    ow_sub = sp.add_subparsers(dest="ow_cmd", required=True)
    ow_sub.add_parser("install", help="Instala custom tools")
    ow_sub.add_parser("check", help="Status do container")
    ow_sub.add_parser("restart", help="Reinicia container")
    ow_logs = ow_sub.add_parser("logs", help="Logs do container")
    ow_logs.add_argument("--lines", type=int, default=50)

    args = p.parse_args()
    cmd = args.cmd

    if cmd == "investigar":
        return cmd_investigar(args)
    elif cmd == "analise":
        return cmd_analise(args)
    elif cmd == "ranking":
        return cmd_ranking(args)
    elif cmd == "sancoes":
        return cmd_sancoes(args)
    elif cmd == "buscar":
        return cmd_buscar(args)
    elif cmd == "sql":
        return cmd_sql(args)
    elif cmd == "dossie":
        return cmd_dossie(args)
    elif cmd == "cronograma":
        return cmd_cronograma(args)
    elif cmd == "pessoas":
        return cmd_pessoas(args)
    elif cmd == "shell":
        return cmd_shell(args)
    elif cmd == "ollama":
        if args.ollama_cmd == "chat":
            from .ollama import cmd_chat as f; return f(args)
        elif args.ollama_cmd == "embed":
            from .ollama import cmd_embed as f; return f(args)
        elif args.ollama_cmd == "models":
            from .ollama import cmd_models as f; return f(args)
        elif args.ollama_cmd == "complete":
            from .ollama import cmd_complete as f; return f(args)
    elif cmd == "relatorio":
        return relatorio.main()
    elif cmd == "osint":
        return osint.main()
    elif cmd == "due_diligence":
        return due_diligence.main()

    # ---- novos atalhos (alta prioridade) ----
    elif cmd == "pep_check":
        from .pep_check import main as pep_main
        return pep_main()
    elif cmd == "socios":
        from .socios import main as socios_main
        return socios_main()
    elif cmd == "geocode_lote":
        from .geocode_lote import main as geo_main
        return geo_main()
    elif cmd == "metadados":
        from .metadados import main as meta_main
        return meta_main()
    elif cmd == "diario":
        from .diario import main as diario_main
        return diario_main()
    elif cmd == "sql_qualquer":
        from .sql_qualquer import main as sqlx_main
        return sqlx_main()
    elif cmd == "csv_diff":
        from .csv_diff import main as diff_main
        return diff_main()

    elif cmd == "openwebui":
        if args.ow_cmd == "install":
            return openwebui_install.cmd_install(args)
        elif args.ow_cmd == "check":
            return openwebui_install.cmd_check(args)
        elif args.ow_cmd == "restart":
            return openwebui_install.cmd_restart(args)
        elif args.ow_cmd == "logs":
            return openwebui_install.cmd_logs(args)


if __name__ == "__main__":
    sys.exit(main())
