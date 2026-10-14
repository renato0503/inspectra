# complexo/rea.py
"""Wrapper Python para o REA (Reverse Engineer Anything).

O REA é uma ferramenta externa (Node.js). Este wrapper:
  * localiza o binário (env ``ENEMY_REA_BIN`` -> ``rea`` no PATH -> checkout em
    ``ENEMY_REA_HOME``);
  * expõe os comandos úteis para auditoria de gastos (SQLite local, aplicações
    JS, inspeção de página via CDP, bundle web, binários .NET);
  * devolve sempre JSON parseado, com fallback para texto cru.

Se o REA não estiver instalado/compilado, :meth:`REA.disponivel` explica o
motivo e os demais métodos levantam :class:`REA.Indisponivel`. O restante do
EnemyDisclosure não depende dele.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from . import caminhos


def _evidencia_ou_caminho(valor) -> str | dict | list:
    """Normaliza um input único do REA (que aceita JSON inline ou arquivo).

    Caminho existente → devolve a str do caminho (o REA lê o arquivo);
    dict/lista → devolve como está. Assim os wrappers podem expor tanto
    "passe o JSON salvo" quanto "passe a Evidence inline".
    """
    if isinstance(valor, Path):
        return str(valor)
    if isinstance(valor, str):
        p = Path(valor)
        return str(p) if p.exists() else valor
    return valor


def _carregar_evidence(valor) -> dict | list:
    """Carrega o lado de uma comparação como Evidence (dict), não caminho.

    ``compare-application-versions`` recebe a Evidence DENTRO de left/right —
    não aceita um caminho de arquivo nesse campo. Então se vier caminho,
    lemos o JSON; se vier string JSON, parseamos; senão devolvemos como está.
    """
    if isinstance(valor, (dict, list)):
        return valor
    if isinstance(valor, Path) or (isinstance(valor, str) and Path(valor).exists()):
        return json.loads(Path(valor).read_text(encoding="utf-8", errors="replace"))
    if isinstance(valor, str):
        return json.loads(valor)
    raise TypeError(f"lado de comparação inválido: {type(valor)!r}")


class REA:
    """Cliente do REA (CLI one-shot)."""

    class Indisponivel(RuntimeError):
        pass

    def __init__(self, timeout: int = 900):
        self.entry = caminhos.rea_entry()
        self.timeout = timeout

    # -- disponibilidade -----------------------------------------------------
    def disponivel(self) -> tuple[bool, str]:
        if not self.entry:
            return (
                False,
                "REA não encontrado. Instale com `npm i -g rea-agents` ou defina "
                "ENEMY_REA_BIN / ENEMY_REA_HOME.",
            )
        # Se for checkout via node scripts/rea.mjs, exige dist/ compilado.
        if self.entry and self.entry[0].lower().endswith(("node", "node.exe")):
            dist = caminhos.rea_home() / "dist"
            if not dist.exists():
                return (
                    False,
                    f"REA encontrado em {self.entry[-1]}, mas dist/ não existe. "
                    f"Rode em {caminhos.rea_home()}: `npm install && npm run build`.",
                )
        return True, "ok"

    def _argv(self, *args: str) -> list[str]:
        ok, motivo = self.disponivel()
        if not ok:
            raise self.Indisponivel(motivo)
        return [*self.entry, *args, "--json"]

    def _exec(self, *args: str, timeout: int | None = None) -> dict:
        argv = self._argv(*args)
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout or self.timeout,
        )
        saida = (proc.stdout or "").strip()
        dados: Any
        try:
            dados = json.loads(saida) if saida else None
        except json.JSONDecodeError:
            dados = {"raw": proc.stdout}
        return {
            "argv": argv,
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
            "resultado": dados,
            "stderr": (proc.stderr or "").strip(),
        }

    # -- SQLite --------------------------------------------------------------
    def inspect_sqlite(
        self,
        db_path: str | Path,
        table: str | None = None,
        columns: list[str] | None = None,
        row_limit: int | None = None,
        schema_scope: str | None = None,
    ) -> dict:
        """Inspeciona um snapshot SQLite (schema + amostra de linhas).

        Não executa SQL arbitrário — leitura segura de estrutura e amostras.
        """
        argv: list[str] = ["inspect-sqlite-database", str(db_path)]
        if table:
            argv += ["--table", table]
        if columns:
            for c in columns:
                argv += ["--column", c]
        if row_limit is not None:
            argv += ["--row-limit", str(row_limit)]
        if schema_scope:
            argv += ["--schema-scope", schema_scope]
        return self._exec(*argv)

    # -- Aplicação JavaScript -------------------------------------------------
    def analyze_javascript_application(
        self,
        app_path: str | Path,
        fmt: str = "auto",
        extras: dict | None = None,
    ) -> dict:
        """Analisa um app JS (ASAR ou diretório) -> Application Graph."""
        payload = {"input_path": str(app_path), "format": fmt}
        if extras:
            payload.update(extras)
        return self._exec_json_payload("analyze-javascript-application", payload)

    def compare_application_versions(
        self, esquerda: dict | str | Path, direita: dict | str | Path,
        seed: dict | None = None,
    ) -> dict:
        """Compara duas versões de um app JS (Evidence de cada lado).

        Cada lado é um dict Evidence completo OU o caminho de um JSON salvo
        (``rea analyze-javascript-application ... --json > ev.json``). Conforme
        os docs, o payload usa ``left``/``right``.
        """
        payload: dict = {
            "left": _carregar_evidence(esquerda),
            "right": _carregar_evidence(direita),
        }
        if seed:
            payload["seed"] = seed
        return self._exec_payload("compare-application-versions", payload)

    def inspect_analysis_view(self, view: dict | str | Path) -> dict:
        """Projeta um summary/módulo/API-surface a partir de Evidence salva.

        ``view`` é o input (dict) ou o caminho de um JSON. Formato do dict
        (ver cli.md/workflows): ``{"source": {"kind":"inline","evidence":{...}},
        "view": {"kind":"summary"}}`` ou ``{"kind":"api-surface",...}``.
        """
        return self._exec_payload("inspect-analysis-view", _evidencia_ou_caminho(view))

    def trace_application_feature(self, entrada: dict | str | Path) -> dict:
        """Traça uma feature (seed) na Application Graph → resultado + Evidence."""
        return self._exec_payload("trace-application-feature", _evidencia_ou_caminho(entrada))

    def reconcile_javascript_runtime(self, entrada: dict | str | Path) -> dict:
        """Combina Application Graph estático com capturas de runtime (CDP/inspector)."""
        return self._exec_payload("reconcile-javascript-runtime", _evidencia_ou_caminho(entrada))

    # -- Binários não-nativos (sem disassembler) -----------------------------
    def inspect_go_binary(self, path: str | Path) -> dict:
        """Metadados de build embutidos num binário Go (sem instalar Go)."""
        return self._exec("inspect-go-binary", str(path))

    def inspect_wasm_artifact(self, path: str | Path) -> dict:
        """Validação/seções/import-exports de um artefato WASM (precisa WABT)."""
        return self._exec("inspect-wasm-artifact", str(path))

    # -- Capturas de rede históricas (HAR) -----------------------------------
    def inspect_web_network_capture(
        self, capture_path: str | Path, fmt: str = "har",
        records: list[int] | None = None, sensitive: list[str] | None = None,
    ) -> dict:
        """Inspeciona uma captura HAR offline (nunca busca as URLs gravadas).

        Útil para auditar uma sessão de portal exportada do DevTools: mostra
        requests, responses, payloads expostos e a **superfície de API**
        (via ``inspect_analysis_view`` com ``view.kind = "api-surface"``).
        """
        argv: list[str] = ["inspect-web-network-capture", str(capture_path), fmt]
        for r in records or []:
            argv += ["--record", str(r)]
        for s in sensitive or []:
            argv += ["--sensitive-value", s]
        return self._exec(*argv)

    # -- Evidência -----------------------------------------------------------
    def evidence_import(self, path: str | Path) -> dict:
        return self._exec("evidence-import", str(path))

    def evidence_export(self, path: str | Path, destino: str | Path) -> dict:
        return self._exec("evidence-export", str(path), str(destino))

    def compare_evidence(self, esquerda: str | Path, direita: str | Path) -> dict:
        return self._exec("compare", str(esquerda), str(direita))

    # -- Descoberta / prontidão ----------------------------------------------
    def providers(self) -> dict:
        """Lista providers nativos e as operações que cada um suporta."""
        return self._exec("providers")

    def doctor(self, provider: str | None = None, scope: str | None = None) -> dict:
        """Diagnóstico de prontidão (`rea doctor`).

        Retorna código 1 quando um check obrigatório do escopo falha — o dict
        ainda traz o diagnóstico estruturado.
        """
        argv = ["doctor"]
        if provider:
            argv += ["--provider", provider]
        if scope:
            argv += ["--scope", scope]
        return self._exec(*argv)

    # -- Inspetores diversos -------------------------------------------------
    def inspect_artifact(self, path: str | Path) -> dict:
        """Inventário/digests de um pacote (zip, plist, bundle, js app...)."""
        return self._exec("inspect-artifact", str(path))

    # -- Browser / CDP --------------------------------------------------------
    def list_browser_targets(self, cdp_endpoint: str = "http://127.0.0.1:9222") -> dict:
        return self._exec("list-browser-targets", cdp_endpoint)

    def inspect_web_page(
        self,
        cdp_endpoint: str,
        target_id: str,
        include_script_sources: bool = False,
        include_json_body_shapes: bool = False,
        observation_ms: int | None = None,
    ) -> dict:
        argv = ["inspect-web-page", cdp_endpoint, target_id]
        if include_script_sources:
            argv += ["--include-script-sources"]
        if include_json_body_shapes:
            argv += ["--include-json-body-shapes"]
        if observation_ms is not None:
            argv += ["--observation-ms", str(observation_ms)]
        return self._exec(*argv)

    def analyze_web_bundle(
        self,
        cdp_endpoint: str,
        target_id: str,
        fetch_source_maps: bool = False,
        observation_ms: int | None = None,
    ) -> dict:
        argv = ["analyze-web-bundle", cdp_endpoint, target_id]
        if fetch_source_maps:
            argv += ["--fetch-source-maps"]
        if observation_ms is not None:
            argv += ["--observation-ms", str(observation_ms)]
        return self._exec(*argv)

    def capture_web_screenshot(self, cdp_endpoint: str, target_id: str) -> dict:
        return self._exec("capture-web-screenshot", cdp_endpoint, target_id)

    def observe_web_session(
        self, cdp_endpoint: str, target_id: str, observation_ms: int = 10_000
    ) -> dict:
        return self._exec(
            "observe-web-session", cdp_endpoint, target_id,
            "--observation-ms", str(observation_ms),
        )

    # -- Código gerenciado (.NET) --------------------------------------------
    def inspect_managed_artifact(self, path: str | Path) -> dict:
        return self._exec("inspect-managed-artifact", str(path))

    def inspect_managed_members(self, path: str | Path, tipo: str | None = None) -> dict:
        argv = ["inspect-managed-members", str(path)]
        if tipo:
            argv += ["--type", tipo]
        return self._exec(*argv)

    # -- Capacidades ---------------------------------------------------------
    def capabilities(self) -> dict:
        """Lista as capacidades disponíveis do REA (`rea capabilities --json`)."""
        return self._exec("capabilities")

    # -- util ----------------------------------------------------------------
    def _exec_payload(self, comando: str, payload) -> dict:
        """Comandos que recebem um JSON inline OU o caminho de um arquivo.

        Se ``payload`` já for um caminho de arquivo (str/Path existente),
        passa direto. Se for dict/lista, serializa inline (ou em temp file se
        grande). O REA aceita ambos.
        """
        if isinstance(payload, (str, Path)):
            p = Path(payload)
            if p.exists():
                return self._exec(comando, str(p))
            # string que não é arquivo: assume que já é JSON inline
            return self._exec(comando, str(payload))
        inline = json.dumps(payload, ensure_ascii=False)
        if len(inline) < 7000:
            return self._exec(comando, inline)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(inline)
            tmp = fh.name
        try:
            return self._exec(comando, tmp)
        finally:
            try:
                Path(tmp).unlink(missing_ok=True)
            except OSError:
                pass

    # alias retrocompatível
    _exec_json_payload = _exec_payload
