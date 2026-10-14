# complexo/grafo.py
"""Grafo de auditoria (adaptação do dual-graph do ARTEX).

Dois grafos sobrepostos, persistidos em JSON (e opcionalmente GraphML via
networkx):

  * **Asset graph** — verdade compartilhada: portais, endpoints, municípios,
    órgãos, fornecedores, sócios e as relações entre eles.
  * **Exploration graph** — por investigação: metas, intents executados,
    fatos coletados e achados (findings), com âncoras ligando cada nó de
    exploração aos assets que ele tocou.

Serve para responder "o que já foi investigado?", "que fornecedor aparece em
mais de um órgão?" e "de qual endpoint veio este achado?" — sem depender de
memória ou de texto solto no context.md.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

try:
    import networkx as nx  # já é dependência do projeto (grafo_fornecedores)
    _TEM_NX = True
except ImportError:  # pragma: no cover
    _TEM_NX = False


def _nid(prefixo: str) -> str:
    return f"{prefixo}_{uuid.uuid4().hex[:10]}"


class GrafoAuditoria:
    """Grafo de auditoria com asset + exploration graph."""

    def __init__(self) -> None:
        self.assets: dict[str, dict] = {}
        self.exploracao: dict[str, dict] = {}
        self.arestas: list[dict] = []      # {origem, destino, grafo, rel}
        self.ancoras: dict[str, list[str]] = {}  # node exploracao -> [asset_id]

    # ── Asset graph ────────────────────────────────────────────────────────
    def _add_asset(self, aid: str, kind: str, **attrs) -> str:
        self.assets[aid] = {"id": aid, "kind": kind, **attrs}
        return aid

    def add_portal(self, url: str, vendor: str | None = None,
                   municipio: str | None = None, familia: str | None = None) -> str:
        aid = url  # URL é a identidade natural
        self._add_asset(aid, "portal", url=url, vendor=vendor,
                        municipio=municipio, familia=familia)
        if municipio:
            mid = f"municipio:{municipio}"
            self._add_asset(mid, "municipio", nome=municipio)
            self._ligar(mid, aid, "asset", "hospeda")
        return aid

    def add_endpoint(self, portal_url: str, metodo: str, path: str,
                     params: list[str] | None = None) -> str:
        aid = f"http:{metodo.upper()} {path}"
        self._add_asset(aid, "endpoint", metodo=metodo.upper(), path=path,
                        params=params or [])
        self._ligar(portal_url, aid, "asset", "expoe")
        return aid

    def add_orgao(self, slug: str, nome: str, portal_url: str | None = None) -> str:
        aid = f"orgao:{slug}"
        self._add_asset(aid, "orgao", slug=slug, nome=nome)
        if portal_url:
            self._ligar(aid, portal_url, "asset", "usa")
        return aid

    def add_fornecedor(self, cnpj: str, nome: str | None = None,
                       valor: float | None = None, sancionado: bool | None = None) -> str:
        aid = f"cnpj:{cnpj}"
        self._add_asset(aid, "fornecedor", cnpj=cnpj, nome=nome,
                        valor=valor, sancionado=sancionado)
        return aid

    def add_socio(self, cpf_ou_nome: str, nome: str | None = None) -> str:
        aid = f"socio:{cpf_ou_nome}"
        self._add_asset(aid, "socio", nome=nome or cpf_ou_nome)
        return aid

    def ligar_fornecedor_orgao(self, cnpj: str, slug: str,
                               valor: float | None = None) -> None:
        self._ligar(f"cnpj:{cnpj}", f"orgao:{slug}", "asset", "fornece",
                    valor=valor)

    def ligar_socio_fornecedor(self, socio: str, cnpj: str,
                               qualificacao: str | None = None) -> None:
        self._ligar(f"socio:{socio}", f"cnpj:{cnpj}", "asset", "socio_de",
                    qualificacao=qualificacao)

    # ── Exploration graph ──────────────────────────────────────────────────
    def nova_investigacao(self, municipio: str, meta: str) -> str:
        gid = _nid("meta")
        self.exploracao[gid] = {"id": gid, "kind": "meta", "municipio": municipio,
                                "descricao": meta, "status": "aberta"}
        if f"municipio:{municipio}" not in self.assets:
            self._add_asset(f"municipio:{municipio}", "municipio", nome=municipio)
        self._ligar(f"municipio:{municipio}", gid, "exploracao", "alvo")
        return gid

    def registrar_intent(self, meta_id: str, descricao: str) -> str:
        iid = _nid("intent")
        self.exploracao[iid] = {"id": iid, "kind": "intent", "descricao": descricao,
                                "status": "aberto"}
        self._ligar(meta_id, iid, "exploracao", "gera")
        return iid

    def concluir_intent(self, intent_id: str, fatos: list[str] | None = None,
                        achados: list[dict] | None = None,
                        assets_tocados: list[str] | None = None) -> dict:
        if intent_id in self.exploracao:
            self.exploracao[intent_id]["status"] = "concluido"
        ids = {"fatos": [], "achados": []}
        for texto in (fatos or []):
            fid = _nid("fato")
            self.exploracao[fid] = {"id": fid, "kind": "fato", "descricao": texto}
            self._ligar(intent_id, fid, "exploracao", "produz")
            ids["fatos"].append(fid)
        for achado in (achados or []):
            aid = _nid("achado")
            self.exploracao[aid] = {"id": aid, "kind": "achado", **achado}
            self._ligar(intent_id, aid, "exploracao", "prova")
            ids["achados"].append(aid)
        if assets_tocados:
            self.ancoras.setdefault(intent_id, []).extend(assets_tocados)
        return ids

    def ancorar(self, node_exploracao: str, asset_id: str) -> None:
        self.ancoras.setdefault(node_exploracao, []).append(asset_id)

    # ── arestas ────────────────────────────────────────────────────────────
    def _ligar(self, origem: str, destino: str, grafo: str, rel: str, **attrs) -> None:
        self.arestas.append({"origem": origem, "destino": destino,
                             "grafo": grafo, "rel": rel, **attrs})

    # ── Consultas ──────────────────────────────────────────────────────────
    def fornecedores_multi_orgao(self, minimo: int = 2) -> list[dict]:
        """Fornecedores que aparecem em >= `minimo` órgãos."""
        por_cnpj: dict[str, set[str]] = {}
        for a in self.arestas:
            if a["grafo"] == "asset" and a["rel"] == "fornece":
                if a["origem"].startswith("cnpj:") and a["destino"].startswith("orgao:"):
                    por_cnpj.setdefault(a["origem"], set()).add(a["destino"])
        saida = []
        for cnpj, orgaos in por_cnpj.items():
            if len(orgaos) >= minimo:
                info = self.assets.get(cnpj, {})
                saida.append({"cnpj": info.get("cnpj", cnpj),
                              "nome": info.get("nome"),
                              "orgaos": sorted(o.replace("orgao:", "") for o in orgaos),
                              "n_orgaos": len(orgaos)})
        return sorted(saida, key=lambda d: d["n_orgaos"], reverse=True)

    def operadores(self, minimo: int = 2) -> list[dict]:
        """Sócios presentes em >= `minimo` empresas contratadas (operadores)."""
        por_socio: dict[str, set[str]] = {}
        for a in self.arestas:
            if a["grafo"] == "asset" and a["rel"] == "socio_de":
                por_socio.setdefault(a["origem"], set()).add(a["destino"])
        saida = []
        for socio, empresas in por_socio.items():
            if len(empresas) >= minimo:
                info = self.assets.get(socio, {})
                saida.append({"socio": info.get("nome", socio),
                              "empresas": sorted(e.replace("cnpj:", "") for e in empresas),
                              "n_empresas": len(empresas)})
        return sorted(saida, key=lambda d: d["n_empresas"], reverse=True)

    def assets_de(self, node_exploracao: str) -> list[str]:
        return self.ancoras.get(node_exploracao, [])

    def resumo(self) -> dict:
        kinds: dict[str, int] = {}
        for n in self.assets.values():
            kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
        ekinds: dict[str, int] = {}
        for n in self.exploracao.values():
            ekinds[n["kind"]] = ekinds.get(n["kind"], 0) + 1
        return {
            "assets": len(self.assets),
            "assets_por_tipo": kinds,
            "exploracao": len(self.exploracao),
            "exploracao_por_tipo": ekinds,
            "arestas": len(self.arestas),
            "ancoras": sum(len(v) for v in self.ancoras.values()),
            "multi_orgao": len(self.fornecedores_multi_orgao()),
            "operadores": len(self.operadores()),
        }

    # ── Serialização ───────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "assets": self.assets,
            "exploracao": self.exploracao,
            "arestas": self.arestas,
            "ancoras": self.ancoras,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GrafoAuditoria":
        g = cls()
        g.assets = d.get("assets", {})
        g.exploracao = d.get("exploracao", {})
        g.arestas = d.get("arestas", [])
        g.ancoras = d.get("ancoras", {})
        return g

    def salvar(self, caminho: str | Path) -> Path:
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return caminho

    @classmethod
    def carregar(cls, caminho: str | Path) -> "GrafoAuditoria":
        d = json.loads(Path(caminho).read_text(encoding="utf-8"))
        return cls.from_dict(d)

    def exportar_graphml(self, caminho: str | Path) -> Path | None:
        """Exporta o asset graph para GraphML (abre em Gephi/yEd)."""
        if not _TEM_NX:
            return None
        G = nx.MultiDiGraph()
        for aid, attrs in self.assets.items():
            G.add_node(aid, **{k: str(v) for k, v in attrs.items()})
        for a in self.arestas:
            if a["grafo"] == "asset":
                G.add_edge(a["origem"], a["destino"], rel=a["rel"])
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        nx.write_graphml(G, str(caminho))
        return caminho
