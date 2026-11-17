from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, StrEnum


class Sentido(Enum):
    """
    Sentido del recorrido. Cada destino lo pide distinto: ATU como código
    (0/1), la plantilla de reconsideración como letra (I/V) y los Excel
    operacionales como texto (IDA/VUELTA).
    """

    IDA = "IDA"
    VUELTA = "VUELTA"

    @property
    def codigo(self) -> int:
        return 0 if self is Sentido.IDA else 1

    @property
    def letra(self) -> str:
        return self.value[0]

    @classmethod
    def parse(cls, value: object) -> Sentido:
        """
        Acepta IDA/VUELTA, I/V (cualquier capitalización) o los códigos 0/1.
        Lanza ValueError con cualquier otro valor.
        """

        if isinstance(value, Sentido):
            return value

        text = str(value).strip().upper() if value is not None else ""

        aliases = {
            "IDA": cls.IDA, "I": cls.IDA, "0": cls.IDA,
            "VUELTA": cls.VUELTA, "V": cls.VUELTA, "1": cls.VUELTA,
        }

        try:
            return aliases[text]
        except KeyError:
            raise ValueError(f"Sentido inválido: {value!r}") from None

    @classmethod
    def try_parse(cls, value: object) -> Sentido | None:
        try:
            return cls.parse(value)
        except ValueError:
            return None


class TripStatus(StrEnum):
    """
    Resultado de procesar un viaje. El valor es lo que se escribe en los
    reportes (_resumen.csv).
    """

    OK = "ok"
    EXISTENTE = "existente"
    SIN_PUNTOS = "sin_puntos"
    SIN_OBJECT_ID = "sin_object_id"
    ERROR = "error"
    FILA_INVALIDA = "fila_invalida"


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
    # Hora real de salida del despacho, cuando date_range fue recortado a una
    # ventana y ya no empieza en la salida. None = usar date_range.start.
    fechora_ini_viaje: datetime | None = None


@dataclass(frozen=True)
class TrackResult:
    trip: Trip
    points: list[TrackPoint] = field(default_factory=list)
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None
