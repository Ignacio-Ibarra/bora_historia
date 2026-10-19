import argparse
import json
import sys
from datetime import date
from typing import Optional, Sequence

from bora_historia.client import TimelineClient
from bora_historia.errors import TimelineError


def _imprimir(datos) -> None:
    print(json.dumps(datos, ensure_ascii=False, indent=2))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bora-historia", description="Consultas al timeline del BORA")
    sub = parser.add_subparsers(dest="comando", required=True)

    def comando(nombre: str, ayuda: str) -> argparse.ArgumentParser:
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("--crudo", action="store_true",
                       help="Imprime la respuesta del timeline sin filtrar ni interpretar")
        return p

    p = comando("sociedad", "Busca una sociedad por nombre")
    p.add_argument("nombre", help='Nombre de la sociedad, p. ej. "TRIVEXA S.A."')
    p.add_argument("--id-aviso", default=None, help="Id de un aviso de la sociedad, para resolver homónimos")

    p = sub.add_parser("previos", help="Avisos de una sociedad anteriores a una fecha (lo que se ve el día D)")
    p.add_argument("nombre", help='Nombre de la sociedad, p. ej. "TRIVEXA S.A."')
    p.add_argument("--antes-de", required=True, type=date.fromisoformat, metavar="AAAA-MM-DD",
                   help="Fecha del aviso nuevo; se listan los avisos publicados antes")
    p.add_argument("--id-aviso", default=None, help="Id de un aviso de la sociedad, para resolver homónimos")

    p = comando("persona", "Sociedades donde figura una persona")
    p.add_argument("identificacion", help="CUIT o DNI de la persona")

    p = comando("texto", "Sociedades con avisos que contienen un texto")
    p.add_argument("texto", help="Texto libre a buscar")
    p.add_argument("--max-length", type=int, default=None, help="Límite de largo de los resultados (ej. 5000)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # la consola de Windows no siempre es UTF-8

    cliente = TimelineClient()
    try:
        if args.comando == "sociedad":
            if args.crudo:
                _imprimir(cliente.consultar("society", args.nombre))
            else:
                _imprimir(cliente.buscar_sociedad(args.nombre, id_aviso=args.id_aviso).model_dump(mode="json"))
        elif args.comando == "previos":
            _imprimir(cliente.avisos_previos(args.nombre, args.antes_de, id_aviso=args.id_aviso).model_dump(mode="json"))
        elif args.comando == "persona":
            if args.crudo:
                _imprimir(cliente.consultar("person", args.identificacion))
            else:
                _imprimir([s.model_dump(mode="json") for s in cliente.buscar_persona(args.identificacion)])
        else:
            if args.crudo:
                _imprimir(cliente.consultar("text", args.texto, max_length=args.max_length))
            else:
                _imprimir([s.model_dump(mode="json")
                           for s in cliente.buscar_texto(args.texto, max_length=args.max_length)])
    except TimelineError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
