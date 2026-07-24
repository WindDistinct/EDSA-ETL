from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Vehicle:
    plate: str
    object_id: str
    imei: str
    credential: str


@dataclass(frozen=True)
class DateRange:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("end must not be before start")


@dataclass(frozen=True)
class TrackPoint:
    datetime: str
    latitude: float | None
    longitude: float | None
    speed: float | None
    ignition_status: str | None = None


@dataclass(frozen=True)
class Trip:
    ruc_empresa: str | None
    placa: str | None
    imei: str | None
    codigo_ruta: str | None
    sentido: str | None
    nro_doc_conductor: str | None
    object_id: str
    date_range: DateRange


@dataclass(frozen=True)
class TrackResult:
    trip: Trip
    points: list[TrackPoint] = field(default_factory=list)
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None
