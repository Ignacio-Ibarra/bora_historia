# bora_historia

Cliente del [timeline del Boletín Oficial](https://timeline.boletinoficial.gob.ar/) (BORA):
dada una sociedad, devuelve su **historia de avisos** ordenada por fecha, con la
clasificación (`asuntos`) y los datos (`tags`) que el timeline asigna a cada aviso.

Es independiente de `bora_pipeline`, `bora_parser` y `bora_wrapper`: no los importa ni
depende de ellos. Pensado para crecer con más consultas sobre el timeline.

## Principio de diseño

El paquete entrega **hechos**, no decisiones. No dice "este aviso es una rectificación":
dice qué avisos tiene la sociedad y de qué tipo son, y quien lo consume decide. Esto
importa porque el timeline tiene huecos y errores (ver "Particularidades") y la misma
historia significa cosas distintas según el caso de uso.

## Instalación

```
uv add "bora-historia @ git+https://github.com/Ignacio-Ibarra/bora_historia"
```

Para desarrollar: `uv sync` y `uv run pytest`.

## Uso

```python
from datetime import date
from bora_historia import Estado, TimelineClient

cliente = TimelineClient()
r = cliente.buscar_sociedad("TRIVEXA S.A.", id_aviso="A1535314")

if r.estado is Estado.ENCONTRADA:
    sociedad = r.sociedad
    previos = sociedad.avisos_antes_de(date(2026, 10, 13))   # estrictamente anteriores
    print([(a.id_aviso, a.asuntos) for a in previos])        # [('A1534865', ['ESTATUTO'])]
```

## Operaciones

El timeline admite tres tipos de búsqueda, y cada uno tiene su método y su subcomando:

| Método | Subcomando | Devuelve |
|---|---|---|
| `buscar_sociedad(nombre, *, id_aviso=None)` | `bora-historia sociedad "TRIVEXA S.A." [--id-aviso A1535314]` | `Busqueda` (con estado explícito) |
| `avisos_previos(nombre, antes_de, *, id_aviso=None)` | `bora-historia previos "TRIVEXA S.A." --antes-de 2026-10-13` | `HistorialPrevio`: los avisos anteriores a la fecha (ver "El día D") |
| `buscar_persona(cuit_o_dni)` | `bora-historia persona 20123456789` | `list[Sociedad]` donde figura la persona |
| `buscar_texto(texto, *, max_length=None)` | `bora-historia texto "fusion por absorcion" [--max-length 5000]` | `list[Sociedad]` con avisos que contienen el texto |
| `consultar(tipo, texto, *, max_length=None)` | `--crudo` en cualquiera de los tres | la lista `societies` tal como la entrega el timeline |

Los subcomandos imprimen JSON. `--crudo` imprime la respuesta sin filtrar ni interpretar
(útil para inspeccionar qué devuelve el timeline). `tipo` es `"society"`, `"person"` o `"text"`.

## Contrato de `buscar_sociedad`

`TimelineClient.buscar_sociedad(nombre, *, id_aviso=None) -> Busqueda`

| `Busqueda.estado` | Significado |
|---|---|
| `encontrada` | Exactamente una sociedad coincide. Está en `.sociedad`. |
| `ambigua` | Varias coinciden (homónimos). Con `id_aviso` se resuelve si solo una contiene ese aviso. |
| `truncada` | La API devolvió el tope de resultados (100) y la sociedad no aparece: no se puede saber si existe. |
| `no_encontrada` | La API no devolvió ninguna sociedad que coincida. `.candidatas` lista los nombres devueltos. |

**`no_encontrada` y `truncada` no equivalen a "sin historia".** Pueden ser un nombre
que la API no resuelve, o un aviso muy reciente que todavía no está indexado. Quien
consume decide qué hacer con cada motivo.

Modelos (`pydantic`, inmutables):

- `Sociedad`: `razon_social`, `tipo`, `total_avisos`, `avisos` (cronológicos);
  `.nombres()`, `.aviso(id)`, `.contiene(id)`, `.avisos_antes_de(fecha)`.
- `Aviso`: `id_aviso`, `fecha_publicado` (`date`), `rubro`, `accion`, `asuntos`,
  `denominacion`, `denominacion_original`, `tags`.
- `Tags`: `cuit`, `dni`, `direccion_sociedad`, `fecha_constitucion`, `firmante`,
  `integrante`, `integrante_renunciante`, `objeto_social`, `autoridad_designada`.

`buscar_persona` y `buscar_texto` devuelven `Sociedad` sin filtrar por nombre (no hay nombre
contra el cual comparar): es lo que el timeline devuelva para esa búsqueda.

## El día D: `avisos_previos`

El timeline recibe los avisos con un día de retraso: el día que se publica un aviso, todavía
no figura en la historia de su sociedad. Lo que se puede saber ese día es qué avisos tenía
**antes**, y eso alcanza para sospechar de un aviso: por ejemplo, un "aviso de constitución"
de una sociedad que ya tiene un `ESTATUTO` publicado no puede ser su constitución.

```python
h = TimelineClient().avisos_previos("TRIVEXA S.A.", date(2026, 10, 13))
h.tiene_previos        # True
h.avisos               # [Aviso(A1534865, 2026-10-09, ['ESTATUTO'])]
```

`HistorialPrevio.tiene_previos` tiene **tres valores**, y la diferencia importa:

| Valor | Significa |
|---|---|
| `True` | La sociedad tiene al menos un aviso anterior a la fecha. |
| `False` | Se encontró la sociedad y no tiene avisos anteriores. |
| `None` | **Sin datos**: no se encontró (o la búsqueda se truncó). No equivale a "sin historia": puede ser una sociedad nueva, o un nombre que la API no resuelve. |

Además trae `estado`, `razones_sociales` y `ambigua`, y se serializa con todo eso
(`model_dump_json()`).

**Homónimos.** El día D no hay `id_aviso` con el cual elegir entre dos sociedades que se
llaman igual, así que, si `ambigua` es `True`, `avisos` es la **unión** de las candidatas. Eso
puede dar una falsa alarma (un homónimo viejo hace parecer que la sociedad nueva tiene
historia), pero nunca oculta una historia real, y las falsas alarmas son baratas.

Simulado el día D sobre ~1270 avisos reales: 4 (0,3%) tenían homónimos; unirlos sumó 3
falsas alarmas y no se perdió ninguno de los 10 avisos mal etiquetados que se buscaban.
Pasando el `id_aviso` (cuando se lo conoce, p. ej. en un análisis posterior) se resuelve el
homónimo y la falsa alarma desaparece.

**Qué no hace.** No decide si un aviso es constitución o modificación: entrega la historia y
quien la usa decide. Tampoco distingue una sociedad nueva de un nombre no resuelto cuando da
`None`.

## Particularidades del timeline

Descubiertas analizando ~1300 avisos reales. El paquete las maneja, pero conviene conocerlas.

- **Las búsquedas son amplias.** "F&C SERVICIOS S.A.S." devolvió 82 sociedades. Se filtra a
  las que realmente coinciden (sin distinguir mayúsculas, tildes ni puntuación).
- **Sociedades renombradas.** La API agrupa bajo la razón social *actual*; los avisos viejos
  conservan el nombre original. Por eso se comparan la razón social y la denominación de cada aviso.
- **Homónimos.** Otra sociedad puede tener, o haber tenido, el mismo nombre. La identidad no
  se puede basar solo en el nombre; usar `id_aviso` cuando se lo conoce.
- **Guiones y la palabra "AND".** "FULL-ARG S.A.S." devuelve 100 sociedades sin la buscada, pero
  "FULL ARG S.A.S." devuelve una. "SPIRITS AND CORP" devuelve 0 y "SPIRITS & CORP" la encuentra.
  `buscar` prueba las variantes (`variantes_consulta`) hasta que una coincide.
- **Tope de 100 resultados** por búsqueda (observado, no documentado).
- **El aviso del día no está.** Los avisos aparecen en el timeline con un día de retraso, así
  que la historia del día D llega hasta D-1.
- **Faltan avisos.** Se observó un día (18/09/2026) con 5 de 16 avisos ausentes.
- **`asuntos` no es verdad absoluta.** Se observó `CONTRATO` en complementarios de SRL. Los avisos
  históricos (id con prefijo `H`) vienen con `asuntos` vacío.

## Tests

```
uv run pytest
```

Usan respuestas sintéticas con el mismo formato del timeline y una sesión HTTP falsa: no
hacen consultas reales ni esperan entre reintentos.
