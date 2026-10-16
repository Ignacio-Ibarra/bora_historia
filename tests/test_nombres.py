import pytest

from bora_historia import coincide, normalizar, variantes_consulta

ROTO = "�"


@pytest.mark.parametrize("a, b", [
    ("S.A.S.", "SAS"),
    ("F&C SERVICIOS S.A.S.", "F&C SERVICIOS SAS"),
    ("KOREA82 S.R.L.", "KOREA 82 SRL"),
    ("Cerámica Buenos Aires S.R.L.", "CERAMICA BUENOS AIRES SRL"),
    ("RED GESTIÓN SALUD S.A.S.", "red gestion salud sas"),
])
def test_coincide_ignora_mayusculas_tildes_y_puntuacion(a, b):
    assert coincide(a, b)


@pytest.mark.parametrize("a, b", [
    ("TRIVEXA S.A.", "TRIVEXA S.A.S."),                      # otro tipo societario
    ("F&C SERVICIOS S.A.S.", "R&C EMPRESA DE OBRAS Y SERVICIOS S.R.L."),
    ("SOLANO CLUB S.A.S.", "SOLANO CLUB HOUSE S.A."),        # prefijo, no igualdad
    ("HALITE S.A.S.", "HALITE CONSULTORES S.R.L."),
])
def test_coincide_no_confunde_nombres_parecidos(a, b):
    assert not coincide(a, b)


def test_caracter_roto_equivale_a_una_letra():
    assert coincide(f"NI{ROTO}O FAJO S.R.L.", "NIÑO FAJO S.R.L.")
    assert coincide(f"NI{ROTO}O FAJO S.R.L.", "NIDO FAJO S.R.L.")
    assert not coincide(f"NI{ROTO}O FAJO S.R.L.", "NIO FAJO S.R.L.")      # falta una letra
    assert not coincide(f"NI{ROTO}O FAJO S.R.L.", "NIXXO FAJO S.R.L.")    # sobran dos


def test_normalizar_deja_solo_alfanumericos_y_ampersand():
    assert normalizar("  f&c  Servicios, S.A.S. ") == "F&CSERVICIOSSAS"


def test_variantes_reemplaza_guiones_por_espacio():
    assert variantes_consulta("FULL-ARG S.A.S.") == ["FULL-ARG S.A.S.", "FULL ARG S.A.S."]


def test_variantes_reemplaza_and_por_ampersand():
    assert variantes_consulta("SPIRITS AND CORP S.A.") == ["SPIRITS AND CORP S.A.", "SPIRITS & CORP S.A."]


def test_variantes_combina_guion_y_and():
    assert variantes_consulta("MIX-ON AND CO S.A.") == [
        "MIX-ON AND CO S.A.", "MIX ON AND CO S.A.", "MIX-ON & CO S.A.", "MIX ON & CO S.A.",
    ]


def test_variantes_nombre_sin_cambios_es_una_sola():
    assert variantes_consulta("TRIVEXA S.A.") == ["TRIVEXA S.A."]


def test_variantes_no_toca_and_dentro_de_palabras():
    assert variantes_consulta("ANDES S.A.") == ["ANDES S.A."]
    assert variantes_consulta("SANDWICH S.R.L.") == ["SANDWICH S.R.L."]


def test_variantes_normaliza_espacios():
    assert variantes_consulta("  ACME   S.A.  ") == ["ACME S.A."]
