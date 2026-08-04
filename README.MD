# ATU Files Processor

Sistema de procesamiento y transformación de archivos operacionales ATU para generar trazabilidad GPS de recorridos mediante integración con FM Track o con el backend de LUCA.

El flujo permite transformar archivos operacionales históricos en documentos enriquecidos con información de vehículos, fechas de tramo y puntos GPS obtenidos desde la API de FM Track o, para clientes que ya trackean con LUCA, desde los endpoints de `/reportes` de LUCA_Backend.

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
        |     FMTrackClient o LucaClient
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

`VehicleCatalog` y `TripResolver` no saben qué proveedor están usando: ambos clientes (`FMTrackClient`, `LucaClient`) implementan la misma interfaz (`get_objects()` / `get_object_coordinates()`), así que el resto del pipeline es idéntico sin importar el `--provider` elegido.

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
│       ├── fixed_range_job.py     # Un mismo rango de fechas para todo el listado
│       ├── pipeline_job.py        # Fechas propias por fila
│       ├── operational_job.py     # Ida/Vuelta + documento limpio -> documento estándar
│       ├── partition_split_job.py # Divide en N particiones por rango de fecha
│       ├── closest_coordinate_job.py  # [legacy] coordenada más cercana a un timestamp
│       └── luca_dispatch_job.py   # LUCA: despachos + track points en un solo paso (sin Excels de ATU)
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

# Proveedor alternativo: LUCA_Backend

Para clientes que no usan FM Track, pero cuyos vehículos ya se trackean dentro del ecosistema LUCA (LUCA_Tracking → Mongo), existe `infrastructure/luca_client.py` como reemplazo directo de `FMTrackClient`. Se activa con `--provider luca` (ver [Ejecución](#ejecución)).

## Requisitos

- El backend de LUCA debe estar accesible con las variables de entorno `LUCA_BASE_URL` y `LUCA_API_KEY` (ver `.env`).
- Se necesita conocer de antemano el `empresa` (int) y `ruta` (int) internos de LUCA para el cliente — no se resuelven desde `RUC_EMPRESA`/`CODIGO_RUTA` del Excel, se pasan por CLI (`--luca-empresa`, `--luca-ruta`). Una corrida cubre una sola empresa/ruta a la vez.

## Endpoints usados (LUCA_Backend, módulo `reportes`, solo requieren `x-api-key`)

- `POST /reportes/obtener_imeis_vehiculos` — `{"empresa": <id>}` → IMEI de todas las placas de esa empresa. Se llama una sola vez por corrida (equivalente a `GET /objects` de FM Track) y alimenta el fallback de IMEI en `VehicleCatalog`.
- `POST /reportes/generar_reporte_puntos_gps` — `{"empresa": <id>, "ruta": <id>, "placa": "...", "fecha": "YYYY-MM-DD"}` → puntos GPS continuos (`latitude`, `longitude`, `speed`, `timestamp_ms`) de esa placa en ese día calendario (hora Lima), ordenados. `LucaClient` llama este endpoint una vez por cada día distinto que toque el rango del tramo y combina los resultados.
- `POST /reportes/generar_reporte_despachos` — `{"empresa": <id>, "ruta": <id>, "fecha_inicio": "YYYY-MM-DD", "fecha_fin": "YYYY-MM-DD"}` → listado plano de despachos (placa, hora, conductor, sentido, hora real/calculada del último punto) de esa empresa/ruta en el rango. Es el reemplazo nativo del "documento operacional" — ver siguiente sección.

## Limitaciones conocidas

- Los puntos GPS continuos solo existen para empresas/rutas habilitadas en el flujo automático/ATU de LUCA_Tracking; el resto de placas devuelve 0 puntos (no es un error, simplemente no hay tracking continuo para ese despacho).
- No hay paginación en estos endpoints (v1): se asume volumen bajo por placa/día (cientos a pocos miles de puntos) y por empresa/ruta/rango de fechas (`generar_reporte_despachos` no tiene tope de rango en v1 — rangos de meses/años podrían crecer bastante).
- `generar_reporte_despachos` excluye siempre los despachos con `estado == "anulado"` (nunca salieron a ruta, no tienen GPS que resolver).

---

# Modo todo-en-uno: `luca-despachos` (sin documento operacional ni documento limpio)

Para un cliente LUCA, los despachos (placa, hora, conductor, sentido, hora real de término) ya viven nativamente en la base de LUCA — no hace falta exportar/mergear el "documento operacional" ni el "documento limpio" de ATU. El subcomando `luca-despachos` reemplaza las Etapas 1, 2 y 3 en un solo paso: pide el listado de despachos directo a `/reportes/generar_reporte_despachos` y lo resuelve con el mismo `TrackPipeline` de siempre.

Clase: `application/jobs/luca_dispatch_job.py` (`LucaDispatchJob`).

## Mapeo de campos

`LucaDispatchJob` arma internamente el mismo formato que produce `OperationalJob` (`OperationalJob.OUTPUT_COLUMNS`), reutilizando los helpers ya existentes de `domain/rules.py`:

| Columna interna                  | Campo de la API LUCA          | Transformación                                    |
| --------------------------------- | ------------------------------ | --------------------------------------------------- |
| RUC_EMPRESA                       | `ruc_empresa`                  | directo                                              |
| PLACA                              | `placa`                         | `.strip()`                                           |
| IMEI                               | —                                | vacío; lo completa `VehicleCatalog` con LUCA         |
| CODIGO_RUTA                       | `codigo_ruta`                   | directo                                              |
| FECHORA_INI_VIAJE                 | `fecha` + `hora`                | combinación directa                                  |
| FECHA_HORA_FIN_TRAMO              | `hora_real_ultimo_punto`        | `domain.rules.parse_operational_datetime`            |
| FECHA_HORA_FIN_TRAMO_CALCULADA    | `hora_calculada_ultimo_punto`   | `domain.rules.parse_operational_datetime`            |
| SENTIDO                           | `sentido`                       | `"ida"→0, "vuelta"→1`                                |
| NRO_DOC_CONDUCTOR                 | `conductor`                     | `domain.rules.extract_driver_document`               |

## Comando

```bash
python main.py luca-despachos --luca-empresa 10 --luca-ruta 6 --start 2026-08-01 --end 2026-08-07 --output output/trackpoints_luca.xlsx
```

No lleva `--input` (no hay Excel de entrada) ni `--provider` (este comando solo tiene sentido para LUCA).

## Diferencia con `pipeline --provider luca`

`pipeline --provider luca` sigue existiendo para cuando ya se tiene un Excel de tramos armado (por cualquier medio). `luca-despachos` es el atajo cuando el origen de los tramos también es LUCA — evita las Etapas 1-2 por completo.

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

El CLI expone un subcomando por job (`python main.py <comando> --help` para ver sus argumentos).

Los subcomandos que consultan coordenadas (`fixed-range`, `pipeline`, `closest-coordinate`) aceptan además:

| Flag             | Default   | Descripción                                                 |
| ---------------- | --------- | ------------------------------------------------------------ |
| `--provider`     | `fmtrack` | Fuente de datos GPS: `fmtrack` o `luca`.                     |
| `--luca-empresa` | —         | ID de empresa en LUCA. **Requerido** si `--provider luca`.  |
| `--luca-ruta`    | —         | ID de ruta en LUCA. **Requerido** si `--provider luca`.     |

`operational` y `partition-split` no consultan GPS, así que no llevan estos flags. `luca-despachos` tampoco lleva `--provider` (solo tiene sentido para LUCA) — usa directamente `--luca-empresa`/`--luca-ruta` (ver [sección dedicada](#modo-todo-en-uno-luca-despachos-sin-documento-operacional-ni-documento-limpio)).

```bash
# Etapa 1: unir Ida/Vuelta con el documento limpio
python main.py operational --operational-file input/documento_operacional.xlsx --clean-file input/documento_limpio.xlsx --output output/documento_operacional_procesado.xlsx

# Etapa 2: particionar el documento procesado
python main.py partition-split --input output/documento_operacional_procesado.xlsx --output-folder output/partitions --partitions 4

# Etapa 3-5: resolver vehículos + track points por partición (fechas propias por fila) -- FM Track (default)
python main.py pipeline --input output/partitions/part_01_*.xlsx --output output/trackpoints_part_01.xlsx

# Lo mismo, pero para un cliente que trackea con LUCA (empresa/ruta internos de LUCA)
python main.py pipeline --input output/partitions/part_01_*.xlsx --output output/trackpoints_part_01.xlsx --provider luca --luca-empresa 10 --luca-ruta 6

# Alternativa: un mismo rango de fechas fijo para todo un listado simple (FM Track)
python main.py fixed-range --input input/listado.xlsx --output output/trackpoints.xlsx --start "2026-07-06 14:00:00" --end "2026-07-12 22:43:00"

# Lo mismo con LUCA
python main.py fixed-range --input input/listado.xlsx --output output/trackpoints.xlsx --start "2026-07-06 14:00:00" --end "2026-07-12 22:43:00" --provider luca --luca-empresa 10 --luca-ruta 6

# Legacy: coordenada más cercana a un timestamp por fila
python main.py closest-coordinate --input input/listado.xlsx --output output/resultado.xlsx

# Todo-en-uno para un cliente LUCA: despachos + track points, sin Excels de ATU (ver sección dedicada más abajo)
python main.py luca-despachos --luca-empresa 10 --luca-ruta 6 --start 2026-08-01 --end 2026-08-07 --output output/trackpoints_luca.xlsx
```

## Comandos de prueba rápida (LUCA)

Para validar la integración con LUCA sin depender de las etapas 1-2, basta un Excel mínimo con columnas `RUC_EMPRESA, PLACA, IMEI, CODIGO_RUTA, FECHORA_INI_VIAJE, FECHA_HORA_FIN_TRAMO, FECHA_HORA_FIN_TRAMO_CALCULADA, SENTIDO, NRO_DOC_CONDUCTOR` (una fila por tramo a probar) y correr `pipeline` apuntando a LUCA:

```bash
python main.py pipeline --input input/prueba_luca.xlsx --output output/prueba_luca.xlsx --provider luca --luca-empresa <ID_EMPRESA> --luca-ruta <ID_RUTA>
```

Antes de correrlo, confirmar en `.env` que `LUCA_BASE_URL` apunta al backend correcto (ej. `http://127.0.0.1:5000/` si LUCA_Backend corre local) y que `LUCA_API_KEY` coincide con el `API_KEY_BACKEND` vigente en el `.env` de LUCA_Backend — si cambian uno de los dos y no el otro, falla con `API Key inválida`.

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

| Variable                | Usado por          | Descripción                                      |
| ------------------------ | ------------------ | ------------------------------------------------- |
| `FMTRACK_BASE_URL`       | `FMTrackClient`    | URL base de la API de FM Track.                    |
| `FMTRACK_API_KEY`        | `FMTrackClient`    | API key principal.                                 |
| `FMTRACK_API_KEY_INTER`  | `FMTrackClient`    | API key secundaria (fallback).                     |
| `LUCA_BASE_URL`          | `LucaClient`       | URL base de LUCA_Backend (ej. `http://127.0.0.1:5000/`). |
| `LUCA_API_KEY`           | `LucaClient`       | Debe coincidir con `API_KEY_BACKEND` de LUCA_Backend. |

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
