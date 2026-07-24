# ATU Files Processor

Sistema de procesamiento y transformación de archivos operacionales ATU para generar trazabilidad GPS de recorridos mediante integración con FM Track.

El flujo permite transformar archivos operacionales históricos en documentos enriquecidos con información de vehículos, fechas de tramo y puntos GPS obtenidos desde la API de FM Track.

---

## Objetivo

El objetivo principal es procesar recorridos operacionales y generar un dataset de puntos GPS asociado a:

- Empresa
- Vehículo
- Ruta
- Sentido del recorrido
- Conductor
- Tramo operativo
- Coordenadas GPS históricas

El resultado final permite almacenar y analizar los recorridos realizados por cada vehículo.

---

# Flujo general

El procesamiento está dividido en etapas independientes:

```
Documento operacional
        |
        v
OperationalJob
        |
        v
Documento operacional procesado
        |
        v
PartitionSplitJob
        |
        v
Particiones de procesamiento
        |
        v
PipelineJob (o FixedRangeJob, si el rango es fijo)
        |
        +----------------+
        |                |
        v                v
VehicleCatalog      TripResolver
        |                |
        |                v
        |          API FM Track
        |
        v
TrackRecordWriter
        |
        v
Documento final de Track Points
```

---

# Estructura del proyecto

```
ATU_Files/
│
├── domain/                        # Modelos y reglas puras (sin pandas/httpx/openpyxl)
│   ├── models.py                  # Vehicle, DateRange, TrackPoint, Trip, TrackResult
│   └── rules.py                   # resolve_date_range, format_for_api, parse_boundary, ...
│
├── infrastructure/                 # Adaptadores de I/O
│   ├── fmtrack_client.py          # Cliente HTTP de FM Track
│   ├── excel_io.py                # Helpers de lectura/normalización de Excel
│   └── track_record_writer.py     # Escritura incremental por hoja/día
│
├── application/                    # Orquestación
│   ├── vehicle_catalog.py         # PLACA -> Vehicle (catálogo FM Track)
│   ├── trip_resolver.py           # Resuelve un Trip a sus TrackPoints (con paginación)
│   ├── track_pipeline.py          # Bucle único: mapear -> resolver -> escribir -> resumen
│   └── jobs/
│       ├── fixed_range_job.py     # Un mismo rango de fechas para todo el listado
│       ├── pipeline_job.py        # Fechas propias por fila
│       ├── operational_job.py     # Ida/Vuelta + documento limpio -> documento estándar
│       ├── partition_split_job.py # Divide en N particiones por rango de fecha
│       └── closest_coordinate_job.py  # [legacy] coordenada más cercana a un timestamp
│
├── scripts/                        # Chequeos manuales contra la API real (no son tests)
│   ├── manual_check_objects.py
│   └── manual_check_coordinate.py
│
├── tests/                          # pytest, sin red (usa un FakeFMTrackClient)
│
├── input/
│   ├── documento_operacional.xlsx
│   └── documento_limpio.xlsx
│
├── output/
│   ├── documento_operacional_procesado.xlsx
│   ├── partitions/
│   └── trackpoints/
│
├── config.py
├── logging_config.py
├── main.py                         # CLI (argparse, un subcomando por job)
└── README.md
```

---

# Fuentes de datos

## Documento operacional

Archivo origen generado por ATU.

Contiene:

- Fecha del despacho
- Hora inicio
- Placa
- Conductor
- Estado del viaje
- Último punto real
- Último punto calculado
- Sentido del recorrido

Tiene dos hojas:

- `Ida`
- `Vuelta`

La aplicación las unifica utilizando:

| Valor | Descripción |
| ----- | ----------- |
| 0     | Ida         |
| 1     | Vuelta      |

---

## Documento limpio

Documento base utilizado para obtener metadata.

Se utiliza para:

- Obtener RUC empresa
- Obtener código de ruta
- Obtener relación:

```
PLACA -> IMEI
```

El `OBJECT_ID` no proviene del documento limpio.

Este dato se obtiene consultando FM Track utilizando la placa.

---

# Etapa 1: Procesamiento operacional

Clase:

```
application/jobs/operational_job.py
```

Responsabilidades:

- Leer hojas Ida/Vuelta
- Normalizar columnas
- Generar `FECHORA_INI_VIAJE`
- Convertir fechas de último punto
- Extraer documento del conductor
- Agregar IMEI según placa
- Agregar RUC y ruta
- Generar documento estándar para procesamiento posterior

Salida:

```
documento_operacional_procesado.xlsx
```

Formato:

| Campo                          | Descripción                |
| ------------------------------ | -------------------------- |
| RUC_EMPRESA                    | Empresa operadora          |
| PLACA                          | Identificador del vehículo |
| IMEI                           | Identificador GPS          |
| CODIGO_RUTA                    | Ruta operacional           |
| FECHORA_INI_VIAJE              | Inicio del tramo           |
| FECHA_HORA_FIN_TRAMO           | Fin real                   |
| FECHA_HORA_FIN_TRAMO_CALCULADA | Fin calculado              |
| SENTIDO                        | Ida/Vuelta                 |
| NRO_DOC_CONDUCTOR              | Documento conductor        |

---

# Etapa 2: Particionado

Clase:

```
application/jobs/partition_split_job.py
```

Responsabilidad:

Dividir grandes archivos en bloques manejables.

Actualmente genera 4 particiones simétricas basadas en rango temporal.

Ejemplo:

```
part_01_2026-06-03_2026-06-15.xlsx
part_02_2026-06-15_2026-06-25.xlsx
part_03_2026-06-25_2026-07-05.xlsx
part_04_2026-07-05_2026-07-15.xlsx
```

Cada archivo conserva:

- Columnas originales
- Orden temporal
- Registros completos

---

# Etapa 3: Resolución de vehículos FM Track

Antes de consultar coordenadas se obtiene el catálogo:

```
PLACA -> OBJECT_ID
```

Ejemplo:

```json
{
  "A0P736": {
    "object_id": "53625cee-2df2-11f1-833b-af5c1df1550e",
    "imei": "863238075031916",
    "credential": "default"
  }
}
```

El `OBJECT_ID` es requerido por FM Track para consultar posiciones.

---

# Etapa 4: Obtención de Track Points

Clase:

```
application/trip_resolver.py
```

Responsabilidades:

- Recibir un tramo operacional
- Resolver fechas
- Consultar coordenadas FM Track
- Manejar paginación
- Enriquecer puntos GPS

Consulta utilizada:

```
GET /objects/{objectId}/coordinates
```

Parámetros:

- object_id
- from_datetime
- to_datetime
- continuation_token
- limit

---

## Paginación

FM Track devuelve máximo:

```
1000 puntos por página
```

El procesador maneja automáticamente:

```
Página 1
    |
    v
continuation_token
    |
    v
Página 2
    |
    v
...
```

Ejemplo:

```
[object_id]
Página 1: 1000 puntos
Página 2: 1000 puntos
Página 3: 524 puntos

Total: 2524 puntos
```

---

# Etapa 5: Escritura de resultados

Clase:

```
infrastructure/track_record_writer.py
```

Responsabilidad:

Guardar resultados incrementalmente.

Formato:

```
trackpoints_part_01.xlsx
```

Estructura:

```
Hoja:
2026-06-03

2026-06-04

2026-06-05
```

Cada hoja corresponde a un día.

Columnas:

| Campo             |
| ----------------- |
| RUC_EMPRESA       |
| PLACA             |
| IMEI              |
| CODIGO_RUTA       |
| FECHORA_INI_VIAJE |
| FECHA_HORA_TRACK  |
| LATITUD           |
| LONGITUD          |
| VELOCIDAD         |
| SENTIDO           |
| NRO_DOC_CONDUCTOR |

---

# Ejecución

El CLI expone un subcomando por job (`python main.py <comando> --ayuda` para ver sus argumentos):

```bash
# Etapa 1: unir Ida/Vuelta con el documento limpio
python main.py operational --operational-file input/documento_operacional.xlsx --clean-file input/documento_limpio.xlsx --output output/documento_operacional_procesado.xlsx

# Etapa 2: particionar el documento procesado
python main.py partition-split --input output/documento_operacional_procesado.xlsx --output-folder output/partitions --partitions 4

# Etapa 3-5: resolver vehículos + track points por partición (fechas propias por fila)
python main.py pipeline --input output/partitions/part_01_*.xlsx --output output/trackpoints_part_01.xlsx

# Alternativa: un mismo rango de fechas fijo para todo un listado simple
python main.py fixed-range --input input/listado.xlsx --output output/trackpoints.xlsx --start "2026-07-06 14:00:00" --end "2026-07-12 22:43:00"

# Legacy: coordenada más cercana a un timestamp por fila
python main.py closest-coordinate --input input/listado.xlsx --output output/resultado.xlsx
```

---

# Dependencias

Instalar (runtime):

```bash
pip install -r requirements.txt
```

Instalar (desarrollo, incluye pytest):

```bash
pip install -r requirements-dev.txt
```

Principales librerías:

- pandas
- openpyxl
- httpx
- python-dotenv

---

# Tests

```bash
python -m pytest
```

Los tests en `tests/` no hacen red: usan un `FakeFMTrackClient` (ver `tests/conftest.py`).

Los scripts en `scripts/` sí pegan contra la API real de FM Track y son solo para chequeos manuales (requieren un `.env` válido); no los ejecuta pytest.

---

# Consideraciones técnicas

## Volumen de datos

El sistema está diseñado para trabajar con grandes cantidades de puntos GPS.

Ejemplo:

- 1000 vehículos
- 1 punto cada 10 segundos

Puede superar:

```
150 millones registros / mes
```

Por ello:

- El procesamiento está particionado.
- La escritura es incremental.
- No se mantienen todos los puntos en memoria.

---

## Manejo de errores

Cada tramo se procesa individualmente.

Un fallo en un vehículo no detiene todo el lote.

Ejemplo:

```
[ERROR] A0P736 -> No existe fecha final
```

El procesamiento continúa con el siguiente tramo.

---

# Próximas mejoras previstas

- Procesamiento paralelo de particiones.
- Reintentos automáticos ante errores FM Track.
- Control de progreso.
- Optimización para procesamiento batch masivo.
- Eliminación de campos temporales antes de exportación final.
