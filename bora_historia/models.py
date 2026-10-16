"""Contrato de datos de bora_historia.

Los modelos separan HECHOS (qué devolvió el timeline) de DECISIONES (qué hacer con
eso): el paquete no clasifica avisos, solo entrega la historia de la sociedad con
suficiente información para que el consumidor decida.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_FECHA_API = re.compile(r"^\d{2}-\d{2}-\d{4}$")


class Estado(str, Enum):
    """Resultado de buscar una sociedad por nombre."""

    ENCONTRADA = "encontrada"          # exactamente una sociedad coincide
    AMBIGUA = "ambigua"                # más de una sociedad coincide (homónimos)
    TRUNCADA = "truncada"              # la API cortó en el tope y no apareció la sociedad
    NO_ENCONTRADA = "no_encontrada"    # la API no devolvió ninguna sociedad que coincida


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class Tags(_Base):
    """Datos que el timeline extrae de cada aviso. Pueden venir vacíos."""

    autoridad_designada: list[str] = Field(default_factory=list)
    cuit: list[str] = Field(default_factory=list)
    direccion_sociedad: list[str] = Field(default_factory=list)
    dni: list[str] = Field(default_factory=list)
    fecha_constitucion: list[str] = Field(default_factory=list)
    firmante: list[str] = Field(default_factory=list)
    integrante: list[str] = Field(default_factory=list)
    integrante_renunciante: list[str] = Field(default_factory=list)
    objeto_social: list[str] = Field(default_factory=list)


class Aviso(_Base):
    """Un aviso de la historia de una sociedad."""

    id_aviso: str
    fecha_publicado: date
    rubro: str = ""
    accion: str = ""
    # Clasificación del timeline (ESTATUTO, CONTRATO, COMPLEMENTO, RECTIFICA/ACLARA
    # AVISO ANTERIOR, CESION DE CUOTAS, ...). No es verdad absoluta: se observó
    # `CONTRATO` en complementarios de SRL. Vacío en avisos históricos (prefijo "H").
    asuntos: list[str] = Field(default_factory=list)
    # Nombre con que se publicó el aviso. Puede diferir de la razón social actual
    # de la sociedad si fue renombrada.
    denominacion: str = ""
    denominacion_original: str = ""
    tags: Tags = Field(default_factory=Tags)

    @field_validator("fecha_publicado", mode="before")
    @classmethod
    def _parsear_fecha(cls, v: Any) -> Any:
        if isinstance(v, str) and _FECHA_API.match(v):
            return datetime.strptime(v, "%d-%m-%Y").date()
        return v

    @field_validator("asuntos", mode="before")
    @classmethod
    def _limpiar_asuntos(cls, v: Any) -> Any:
        # La API deja espacios al final (p. ej. "AUMENTO DE CAPITAL CON REFORMA ").
        if isinstance(v, list):
            return [a.strip() for a in v if isinstance(a, str) and a.strip()]
        return v


class Sociedad(_Base):
    """Una sociedad y todos sus avisos, ordenados por fecha."""

    razon_social: str
    tipo: str = ""                     # SA, SAS, SRL, COMERCIALES, ...
    total_avisos: int = 0
    avisos: list[Aviso] = Field(default_factory=list)

    @classmethod
    def desde_api(cls, crudo: dict[str, Any]) -> "Sociedad":
        """Construye la sociedad desde el objeto del timeline (aplana `items` -> `avisos`)."""
        avisos = [a for item in crudo.get("items", []) for a in item.get("avisos", [])]
        return cls(
            razon_social=crudo.get("razon_social", ""),
            tipo=crudo.get("tipo", ""),
            total_avisos=crudo.get("total_avisos", len(avisos)),
            avisos=sorted(
                (Aviso.model_validate(a) for a in avisos),
                key=lambda a: (a.fecha_publicado, a.id_aviso),
            ),
        )

    def nombres(self) -> set[str]:
        """Todos los nombres con que figura la sociedad (razón social actual y denominaciones)."""
        nombres = {self.razon_social}
        for a in self.avisos:
            nombres.update((a.denominacion, a.denominacion_original))
        return {n for n in nombres if n}

    def aviso(self, id_aviso: str) -> Optional[Aviso]:
        return next((a for a in self.avisos if a.id_aviso == id_aviso), None)

    def contiene(self, id_aviso: str) -> bool:
        return self.aviso(id_aviso) is not None

    def avisos_antes_de(self, fecha: date) -> list[Aviso]:
        """Avisos publicados estrictamente antes de `fecha`."""
        return [a for a in self.avisos if a.fecha_publicado < fecha]


class Busqueda(_Base):
    """Resultado de buscar una sociedad por nombre."""

    consulta: str                      # nombre pedido por el llamador
    consulta_enviada: str              # variante del nombre con la que se obtuvo este resultado
    estado: Estado
    # Sociedades que coinciden con el nombre. 1 si ENCONTRADA; más de 1 si AMBIGUA
    # (salvo que se haya resuelto por id de aviso); vacío en los demás estados.
    sociedades: list[Sociedad] = Field(default_factory=list)
    n_devueltas: int = 0               # sociedades que devolvió la API antes de filtrar
    n_coincidentes: int = 0            # sociedades que coincidían antes de resolver por id
    # Nombres devueltos por la API cuando ninguna coincidió (para diagnosticar).
    candidatas: list[str] = Field(default_factory=list)

    @property
    def sociedad(self) -> Optional[Sociedad]:
        """La sociedad, si hay exactamente una."""
        return self.sociedades[0] if len(self.sociedades) == 1 else None

    def contiene(self, id_aviso: str) -> bool:
        return any(s.contiene(id_aviso) for s in self.sociedades)
