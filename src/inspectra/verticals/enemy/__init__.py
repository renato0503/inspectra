r"""Vertical: integração com o projeto EnemyDisclosure (D:\Dev\EnemyDisclosure).

Inspectra usa o B-suite do EnemyDisclosure como "vertical exemplo"
(auditoria de gastos públicos municipais). Se você não tem o EnemyDisclosure
instalado, pode usar Inspectra em outros verticais (fraude fiscal, due
diligence, OSINT etc).

API pública desta vertical:
    from inspectra.verticals.enemy import EnemyDisclosure
    ed = EnemyDisclosure(raiz=r"D:\Dev\EnemyDisclosure")
    ed.rodar_analise_b("fracionamento", "prefeitura_cuiaba", 2025)
    ed.investigar_fornecedor("COSTA OESTE")
    ed.classificar_achados("camara_cuiaba", 2025)
    ed.regenerar_dossies(limite=20)
"""
from .b_suite import rodar_analise_b, listar_orgaos
from .dossie import dossie_fornecedor, listar_sancoes
from .investigar import investigar_fornecedor
from .cronograma import cronograma_mensal

__all__ = [
    "EnemyDisclosure",
    "rodar_analise_b",
    "listar_orgaos",
    "dossie_fornecedor",
    "investigar_fornecedor",
    "listar_sancoes",
    "cronograma_mensal",
]


class EnemyDisclosure:
    """Cliente da vertical EnemyDisclosure para Inspectra.

    Path padrao: D:\\Dev\\EnemyDisclosure
    """

    def __init__(self, raiz: str = r"D:\Dev\EnemyDisclosure"):
        self.raiz = raiz
        self.orgaos = None
        self.macro_db = f"{raiz}\\shared_data\\macro_mt\\macro_mt.db"

    def listar_orgaos(self) -> list:
        return listar_orgaos(self.raiz)

    def regenerar_dossies(self, limite: int = 20, min_valor: float = 1_000_000) -> int:
        """Regenera mini-dossies em batch."""
        from inspectra.verticals.enemy.dossie import regen
        return regen(limite=limite, min_valor=min_valor, raiz=self.raiz)

    def rodar_analise_b(self, nome: str, orgao: str, ano: int, model: str = "gemma4-26b") -> int:
        """Roda analise B-suite via Ollama."""
        return rodar_analise_b(nome, orgao, ano, model, raiz=self.raiz)

    def investigar_fornecedor(self, termo: str, model: str = "gemma4:latest") -> str:
        """Investiga fornecedor em todos os municipios via coding agent."""
        return investigar_fornecedor(termo, model, raiz=self.raiz)

    def classificar_achados(self, orgao: str, ano: int, model: str = "gemma4-26b") -> int:
        """Classifica achados via LLM."""
        from inspectra.shortcuts.classificar import classificar_orgaos
        return classificar_orgaos(orgao, ano, model, raiz=self.raiz)

    def regenerar_dossies(self, limite: int = 20, min_valor: float = 1_000_000) -> int:
        """Regenera mini-dossies em batch."""
        from inspectra.shortcuts.regen_dossies import regen
        return regen(limite=limite, min_valor=min_valor, raiz=self.raiz)

    def dossie_fornecedor(self, cnpj: str) -> str:
        """Gera mini-dossie de um CNPJ."""
        return dossie_fornecedor(cnpj, raiz=self.raiz)

    def listar_sancoes(self, cnpj: str) -> list:
        return listar_sancoes(cnpj, raiz=self.raiz)

    def cronograma(self, orgao: str = "todos", model: str = "gemma4:latest") -> str:
        """Analise temporal mensal."""
        return cronograma_mensal(orgao, model, raiz=self.raiz)