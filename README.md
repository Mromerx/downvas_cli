# DownVas - Canvas Downloader CLI

DownVas es una herramienta de interfaz de línea de comandos (CLI) escrita en Python para descargar de forma estructurada e interactiva los archivos de cursos alojados en Canvas LMS.

## Características Principales

- **Autenticación mediante Token**: Configura tu URL de Canvas y tu token de acceso (API Token) de manera segura y sencilla.
- **Exploración Jerárquica**: Visualiza todo el contenido de tu curso en una estructura de árbol (Carpetas, Módulos y Archivos) con colores distintivos por tipo de archivo, todo desde la terminal.
- **Multiples Opciones de Descarga**:
  - Descargar un archivo especifico (por su ID, nombre o indice en el arbol).
  - Descargar una cola de varios archivos seleccionados manualmente.
  - Descargar todos los archivos con una extension especifica (ej. `.pdf`, `.pptx`).
  - Descargar todos los archivos del curso de una sola vez.
- **Descargas Robustas**: 
  - Las descargas se realizan en fragmentos e incluyen una barra de progreso detallada con velocidad de transferencia y tiempo restante.
  - Se utilizan archivos temporales (`.part`) durante la transferencia para evitar archivos corruptos si se interrumpe la conexion.
  - Soporte nativo para saltar (omitir) automaticamente archivos que ya se encuentren descargados localmente.
- **Organizacion Automatica**: Los archivos descargados se guardan automaticamente respetando la estructura de carpetas y modulos originales del curso.

## Requisitos

- Python 3.10+
- Dependencias (pueden ser instaladas vía `requirements.txt`):
  - `requests`
  - `rich`
  - `pydantic`
  - `python-dotenv`

## Instalación

1. Clona o descarga este repositorio.
2. Activa tu entorno virtual (opcional pero recomendado):
   ```bash
   source env/bin/activate
   ```
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
3. **Carpeta de descarga local** (la ruta donde deseas guardar los cursos, ej. `./Descargas`).

*Estos datos se guardarán localmente en un archivo `.env`.*

### Menú Principal
Una vez configurado y tras ingresar el ID de un curso (o su URL completa), se te presentará un menú interactivo con las siguientes opciones:

1. **Ver listado del curso**: Imprime la estructura jerárquica de archivos, carpetas y módulos.
2. **Descargar un archivo**: Selecciona y descarga un único archivo.
3. **Descargar varios archivos**: Permite agregar archivos a una cola y descargarlos en lote.
4. **Descargar archivos por extensión (ej: .pdf)**: Filtra y descarga todos los `.pdf`, `.ppt`, etc.
5. **Descargar todos los archivos del curso**: Descarga el curso completo manteniendo la jerarquía de carpetas.
6. **Actualizar información del curso**: Vuelve a cargar el árbol de archivos desde el servidor.
7. **Cambiar de curso**: Permite ingresar un nuevo ID para explorar otro curso.
8. **Cambiar URL de Canvas**: Opción de reconfiguración.
9. **Cambiar token de acceso**: Opción de reconfiguración.
10. **Salir**

## Estructura de Directorios

- `main.py`: Punto de entrada de la aplicación y controlador del menú interactivo.
- `src/`
  - `cli.py`: Handlers de cada opción del menú (asistente de configuración, descargas, actualización, cambio de curso/URL/token).
  - `core.py`: Definición de errores comunes, utilidades (ej. validación de URLs) y carga de configuraciones (Settings).
  - `courses.py`: Cliente de la API de Canvas, manejo de peticiones paginadas y generación del árbol jerárquico.
  - `downloader.py`: Servicio dedicado a la descarga de archivos en fragmentos, manejo de archivos `.part` e interfaz de la barra de progreso.
  - `theme.py`: Definición centralizada del tema visual (colores y estilos) de la interfaz de terminal.
- `.env`: (Generado automaticamente) Archivo de variables de entorno para almacenar credenciales.
