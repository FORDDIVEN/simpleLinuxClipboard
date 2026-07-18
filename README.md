# WinV Clipboard para Linux

Historial de portapapeles para Linux inspirado en la experiencia de `Win + V` de Windows.

El objetivo del proyecto es ser simple, rápido y sentirse como una función nativa del sistema: una ventana compacta para recuperar textos e imágenes copiadas recientemente, sin convertirse en un gestor de notas ni en un administrador de snippets.

## Características

- Historial compacto de portapapeles.
- Guarda los últimos 50 elementos.
- Soporte para texto, emojis, kaomojis, símbolos e imágenes.
- Elementos fijados para evitar que se eliminen automáticamente.
- Búsqueda instantánea.
- Filtros por todo, texto e imágenes.
- Miniaturas para imágenes.
- Tema claro y oscuro según el sistema.
- Icono en la bandeja del sistema.
- Opción para limpiar el historial no fijado.
- Atajo global configurable desde la interfaz.
- Persistencia en JSON, sin base de datos.
- Caché de imágenes fuera del JSON.

## Estado del proyecto

Proyecto en desarrollo. Actualmente está pensado principalmente para Linux Mint/Cinnamon sobre X11.

El atajo global interno usa X11. En sesiones Wayland puede no funcionar dependiendo del entorno de escritorio. En ese caso se puede usar un atajo del sistema que ejecute la app con `--toggle`.

## Requisitos

- Python 3.12+
- Linux con entorno de escritorio
- PySide6
- PyInstaller, solo si quieres generar un ejecutable

Instala dependencias con:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Ejecutar

Para abrir la aplicación:

```bash
python3 main.py
```

Si ya hay una instancia abierta en segundo plano, el mismo comando mostrará la ventana.

Para iniciar la app oculta, útil para autoinicio:

```bash
python3 main.py --background
```

Comandos disponibles:

```bash
python3 main.py --show
python3 main.py --hide
python3 main.py --toggle
python3 main.py --quit
```

## Atajo de teclado

Por defecto el atajo global viene desactivado para evitar conflictos en el primer inicio.

Para configurarlo:

1. Abre la aplicación.
2. Pulsa el icono de configuración.
3. Activa el atajo.
4. Elige la combinación que prefieras.

Ejemplo recomendado:

```text
Super+V
```

Para que la apertura sea instantánea, conviene dejar la aplicación corriendo en segundo plano y usar el atajo global interno.

## Dónde se guardan los datos

Historial y configuración:

```text
~/.local/share/winvclipboard/history.json
~/.local/share/winvclipboard/settings.json
```

Imágenes copiadas:

```text
~/.cache/winvclipboard/
```

Las imágenes no se guardan dentro del JSON. El JSON solo almacena la ruta del archivo en caché.

Al eliminar una imagen del historial también se elimina su archivo asociado. Al iniciar, la app limpia imágenes huérfanas que hayan quedado en caché.

## Pruebas

Usando el entorno virtual:

```bash
venv/bin/python -m unittest discover -s tests
```

## Generar ejecutable

Con el entorno virtual activo:

```bash
pyinstaller --noconfirm --onefile --windowed --name winvclipboard main.py
```

El ejecutable quedará en:

```text
dist/winvclipboard
```

Puedes ejecutarlo con:

```bash
./dist/winvclipboard
```

Para iniciar oculto:

```bash
./dist/winvclipboard --background
```

Para usarlo desde un atajo del sistema:

```bash
./dist/winvclipboard --toggle
```

## Filosofía

Este proyecto prioriza:

- Simplicidad.
- Rapidez de apertura.
- Código fácil de mantener.
- Pocas dependencias.
- Experiencia parecida al historial de portapapeles de Windows.

No busca reemplazar gestores avanzados de snippets ni aplicaciones de notas.

## Estructura principal

```text
main.py        Arranque, bandeja del sistema, IPC y ciclo principal.
ui.py          Interfaz gráfica con PySide6.
clipboard.py   Observador del portapapeles.
history.py     Persistencia, pins, limpieza y límite del historial.
hotkey.py      Atajo global sobre X11.
settings.py    Configuración en JSON.
ipc.py         Comunicación con una instancia ya abierta.
config.py      Rutas y constantes.
utils.py       Utilidades pequeñas.
```

## Licencia

De libre uso, sientase libre de modificar o mejorar el proyecto.
