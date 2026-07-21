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
OperationalProcessor
        |
        v
Documento operacional procesado
        |
        v
PartitionSplitter
        |
        v
Particiones de procesamiento
        |
        v
PipelineProcessor
        |
        +----------------+
        |                |
        v                v
VehicleResolver     TrackPointsProcessor
        |                |
        |                v
        |          API FM Track
        |
        v
TrackPointsWriter
        |
        v
Documento final de Track Points
```

---

# Estructura del proyecto

```
ATU_Files/
│
├── client/
│   └── fmtrack_client.py
│
├── services/
│   ├── operational_processor.py
│   ├── partition_splitter.py
│   ├── pipeline_processor.py
│   ├── trackpoints_processor.py
│   ├── trackpoints_writer.py
│   └── vehicle_resolver.py
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
├── main.py
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
services/operational_processor.py
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
services/partition_splitter.py
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
services/trackpoints_processor.py
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
services/trackpoints_writer.py
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
| SENTIDO           |
| NRO_DOC_CONDUCTOR |
| INICIO_TRAMO      |
| FIN_TRAMO         |
| FECHA_HORA_TRACK  |
| LATITUD           |
| LONGITUD          |
| VELOCIDAD         |

---

# Ejecución

Ejecutar:

```bash
python main.py
```

Ejemplo de flujo:

```python
processor.process(
    input_file="output/partitions/part_01.xlsx",
    output_file="output/trackpoints_part_01.xlsx",
)
```

---

# Dependencias

Instalar:

```bash
pip install -r requirements.txt
```

Principales librerías:

- pandas
- openpyxl
- requests

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
