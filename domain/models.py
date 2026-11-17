from __future__ import annotations

from dataclasses import dataclass
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
    """
    Un viaje a resolver: una placa y el rango de tiempo cuyos puntos GPS se
    quieren. object_id se resuelve contra el catálogo del proveedor si no
    viene informado.
    """

    placa: str
    date_range: DateRange
    ruc_empresa: str | None = None
    imei: str | None = None
    codigo_ruta: str | None = None
    sentido: Sentido | None = None
    nro_doc_conductor: str | None = None
    object_id: str | None = None
    # Hora real de salida del despacho, cuando date_range fue recortado a una
    # ventana y ya no empieza en la salida. None = usar date_range.start.
    fechora_ini_viaje: datetime | None = None
    # Identificador de la fila de origen (N°, fila del Excel, índice) para
    # reportes y nombres de archivo.
    ref: str | None = None


@dataclass(frozen=True)
class TripOutcome:
    """
    Qué pasó con un viaje. trip es None cuando la fila de origen no llegó a
    formar un viaje válido (FILA_INVALIDA); ref y placa la identifican igual.
    """

    status: TripStatus
    ref: str | None = None
    placa: str | None = None
    trip: Trip | None = None
    points: int = 0
    output: str = ""
    detail: str = ""

    @classmethod
    def of(cls, trip: Trip, status: TripStatus, **kwargs) -> TripOutcome:
        return cls(status=status, ref=trip.ref, placa=trip.placa, trip=trip, **kwargs)
