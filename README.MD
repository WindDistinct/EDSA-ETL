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

Toda corrida tiene la misma forma: una **fuente** arma los viajes, `run_trips` los resuelve contra un
**proveedor GPS** y los entrega a un **sink** que los escribe. Al final queda un reporte con el estado de
cada viaje.

```
Fuente                         Proveedor GPS (TrackProvider)       Sink (TripSink)
------                         -----------------------------       ---------------
despachos_luca (LUCA)          FMTrackClient  (--provider fmtrack) TrackRecordWriter (Excel ATU + CSV "|")
rango_fijo (listado)           LucaClient     (--provider luca)    TripCsvWriter     (un CSV por viaje)
reconsideracion (Excel)
        |                                   ^                               ^
        v                                   |                               |
   list[Trip | TripOutcome]  ---->  application/run_trips.py  --------------+
                                    - catálogo PLACA -> object_id (get_objects)
                                    - fetch_track en paralelo (--workers)
                                    - escritura en un solo hilo
                                    - RunReport: estado por viaje -> <salida>_resumen.csv
```

El despacho (qué placa salió, cuándo, con qué conductor) siempre viene de LUCA_Backend, sin importar el
proveedor de GPS de la empresa. `--provider` solo decide con qué cliente se resuelven los puntos GPS.
Ambos clientes implementan el mismo contrato (`domain/ports.py`: `get_objects()` / `fetch_track()`), así
que `run_trips` es idéntico sin importar el proveedor — para `--provider luca`, `dispatch_client` y
`track_client` son literalmente la misma instancia de `LucaClient`.

Estados posibles de un viaje en el reporte (`TripStatus`):

| Estado          | Significado                                                                 |
| --------------- | --------------------------------------------------------------------------- |
| `ok`            | Tiene puntos y se escribió.                                                 |
| `sin_puntos`    | El proveedor respondió, pero no hay puntos en ese rango.                    |
| `sin_object_id` | La placa no está en el catálogo del proveedor GPS.                          |
| `error`         | La consulta falló después de los reintentos (detalle en `DETALLE`).         |
| `fila_invalida` | La fila de origen no forma un viaje válido (fechas o sentido inválidos).    |
| `existente`     | El sink ya tenía ese viaje de una corrida anterior (solo `TripCsvWriter`).  |

---

# Estructura del proyecto

```
EDSA-ETL/
│
├── domain/                        # Modelos y reglas puras (sin pandas/httpx/openpyxl)
│   ├── models.py                  # Vehicle, DateRange, TrackPoint, Trip, TripOutcome, Sentido, TripStatus
│   ├── ports.py                   # Contratos TrackProvider y TripSink
│   ├── rules.py                   # format_for_api, to_local_isoformat, parse_boundary
│   ├── horas.py                   # Reglas de horas escritas a mano (parse_hora, cruce de medianoche, recorte)
│   └── tiempo.py                  # LOCAL_TZ (America/Lima) y to_local
│
├── infrastructure/                 # Adaptadores de I/O
│   ├── fmtrack_client.py          # FM Track: catálogo multi-key, fetch_track con paginación
│   ├── luca_client.py             # LUCA_Backend (/reportes): despachos, vehículos, fetch_track
│   ├── http_retry.py              # Reintentos con backoff exponencial, Retry-After y RateGate
│   ├── excel_io.py                # Helpers de lectura/normalización de Excel
│   ├── track_record_writer.py     # Sink ATU: Excel (hoja por día) + CSV "|"
│   └── trip_csv_writer.py         # Sink de un CSV por viaje (plantilla de reconsideración)
│
├── application/                    # Orquestación
│   ├── run_trips.py               # Bucle único: catálogo -> fetch en paralelo -> sink -> RunReport
│   ├── commands.py                # Un caso de uso por subcomando: fuente + proveedor + sink
│   └── sources/                   # Arman la lista de viajes (Trip | TripOutcome)
│       ├── despachos_luca.py      # Despachos de LUCA_Backend (y el parseo de su formato)
│       ├── rango_fijo.py          # Un mismo rango para un listado (Excel o vehículos de LUCA)
│       └── reconsideracion.py     # Excel de viajes rechazados
│
├── scripts/                        # Utilidades y flujos puntuales (ver docstring de cada uno)
│   ├── despachos_tramas.py        # Cruce de despachos manuales con un Excel de tramas
│   ├── recuperar_omitidos.py      # Recupera despachos omitidos corregidos a mano
│   ├── xlsx_to_csv.py / xlsx_formatear.py / unir_hojas.py
│   └── manual_check_objects.py    # Chequeo manual contra la API real (no es un test)
│
├── tests/                          # pytest, sin red (FakeTrackProvider y httpx.MockTransport)
├── input/  output/                 # (ignorados por git)
├── config.py
├── logging_config.py               # Logging + filtro que oculta api_key
├── main.py                         # CLI (argparse, un subcomando por job)
└── README.MD
```

---

# Fuente de datos: despachos en LUCA_Backend

El comando `despachos` obtiene los tramos a resolver directo de LUCA_Backend — ya no hace falta ningún
Excel de ATU (ni "documento operacional" ni "documento limpio"). El despacho es un dato de negocio que
vive en LUCA_Backend independientemente de qué proveedor de GPS use la empresa para el tracking.

`application/sources/despachos_luca.py` convierte cada despacho en un `Trip`. Un despacho sin
salida o sin hora de último punto queda en el reporte como `fila_invalida`:

| Columna interna                  | Campo de la API LUCA          | Transformación                                    |
| --------------------------------- | ------------------------------ | --------------------------------------------------- |
| RUC_EMPRESA                       | `ruc_empresa`                  | directo                                              |
| PLACA                              | `placa`                         | `.strip()`                                           |
| IMEI                               | —                                | vacío; lo completa `run_trips` desde el catálogo del `track_client` |
| CODIGO_RUTA                       | `codigo_ruta`                   | directo                                              |
| FECHORA_INI_VIAJE                 | `fecha` + `hora`                | combinación directa                                  |
| FECHA_HORA_FIN_TRAMO              | `hora_real_ultimo_punto`        | `despachos_luca.parse_operational_datetime`          |
| FECHA_HORA_FIN_TRAMO_CALCULADA    | `hora_calculada_ultimo_punto`   | `despachos_luca.parse_operational_datetime`          |
| SENTIDO                           | `sentido`                       | `Sentido.parse` → `IDA`/`VUELTA` (ATU: 0/1)          |
| NRO_DOC_CONDUCTOR                 | `conductor`                     | `despachos_luca.extract_driver_document`             |

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

- `POST /reportes/obtener_imeis_vehiculos` — `{"empresa": <id>}` → IMEI de todas las placas de esa empresa. Se llama una sola vez por corrida (equivalente a `GET /objects` de FM Track) y alimenta el fallback de IMEI en `run_trips`. También es el origen del listado de vehículos de `fixed-range` cuando se omite `--input` (no filtra por ruta ni devuelve RUC/nombre de ruta, por eso `rango_fijo` completa `CODIGO_RUTA` con el `--luca-ruta` recibido y deja `RUC_EMPRESA` vacío).
- `POST /reportes/generar_reporte_puntos_gps` — `{"empresa": <id>, "ruta": <id>, "placa": "...", "fecha": "YYYY-MM-DD"}` → puntos GPS continuos (`latitude`, `longitude`, `speed`, `timestamp_ms`) de esa placa en ese día calendario (hora Lima), ordenados. `LucaClient` llama este endpoint una vez por cada día distinto que toque el rango del tramo y combina los resultados. Solo se usa cuando `track_client` es `LucaClient` (`--provider luca`).
- `POST /reportes/generar_reporte_despachos` — `{"empresa": <id>, "ruta": <id>, "fecha_inicio": "YYYY-MM-DD", "fecha_fin": "YYYY-MM-DD"}` → listado plano de despachos (placa, hora, conductor, sentido, hora real/calculada del último punto) de esa empresa/ruta en el rango. Es el origen de despachos del comando `despachos`, sin importar el `--provider` elegido para el GPS.

## Limitaciones conocidas

- Los puntos GPS continuos de LUCA (`generar_reporte_puntos_gps`) solo existen para empresas/rutas habilitadas en el flujo automático/ATU de LUCA_Tracking; el resto de placas devuelve 0 puntos (no es un error, simplemente no hay tracking continuo para ese despacho). No aplica cuando el GPS se resuelve con `--provider fmtrack`.
- No hay paginación en estos endpoints (v1): se asume volumen bajo por placa/día (cientos a pocos miles de puntos) y por empresa/ruta/rango de fechas (`generar_reporte_despachos` no tiene tope de rango en v1 — rangos de meses/años podrían crecer bastante).
- `generar_reporte_despachos` excluye siempre los despachos con `estado == "anulado"` (nunca salieron a ruta, no tienen GPS que resolver).

---

# Obtención de Track Points

Cada proveedor implementa `fetch_track(object_id, date_range) -> list[TrackPoint]`
(`infrastructure/fmtrack_client.py`, `infrastructure/luca_client.py`): la paginación, las credenciales y
el formato de la API quedan dentro del adaptador. Los `TrackPoint` salen con la hora en Lima.

Consulta utilizada en FM Track:

```
GET /objects/{objectId}/coordinates
```

Parámetros:

- object_id
- from_datetime / to_datetime (ISO 8601 con offset de Lima, `-05:00`)
- continuation_token
- limit

FM Track tiene dos API keys (`FMTRACK_API_KEY`, `FMTRACK_API_KEY_INTER`). `get_objects()` combina los
vehículos de todas las que respondan (una key que falla se omite con un aviso) y cada vehículo se
consulta solo con la key con la que se listó.

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

El CLI expone un subcomando por caso de uso (`python main.py <comando> --help` para ver sus argumentos):
`despachos`, `fixed-range` y `reconsideracion`. Todos dejan un resumen por viaje.

## Comando principal: `despachos` (sin Excels de ATU)

Reemplaza el flujo manual anterior (`operational` → `partition-split` → `pipeline`) en un solo paso: pide
el listado de despachos directo a `/reportes/generar_reporte_despachos` en LUCA_Backend y lo resuelve con
`run_trips` (`application/commands.py::despachos`). Junto al Excel de salida queda
`<salida>_resumen.csv` con el estado de cada despacho.

| Flag             | Default   | Descripción                                                        |
| ---------------- | --------- | --------------------------------------------------------------------- |
| `--luca-empresa` | —         | ID de empresa en LUCA. **Siempre requerido** (origen de despachos).  |
| `--luca-ruta`    | —         | ID de ruta en LUCA. **Siempre requerido** (origen de despachos).     |
| `--start`        | —         | Inicio del rango: `YYYY-MM-DD` o `"YYYY-MM-DD HH:MM[:SS]"`.           |
| `--end`          | —         | Fin del rango: `YYYY-MM-DD` (hasta 23:59:59) o `"YYYY-MM-DD HH:MM[:SS]"`. |
| `--output`       | —         | Excel de salida.                                                       |
| `--provider`     | `fmtrack` | Proveedor de GPS para resolver los track points: `fmtrack` o `luca`.  |
| `--workers`      | `8`       | Tramos resueltos en paralelo.                                          |

```bash
# Despachos + track points de un cliente que trackea con FM Track (default)
python main.py despachos --luca-empresa 10 --luca-ruta 6 --start 2026-08-01 --end 2026-08-07 --output output/trackpoints.xlsx

# Lo mismo, pero resolviendo el GPS también desde LUCA_Backend
python main.py despachos --luca-empresa 10 --luca-ruta 6 --start 2026-08-01 --end 2026-08-07 --output output/trackpoints.xlsx --provider luca

# Solo los track points entre las 06:00 y las 12:00 del 1 de agosto
python main.py despachos --luca-empresa 10 --luca-ruta 6 --start "2026-08-01 06:00" --end "2026-08-01 12:00" --output output/trackpoints.xlsx
```

El rango filtra la hora de los **track points**, no la de salida del despacho: cada tramo se consulta
solo en su intersección con `[--start, --end]`, y los tramos que no se cruzan con el rango se descartan
antes de consultar el GPS. `FECHORA_INI_VIAJE` en la salida sigue siendo la hora real de salida. Como
LUCA_Backend filtra despachos por día calendario, se piden desde el día anterior a `--start` para no perder
tramos que cruzan la medianoche hacia el rango.

Antes de correrlo, confirmar en `.env` que `LUCA_BASE_URL` apunta al backend correcto (ej. `http://127.0.0.1:5000/` si LUCA_Backend corre local) y que `LUCA_API_KEY` coincide con el `API_KEY_BACKEND` vigente en el `.env` de LUCA_Backend — si cambian uno de los dos y no el otro, falla con `API Key inválida`.

## Otros comandos

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
| `--workers`      | `8`       | Viajes resueltos en paralelo.                                                 |

```bash
# Un mismo rango de fechas fijo para todo un listado simple (FM Track)
python main.py fixed-range --input input/listado.xlsx --output output/trackpoints.xlsx --start "2026-07-06 14:00:00" --end "2026-07-12 22:43:00"

# Lo mismo con el Excel, pero resolviendo el GPS desde LUCA
python main.py fixed-range --input input/listado.xlsx --output output/trackpoints.xlsx --start "2026-07-06 14:00:00" --end "2026-07-12 22:43:00" --provider luca --luca-empresa 10 --luca-ruta 6

# Sin Excel: listado de vehículos directo de LUCA (empresa/ruta), tracking por FM Track (default)
python main.py fixed-range --output output/trackpoints.xlsx --start "2026-07-06 14:00:00" --end "2026-07-12 22:43:00" --luca-empresa 10 --luca-ruta 6
```

## `reconsideracion`: un CSV por viaje rechazado

Lee el Excel `Reconsideracion_Viajes_Rechazados` (columnas `N°`, `RUC`, `Placa`, `Ruta`, `Sentido`,
`H. Inicio`, `H. Fin`, fechas `dd/mm/yyyy HH:MM:SS`) y escribe en la carpeta de salida un CSV por viaje
con el formato de `Plantilla_Traza_Reconsideracion.csv`:

```
{N}_{PLACA}_{YYYYMMDD_HHMMSS}.csv        (timestamp del primer punto GPS del viaje)
latitud,longitud,timestamp,velocidad,sentido
-12.0750933,-77.1165316,2026-10-20 10:34:17,32,V
```

El sentido va como letra (`IDA` → `I`, `VUELTA` → `V`) y no se filtra por ignición. Los viajes sin puntos
o con error no generan archivo; quedan en `_resumen.csv` dentro de la misma carpeta. Es reanudable: al
volver a correrlo se saltan los `N°` que ya tienen CSV (estado `existente`) y solo se reintentan los que
faltan.

| Flag         | Default                   | Descripción                                          |
| ------------ | ------------------------- | ---------------------------------------------------- |
| `--input`    | —                         | Excel de viajes rechazados.                          |
| `--output`   | `output/reconsideracion`  | Carpeta de salida.                                   |
| `--limite`   | —                         | Procesar solo las primeras N filas (prueba).         |
| `--provider` | `fmtrack`                 | Proveedor GPS (`luca` requiere `--luca-empresa/--luca-ruta`). |
| `--workers`  | `8`                       | Viajes resueltos en paralelo.                        |

```bash
python main.py reconsideracion --input "input/Reconsideracion_Viajes_Rechazados_1794927644146 - 0.xlsx"

# Prueba con las primeras 10 filas en otra carpeta
python main.py reconsideracion --input input/rechazados.xlsx --output output/prueba --limite 10
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
| `FMTRACK_API_KEY_INTER`  | `FMTrackClient`    | API key secundaria; sus vehículos se suman al catálogo. Vacía = no se usa. |
| `LUCA_BASE_URL`          | `LucaClient`       | URL base de LUCA_Backend (ej. `http://127.0.0.1:5000/`). |
| `LUCA_API_KEY`           | `LucaClient`       | Debe coincidir con `API_KEY_BACKEND` de LUCA_Backend.    |

---

# Tests

```bash
python -m pytest
```

Los tests en `tests/` no hacen red: usan un `FakeTrackProvider` (ver `tests/conftest.py`) o
`httpx.MockTransport` para los clientes HTTP.

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

El procesamiento continúa con el siguiente tramo y cada fallo queda en `<salida>_resumen.csv` con su
estado y detalle (ver [estados](#flujo-general)).

Ante errores transitorios de red (timeouts, conexión caída, HTTP 429/5xx), cada llamada a FM Track o
LUCA_Backend se reintenta hasta 5 veces con backoff exponencial (1, 2, 4, 8 s, con variación aleatoria),
respetando la cabecera `Retry-After`. Ante un 429, todos los workers hacen una misma pausa
(`RateGate`) en vez de seguir consultando cada uno por su cuenta (`infrastructure/http_retry.py`).

Las API keys de FM Track viajan como query param: los errores de `FMTrackClient` no incluyen la URL y
`logging_config.py` oculta cualquier `api_key=...` que llegue a un log.

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
