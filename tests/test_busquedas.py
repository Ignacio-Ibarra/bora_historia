"""Búsquedas por persona y por texto, y consulta sin interpretar."""
from bora_historia import Sociedad
from tests.conftest import FakeSession, aviso, sociedad


def _sociedades():
    return [
        sociedad("ACME S.A.", [aviso("A1", "09-10-2026", denominacion="ACME S.A.")]),
        sociedad("OTRA S.R.L.", [aviso("A2", "10-10-2026", asuntos=("CONTRATO",), denominacion="OTRA S.R.L.")], tipo="SRL", indice=2),
    ]


def test_buscar_persona_devuelve_sociedades_tipadas_sin_filtrar(cliente):
    sesion = FakeSession({"20123456789": _sociedades()})
    r = cliente(sesion).buscar_persona("20123456789")
    assert all(isinstance(s, Sociedad) for s in r)
    assert [s.razon_social for s in r] == ["ACME S.A.", "OTRA S.R.L."]  # ninguna se descarta
    assert sesion.posts[0]["searchtext_type"] == "person"
    assert sesion.posts[0]["searchtext_person"] == "20123456789"
    assert sesion.posts[0]["searchtext_society"] == ""


def test_buscar_texto_envia_el_tipo_y_max_length(cliente):
    sesion = FakeSession({"fusion por absorcion": _sociedades()[:1]})
    r = cliente(sesion).buscar_texto("fusion por absorcion", max_length=5000)
    assert [s.razon_social for s in r] == ["ACME S.A."]
    assert sesion.posts[0]["searchtext_type"] == "text"
    assert sesion.posts[0]["searchtext_text"] == "fusion por absorcion"
    assert sesion.posts[0]["max_length"] == "5000"


def test_buscar_texto_sin_max_length_no_envia_el_parametro(cliente):
    sesion = FakeSession()
    cliente(sesion).buscar_texto("algo")
    assert "max_length" not in sesion.posts[0]


def test_consultar_devuelve_lo_que_responde_el_timeline_sin_filtrar(cliente):
    crudo = _sociedades()
    r = cliente(FakeSession({"ACME S.A.": crudo})).consultar("society", "ACME S.A.")
    assert r == crudo  # dicts tal cual, sin pasar por los modelos
