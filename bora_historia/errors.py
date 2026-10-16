class TimelineError(Exception):
    """Error al consultar el timeline del BORA."""


class RespuestaInesperada(TimelineError):
    """La respuesta no tiene la estructura esperada (`const societies = [...]`)."""
