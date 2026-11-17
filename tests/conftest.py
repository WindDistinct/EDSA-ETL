from __future__ import annotations

from domain.models import DateRange, TrackPoint, Vehicle


class FakeTrackProvider:
    """
    Doble de prueba de un TrackProvider (FMTrackClient / LucaClient). No hace red.

    tracks: dict[object_id, list[TrackPoint]] -- puntos que devuelve fetch_track.
    errors: dict[object_id, Exception]        -- fetch_track lanza esa excepción.
    ranges: registra el DateRange consultado por cada object_id.
    """

    def __init__(
        self,
        objects: dict[str, Vehicle] | None = None,
        tracks: dict[str, list[TrackPoint]] | None = None,
        errors: dict[str, Exception] | None = None,
    ):
        self._objects = objects or {}
        self._tracks = tracks or {}
        self._errors = errors or {}
        self.ranges: dict[str, DateRange] = {}

    def get_objects(self) -> dict[str, Vehicle]:
        return dict(self._objects)

    def fetch_track(self, object_id: str, date_range: DateRange) -> list[TrackPoint]:
        self.ranges[object_id] = date_range
        if object_id in self._errors:
            raise self._errors[object_id]
        return list(self._tracks.get(object_id, []))


def vehicle(plate: str, object_id: str | None = None, imei: str = "863238075031916", credential: str = "default") -> Vehicle:
    return Vehicle(plate=plate, object_id=object_id or f"obj-{plate}", imei=imei, credential=credential)


def point(dt: str, lat: float = -12.0, lon: float = -77.0, speed: float = 10.0, ignition: str | None = "ON") -> TrackPoint:
    return TrackPoint(datetime=dt, latitude=lat, longitude=lon, speed=speed, ignition_status=ignition)
