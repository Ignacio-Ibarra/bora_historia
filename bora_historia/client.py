"""Cliente del timeline del BORA (https://timeline.boletinoficial.gob.ar/).

El timeline no tiene API JSON: se replica el POST del formulario de búsqueda y se
extrae el literal `const societies = [...]` del HTML de respuesta.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from typing import Any, Callable, Optional

import requests

from bora_historia.errors import RespuestaInesperada, TimelineError
from bora_historia.models import Busqueda, Estado, HistorialPrevio, Sociedad
from bora_historia.nombres import coincide, variantes_consulta

BASE_URL = "https://timeline.boletinoficial.gob.ar/"

# Tope de sociedades que devuelve el timeline por búsqueda (observado, no documentado).
# Si llega al tope y la sociedad no aparece, el resultado es TRUNCADA y no NO_ENCONTRADA.
TOPE_RESULTADOS = 100

_MAX_CANDIDATAS = 10
_TIPOS = ("society", "person", "text")
_SOCIETIES = re.compile(r"const\s+societies\s*=\s*")
_RANGO = {Estado.NO_ENCONTRADA: 0, Estado.TRUNCADA: 1, Estado.AMBIGUA: 2, Estado.ENCONTRADA: 3}


def extraer_sociedades(html: str) -> list[dict[str, Any]]:
    """Extrae el literal `const societies = [...]` de la respuesta."""
    m = _SOCIETIES.search(html)
    if not m:
        raise RespuestaInesperada(f"No se encontró 'const societies' en la respuesta: {html[:200]!r}")
    try:
        valor, _ = json.JSONDecoder().raw_decode(html, m.end())
    except json.JSONDecodeError as exc:
        raise RespuestaInesperada(f"'const societies' no es JSON válido: {exc}") from exc
    if not isinstance(valor, list):
        raise RespuestaInesperada("'const societies' no es una lista")
    return valor


def _nombres_crudos(sociedad: dict[str, Any]) -> set[str]:
    nombres = {sociedad.get("razon_social", "")}
    for item in sociedad.get("items", []):
        for a in item.get("avisos", []):
            nombres.update((a.get("denominacion", ""), a.get("denominacion_original", "")))
    return {n for n in nombres if n}


def construir_busqueda(
    consulta: str,
    consulta_enviada: str,
    devueltas: list[dict[str, Any]],
    id_aviso: Optional[str] = None,
) -> Busqueda:
    """Filtra lo que devolvió la API a las sociedades que coinciden y determina el estado.

    Una sociedad coincide si algún nombre suyo (razón social actual o la denominación de
    cualquiera de sus avisos) coincide con `consulta`: las sociedades renombradas figuran
    bajo su razón social nueva pero sus avisos viejos conservan el nombre original.
    """
    coincidentes = [
        Sociedad.desde_api(s)
        for s in devueltas
        if any(coincide(consulta, n) for n in _nombres_crudos(s))
    ]
    n_coincidentes = len(coincidentes)

    if n_coincidentes > 1 and id_aviso:
        con_el_aviso = [s for s in coincidentes if s.contiene(id_aviso)]
        if len(con_el_aviso) == 1:
            coincidentes = con_el_aviso

    if len(coincidentes) == 1:
        estado = Estado.ENCONTRADA
    elif len(coincidentes) > 1:
        estado = Estado.AMBIGUA
    elif len(devueltas) >= TOPE_RESULTADOS:
        estado = Estado.TRUNCADA
    else:
        estado = Estado.NO_ENCONTRADA

    return Busqueda(
        consulta=consulta,
        consulta_enviada=consulta_enviada,
        estado=estado,
        sociedades=coincidentes,
        n_devueltas=len(devueltas),
        n_coincidentes=n_coincidentes,
        candidatas=[] if coincidentes else [s.get("razon_social", "") for s in devueltas[:_MAX_CANDIDATAS]],
    )


class TimelineClient:
    """Cliente con pausa entre consultas y reintentos ante errores de red o 5xx."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        timeout: float = 60,
        min_intervalo: float = 0.5,
        max_reintentos: int = 3,
        backoff: float = 1.0,
        session: Optional[requests.Session] = None,
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.min_intervalo = min_intervalo
        self.max_reintentos = max_reintentos
        self.backoff = backoff
        self._dormir = dormir
        self._reloj = reloj
        self._ultima: Optional[float] = None
        self._session = session or requests.Session()
        if session is None:
            self._session.headers.update({
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"),
                "Referer": base_url,
                "Origin": base_url.rstrip("/"),
            })

    # -- búsquedas tipadas ----------------------------------------------

    def buscar_sociedad(self, nombre: str, *, id_aviso: Optional[str] = None) -> Busqueda:
        """Busca UNA sociedad por su nombre y devuelve el resultado con un estado explícito.

        Prueba las `variantes_consulta` del nombre hasta que una devuelva una sociedad
        que coincida. Si `id_aviso` está, sirve para resolver homónimos: entre varias
        sociedades que coinciden se queda con la que contiene ese aviso.
        """
        mejor: Optional[Busqueda] = None
        for variante in variantes_consulta(nombre):
            resultado = construir_busqueda(nombre, variante, self.consultar("society", variante), id_aviso)
            if resultado.estado in (Estado.ENCONTRADA, Estado.AMBIGUA):
                return resultado
            if mejor is None or _RANGO[resultado.estado] > _RANGO[mejor.estado]:
                mejor = resultado
        assert mejor is not None  # variantes_consulta siempre devuelve al menos una
        return mejor

    def avisos_previos(
        self, nombre: str, antes_de: date, *, id_aviso: Optional[str] = None
    ) -> HistorialPrevio:
        """Avisos de una sociedad anteriores a `antes_de`: lo que se ve el día que sale un aviso nuevo.

        Es `buscar_sociedad` más el filtro por fecha, con el resultado de tres valores de
        `HistorialPrevio.tiene_previos` (True, False o None si no hay datos). Si hay homónimos
        y no se pasa `id_aviso` (el día D no existe todavía), devuelve la unión de las candidatas
        marcando `ambigua`: puede dar una falsa alarma, pero no oculta una historia real.
        """
        busqueda = self.buscar_sociedad(nombre, id_aviso=id_aviso)
        return HistorialPrevio.desde_busqueda(busqueda, antes_de)

    def buscar_persona(self, identificacion: str) -> list[Sociedad]:
        """Sociedades en cuyos avisos figura una persona, por CUIT o DNI."""
        return [Sociedad.desde_api(s) for s in self.consultar("person", identificacion)]

    def buscar_texto(self, texto: str, *, max_length: Optional[int] = None) -> list[Sociedad]:
        """Sociedades con avisos que contienen `texto` (búsqueda de texto libre del timeline)."""
        return [Sociedad.desde_api(s) for s in self.consultar("text", texto, max_length=max_length)]

    # -- consulta sin interpretar ---------------------------------------

    def consultar(self, tipo: str, texto: str, *, max_length: Optional[int] = None) -> list[dict[str, Any]]:
        """Consulta el timeline y devuelve la lista `societies` tal como la entrega, sin filtrar.

        `tipo`: "society" (nombre o CUIT de la sociedad; admite comodín `*`),
        "person" (CUIT o DNI de una persona) o "text" (texto libre).
        `max_length`: parámetro del formulario que limita el largo de los resultados.
        """
        if tipo not in _TIPOS:
            raise ValueError(f"tipo debe ser uno de {_TIPOS}")
        data = {
            "searchtext_type": tipo,
            "searchtext_society": texto if tipo == "society" else "",
            "searchtext_person": texto if tipo == "person" else "",
            "searchtext_text": texto if tipo == "text" else "",
        }
        if max_length:
            data["max_length"] = str(max_length)
        return extraer_sociedades(self._post(data))

    # -- HTTP -----------------------------------------------------------

    def _esperar(self) -> None:
        if self._ultima is not None:
            faltan = self.min_intervalo - (self._reloj() - self._ultima)
            if faltan > 0:
                self._dormir(faltan)
        self._ultima = self._reloj()

    def _post(self, data: dict[str, str]) -> str:
        ultimo: Optional[Exception] = None
        for intento in range(self.max_reintentos + 1):
            self._esperar()
            try:
                if not self._session.cookies:
                    self._session.get(self.base_url, timeout=self.timeout)
                r = self._session.post(self.base_url, data=data, timeout=self.timeout)
                if r.status_code >= 500:
                    raise TimelineError(f"HTTP {r.status_code}")
                if r.status_code >= 400:
                    raise _ErrorCliente(f"HTTP {r.status_code}")
                if "charset" not in r.headers.get("Content-Type", "").lower():
                    r.encoding = "utf-8"
                return r.text
            except _ErrorCliente as exc:
                raise TimelineError(str(exc)) from exc  # un 4xx no se arregla reintentando
            except (requests.RequestException, TimelineError) as exc:
                ultimo = exc
                if intento < self.max_reintentos:
                    self._dormir(self.backoff * 2 ** intento)
        raise TimelineError(f"El timeline no respondió tras {self.max_reintentos + 1} intentos: {ultimo}") from ultimo


class _ErrorCliente(Exception):
    """4xx: no se reintenta."""
