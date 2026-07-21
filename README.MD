# FM Track Excel Enricher

## Descripción

FM Track Excel Enricher es una herramienta desarrollada en Python para enriquecer reportes de Excel con información histórica obtenida desde la API de FM Track.

A partir de un archivo Excel que contiene información de viajes y vehículos, el sistema consulta automáticamente la posición histórica correspondiente a cada registro y reemplaza las columnas de:

- Latitud
- Longitud
- Velocidad

El resultado es un nuevo archivo Excel listo para ser utilizado en procesos de análisis o generación de reportes.

---

## Características

- Lectura de archivos Excel (.xlsx).
- Integración con la API REST de FM Track.
- Resolución automática de vehículos mediante placa.
- Consulta de coordenadas históricas por fecha y hora.
- Reemplazo automático de las columnas:
  - LATITUD
  - LONGITUD
  - VELOCIDAD

- Procesamiento por lotes para respetar límites de la API.
- Pausas configurables entre lotes.
- Manejo de múltiples API Keys.
- Arquitectura modular para facilitar futuras extensiones.

---

## Estructura del proyecto

```text
ATU_Files/
│
├── client/
│   └── fmtrack_client.py      # Cliente HTTP para FM Track
│
├── services/
│   └── excel_processor.py     # Procesamiento del archivo Excel
│
├── input/                     # Archivos de entrada
├── output/                    # Archivos generados
│
├── config.py                  # Configuración de la aplicación
├── main.py                    # Punto de entrada
├── requirements.txt
└── .env
```

---

## Requisitos

- Python 3.12 o superior
- Cuenta con acceso a FM Track
- API Keys válidas

---

## Instalación

Clonar el repositorio:

```bash
git clone <repository_url>

cd ATU_Files
```

Crear un entorno virtual:

```bash
python -m venv .venv
```

Activar el entorno:

### Windows

```bash
.venv\Scripts\activate
```

### Linux / macOS

```bash
source .venv/bin/activate
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

---

## Configuración

Crear un archivo `.env` en la raíz del proyecto.

Ejemplo:

```env
FMTRACK_API_KEY=xxxxxxxxxxxxxxxx
FMTRACK_API_KEY_INTER=xxxxxxxxxxxxxxxx

FMTRACK_BASE_URL=https://api.fm-track.com
```

---

## Formato esperado del Excel

El archivo de entrada debe contener, como mínimo, las siguientes columnas:

| Columna          |
| ---------------- |
| PLACA            |
| FECHA_HORA_TRACK |
| LATITUD          |
| LONGITUD         |
| VELOCIDAD        |

Las demás columnas se conservan sin modificaciones.

---

## Ejecución

Colocar el archivo Excel dentro de la carpeta `input`.

Ejecutar:

```bash
python main.py
```

El archivo enriquecido será generado en la carpeta `output`.

---

## Flujo de procesamiento

```text
Excel
    │
    ▼
Leer registros
    │
    ▼
Consultar vehículos en FM Track
    │
    ▼
Resolver object_id mediante placa
    │
    ▼
Consultar coordenadas históricas
    │
    ▼
Actualizar:
    • LATITUD
    • LONGITUD
    • VELOCIDAD
    │
    ▼
Exportar nuevo Excel
```

---

## Procesamiento por lotes

Para respetar las restricciones de la API, el procesamiento se realiza por lotes configurables.

Parámetros disponibles:

- `batch_size`
- `batch_delay`

Ejemplo:

```python
processor = ExcelProcessor(
    client,
    batch_size=1000,
    batch_delay=10,
)
```

---

## Tecnologías utilizadas

- Python
- Pandas
- OpenPyXL
- HTTPX
- python-dotenv
- FM Track REST API

---

## Posibles mejoras

- Procesamiento concurrente con límite de conexiones.
- Barra de progreso en consola.
- Reintentos automáticos ante errores temporales.
- Registro de errores en archivo separado.
- Interfaz gráfica para usuarios no técnicos.
- Empaquetado como ejecutable para Windows.

---

## Licencia

Este proyecto fue desarrollado para automatizar la generación de reportes enriquecidos utilizando la plataforma FM Track.
