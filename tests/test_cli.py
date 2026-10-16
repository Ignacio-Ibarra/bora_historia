import json

import pytest

from bora_historia import TimelineClient, cli
from tests.conftest import FakeSession, aviso, sociedad

ACME = sociedad("ACME S.A.", [aviso("A1", "09-10-2026", denominacion="ACME S.A.")])


@pytest.fixture
def correr(monkeypatch, capsys, reloj):
    """Ejecuta la CLI con una sesión falsa y devuelve (JSON impreso, sesión)."""

    def _correr(argv, por_consulta=None):
        sesion = FakeSession(por_consulta or {})
        monkeypatch.setattr(
            cli, "TimelineClient",
            lambda: TimelineClient(session=sesion, min_intervalo=0, dormir=reloj.dormir, reloj=reloj),
        )
        cli.main(argv)
        return json.loads(capsys.readouterr().out), sesion

    return _correr


def test_sociedad_imprime_la_busqueda_interpretada(correr):
    salida, _ = correr(["sociedad", "ACME S.A."], {"ACME S.A.": [ACME]})
    assert salida["estado"] == "encontrada"
    assert salida["sociedades"][0]["avisos"][0]["fecha_publicado"] == "2026-10-09"


def test_sociedad_con_id_aviso(correr):
    otra = sociedad("ACME S.A.", [aviso("A2", "01-01-2010", denominacion="ACME S.A.")], indice=2)
    salida, _ = correr(["sociedad", "ACME S.A.", "--id-aviso", "A1"], {"ACME S.A.": [ACME, otra]})
    assert salida["estado"] == "encontrada" and salida["n_coincidentes"] == 2


def test_sociedad_crudo_imprime_la_respuesta_sin_filtrar(correr):
    ruido = sociedad("OTRA S.R.L.", [aviso("A2", "10-10-2026", denominacion="OTRA S.R.L.")], tipo="SRL", indice=2)
    salida, sesion = correr(["sociedad", "ACME S.A.", "--crudo"], {"ACME S.A.": [ACME, ruido]})
    assert [s["razon_social"] for s in salida] == ["ACME S.A.", "OTRA S.R.L."]  # sin filtrar
    assert len(sesion.posts) == 1  # sin probar variantes


def test_persona(correr):
    salida, sesion = correr(["persona", "20123456789"], {"20123456789": [ACME]})
    assert salida[0]["razon_social"] == "ACME S.A."
    assert sesion.posts[0]["searchtext_type"] == "person"


def test_persona_crudo(correr):
    salida, _ = correr(["persona", "20123456789", "--crudo"], {"20123456789": [ACME]})
    assert salida == [ACME]


def test_texto_con_max_length(correr):
    salida, sesion = correr(["texto", "fusion", "--max-length", "5000"], {"fusion": [ACME]})
    assert salida[0]["razon_social"] == "ACME S.A."
    assert sesion.posts[0]["max_length"] == "5000"


def test_texto_crudo(correr):
    salida, sesion = correr(["texto", "fusion", "--crudo"], {"fusion": [ACME]})
    assert salida == [ACME] and sesion.posts[0]["searchtext_type"] == "text"


def test_error_del_timeline_sale_con_codigo_1(monkeypatch, capsys, reloj):
    from tests.conftest import FakeResponse

    sesion = FakeSession(acciones=[FakeResponse("", status=403)])
    monkeypatch.setattr(cli, "TimelineClient", lambda: TimelineClient(session=sesion, min_intervalo=0, dormir=reloj.dormir, reloj=reloj))
    with pytest.raises(SystemExit) as salida:
        cli.main(["sociedad", "X"])
    assert salida.value.code == 1
    assert "403" in capsys.readouterr().err


def test_sin_subcomando_falla():
    with pytest.raises(SystemExit):
        cli.main([])
