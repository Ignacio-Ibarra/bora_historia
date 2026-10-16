"""Respuestas sintéticas con el mismo formato que el timeline del BORA."""
import json

import pytest
import requests


def aviso(id_aviso, fecha, asuntos=("ESTATUTO",), denominacion="ACME S.A.", denominacion_original=None):
    """Aviso en formato timeline. `fecha` es dd-mm-YYYY."""
    return {
        "accion": "CONSTITUCION SA",
        "asuntos": list(asuntos),
        "denominacion": denominacion,
        "denominacion_original": denominacion_original or denominacion,
        "fecha_desde": fecha,
        "fecha_hasta": fecha,
        "fecha_publicado": fecha,
        "id_aviso": id_aviso,
        "id_rubro": 1110,
        "nuevo": True,
        "rubro": "CONSTITUCION SA",
        "tags": {"cuit": [], "dni": [], "firmante": ["una persona"], "integrante": []},
    }


def sociedad(razon_social, avisos, tipo="SA", indice=1):
    """Sociedad en formato timeline: un item por fecha, como lo entrega la API."""
    return {
        "indice": indice,
        "items": [
            {"avisos": [a], "fecha_desde": a["fecha_publicado"], "fecha_hasta": a["fecha_publicado"]}
            for a in avisos
        ],
        "razon_social": razon_social,
        "tipo": tipo,
        "total_avisos": len(avisos),
    }


def html(sociedades):
    return f"<html><script>\nconst societies = {json.dumps(sociedades)};\n</script></html>"


class FakeResponse:
    def __init__(self, text, status=200, content_type="text/html; charset=utf-8"):
        self.text = text
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.encoding = None


class FakeSession:
    """Sesión falsa. `por_consulta` mapea el texto buscado a la lista de sociedades
    que devuelve; `acciones` es una cola de respuestas o excepciones que se
    consumen primero (para simular fallos)."""

    def __init__(self, por_consulta=None, acciones=None):
        self.por_consulta = por_consulta or {}
        self.acciones = list(acciones or [])
        self.cookies = {"sesion": "1"}
        self.headers = {}
        self.posts = []

    def get(self, url, timeout=None):
        return FakeResponse("")

    def post(self, url, data=None, timeout=None):
        self.posts.append(data)
        if self.acciones:
            accion = self.acciones.pop(0)
            if isinstance(accion, Exception):
                raise accion
            return accion
        texto = data["searchtext_society"] or data["searchtext_person"] or data["searchtext_text"]
        return FakeResponse(html(self.por_consulta.get(texto, [])))


class Reloj:
    """Reloj y `dormir` falsos: dormir avanza el tiempo, sin esperar de verdad."""

    def __init__(self):
        self.t = 0.0
        self.pausas = []

    def __call__(self):
        return self.t

    def dormir(self, segundos):
        self.pausas.append(segundos)
        self.t += segundos


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def cliente(reloj):
    """Fábrica de clientes con una sesión falsa y sin esperas reales."""
    from bora_historia import TimelineClient

    def _crear(session, **kw):
        kw.setdefault("min_intervalo", 0)
        return TimelineClient(session=session, dormir=reloj.dormir, reloj=reloj, **kw)

    return _crear


ConnectionError_ = requests.ConnectionError
