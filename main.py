import argparse

from application.jobs.closest_coordinate_job import ClosestCoordinateJob
from application.jobs.dispatch_job import DispatchJob
from application.jobs.fixed_range_job import FixedRangeJob
from infrastructure.fmtrack_client import FMTrackClient
from infrastructure.luca_client import LucaClient
from logging_config import configure_logging


def add_provider_arguments(parser: argparse.ArgumentParser) -> None:

    parser.add_argument(
        "--provider",
        choices=["fmtrack", "luca"],
        default="fmtrack",
        help="Fuente de datos GPS a utilizar (default: fmtrack).",
    )
    parser.add_argument(
        "--luca-empresa",
        type=int,
        help="ID de empresa en LUCA (requerido si --provider luca).",
    )
    parser.add_argument(
        "--luca-ruta",
        type=int,
        help="ID de ruta en LUCA (requerido si --provider luca).",
    )


def add_workers_argument(parser: argparse.ArgumentParser) -> None:

    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Tramos resueltos en paralelo (default: 8).",
    )


def build_client(args: argparse.Namespace):

    if args.provider == "luca":

        if args.luca_empresa is None or args.luca_ruta is None:
            raise SystemExit("--luca-empresa y --luca-ruta son requeridos con --provider luca.")

        return LucaClient(empresa=args.luca_empresa, ruta=args.luca_ruta)

    return FMTrackClient()


def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(prog="main.py")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "fixed-range",
        help="Aplica un mismo rango de fechas a un listado simple (RUC/CODIGO_RUTA/PLACA/IMEI).",
    )
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    add_workers_argument(p)
    add_provider_arguments(p)

    p = sub.add_parser(
        "closest-coordinate",
        help="[legacy] Busca la coordenada mas cercana a un timestamp por fila.",
    )
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--batch-size", type=int, default=1000)
    p.add_argument("--batch-delay", type=int, default=10)
    add_provider_arguments(p)

    p = sub.add_parser(
        "despachos",
        help="Obtiene los despachos de una empresa/ruta desde LUCA_Backend por rango de fechas y resuelve sus track points con el proveedor GPS elegido (reemplaza operational/partition-split/pipeline).",
    )
    p.add_argument("--luca-empresa", type=int, required=True)
    p.add_argument("--luca-ruta", type=int, required=True)
    p.add_argument("--start", required=True, help="Fecha inicio (YYYY-MM-DD).")
    p.add_argument("--end", required=True, help="Fecha fin (YYYY-MM-DD).")
    p.add_argument("--output", required=True)
    p.add_argument(
        "--provider",
        choices=["fmtrack", "luca"],
        default="fmtrack",
        help="Fuente de datos GPS para resolver los track points (default: fmtrack). Los despachos siempre se obtienen de LUCA_Backend.",
    )
    add_workers_argument(p)

    return parser


def main(argv: list[str] | None = None) -> None:

    configure_logging()

    args = build_parser().parse_args(argv)

    if args.command == "despachos":
        dispatch_client = LucaClient(empresa=args.luca_empresa, ruta=args.luca_ruta)
        track_client = dispatch_client if args.provider == "luca" else FMTrackClient()
        try:
            DispatchJob(dispatch_client, track_client, max_workers=args.workers).run(
                fecha_inicio=args.start,
                fecha_fin=args.end,
                output_file=args.output,
            )
        finally:
            dispatch_client.close()
            if track_client is not dispatch_client:
                track_client.close()
        return

    client = build_client(args)

    try:

        if args.command == "fixed-range":
            FixedRangeJob(client, max_workers=args.workers).run(
                input_file=args.input,
                output_file=args.output,
                start_date=args.start,
                end_date=args.end,
            )

        elif args.command == "closest-coordinate":
            ClosestCoordinateJob(
                client,
                batch_size=args.batch_size,
                batch_delay=args.batch_delay,
            ).run(
                input_file=args.input,
                output_file=args.output,
            )

    finally:

        client.close()


if __name__ == "__main__":
    main()
