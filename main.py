import argparse

from application.jobs.closest_coordinate_job import ClosestCoordinateJob
from application.jobs.fixed_range_job import FixedRangeJob
from application.jobs.luca_dispatch_job import LucaDispatchJob
from application.jobs.operational_job import OperationalJob
from application.jobs.partition_split_job import PartitionSplitJob
from application.jobs.pipeline_job import PipelineJob
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
    add_provider_arguments(p)

    p = sub.add_parser(
        "pipeline",
        help="Procesa tramos con fechas propias por fila (ya calculadas por operational/partition-split).",
    )
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    add_provider_arguments(p)

    p = sub.add_parser(
        "operational",
        help="Une un documento operacional (Ida/Vuelta) con un documento limpio.",
    )
    p.add_argument("--operational-file", required=True)
    p.add_argument("--clean-file", required=True)
    p.add_argument("--output", required=True)

    p = sub.add_parser(
        "partition-split",
        help="Divide un documento de tramos grande en N particiones por rango de fecha.",
    )
    p.add_argument("--input", required=True)
    p.add_argument("--output-folder", required=True)
    p.add_argument("--partitions", type=int, default=4)

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
        "luca-despachos",
        help="Obtiene los despachos de una empresa/ruta de LUCA por rango de fechas y resuelve sus track points (reemplaza operational/partition-split/pipeline para clientes LUCA).",
    )
    p.add_argument("--luca-empresa", type=int, required=True)
    p.add_argument("--luca-ruta", type=int, required=True)
    p.add_argument("--start", required=True, help="Fecha inicio (YYYY-MM-DD).")
    p.add_argument("--end", required=True, help="Fecha fin (YYYY-MM-DD).")
    p.add_argument("--output", required=True)

    return parser


def main(argv: list[str] | None = None) -> None:

    configure_logging()

    args = build_parser().parse_args(argv)

    if args.command == "operational":
        OperationalJob().run(
            operational_file=args.operational_file,
            clean_file=args.clean_file,
            output_file=args.output,
        )
        return

    if args.command == "partition-split":
        PartitionSplitJob(partitions=args.partitions).run(
            input_file=args.input,
            output_folder=args.output_folder,
        )
        return

    if args.command == "luca-despachos":
        client = LucaClient(empresa=args.luca_empresa, ruta=args.luca_ruta)
        try:
            LucaDispatchJob(client).run(
                fecha_inicio=args.start,
                fecha_fin=args.end,
                output_file=args.output,
            )
        finally:
            client.close()
        return

    client = build_client(args)

    try:

        if args.command == "fixed-range":
            FixedRangeJob(client).run(
                input_file=args.input,
                output_file=args.output,
                start_date=args.start,
                end_date=args.end,
            )

        elif args.command == "pipeline":
            PipelineJob(client).run(
                input_file=args.input,
                output_file=args.output,
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
