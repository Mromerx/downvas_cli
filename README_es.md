# DownVas - Canvas Downloader CLI

DownVas es una herramienta de interfaz de línea de comandos (CLI) escrita en Python para descargar de forma estructurada e interactiva los archivos de cursos alojados en Canvas LMS.

## Características Principales

- **Autenticación mediante Token**: Configura tu URL de Canvas y tu token de acceso (API Token) de manera segura y sencilla.
- **Soporte Multi-idioma (i18n)**: Interfaz disponible en Español e Inglés, configurable desde el asistente.
- **Exploración Jerárquica**: Visualiza todo el contenido de tu curso en una estructura de árbol (Carpetas, Módulos y Archivos) con colores distintivos por tipo de archivo, todo desde la terminal.
- **Múltiples Opciones de Descarga**:
  - Descargar un archivo específico (por su ID, nombre o índice en el árbol).
  - Descargar una cola de varios archivos seleccionados manualmente.
  - Descargar todos los archivos con una extensión específica (ej. `.pdf`, `.pptx`).
  - Descargar todos los archivos del curso de una sola vez.
  - Descargar todos los archivos de una sección o módulo.
- **Descargas Robustas**: 
  - Las descargas se realizan en fragmentos e incluyen una barra de progreso detallada con velocidad de transferencia y tiempo restante.
  - Se utilizan archivos temporales (`.part`) durante la transferencia para evitar archivos corruptos si se interrumpe la conexión.
  - Soporte nativo para saltar (omitir) automáticamente archivos que ya se encuentren descargados localmente.
- **Organización Automática**: Los archivos descargados se guardan automáticamente respetando la estructura de carpetas y módulos originales del curso.

## Requisitos

- Python 3.10+
- Dependencias (pueden ser instaladas vía `requirements.txt`):
  - `requests`
  - `rich`
  - `pydantic`
  - `python-dotenv`

## Instalación

1. Clona o descarga este repositorio.
2. Crea y activa tu entorno virtual (opcional pero recomendado):
   ```bash
   python -m venv env
   ```
   - **Linux/macOS**: `source env/bin/activate`
   - **Windows**: `env\Scripts\activate`
3. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

## Uso

Para iniciar el asistente y el menú principal, simplemente ejecuta:

```bash
python main.py
```

### Primer inicio (Configuración)
Si es la primera vez que lo ejecutas, DownVas iniciará un asistente interactivo pidiendo:
1. **URL de Canvas LMS** (por ejemplo: `https://canvas.instructure.com` o el dominio de tu universidad).
2. **Token de acceso** (puedes generarlo desde Canvas -> Cuenta -> Configuraciones -> Nuevo Token de Acceso).
3. **Idioma de la interfaz** (selecciona `es` para Español o `en` para Inglés).
4. **Carpeta de descarga local** (la ruta donde deseas guardar los cursos, ej. `./Descargas` o `./Downloads` adaptándose al idioma).

*Estos datos se guardarán localmente en un archivo `.env`.*

### Menú Principal
Una vez configurado y tras ingresar el ID de un curso (o su URL completa), se te presentará un menú interactivo con las siguientes opciones:

1. **Ver listado del curso**: Imprime la estructura jerárquica de archivos, carpetas y módulos.
2. **Actualizar información del curso**: Vuelve a cargar el árbol de archivos desde el servidor.
3. **Descargar un archivo**: Selecciona y descarga un único archivo.
4. **Descargar varios archivos**: Permite agregar archivos a una cola y descargarlos en lote.
5. **Descargar archivos por extensión (ej: .pdf)**: Filtra y descarga todos los `.pdf`, `.ppt`, etc.
6. **Descargar todos los archivos del curso**: Descarga el curso completo manteniendo la jerarquía de carpetas.
7. **Descargar por sección**: Descarga todos los archivos de un módulo o carpeta específica.
8. **Reasignar credenciales**: Opción de reconfiguración.
9. **Cambiar de curso**: Permite ingresar un nuevo ID para explorar otro curso.
10. **Salir**

## Estructura de Directorios

- `main.py`: Punto de entrada de la aplicación y controlador del menú interactivo.
- `src/`
  - `cli.py`: Handlers de cada opción del menú (asistente de configuración, descargas, actualización, cambio de curso/URL/token).
  - `core.py`: Definición de errores comunes, utilidades (ej. validación de URLs) y carga de configuraciones (Settings).
  - `courses.py`: Cliente de la API de Canvas, manejo de peticiones paginadas y generación del árbol jerárquico.
  - `downloader.py`: Servicio dedicado a la descarga de archivos en fragmentos, manejo de archivos `.part` e interfaz de la barra de progreso.
  - `i18n.py`: Motor de internacionalización para traducir la interfaz.
  - `theme.py`: Definición centralizada del tema visual (colores y estilos) de la interfaz de terminal.
- `locales/`: Archivos de traducción y diccionarios compilados (`.po` y `.mo`).
- `.env`: (Generado automáticamente) Archivo de variables de entorno para almacenar credenciales.
