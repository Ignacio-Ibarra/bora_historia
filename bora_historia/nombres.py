"""Normalización y comparación de nombres de sociedades.

El timeline responde con búsquedas amplias (p. ej. "F&C SERVICIOS S.A.S." devolvió 82
sociedades), así que hay que quedarse solo con las que realmente coinciden. Y hay
nombres que la API no resuelve bien tal cual vienen, ver `variantes_consulta`.
"""
from __future__ import annotations

import re
import unicodedata

# Carácter de reemplazo (U+FFFD): en los textos extraídos del BORA aparece donde se
# perdió una tilde o una eñe. Al comparar equivale a exactamente una letra.
ROTO = "�"


def normalizar(nombre: str) -> str:
    """Mayúsculas, sin tildes, solo [A-Z0-9&]: "S.A.S." == "SAS" == "S A S".

    Conserva el carácter roto para tratarlo como comodín en `coincide`.
    """
    s = unicodedata.normalize("NFKD", nombre or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    return "".join(c for c in s if (c.isascii() and c.isalnum()) or c in "&" + ROTO)


def coincide(consulta: str, nombre: str) -> bool:
    """¿`nombre` es el mismo nombre que `consulta`, ignorando mayúsculas, tildes y puntuación?"""
    q, n = normalizar(consulta), normalizar(nombre)
    if ROTO in q:
        return re.fullmatch(re.escape(q).replace(ROTO, "."), n) is not None
    return q == n


def variantes_consulta(nombre: str) -> list[str]:
    """Formas de pedir el mismo nombre a la API, de la más fiel a la más transformada.

    Se observó que el timeline falla con:
      - guiones: "FULL-ARG S.A.S." devuelve 100 sociedades sin la buscada, mientras que
        "FULL ARG S.A.S." devuelve exactamente una.
      - la palabra "AND": "SPIRITS AND CORP S.A." devuelve 0, "SPIRITS & CORP S.A." la encuentra.
    """
    base = " ".join(nombre.split())
    sin_guion = " ".join(base.replace("-", " ").split())
    con_ampersand = re.sub(r"\bAND\b", "&", base, flags=re.IGNORECASE)
    ambas = re.sub(r"\bAND\b", "&", sin_guion, flags=re.IGNORECASE)
    unicas: list[str] = []
    for v in (base, sin_guion, con_ampersand, ambas):
        if v and v not in unicas:
            unicas.append(v)
    return unicas
