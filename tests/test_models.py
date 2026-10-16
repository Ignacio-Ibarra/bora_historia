from datetime import date

from bora_historia import Aviso, Busqueda, Estado, Sociedad
from tests.conftest import aviso, sociedad


def test_aviso_parsea_fecha_y_limpia_asuntos():
    a = Aviso.model_validate(aviso("A1", "13-10-2026", asuntos=("AUMENTO DE CAPITAL CON REFORMA ", " ")))
    assert a.fecha_publicado == date(2026, 10, 13)
    assert a.asuntos == ["AUMENTO DE CAPITAL CON REFORMA"]


def test_aviso_ignora_campos_extra_y_tolera_tags_incompletos():
    a = Aviso.model_validate(aviso("A1", "13-10-2026"))
    assert a.tags.firmante == ["una persona"]
    assert a.tags.objeto_social == []  # no vino en el crudo


def test_aviso_historico_sin_asuntos():
    a = Aviso.model_validate(aviso("H2031860", "05-09-2007", asuntos=()))
    assert a.asuntos == []


def test_sociedad_aplana_items_y_ordena_por_fecha():
    crudo = sociedad("ACME S.A.", [aviso("A2", "13-10-2026"), aviso("A1", "09-10-2026")])
    s = Sociedad.desde_api(crudo)
    assert [a.id_aviso for a in s.avisos] == ["A1", "A2"]  # cronológico, aunque la API los entregue al revés


def test_sociedad_desempata_por_id_el_mismo_dia():
    crudo = sociedad("ACME S.A.", [aviso("A9", "13-10-2026"), aviso("A3", "13-10-2026")])
    assert [a.id_aviso for a in Sociedad.desde_api(crudo).avisos] == ["A3", "A9"]


def test_sociedad_nombres_incluye_denominaciones_historicas():
    crudo = sociedad(
        "AMICI FORTI S.R.L.",
        [aviso("A1", "05-06-2026", denominacion="FORTEZZA S.R.L."),
         aviso("A2", "18-06-2026", denominacion="AMICI FORTI S.R.L.")],
        tipo="SRL",
    )
    assert Sociedad.desde_api(crudo).nombres() == {"AMICI FORTI S.R.L.", "FORTEZZA S.R.L."}


def test_avisos_antes_de_es_estricto():
    s = Sociedad.desde_api(sociedad("ACME S.A.", [aviso("A1", "09-10-2026"), aviso("A2", "13-10-2026")]))
    assert [a.id_aviso for a in s.avisos_antes_de(date(2026, 10, 13))] == ["A1"]  # el del mismo día no cuenta
    assert s.avisos_antes_de(date(2026, 10, 9)) == []


def test_aviso_y_contiene():
    s = Sociedad.desde_api(sociedad("ACME S.A.", [aviso("A1", "09-10-2026")]))
    assert s.contiene("A1") and not s.contiene("A9")
    assert s.aviso("A1").id_aviso == "A1" and s.aviso("A9") is None


def test_busqueda_sociedad_solo_si_hay_exactamente_una():
    una = Sociedad.desde_api(sociedad("A S.A.", [aviso("A1", "09-10-2026")]))
    otra = Sociedad.desde_api(sociedad("A S.A.", [aviso("A2", "10-10-2026")]))
    assert Busqueda(consulta="A", consulta_enviada="A", estado=Estado.ENCONTRADA, sociedades=[una]).sociedad == una
    ambigua = Busqueda(consulta="A", consulta_enviada="A", estado=Estado.AMBIGUA, sociedades=[una, otra])
    assert ambigua.sociedad is None
    assert ambigua.contiene("A2")
