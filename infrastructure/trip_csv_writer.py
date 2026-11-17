from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from domain.models import TrackPoint, Trip

HEADER = ["latitud", "longitud", "timestamp", "velocidad", "sentido"]


class TripCsvWriter:
    """
    Sink de un CSV por viaje (formato de Plantilla_Traza_Reconsideracion):

        {ref}_{PLACA}_{YYYYMMDD_HHMMSS}.csv
        latitud,longitud,timestamp,velocidad,sentido

    El timestamp del nombre es el del primer punto. Reanudable: un viaje con
    archivo previo ({ref}_{PLACA}_*.csv) no se vuelve a consultar.
    """

    def __init__(self, out_dir: str | Path) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def existing(self, trip: Trip) -> str | None:
        found = next(self.out_dir.glob(f"{trip.ref}_{trip.placa}_*.csv"), None)
        return found.name if found else None

    def write(self, trip: Trip, points: list[TrackPoint]) -> str:

        points = sorted(points, key=lambda p: p.datetime)

        first = datetime.fromisoformat(points[0].datetime)

        path = self.out_dir / f"{trip.ref}_{trip.placa}_{first:%Y%m%d_%H%M%S}.csv"

        sentido = trip.sentido.letra if trip.sentido else ""

        # Se escribe a .tmp y se renombra: un corte a medias no deja un CSV
        # incompleto que la próxima corrida tomaría como ya generado.
        tmp = path.with_suffix(".tmp")

        with tmp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(HEADER)
            for p in points:
                writer.writerow([p.latitude, p.longitude, p.datetime.replace("T", " "), p.speed, sentido])

        tmp.replace(path)

        return path.name
