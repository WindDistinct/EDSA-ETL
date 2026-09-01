# ATU Files Processor

Sistema de generación de trazabilidad GPS de recorridos a partir de los despachos ya registrados en
LUCA_Backend, resolviendo sus puntos GPS mediante FM Track o mediante el propio LUCA_Backend.

El comando principal (`despachos`) obtiene el listado de despachos (placa, hora, conductor, sentido) directo
de `/reportes/generar_reporte_despachos` en LUCA_Backend — ya no hace falta ningún Excel operacional de
ATU — y resuelve sus puntos GPS con el proveedor que se elija vía `--provider` (`fmtrack` o `luca`).

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

El comando principal (`despachos`) separa dos fuentes de datos independientes:

```
LUCA_Backend
/reportes/generar_reporte_despachos
        |
        v
DispatchJob  (dispatch_client: siempre LucaClient)
        |
        v
Tramos (placa, hora, conductor, sentido)
        |
        v
TrackPipeline
        |
        +----------------+
        |                |
        v                v
VehicleCatalog      TripResolver
        |                |
        |                v
        |     FMTrackClient o LucaClient   (track_client)
        |     (--provider fmtrack | luca)
        |                |
        |          API FM Track o
        |          /reportes de LUCA_Backend
        |
        v
TrackRecordWriter
        |
        v
Documento final de Track Points
```

El despacho (qué placa salió, cuándo, con qué conductor) siempre viene de LUCA_Backend, sin importar el
proveedor de GPS de la empresa. `--provider` solo decide con qué cliente se resuelven los puntos GPS de
esos despachos. `VehicleCatalog` y `TripResolver` no saben qué proveedor están usando: ambos clientes
(`FMTrackClient`, `LucaClient`) implementan la misma interfaz (`get_objects()` / `get_object_coordinates()`),
así que el resto del pipeline es idéntico sin importar el `--provider` elegido — para `--provider luca`,
`dispatch_client` y `track_client` son literalmente la misma instancia de `LucaClient`.

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
│   ├── luca_client.py             # Cliente HTTP de LUCA_Backend (/reportes)
│   ├── excel_io.py                # Helpers de lectura/normalización de Excel
│   └── track_record_writer.py     # Escritura incremental por hoja/día
│
├── application/                    # Orquestación
│   ├── vehicle_catalog.py         # PLACA -> Vehicle (catálogo FM Track o LUCA) + fallback de IMEI
│   ├── trip_resolver.py           # Resuelve un Trip a sus TrackPoints (con paginación)
│   ├── track_pipeline.py          # Bucle único: mapear -> resolver -> escribir -> resumen
│   └── jobs/
│       ├── dispatch_job.py        # Despachos (LUCA_Backend) + track points en un solo paso
│       ├── fixed_range_job.py     # Un mismo rango de fechas para todo un listado simple
│       └── closest_coordinate_job.py  # [legacy] coordenada más cercana a un timestamp
│
├── scripts/                        # Chequeos manuales contra la API real (no son tests)
│   ├── manual_check_objects.py
│   └── manual_check_coordinate.py
│
├── tests/                          # pytest, sin red (usa un FakeFMTrackClient)
│
├── input/
│   └── listado.xlsx                # solo para fixed-range / closest-coordinate
│
├── output/
│   └── trackpoints/
│
├── config.py
├── logging_config.py
├── main.py                         # CLI (argparse, un subcomando por job)
└── README.md
```

---

# Fuente de datos: despachos en LUCA_Backend

El comando `despachos` obtiene los tramos a resolver directo de LUCA_Backend — ya no hace falta ningún
Excel de ATU (ni "documento operacional" ni "documento limpio"). El despacho es un dato de negocio que
vive en LUCA_Backend independientemente de qué proveedor de GPS use la empresa para el tracking.

`DispatchJob` arma internamente el mismo formato de fila que antes producía el Excel operacional,
reutilizando los helpers ya existentes de `domain/rules.py`:

| Columna interna                  | Campo de la API LUCA          | Transformación                                    |
| --------------------------------- | ------------------------------ | --------------------------------------------------- |
| RUC_EMPRESA                       | `ruc_empresa`                  | directo                                              |
| PLACA                              | `placa`                         | `.strip()`                                           |
| IMEI                               | —                                | vacío; lo completa `VehicleCatalog` con el `track_client` elegido |
| CODIGO_RUTA                       | `codigo_ruta`                   | directo                                              |
| FECHORA_INI_VIAJE                 | `fecha` + `hora`                | combinación directa                                  |
| FECHA_HORA_FIN_TRAMO              | `hora_real_ultimo_punto`        | `domain.rules.parse_operational_datetime`            |
| FECHA_HORA_FIN_TRAMO_CALCULADA    | `hora_calculada_ultimo_punto`   | `domain.rules.parse_operational_datetime`            |
| SENTIDO                           | `sentido`                       | `"ida"→0, "vuelta"→1`                                |
| NRO_DOC_CONDUCTOR                 | `conductor`                     | `domain.rules.extract_driver_document`               |

---

# Resolución de vehículos

Antes de consultar coordenadas se obtiene el catálogo:

```
PLACA -> OBJECT_ID
```

Ejemplo (FM Track):

```json
{
  "A0P736": {
    "object_id": "53625cee-2df2-11f1-833b-af5c1df1550e",
    "imei": "863238075031916",
    "credential": "default"
  }
}
```

El `OBJECT_ID` es requerido por el proveedor de tracking (`track_client`) para consultar posiciones. Con
FM Track es un UUID propio del objeto; con LUCA, la placa se reutiliza como `object_id` (LUCA direcciona
vehículos por placa, no por un ID de dispositivo separado).

---

# LUCA_Backend

`infrastructure/luca_client.py` (`LucaClient`) cumple dos roles:

- **`dispatch_client`**: siempre — provee `get_dispatch_records()`, el origen de despachos del comando
  `despachos` (ver [sección dedicada](#comando-principal-despachos-sin-excels-de-atu)).
- **`track_client`**: solo cuando se elige `--provider luca` — reemplazo directo de `FMTrackClient` para
  resolver puntos GPS, para empresas cuyos vehículos ya trackean dentro del ecosistema LUCA
  (LUCA_Tracking → Mongo).

## Requisitos

- El backend de LUCA debe estar accesible con las variables de entorno `LUCA_BASE_URL` y `LUCA_API_KEY` (ver `.env`).
- Se necesita conocer de antemano el `empresa` (int) y `ruta` (int) internos de LUCA — se pasan por CLI (`--luca-empresa`, `--luca-ruta`). Una corrida cubre una sola empresa/ruta a la vez.

## Endpoints usados (LUCA_Backend, módulo `reportes`, solo requieren `x-api-key`)

- `POST /reportes/obtener_imeis_vehiculos` — `{"empresa": <id>}` → IMEI de todas las placas de esa empresa. Se llama una sola vez por corrida (equivalente a `GET /objects` de FM Track) y alimenta el fallback de IMEI en `VehicleCatalog`. También es el origen del listado de vehículos de `fixed-range` cuando se omite `--input` (no filtra por ruta ni devuelve RUC/nombre de ruta, por eso `FixedRangeJob` completa `CODIGO_RUTA` con el `--luca-ruta` recibido y deja `RUC_EMPRESA` vacío).
- `POST /reportes/generar_reporte_puntos_gps` — `{"empresa": <id>, "ruta": <id>, "placa": "...", "fecha": "YYYY-MM-DD"}` → puntos GPS continuos (`latitude`, `longitude`, `speed`, `timestamp_ms`) de esa placa en ese día calendario (hora Lima), ordenados. `LucaClient` llama este endpoint una vez por cada día distinto que toque el rango del tramo y combina los resultados. Solo se usa cuando `track_client` es `LucaClient` (`--provider luca`).
- `POST /reportes/generar_reporte_despachos` — `{"empresa": <id>, "ruta": <id>, "fecha_inicio": "YYYY-MM-DD", "fecha_fin": "YYYY-MM-DD"}` → listado plano de despachos (placa, hora, conductor, sentido, hora real/calculada del último punto) de esa empresa/ruta en el rango. Es el origen de despachos del comando `despachos`, sin importar el `--provider` elegido para el GPS.

## Limitaciones conocidas

- Los puntos GPS continuos de LUCA (`generar_reporte_puntos_gps`) solo existen para empresas/rutas habilitadas en el flujo automático/ATU de LUCA_Tracking; el resto de placas devuelve 0 puntos (no es un error, simplemente no hay tracking continuo para ese despacho). No aplica cuando el GPS se resuelve con `--provider fmtrack`.
- No hay paginación en estos endpoints (v1): se asume volumen bajo por placa/día (cientos a pocos miles de puntos) y por empresa/ruta/rango de fechas (`generar_reporte_despachos` no tiene tope de rango en v1 — rangos de meses/años podrían crecer bastante).
- `generar_reporte_despachos` excluye siempre los despachos con `estado == "anulado"` (nunca salieron a ruta, no tienen GPS que resolver).

---

# Obtención de Track Points

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

# Escritura de resultados

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

El CLI expone un subcomando por job (`python main.py <comando> --help` para ver sus argumentos).

## Comando principal: `despachos` (sin Excels de ATU)

Reemplaza el flujo manual anterior (`operational` → `partition-split` → `pipeline`) en un solo paso: pide
el listado de despachos directo a `/reportes/generar_reporte_despachos` en LUCA_Backend y lo resuelve con
el mismo `TrackPipeline` de siempre. Clase: `application/jobs/dispatch_job.py` (`DispatchJob`).

| Flag             | Default   | Descripción                                                        |
| ---------------- | --------- | --------------------------------------------------------------------- |
| `--luca-empresa` | —         | ID de empresa en LUCA. **Siempre requerido** (origen de despachos).  |
| `--luca-ruta`    | —         | ID de ruta en LUCA. **Siempre requerido** (origen de despachos).     |
| `--start`        | —         | Fecha inicio del rango (`YYYY-MM-DD`).                                |
| `--end`          | —         | Fecha fin del rango (`YYYY-MM-DD`).                                   |
| `--output`       | —         | Excel de salida.                                                       |
| `--provider`     | `fmtrack` | Proveedor de GPS para resolver los track points: `fmtrack` o `luca`.  |
| `--workers`      | `8`       | Tramos resueltos en paralelo.                                          |

```bash
# Despachos + track points de un cliente que trackea con FM Track (default)
python main.py despachos --luca-empresa 10 --luca-ruta 6 --start 2026-08-01 --end 2026-08-07 --output output/trackpoints.xlsx

# Lo mismo, pero resolviendo el GPS también desde LUCA_Backend
python main.py despachos --luca-empresa 10 --luca-ruta 6 --start 2026-08-01 --end 2026-08-07 --output output/trackpoints.xlsx --provider luca
```

Antes de correrlo, confirmar en `.env` que `LUCA_BASE_URL` apunta al backend correcto (ej. `http://127.0.0.1:5000/` si LUCA_Backend corre local) y que `LUCA_API_KEY` coincide con el `API_KEY_BACKEND` vigente en el `.env` de LUCA_Backend — si cambian uno de los dos y no el otro, falla con `API Key inválida`.

## Otros comandos

`closest-coordinate` no depende de despachos de LUCA — trabaja sobre un Excel simple
(`RUC/CODIGO_RUTA/PLACA/IMEI`) y acepta el mismo selector de proveedor GPS.

`fixed-range` aplica un mismo rango de fechas fijo a un listado de vehículos, y admite dos orígenes
para ese listado:

- **Excel** (`--input`): el modo original, un Excel simple `RUC/CODIGO_RUTA/PLACA/IMEI`.
- **LUCA** (sin `--input`): igual que `despachos`, separa el origen del listado (siempre `LucaClient`,
  vía `/reportes/obtener_imeis_vehiculos` con `--luca-empresa`) del proveedor de tracking (`--provider`,
  `FMTrackClient` o `LucaClient`). Ese endpoint no filtra por ruta ni devuelve `RUC_EMPRESA`/nombre de
  ruta, así que `CODIGO_RUTA` se completa con el propio `--luca-ruta` en todas las filas y
  `RUC_EMPRESA` queda vacío.

| Flag             | Default   | Descripción                                                                 |
| ---------------- | --------- | ---------------------------------------------------------------------------- |
| `--input`        | —         | Excel simple. Si se omite, el listado se obtiene de LUCA (requiere los dos flags de abajo). |
| `--provider`     | `fmtrack` | Proveedor de GPS para resolver los track points: `fmtrack` o `luca`.        |
| `--luca-empresa` | —         | ID de empresa en LUCA. Requerido si `--provider luca`, o siempre que se omita `--input`. |
| `--luca-ruta`    | —         | ID de ruta en LUCA. Requerido si `--provider luca`, o siempre que se omita `--input`. |
| `--workers`      | `8`       | Tramos resueltos en paralelo (solo `fixed-range`).                            |

```bash
# Un mismo rango de fechas fijo para todo un listado simple (FM Track)
python main.py fixed-range --input input/listado.xlsx --output output/trackpoints.xlsx --start "2026-07-06 14:00:00" --end "2026-07-12 22:43:00"

# Lo mismo con el Excel, pero resolviendo el GPS desde LUCA
python main.py fixed-range --input input/listado.xlsx --output output/trackpoints.xlsx --start "2026-07-06 14:00:00" --end "2026-07-12 22:43:00" --provider luca --luca-empresa 10 --luca-ruta 6

# Sin Excel: listado de vehículos directo de LUCA (empresa/ruta), tracking por FM Track (default)
python main.py fixed-range --output output/trackpoints.xlsx --start "2026-07-06 14:00:00" --end "2026-07-12 22:43:00" --luca-empresa 10 --luca-ruta 6

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

## Variables de entorno (`.env`)

| Variable                 | Usado por          | Descripción                                              |
| ------------------------ | ------------------ | ---------------------------------------------------------|
| `FMTRACK_BASE_URL`       | `FMTrackClient`    | URL base de la API de FM Track.                          |
| `FMTRACK_API_KEY`        | `FMTrackClient`    | API key principal.                                       |
| `FMTRACK_API_KEY_INTER`  | `FMTrackClient`    | API key secundaria (fallback).                           |
| `LUCA_BASE_URL`          | `LucaClient`       | URL base de LUCA_Backend (ej. `http://127.0.0.1:5000/`). |
| `LUCA_API_KEY`           | `LucaClient`       | Debe coincidir con `API_KEY_BACKEND` de LUCA_Backend.    |

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

- La escritura es incremental (una hoja por día, vía `TrackRecordWriter`).
- No se mantienen todos los puntos en memoria.
- Para rangos muy grandes, correr `despachos` una vez por sub-rango de fechas en vez de un único rango extenso.

---

## Manejo de errores

Cada tramo se procesa individualmente.

Un fallo en un vehículo no detiene todo el lote.

Ejemplo:

```
[ERROR] A0P736 -> No existe fecha final
```

El procesamiento continúa con el siguiente tramo.

Ante errores transitorios de red (timeouts, conexión caída, HTTP 429/5xx), cada llamada a FM Track o
LUCA_Backend se reintenta automáticamente hasta 3 veces con backoff antes de darse por vencida
(`infrastructure/http_retry.py`).

---

# Rendimiento

Los tramos de un mismo lote se resuelven en paralelo contra el proveedor de GPS (`ThreadPoolExecutor`,
`--workers`, default 8) — la escritura al Excel se mantiene en un único hilo. El writer usa el modo
`write_only` de openpyxl para no mantener todas las filas en memoria antes de guardar, pensado para el
volumen descrito en [Volumen de datos](#volumen-de-datos).

```bash
python main.py despachos --luca-empresa 10 --luca-ruta 6 --start 2026-08-01 --end 2026-08-07 --output output/trackpoints.xlsx --workers 16
```

---

# Próximas mejoras previstas

- Eliminación de campos temporales antes de exportación final.
