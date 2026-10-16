import pytest

from bora_historia import (
    Estado,
    RespuestaInesperada,
    TimelineError,
    TOPE_RESULTADOS,
    construir_busqueda,
    extraer_sociedades,
)
from tests.conftest import FakeResponse, FakeSession, ConnectionError_, aviso, html, sociedad


def _ruido(n):
    """n sociedades que no tienen nada que ver con la consulta."""
    return [sociedad(f"OTRA EMPRESA {i} S.A.", [aviso(f"A{i}", "01-01-2026", denominacion=f"OTRA EMPRESA {i} S.A.")], indice=i)
            for i in range(n)]


# -- extraer_sociedades ---------------------------------------------------

def test_extraer_sociedades_lee_el_literal():
    s = sociedad("ACME S.A.", [aviso("A1", "13-10-2026")])
    assert extraer_sociedades(html([s])) == [s]


def test_extraer_sociedades_sin_literal_falla():
    with pytest.raises(RespuestaInesperada, match="const societies"):
        extraer_sociedades("<html>sin datos</html>")


def test_extraer_sociedades_json_invalido_falla():
    with pytest.raises(RespuestaInesperada, match="JSON"):
        extraer_sociedades("const societies = [{oops};")


def test_extraer_sociedades_que_no_es_lista_falla():
    with pytest.raises(RespuestaInesperada, match="lista"):
        extraer_sociedades('const societies = {"a": 1};')


# -- construir_busqueda: estados -----------------------------------------

def test_encontrada_acota_a_la_sociedad_que_coincide():
    objetivo = sociedad("F&C SERVICIOS S.A.S.", [aviso("A1", "30-06-2026")], tipo="SAS")
    b = construir_busqueda("F&C SERVICIOS S.A.S.", "F&C SERVICIOS S.A.S.", _ruido(81) + [objetivo])
    assert b.estado is Estado.ENCONTRADA
    assert b.n_devueltas == 82 and b.n_coincidentes == 1
    assert b.sociedad.razon_social == "F&C SERVICIOS S.A.S."
    assert b.candidatas == []


def test_encontrada_por_denominacion_de_una_sociedad_renombrada():
    """La API agrupa bajo la razón social NUEVA; el aviso viejo conserva el nombre original."""
    renombrada = sociedad("AMICI FORTI S.R.L.", [
        aviso("A1", "05-06-2026", denominacion="FORTEZZA S.R.L."),
        aviso("A2", "18-06-2026", asuntos=("RECTIFICA/ACLARA AVISO ANTERIOR",), denominacion="AMICI FORTI S.R.L."),
    ], tipo="SRL")
    b = construir_busqueda("FORTEZZA S.R.L.", "FORTEZZA S.R.L.", [renombrada])
    assert b.estado is Estado.ENCONTRADA
    assert b.sociedad.razon_social == "AMICI FORTI S.R.L."


def test_ambigua_cuando_coinciden_varias_sociedades():
    a = sociedad("NIXA S.R.L.", [aviso("A1", "05-08-2026", denominacion="NIXA S.R.L.")], tipo="SRL")
    b_ = sociedad("AWAM TEX S.R.L.", [aviso("A2", "12-08-2016", denominacion="NIXA S.R.L.")], tipo="SRL", indice=2)
    r = construir_busqueda("NIXA S.R.L.", "NIXA S.R.L.", [a, b_])
    assert r.estado is Estado.AMBIGUA
    assert r.n_coincidentes == 2 and r.sociedad is None


def test_ambigua_se_resuelve_con_el_id_del_aviso():
    a = sociedad("NIXA S.R.L.", [aviso("A1", "05-08-2026", denominacion="NIXA S.R.L.")], tipo="SRL")
    b_ = sociedad("AWAM TEX S.R.L.", [aviso("A2", "12-08-2016", denominacion="NIXA S.R.L.")], tipo="SRL", indice=2)
    r = construir_busqueda("NIXA S.R.L.", "NIXA S.R.L.", [a, b_], id_aviso="A1")
    assert r.estado is Estado.ENCONTRADA
    assert r.sociedad.razon_social == "NIXA S.R.L."
    assert r.n_coincidentes == 2  # queda registrado que había homónimos


def test_ambigua_sigue_ambigua_si_el_id_no_esta_en_ninguna():
    a = sociedad("NIXA S.R.L.", [aviso("A1", "05-08-2026", denominacion="NIXA S.R.L.")], tipo="SRL")
    b_ = sociedad("AWAM TEX S.R.L.", [aviso("A2", "12-08-2016", denominacion="NIXA S.R.L.")], tipo="SRL", indice=2)
    assert construir_busqueda("NIXA S.R.L.", "NIXA S.R.L.", [a, b_], id_aviso="A99").estado is Estado.AMBIGUA


def test_truncada_si_llega_al_tope_sin_la_sociedad():
    r = construir_busqueda("FULL-ARG S.A.S.", "FULL-ARG S.A.S.", _ruido(TOPE_RESULTADOS))
    assert r.estado is Estado.TRUNCADA
    assert r.sociedades == [] and len(r.candidatas) == 10


def test_no_encontrada_con_candidatas_para_diagnosticar():
    parecida = sociedad("HALITE CONSULTORES S.R.L.", [aviso("A1", "01-01-2026", denominacion="HALITE CONSULTORES S.R.L.")], tipo="SRL")
    r = construir_busqueda("HALITE S.A.S.", "HALITE S.A.S.", [parecida])
    assert r.estado is Estado.NO_ENCONTRADA
    assert r.candidatas == ["HALITE CONSULTORES S.R.L."]


def test_no_encontrada_si_la_api_no_devuelve_nada():
    r = construir_busqueda("THEODYNAMICS S.A.S.", "THEODYNAMICS S.A.S.", [])
    assert r.estado is Estado.NO_ENCONTRADA and r.n_devueltas == 0


def test_encontrada_pero_sin_el_aviso_se_puede_consultar():
    """Caso del lag: la sociedad existe pero el aviso de hoy todavía no está."""
    s = sociedad("ALFA S.R.L.", [aviso("A1", "02-09-2026", asuntos=("CONTRATO",), denominacion="ALFA S.R.L.")], tipo="SRL")
    r = construir_busqueda("ALFA S.R.L.", "ALFA S.R.L.", [s])
    assert r.estado is Estado.ENCONTRADA
    assert not r.contiene("A2") and r.contiene("A1")


# -- TimelineClient.buscar ------------------------------------------------

def test_buscar_usa_la_variante_sin_guion_cuando_la_original_no_sirve(cliente):
    objetivo = sociedad("FULL-ARG S.A.S.", [aviso("A1", "19-08-2026", denominacion="FULL-ARG S.A.S.")], tipo="SAS")
    sesion = FakeSession({"FULL-ARG S.A.S.": _ruido(TOPE_RESULTADOS), "FULL ARG S.A.S.": [objetivo]})
    r = cliente(sesion).buscar_sociedad("FULL-ARG S.A.S.")
    assert r.estado is Estado.ENCONTRADA
    assert r.consulta == "FULL-ARG S.A.S." and r.consulta_enviada == "FULL ARG S.A.S."
    assert len(sesion.posts) == 2


def test_buscar_se_detiene_en_la_primera_variante_que_coincide(cliente):
    objetivo = sociedad("TRIVEXA S.A.", [aviso("A1", "09-10-2026", denominacion="TRIVEXA S.A.")])
    sesion = FakeSession({"TRIVEXA S.A.": [objetivo]})
    assert cliente(sesion).buscar_sociedad("TRIVEXA S.A.").estado is Estado.ENCONTRADA
    assert len(sesion.posts) == 1


def test_buscar_agota_las_variantes_y_prefiere_truncada_a_no_encontrada(cliente):
    sesion = FakeSession({"BROKERS S.R.L.": _ruido(TOPE_RESULTADOS)})
    r = cliente(sesion).buscar_sociedad("BROKERS S.R.L.")
    assert r.estado is Estado.TRUNCADA

    sesion2 = FakeSession({"MIX-ON S.A.S.": _ruido(TOPE_RESULTADOS)})  # la variante sin guion devuelve 0
    assert cliente(sesion2).buscar_sociedad("MIX-ON S.A.S.").estado is Estado.TRUNCADA
    assert len(sesion2.posts) == 2


def test_buscar_resuelve_homonimos_con_id_aviso(cliente):
    a = sociedad("NIXA S.R.L.", [aviso("A1", "05-08-2026", denominacion="NIXA S.R.L.")], tipo="SRL")
    b_ = sociedad("AWAM TEX S.R.L.", [aviso("A2", "12-08-2016", denominacion="NIXA S.R.L.")], tipo="SRL", indice=2)
    r = cliente(FakeSession({"NIXA S.R.L.": [a, b_]})).buscar_sociedad("NIXA S.R.L.", id_aviso="A1")
    assert r.estado is Estado.ENCONTRADA and r.sociedad.razon_social == "NIXA S.R.L."


def test_tipo_de_busqueda_invalido(cliente):
    with pytest.raises(ValueError):
        cliente(FakeSession()).consultar("otro", "x")


# -- HTTP: reintentos, pausas, errores -----------------------------------

def test_reintenta_ante_errores_de_red_y_luego_responde(cliente, reloj):
    objetivo = sociedad("TRIVEXA S.A.", [aviso("A1", "09-10-2026", denominacion="TRIVEXA S.A.")])
    sesion = FakeSession({"TRIVEXA S.A.": [objetivo]}, acciones=[ConnectionError_("caído"), FakeResponse("", status=503)])
    r = cliente(sesion, backoff=1.0).buscar_sociedad("TRIVEXA S.A.")
    assert r.estado is Estado.ENCONTRADA
    assert len(sesion.posts) == 3
    assert reloj.pausas == [1.0, 2.0]  # backoff exponencial


def test_falla_si_se_agotan_los_reintentos(cliente):
    sesion = FakeSession(acciones=[ConnectionError_("caído")] * 10)
    with pytest.raises(TimelineError, match="no respondió"):
        cliente(sesion, max_reintentos=2).consultar("society", "X")
    assert len(sesion.posts) == 3


def test_un_4xx_no_se_reintenta(cliente):
    sesion = FakeSession(acciones=[FakeResponse("", status=403)])
    with pytest.raises(TimelineError, match="403"):
        cliente(sesion).consultar("society", "X")
    assert len(sesion.posts) == 1


def test_respeta_el_intervalo_minimo_entre_consultas(cliente, reloj):
    sesion = FakeSession()
    c = cliente(sesion, min_intervalo=0.5)
    c.consultar("society", "A")
    c.consultar("society", "B")
    assert reloj.pausas == [0.5]  # la primera consulta no espera; la segunda sí


def test_fuerza_utf8_si_la_respuesta_no_declara_charset(cliente):
    respuesta = FakeResponse(html([]), content_type="text/html")
    cliente(FakeSession(acciones=[respuesta])).consultar("society", "X")
    assert respuesta.encoding == "utf-8"
