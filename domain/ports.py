"""Contratos que la aplicación espera de la infraestructura."""

from __future__ import annotations

from typing import Protocol

from domain.models import DateRange, TrackPoint, Trip, Vehicle


class TrackProvider(Protocol):
    """
    Fuente de puntos GPS (FM Track, LUCA_Backend). La paginación, las
    credenciales y el formato de la API quedan dentro de cada adaptador.
    """

    def get_objects(self) -> dict[str, Vehicle]:
        """Catálogo de vehículos indexado por placa."""
        ...

    def fetch_track(self, object_id: str, date_range: DateRange) -> list[TrackPoint]:
        """
        Todos los puntos del objeto dentro del rango, con datetime en hora
        local de Lima (ISO 8601 sin zona, a segundos).
        """
        ...


class TripSink(Protocol):
    """
    Destino de los puntos de cada viaje (Excel/CSV consolidado, un CSV por
    viaje, ...). Solo se llama desde un hilo.
    """

    def existing(self, trip: Trip) -> str | None:
        """Lo que ya se escribió para este viaje en una corrida anterior, o None."""
        ...

    def write(self, trip: Trip, points: list[TrackPoint]) -> str:
        """Escribe los puntos y devuelve dónde quedaron (nombre de archivo)."""
        ...
