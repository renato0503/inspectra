"""Wrappers para geracao de dossies."""
from pathlib import Path

from inspectra.shortcuts.dossie import cmd_dossie as _cmd_dossie
from inspectra.shortcuts.sancoes import cmd_sancoes as _cmd_sancoes


def dossie_fornecedor(cnpj: str, raiz: str = r"D:\Dev\EnemyDisclosure") -> str:
    """Wrapper que retorna o dossie markdown completo como string."""
    from types import SimpleNamespace
    args = SimpleNamespace(cnpj=cnpj, save=False)
    rc = _cmd_dossie(args)
    return f"(rc={rc})"


def listar_sancoes(cnpj: str, raiz: str = r"D:\Dev\EnemyDisclosure") -> list:
    """Retorna lista de matches em CEIS/CNEP/CEPIM para o CNPJ."""
    from inspectra.shortcuts.sancoes import _buscar_em_csv_em
    from inspectra.shortcuts.sancoes import _norm
    cnpj_n = _norm(cnpj)
    raiz_p = Path(raiz)
    matches = _buscar_em_csv_em(cnpj_n[:8], raiz_p)
    if not matches and len(cnpj_n) >= 14:
        matches = _buscar_em_csv_em(cnpj_n, raiz_p)
    return matches


def regen(limite: int = 20, min_valor: float = 1_000_000, raiz: str = r"D:\Dev\EnemyDisclosure") -> int:
    """Regenera mini-dossies para CNPJs relevantes."""
    from inspectra.shortcuts.regen_dossies import main as _regen_main
    from types import SimpleNamespace
    args = SimpleNamespace(limite=limite, raiz=None, min_valor=min_valor, cross=False)
    return _regen_main(args)