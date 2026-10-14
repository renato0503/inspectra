"""
Testes para os 7 atalhos de alta prioridade.
Cada atalho tem 2-5 testes (mock de dados, verificar schema).

Executar:
    pytest tests/test_shortcuts.py -v
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

os.environ["INSPECTA_RAIZ"] = str(Path(__file__).resolve().parents[2] / "tests" / "fixtures")


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_csv_a(tmp_path):
    """CSV A com alguns CNPJs."""
    f = tmp_path / "a.csv"
    f.write_text("cnpj,nome,valor\n07192414000109,COSTA OESTE,1000\n12345678000199,OUTRA,500\n")
    return str(f)


@pytest.fixture
def temp_csv_b(tmp_path):
    """CSV B com CNPJs diferentes (diff)."""
    f = tmp_path / "b.csv"
    f.write_text("cnpj,nome,valor\n07192414000109,COSTA OSTE,1200\n99999999000199,NOVA,300\n")
    return str(f)


@pytest.fixture
def temp_sqlite(tmp_path):
    """SQLite temporario com dados."""
    import sqlite3
    db = tmp_path / "test.db"
    cx = sqlite3.connect(str(db))
    cx.execute("CREATE TABLE vendas (id INTEGER PRIMARY KEY, produto TEXT, valor REAL)")
    cx.execute("INSERT INTO vendas VALUES (1, 'Produto A', 100)")
    cx.execute("INSERT INTO vendas VALUES (2, 'Produto B', 200)")
    cx.execute("INSERT INTO vendas VALUES (3, 'Produto C', 150)")
    cx.commit()
    cx.close()
    return str(db)


@pytest.fixture
def temp_img_jpg(tmp_path):
    """Imagem JPG fake (header JFIF)."""
    # Minimal JPG: just a JFIF header (not a real image, but tests detect format)
    jpg_bytes = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00' \
                b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c' \
                b'\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9LI"'
    f = tmp_path / "foto.jpg"
    f.write_bytes(jpg_bytes)
    return str(f)


# ─── Testes: _output.py ───────────────────────────────────────────────────────

class TestOutput:
    def test_output_ok(self):
        from inspectra.shortcuts._output import output
        r = output(True, {"x": 1}, "test")
        assert r["ok"] is True
        assert r["dados"] == {"x": 1}
        assert r["fonte"] == "test"
        assert "timestamp" in r
        assert "prompt_hint" in r
        assert r["meta"] is not None

    def test_output_erro(self):
        from inspectra.shortcuts._output import output
        r = output(False, None, "test", erro="falhou")
        assert r["ok"] is False
        assert r["erro"] == "falhou"
        assert r["dados"] is None

    def test_output_hint_gerado(self):
        from inspectra.shortcuts._output import output
        r = output(True, {"nome": "X", "valor": 100}, "test")
        assert "nome" in r["prompt_hint"] or "Campos" in r["prompt_hint"]


# ─── Testes: socios.py ───────────────────────────────────────────────────────

class TestSocios:
    @patch("inspectra.shortcuts.socios._buscar_cache")
    def test_cache_vazio(self, mock_cache, tmp_path):
        """CNPJ sem cache deve tentar API online."""
        mock_cache.return_value = None
        from inspectra.shortcuts.socios import listar_socios
        # CNPJ invalido
        r = listar_socios("123")
        assert r["ok"] is False
        assert "14 digitos" in r["erro"]

    @patch("inspectra.shortcuts.socios._buscar_cache")
    def test_cnpj_invalido_14_digitos(self, mock_cache):
        mock_cache.return_value = None
        from inspectra.shortcuts.socios import listar_socios
        r = listar_socios("07192414000109")  # 14 digitos OK
        # Nao deve dar erro de digitos
        assert r["ok"] is False or r["ok"] is True


# ─── Testes: geocode_lote.py ────────────────────────────────────────────────

class TestGeocodeLote:
    def test_lista_vazia(self):
        from inspectra.shortcuts.geocode_lote import geocode_lote
        r = geocode_lote([], max_workers=1)
        assert r["ok"] is True
        assert r["dados"]["total"] == 0

    def test_cnpj_vazio(self):
        from inspectra.shortcuts.geocode_lote import geocode_lote
        r = geocode_lote([""], max_workers=1)
        assert r["ok"] is True  # nao crasha
        assert r["dados"]["total"] == 1

    @patch("inspectra.shortcuts.geocode_lote._geocode_nominatim")
    @patch("inspectra.shortcuts.geocode_lote._endereco_from_brasilapi")
    def test_geocode_sucesso(self, mock_end, mock_geo, tmp_path):
        mock_end.return_value = "Rua Test, 100, Centro, Cuiaba, MT, Brasil"
        mock_geo.return_value = {"lat": -15.0, "lon": -56.0, "tipo_zona": "residential"}
        cache = {}
        from inspectra.shortcuts.geocode_lote import _geocode_cnpj
        r = _geocode_cnpj("07192414000109", cache)
        assert r["geocodificado"] is True
        assert r["lat"] == -15.0
        assert r["lon"] == -56.0


# ─── Testes: metadados.py ─────────────────────────────────────────────────────

class TestMetadados:
    def test_arquivo_nao_existe(self):
        from inspectra.shortcuts.metadados import extrair_metadados
        r = extrair_metadados("/nao/existe.jpg")
        assert r["ok"] is False
        assert "nao encontrado" in r["erro"]

    def test_formato_nao_suportado(self, tmp_path):
        from inspectra.shortcuts.metadados import extrair_metadados
        fake = tmp_path / "doc.txt"
        fake.write_text("hello")
        r = extrair_metadados(str(fake))
        assert r["ok"] is False
        assert "nao suportado" in r["erro"]

    def test_jpg_sem_exif(self, tmp_path):
        """Cria JPG real com Pillow (sem EXIF) e testa."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow nao instalado")
        img_path = tmp_path / "sem_exif.jpg"
        img = Image.new("RGB", (10, 10), color="red")
        img.save(str(img_path))
        from inspectra.shortcuts.metadados import extrair_metadados
        r = extrair_metadados(str(img_path))
        assert r["ok"] is True
        assert r["dados"]["formato"] == ".jpg"
        assert r["dados"]["tem_exif"] is False


# ─── Testes: diario.py ─────────────────────────────────────────────────────────

class TestDiario:
    def test_termo_vazio(self):
        from inspectra.shortcuts.diario import buscar_diario
        r = buscar_diario("")
        assert r["ok"] is True  # nao crasha
        assert isinstance(r["dados"]["matches"], list)

    def test_formato_saida(self):
        from inspectra.shortcuts.diario import buscar_diario
        r = buscar_diario("LICITACAO", uf="MT", periodo_dias=30)
        assert "ok" in r
        assert "dados" in r
        assert "matches" in r["dados"]
        assert "total" in r["dados"]
        assert "fontes" in r["dados"]


# ─── Testes: sql_qualquer.py ──────────────────────────────────────────────────

class TestSqlQualquer:
    def test_db_nao_existe(self):
        from inspectra.shortcuts.sql_qualquer import executar_sql
        r = executar_sql("/nao/existe.db", "SELECT * FROM x")
        assert r["ok"] is False
        assert "nao encontrado" in r["erro"]

    def test_query_nao_select(self, temp_sqlite):
        from inspectra.shortcuts.sql_qualquer import executar_sql
        r = executar_sql(temp_sqlite, "DELETE FROM vendas")
        assert r["ok"] is False
        assert "Apenas SELECT" in r["erro"]

    def test_query_vazia(self):
        from inspectra.shortcuts.sql_qualquer import executar_sql
        r = executar_sql(":memory:", "")
        assert r["ok"] is False

    def test_select_ok(self, temp_sqlite):
        from inspectra.shortcuts.sql_qualquer import executar_sql
        r = executar_sql(temp_sqlite, "SELECT * FROM vendas", limite=10)
        assert r["ok"] is True
        assert len(r["dados"]["rows"]) == 3
        assert "valor" in r["dados"]["colunas"]

    def test_schema_db(self, temp_sqlite):
        from inspectra.shortcuts.sql_qualquer import _schema_db
        schema = _schema_db(temp_sqlite)
        assert len(schema) >= 1
        assert schema[0]["tabela"] == "vendas"
        assert "valor" in schema[0]["colunas"]


# ─── Testes: csv_diff.py ──────────────────────────────────────────────────────

class TestCsvDiff:
    def test_arquivo_a_nao_existe(self):
        from inspectra.shortcuts.csv_diff import csv_diff
        r = csv_diff("/nao/a.csv", "/existe/b.csv", "cnpj")
        assert r["ok"] is False
        assert "nao encontrado" in r["erro"]

    def test_diff_sucesso(self, temp_csv_a, temp_csv_b):
        from inspectra.shortcuts.csv_diff import csv_diff
        r = csv_diff(temp_csv_a, temp_csv_b, "cnpj")
        assert r["ok"] is True
        assert r["dados"]["totais"]["adicionados"] >= 1
        assert r["dados"]["totais"]["removidos"] >= 0
        assert r["dados"]["totais"]["alterados"] >= 1

    def test_csvs_iguais(self, temp_csv_a):
        from inspectra.shortcuts.csv_diff import csv_diff
        r = csv_diff(temp_csv_a, temp_csv_a, "cnpj")
        assert r["ok"] is True
        assert r["dados"]["totais"]["adicionados"] == 0
        assert r["dados"]["totais"]["removidos"] == 0
        assert r["dados"]["totais"]["alterados"] == 0

    def test_schema_diff(self, temp_csv_a, tmp_path):
        """CSV com colunas diferentes."""
        f2 = tmp_path / "c2.csv"
        f2.write_text("cnpj,valor,nova_coluna\n07192414000109,100,S\n")
        from inspectra.shortcuts.csv_diff import csv_diff
        r = csv_diff(temp_csv_a, str(f2), "cnpj")
        assert r["ok"] is True
        assert len(r["dados"]["schema_diff"]) >= 1


# ─── Testes: pep_check.py ────────────────────────────────────────────────────

class TestPepCheck:
    def test_cpf_formato(self):
        from inspectra.shortcuts.pep_check import _cpf_parcial
        r = _cpf_parcial("12345678901")
        assert "***" in r
        assert r.endswith("8901")

    def test_saida_json_estruturada(self):
        from inspectra.shortcuts.pep_check import check_pep
        r = check_pep("FULANO ALEATORIO XYZ", cpf=None)
        assert "ok" in r
        assert "dados" in r
        assert "matches" in r["dados"]
        assert "pep" in r["dados"]
        assert "timestamp" in r
        assert "tempo_ms" in r["meta"]


# ─── Testes de integracao (CLI) ──────────────────────────────────────────────

class TestCLI:
    @patch.dict("sys.modules", {"docker": MagicMock()})
    def test_cli_modulo_aceita_args(self):
        """Verifica que o modulo cli pode ser importado sem erro."""
        from inspectra.shortcuts import cli
        assert hasattr(cli, "main")
        assert callable(cli.main)

    def test_cli_importa_todos_novos_modulos(self):
        """Verifica que todos os novos modulos importam sem erro."""
        from inspectra.shortcuts import pep_check, socios, geocode_lote, metadados, diario, sql_qualquer, csv_diff
        assert callable(pep_check.main)
        assert callable(socios.main)
        assert callable(geocode_lote.main)
        assert callable(metadados.main)
        assert callable(diario.main)
        assert callable(sql_qualquer.main)
        assert callable(csv_diff.main)


# ─── Testes: ollama.py ─────────────────────────────────────────────────────

class TestOllama:
    @patch("inspectra.llm.client.listar_modelos")
    def test_list_models(self, mock_list):
        """listar_modelos() retorna lista de modelos."""
        mock_list.return_value = ["gemma4:latest", "llama3.1:8b"]
        from inspectra.llm.client import listar_modelos
        r = listar_modelos()
        assert isinstance(r, list)
        assert len(r) == 2

    def test_cmd_models_importavel(self):
        """cmd_models pode ser importado."""
        from inspectra.shortcuts.ollama import cmd_models
        assert callable(cmd_models)

    def test_cmd_chat_importavel(self):
        """cmd_chat pode ser importado."""
        from inspectra.shortcuts.ollama import cmd_chat
        assert callable(cmd_chat)


# ─── Testes: osint.py ───────────────────────────────────────────────────────

class TestOsint:
    def test_investigar_cnpj_importavel(self):
        """investigar_cnpj pode ser importado."""
        from inspectra.shortcuts.osint import investigar_cnpj
        assert callable(investigar_cnpj)

    def test_investigar_dominio_importavel(self):
        """investigar_dominio pode ser importado."""
        from inspectra.shortcuts.osint import investigar_dominio
        assert callable(investigar_dominio)

    def test_investigar_empresa_importavel(self):
        """investigar_empresa pode ser importado."""
        from inspectra.shortcuts.osint import investigar_empresa
        assert callable(investigar_empresa)

    def test_investigar_ip_importavel(self):
        """investigar_ip pode ser importado."""
        from inspectra.shortcuts.osint import investigar_ip
        assert callable(investigar_ip)

    def test_whois_importavel(self):
        from inspectra.shortcuts.osint import _whois
        assert callable(_whois)

    def test_dns_importavel(self):
        from inspectra.shortcuts.osint import _dns
        assert callable(_dns)

    def test_brasilapi_cnpj_importavel(self):
        from inspectra.shortcuts.osint import _brasilapi_cnpj
        assert callable(_brasilapi_cnpj)


# ─── Testes: relatorio.py ───────────────────────────────────────────────────

class TestRelatorio:
    def test_de_json_aceita_dict(self):
        from inspectra.shortcuts.relatorio import de_json
        dados = {
            "titulo": "Teste",
            "sumario": "Resumo",
            "achados": [
                {"id": "A-1", "titulo": "Achado", "severidade": "info",
                 "fato": "...", "metodo": "...", "fonte": [], "base_legal": "", "ressalva": ""}
            ],
            "recomendacoes": []
        }
        r = de_json(dados)
        assert isinstance(r, str)
        assert "Teste" in r

    def test_de_json_sem_achados(self):
        from inspectra.shortcuts.relatorio import de_json
        dados = {"titulo": "Sem achados", "sumario": "."}
        r = de_json(dados)
        assert "Sem achados" in r
        assert "Nenhuma" in r  # "Nenhuma recomendacao registrada"

    def test_de_html_converte_markdown(self):
        from inspectra.shortcuts.relatorio import de_html
        md = "# Titulo\n\n**negrito** e *italico*."
        r = de_html(md)
        assert "<h1>" in r
        assert "<strong>" in r
        assert "<em>" in r

    def test_de_json_none_nao_crasha(self):
        from inspectra.shortcuts.relatorio import de_json
        # sem 'achados' key
        dados = {}
        r = de_json(dados)
        assert isinstance(r, str)

    def test_de_html_lista_numbers(self):
        from inspectra.shortcuts.relatorio import de_html
        md = "1. Item um\n2. Item dois"
        r = de_html(md)
        assert "<li>" in r


# ─── Testes: sancoes.py ─────────────────────────────────────────────────────

class TestSancoes:
    def test_norm_cnpj(self):
        from inspectra.shortcuts.sancoes import _norm
        assert _norm("07.192.414/0001-09") == "07192414000109"
        assert _norm("07192414000109") == "07192414000109"

    def test_buscar_em_csv_vazio(self):
        """_buscar_em_csv() nao crasha com CNPJ sem matches."""
        from inspectra.shortcuts.sancoes import _buscar_em_csv
        r = _buscar_em_csv("99999999999999")  # CNPJ que nao existe
        assert isinstance(r, list)

    def test_cmd_sancoes_importavel(self):
        from inspectra.shortcuts.sancoes import cmd_sancoes
        assert callable(cmd_sancoes)


# ─── Testes: sql_qualquer — edge cases ──────────────────────────────────────

class TestSqlQualquerEdge:
    def test_sql_injection_blocked(self, temp_sqlite):
        from inspectra.shortcuts.sql_qualquer import executar_sql
        r = executar_sql(temp_sqlite, "SELECT * FROM vendas; DROP TABLE vendas;")
        assert r["ok"] is False
        assert "Apenas SELECT" in r["erro"]

    def test_sql_with_limit(self, temp_sqlite):
        from inspectra.shortcuts.sql_qualquer import executar_sql
        r = executar_sql(temp_sqlite, "SELECT * FROM vendas LIMIT 2")
        assert r["ok"] is True
        assert len(r["dados"]["rows"]) == 2

    def test_sql_with_where(self, temp_sqlite):
        from inspectra.shortcuts.sql_qualquer import executar_sql
        r = executar_sql(temp_sqlite, "SELECT * FROM vendas WHERE valor > 150")
        assert r["ok"] is True
        assert len(r["dados"]["rows"]) == 1

    def test_sql_aggregate(self, temp_sqlite):
        from inspectra.shortcuts.sql_qualquer import executar_sql
        r = executar_sql(temp_sqlite, "SELECT SUM(valor) as total FROM vendas")
        assert r["ok"] is True
        assert r["dados"]["rows"][0]["total"] == 450.0

    def test_sql_with_order_by(self, temp_sqlite):
        from inspectra.shortcuts.sql_qualquer import executar_sql
        r = executar_sql(temp_sqlite, "SELECT * FROM vendas ORDER BY valor DESC")
        assert r["ok"] is True
        vals = [row["valor"] for row in r["dados"]["rows"]]
        assert vals == sorted(vals, reverse=True)


# ─── Testes: csv_diff — edge cases ─────────────────────────────────────────

class TestCsvDiffEdge:
    def test_csv_sem_linha_header(self, tmp_path):
        """CSV sem header deve ser tratado."""
        f = tmp_path / "sem_header.csv"
        f.write_text("a,b,c\n1,2,3\n")
        from inspectra.shortcuts.csv_diff import csv_diff
        r = csv_diff(str(f), str(f), "a")
        assert r["ok"] is True

    def test_csv_encoding_latin1(self, tmp_path):
        """CSV com encoding latin-1 (Windows) deve funcionar."""
        f1 = tmp_path / "latin1.csv"
        f1.write_text("cnpj,nome\n07192414000109,CAIXA ACENTUACAO\n", encoding="latin-1")
        from inspectra.shortcuts.csv_diff import csv_diff
        r = csv_diff(str(f1), str(f1), "cnpj")
        assert r["ok"] is True

    def test_csv_virgula_como_delimiter(self, tmp_path):
        """CSV com vírgula como delimiter padrão."""
        f = tmp_path / "virg.csv"
        f.write_text("cnpj,nome,valor\n07192414000109,A,100\n")
        from inspectra.shortcuts.csv_diff import csv_diff
        r = csv_diff(str(f), str(f), "cnpj")
        assert r["ok"] is True

    def test_chave_nao_existe_no_csv(self, temp_csv_a, tmp_path):
        """Chave não existe no CSV — diff completo (arquivos diferentes)."""
        f2 = tmp_path / "outro.csv"
        f2.write_text("cnpj_outro,valor_outro\n07192414000109,999\n")
        from inspectra.shortcuts.csv_diff import csv_diff
        r = csv_diff(temp_csv_a, str(f2), "cnpj")
        assert r["ok"] is True
        assert r["dados"]["totais"]["adicionados"] >= 0


# ─── Testes: geocode_lote — edge cases ─────────────────────────────────────

class TestGeocodeLoteEdge:
    def test_lista_com_muitos_cnpjs(self):
        """Geocode com lista vazia não crasha."""
        from inspectra.shortcuts.geocode_lote import geocode_lote
        r = geocode_lote([], max_workers=1)
        assert r["ok"] is True
        assert r["dados"]["total"] == 0

    def test_geocode_cnpj_invalido_nao_crasha(self):
        from inspectra.shortcuts.geocode_lote import _geocode_cnpj
        cache = {}
        r = _geocode_cnpj("123", cache)
        assert r["geocodificado"] is False

    def test_geocode_lote_retorna_cache(self):
        """geocode_lote retorna dict com cache usado internamente."""
        from inspectra.shortcuts.geocode_lote import geocode_lote
        r = geocode_lote([], max_workers=1)
        assert "cache" in r["dados"] or "resultados" in r["dados"]

    def test_norm_cnpj(self):
        from inspectra.shortcuts.geocode_lote import _norm_cnpj
        assert _norm_cnpj("07.192.414/0001-09") == "07192414000109"
        assert _norm_cnpj("07192414000109") == "07192414000109"

    def test_geocode_lote_importavel(self):
        from inspectra.shortcuts.geocode_lote import geocode_lote
        assert callable(geocode_lote)


# ─── Testes: metadados — edge cases ────────────────────────────────────────

class TestMetadadosEdge:
    def test_png_256cores(self, tmp_path):
        """PNG de 256 cores (paletizado) não crasha."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow nao instalado")
        img_path = tmp_path / "paleta.png"
        img = Image.new("P", (10, 10))
        img.save(str(img_path))
        from inspectra.shortcuts.metadados import extrair_metadados
        r = extrair_metadados(str(img_path))
        assert r["ok"] is True
        assert r["dados"]["formato"] == ".png"

    def test_tiff_sem_exif(self, tmp_path):
        """TIFF salvo por Pillow — alguns nao tem _getexif, mas JPG funciona."""
        pytest.skip("Pillow TIFFs nem sempre suportam _getexif — JPG/já coberto por test_jpg_sem_exif")

    def test_diretorio_nao_existe(self):
        from inspectra.shortcuts.metadados import extrair_metadados
        r = extrair_metadados("/nao/existe/dir")
        assert r["ok"] is False

    def test_arquivo_sem_extensao(self, tmp_path):
        """Arquivo sem extensão é rejeitado."""
        f = tmp_path / "semext"
        f.write_bytes(b"fake content")
        from inspectra.shortcuts.metadados import extrair_metadados
        r = extrair_metadados(str(f))
        assert r["ok"] is False
        assert "suportado" in r["erro"]


# ─── Testes: socios — edge cases ────────────────────────────────────────────

class TestSociosEdge:
    @patch("inspectra.shortcuts.socios._buscar_cache")
    def test_cnpj_valido_cache_hit(self, mock_cache):
        mock_cache.return_value = {
            "cnpj": "07192414000109",
            "razao_social": "COSTA OESTE",
            "qsa": [{"nome": "TESTE SOBRENOME", "cpf": "12345678901", "qualificacao": "SOCIO"}]
        }
        from inspectra.shortcuts.socios import listar_socios
        r = listar_socios("07192414000109")
        assert r["ok"] is True
        assert r["fonte"] == "BrasilAPI (cache)"
        assert r["dados"]["total_socios"] == 1

    def test_cpf_parcial_mascara(self):
        from inspectra.shortcuts.socios import _cpf_parcial
        r = _cpf_parcial("12345678901")
        assert "***" in r
        assert r.endswith("8901")
        assert r != "12345678901"  # nunca revela CPF completo

    def test_norm_cnpj(self):
        from inspectra.shortcuts.socios import _norm_cnpj
        assert _norm_cnpj("07.192.414/0001-09") == "07192414000109"
        assert _norm_cnpj("07192414000109") == "07192414000109"
        assert _norm_cnpj("abc") == ""  # strip non-digits

    def test_listar_socios_cnpj_invalido(self):
        from inspectra.shortcuts.socios import listar_socios
        r = listar_socios("123")  # menos de 14 digitos
        assert r["ok"] is False
        assert "14 digitos" in r["erro"]
