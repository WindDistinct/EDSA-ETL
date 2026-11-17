"""CLI: arma los clientes según los argumentos y delega en application/commands.py."""

import argparse
from contextlib import ExitStack, closing

from application import commands
from application.run_trips import RunReport, report_path
from infrastructure.fmtrack_client import FMTrackClient
from infrastructure.luca_client import LucaClient
from logging_config import configure_logging

RANGE_HELP_START = 'Inicio del rango (YYYY-MM-DD o "YYYY-MM-DD HH:MM[:SS]").'
RANGE_HELP_END = 'Fin del rango (YYYY-MM-DD o "YYYY-MM-DD HH:MM[:SS]"; solo fecha = hasta 23:59:59).'


def add_provider_arguments(parser: argparse.ArgumentParser, *, luca_required: bool = False) -> None:

    parser.add_argument(
        "--provider",
        choices=["fmtrack", "luca"],
        default="fmtrack",
        help="Proveedor GPS para resolver los track points (default: fmtrack).",
    )
    parser.add_argument(
        "--luca-empresa",
        type=int,
        required=luca_required,
        help="ID de empresa en LUCA" + ("." if luca_required else " (requerido si --provider luca)."),
    )
    parser.add_argument(
        "--luca-ruta",
        type=int,
        required=luca_required,
        help="ID de ruta en LUCA" + ("." if luca_required else " (requerido si --provider luca)."),
    )


def add_workers_argument(parser: argparse.ArgumentParser) -> None:

    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Viajes resueltos en paralelo (default: 8).",
    )


def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(prog="main.py")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "despachos",
        help="Despachos de una empresa/ruta desde LUCA_Backend por rango de fechas, con sus track points (Excel ATU).",
    )
    p.add_argument("--start", required=True, help=RANGE_HELP_START + " Filtra la hora de los track points.")
    p.add_argument("--end", required=True, help=RANGE_HELP_END)
    p.add_argument("--output", required=True, help="Excel de salida (deja también .csv y _resumen.csv).")
    add_provider_arguments(p, luca_required=True)
    add_workers_argument(p)

    p = sub.add_parser(
        "fixed-range",
        help=(
            "Un mismo rango de fechas para un listado de vehículos: un Excel simple (--input) o, "
            "sin --input, los vehículos de --luca-empresa (Excel ATU)."
        ),
    )
    p.add_argument("--input", help="Excel simple (RUC/CODIGO_RUTA/PLACA/IMEI). Sin él se usan --luca-empresa/--luca-ruta.")
    p.add_argument("--output", required=True, help="Excel de salida (deja también .csv y _resumen.csv).")
    p.add_argument("--start", required=True, help=RANGE_HELP_START)
    p.add_argument("--end", required=True, help=RANGE_HELP_END)
    add_provider_arguments(p)
    add_workers_argument(p)

    p = sub.add_parser(
        "reconsideracion",
        help="Un CSV de trama por viaje del Excel de viajes rechazados (Plantilla_Traza_Reconsideracion).",
    )
    p.add_argument("--input", required=True, help="Excel Reconsideracion_Viajes_Rechazados (N°, Placa, Sentido, H. Inicio, H. Fin).")
    p.add_argument("--output", default="output/reconsideracion", help="Carpeta de salida (default: output/reconsideracion).")
    p.add_argument("--limite", type=int, help="Procesar solo las primeras N filas (prueba).")
    add_provider_arguments(p)
    add_workers_argument(p)

    return parser


def _luca(args: argparse.Namespace) -> LucaClient:

    if args.luca_empresa is None or args.luca_ruta is None:
        raise SystemExit("--luca-empresa y --luca-ruta son requeridos para consultar LUCA.")

    return LucaClient(empresa=args.luca_empresa, ruta=args.luca_ruta)


def _track_client(args: argparse.Namespace, stack: ExitStack, luca: LucaClient | None = None):
    """
    Cliente GPS según --provider. Con --provider luca reutiliza el LucaClient
    que ya se haya abierto para despachos o vehículos.
    """

    if args.provider == "luca":
        return luca or stack.enter_context(closing(_luca(args)))

    return stack.enter_context(closing(FMTrackClient()))


def _print_summary(report: RunReport, resumen: str) -> None:

    print()
    for estado, cantidad in sorted(report.counts().items()):
        print(f"  {estado:<15}{cantidad:>7}")
    print(f"  {'total':<15}{report.total:>7}")
    print(f"\nResumen por viaje: {resumen}")


def main(argv: list[str] | None = None) -> None:

    configure_logging()

    args = build_parser().parse_args(argv)

    with ExitStack() as stack:

        if args.command == "despachos":
            luca = stack.enter_context(closing(_luca(args)))
            report = commands.despachos(
                luca,
                _track_client(args, stack, luca),
                start=args.start,
                end=args.end,
                output=args.output,
                workers=args.workers,
            )
            resumen = report_path(args.output)

        elif args.command == "fixed-range":
            luca = None if args.input else stack.enter_context(closing(_luca(args)))
            report = commands.rango_fijo(
                _track_client(args, stack, luca),
                start=args.start,
                end=args.end,
                output=args.output,
                workers=args.workers,
                input_file=args.input,
                vehicle_source=luca,
                codigo_ruta=args.luca_ruta,
            )
            resumen = report_path(args.output)

        elif args.command == "reconsideracion":
            report = commands.reconsideracion(
                _track_client(args, stack),
                input_file=args.input,
                output_dir=args.output,
                workers=args.workers,
                limite=args.limite,
            )
            resumen = f"{args.output}/_resumen.csv"

    _print_summary(report, str(resumen))


if __name__ == "__main__":
    main()
