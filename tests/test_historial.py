"""Historial previo: lo que se ve el día que sale un aviso nuevo (el timeline va con un día de retraso)."""
import json
from datetime import date

import pytest

from bora_historia import Estado, HistorialPrevio, construir_busqueda
from tests.conftest import FakeSession, aviso, sociedad

DIA_D = date(2026, 10, 13)


def _historial(nombre, sociedades, antes_de=DIA_D, id_aviso=None):
    return HistorialPrevio.desde_busqueda(construir_busqueda(nombre, nombre, sociedades, id_aviso), antes_de)


def _acme(*avisos):
    return sociedad("ACME S.A.", list(avisos))


# -- tiene_previos: los tres valores --------------------------------------

def test_con_un_aviso_anterior_tiene_previos():
    """TRIVEXA el 13/10: el aviso de ese día todavía no está, pero sí el ESTATUTO del 09/10."""
    h = _historial("ACME S.A.", [_acme(aviso("A1", "09-10-2026", ("ESTATUTO",)))])
    assert h.tiene_previos is True
    assert [a.id_aviso for a in h.avisos] == ["A1"] and h.avisos[0].asuntos == ["ESTATUTO"]
    assert h.estado is Estado.ENCONTRADA and h.ambigua is False


def test_sociedad_encontrada_sin_avisos_anteriores_es_false():
    h = _historial("ACME S.A.", [_acme(aviso("A9", "20-10-2026"))])        # solo uno posterior
    assert h.tiene_previos is False and h.avisos == []


def test_sociedad_no_encontrada_es_sin_datos_y_no_sin_historia():
    """Una sociedad nueva y un nombre que la API no resuelve dan lo mismo: no hay que confundirlos con False."""
    h = _historial("NUEVA S.A.", [])
    assert h.estado is Estado.NO_ENCONTRADA and h.tiene_previos is None


def test_busqueda_truncada_es_sin_datos():
    ruido = [sociedad(f"OTRA {i} S.A.", [aviso(f"A{i}", "01-01-2026", denominacion=f"OTRA {i} S.A.")]) for i in range(100)]
    h = _historial("BROKERS S.R.L.", ruido)
    assert h.estado is Estado.TRUNCADA and h.tiene_previos is None


# -- la fecha ------------------------------------------------------------

def test_los_avisos_del_mismo_dia_y_posteriores_no_cuentan():
    h = _historial("ACME S.A.", [_acme(
        aviso("A1", "09-10-2026"), aviso("A2", "13-10-2026"), aviso("A3", "20-10-2026"))])
    assert [a.id_aviso for a in h.avisos] == ["A1"]


def test_los_avisos_salen_en_orden_cronologico():
    h = _historial("ACME S.A.", [_acme(aviso("A2", "12-10-2026"), aviso("A1", "02-10-2026"))])
    assert [a.id_aviso for a in h.avisos] == ["A1", "A2"]


# -- homónimos -----------------------------------------------------------

def _homonimos():
    nixa = sociedad("NIXA S.R.L.", [aviso("A1", "05-08-2026", ("CONTRATO",), "NIXA S.R.L.")], tipo="SRL")
    awam = sociedad("AWAM TEX S.R.L.", [aviso("A8", "12-08-2016", ("CONTRATO",), "NIXA S.R.L.")], tipo="SRL")
    return [nixa, awam]


def test_homonimos_sin_id_devuelven_la_union_y_se_marcan_ambiguos():
    """El día D no hay id de aviso: la historia de ambas candidatas, avisando que no se sabe cuál es."""
    h = _historial("NIXA S.R.L.", _homonimos(), antes_de=date(2026, 8, 14))
    assert h.estado is Estado.AMBIGUA and h.ambigua is True
    assert [a.id_aviso for a in h.avisos] == ["A8", "A1"]                 # unión, cronológica
    assert h.tiene_previos is True
    assert sorted(h.razones_sociales) == ["AWAM TEX S.R.L.", "NIXA S.R.L."]


def test_la_union_nunca_oculta_una_historia_real():
    """GLOBAL AGRO: el aviso es una constitución nueva, pero un homónimo viejo da una falsa alarma.
    Es el costo aceptado: una alarma de más es barata, una historia perdida no."""
    nueva = sociedad("GLOBAL AGRO S.A.", [aviso("A1", "21-09-2026", denominacion="GLOBAL AGRO S.A.")])
    vieja = sociedad("GL CAPITAL SA", [aviso("H1", "09-08-2001", ("ESTATUTO",), "GLOBAL AGRO S.A.")])
    h = _historial("GLOBAL AGRO S.A.", [nueva, vieja], antes_de=date(2026, 9, 21))
    assert h.ambigua and h.tiene_previos is True


def test_homonimos_sin_ningun_aviso_anterior_es_false_pero_sigue_ambiguo():
    a = sociedad("X S.A.", [aviso("A1", "20-10-2026", denominacion="X S.A.")], indice=1)
    b = sociedad("X SA", [aviso("A2", "21-10-2026", denominacion="X S.A.")], indice=2)
    h = _historial("X S.A.", [a, b])
    assert h.ambigua and h.tiene_previos is False


def test_con_el_id_del_aviso_se_resuelve_el_homonimo():
    """Para el aviso A1 (05/08), la NIXA correcta no tiene nada antes; solo el homónimo viejo hace ruido."""
    fecha = date(2026, 8, 5)
    con_id = _historial("NIXA S.R.L.", _homonimos(), antes_de=fecha, id_aviso="A1")
    assert con_id.estado is Estado.ENCONTRADA and con_id.ambigua is False
    assert con_id.tiene_previos is False and con_id.razones_sociales == ["NIXA S.R.L."]
    sin_id = _historial("NIXA S.R.L.", _homonimos(), antes_de=fecha)          # el día D: no hay id
    assert sin_id.ambigua and sin_id.tiene_previos is True                      # falsa alarma por el homónimo


# -- serialización -------------------------------------------------------

def test_el_json_incluye_los_valores_calculados():
    h = _historial("ACME S.A.", [_acme(aviso("A1", "09-10-2026"))])
    d = json.loads(h.model_dump_json())
    assert (d["tiene_previos"], d["ambigua"], d["estado"]) == (True, False, "encontrada")
    assert d["antes_de"] == "2026-10-13" and d["razones_sociales"] == ["ACME S.A."]
    assert d["avisos"][0]["id_aviso"] == "A1"


def test_sin_datos_se_serializa_como_null():
    d = json.loads(_historial("NUEVA S.A.", []).model_dump_json())
    assert d["tiene_previos"] is None and d["estado"] == "no_encontrada"


# -- el método del cliente -----------------------------------------------

def test_cliente_avisos_previos_de_punta_a_punta(cliente):
    sesion = FakeSession({"ACME S.A.": [_acme(aviso("A1", "09-10-2026", ("ESTATUTO",)))]})
    h = cliente(sesion).avisos_previos("ACME S.A.", DIA_D)
    assert h.tiene_previos is True and [a.id_aviso for a in h.avisos] == ["A1"]


def test_cliente_avisos_previos_usa_las_variantes_del_nombre(cliente):
    """FULL-ARG: con guion la API devuelve ruido; sin guion encuentra la sociedad."""
    ruido = [sociedad(f"OTRA {i} S.A.", [aviso(f"A{i}", "01-01-2026", denominacion=f"OTRA {i} S.A.")]) for i in range(100)]
    objetivo = sociedad("FULL-ARG S.A.S.", [aviso("A1", "19-08-2026", denominacion="FULL-ARG S.A.S.")], tipo="SAS")
    sesion = FakeSession({"FULL-ARG S.A.S.": ruido, "FULL ARG S.A.S.": [objetivo]})
    h = cliente(sesion).avisos_previos("FULL-ARG S.A.S.", date(2026, 9, 1))
    assert h.tiene_previos is True and h.busqueda.consulta_enviada == "FULL ARG S.A.S."


def test_cliente_avisos_previos_sociedad_nueva(cliente):
    h = cliente(FakeSession({})).avisos_previos("NUEVA S.A.", DIA_D)
    assert h.tiene_previos is None


def test_cliente_pasa_el_id_aviso_para_resolver_homonimos(cliente):
    h = cliente(FakeSession({"NIXA S.R.L.": _homonimos()})).avisos_previos("NIXA S.R.L.", date(2026, 8, 14), id_aviso="A1")
    assert h.estado is Estado.ENCONTRADA


@pytest.mark.parametrize("modelo", [HistorialPrevio])
def test_el_modelo_es_inmutable(modelo):
    h = _historial("ACME S.A.", [_acme(aviso("A1", "09-10-2026"))])
    with pytest.raises(Exception):
        h.avisos = []
