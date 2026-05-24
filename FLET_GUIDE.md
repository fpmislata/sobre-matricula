# Guía de Flet 0.85 — Referencia del proyecto

Patrones correctos, breaking changes y referencia de API para Flet 0.85.1.

---

## Convención de documentación

Este fichero recoge los patrones y controles **más usados** en el proyecto. Los controles que no estén aquí se documentan en ficheros individuales dentro de `flet_docs/`.

**Flujo cuando se necesita un control no documentado:**
1. Consultar la documentación oficial en https://flet.dev/docs
2. Crear `flet_docs/<NombreControl>.md` con propiedades, eventos y ejemplos para Flet 0.85
3. Añadir una línea en la sección **"Índice de controles documentados"** más abajo

### Índice de controles documentados

| Control / Servicio | Documentación |
|---|---|
| AlertDialog | [esta guía → §AlertDialog](#alertdialog) |
| SnackBar | [esta guía → §SnackBar](#snackbar) |
| FilePicker | [esta guía → §FilePicker](#filepicker) |
| Tabs / TabBar | [esta guía → §Tabs](#tabs) |
| Dropdown | [esta guía → §Dropdown](#dropdown) |
| GestureDetector | [esta guía → §GestureDetector](#gesturedetector) |
| Breaking changes 0.80→0.85 | [esta guía → §Breaking changes](#breaking-changes-flet-080--085) |

---

## Documentación oficial

| Recurso | URL |
|---|---|
| Índice completo | https://flet.dev/docs |
| Referencia API | https://flet.dev/docs/reference/ |
| Catálogo de controles | https://flet.dev/docs/controls |
| Servicios | https://flet.dev/docs/services |
| AlertDialog | https://flet.dev/docs/controls/alertdialog/ |
| DialogControl | https://flet.dev/docs/controls/dialogcontrol/ |
| Page | https://flet.dev/docs/controls/page/ |
| SnackBar | https://flet.dev/docs/controls/snackbar/ |
| FilePicker | https://flet.dev/docs/services/filepicker/ |
| Clipboard | https://flet.dev/docs/services/clipboard |
| UrlLauncher | https://flet.dev/docs/services/url-launcher |
| StoragePaths | https://flet.dev/docs/services/storage-paths |

---

## AlertDialog

### API de Page para diálogos

```python
page.show_dialog(dlg)   # abrir
page.pop_dialog()       # cerrar (cierra el diálogo activo)
```

### Propiedades principales

| Propiedad | Tipo | Descripción |
|---|---|---|
| `title` | Control | Texto grande en la parte superior |
| `content` | Control | Cuerpo del diálogo |
| `actions` | list | Botones de acción (típicamente TextButton) |
| `modal` | bool | Si `True`, no se cierra al hacer clic fuera |
| `bgcolor` | str | Color de fondo |
| `actions_alignment` | MainAxisAlignment | Alineación de los botones |
| `barrier_color` | str | Color del fondo semitransparente |
| `scrollable` | bool | Hace el contenido scrollable si desborda |

### Evento

- `on_dismiss` — se dispara al cerrar. **No usar para cerrar desde botones**: se ejecuta antes del `on_click` del botón, impidiendo su handler.

### Patrón correcto completo

```python
def _show_confirm_dialog(self):
    def _on_confirm(e):
        page.pop_dialog()   # cerrar primero
        do_action()         # luego la acción
        page.update()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("¿Confirmar?"),
        content=ft.Text("Esta acción no se puede deshacer."),
        bgcolor=colors["surface"],
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: page.pop_dialog()),
            ft.ElevatedButton("Aceptar", bgcolor=colors["accent"],
                              color="#ffffff", on_click=_on_confirm),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)
```

### Helpers en este proyecto (`gui/flet_compat.py`)

```python
from gui.flet_compat import dlg_open, dlg_close

dlg_open(page, dlg)   # → page.show_dialog(dlg)
dlg_close(page)       # → page.pop_dialog()
```

### Lo que NO funciona en Flet 0.85

| Patrón | Problema |
|---|---|
| `page.dialog = dlg; dlg.open = True; page.update()` | `page.dialog` eliminado |
| `page.open(dlg)` | No existe en 0.85 |
| `page.close(dlg)` | No existe en 0.85 |
| `dlg.open = False; page.update()` | No cierra visualmente de forma fiable |
| `on_dismiss=lambda e: cerrar()` | Se dispara antes del `on_click` del botón |

---

## SnackBar

`page.show_dialog()` acepta también SnackBar:

```python
page.show_dialog(ft.SnackBar(
    ft.Text("Operación completada", color="#ffffff"),
    bgcolor=colors["success"],
    duration=ft.Duration(milliseconds=2500),
))
```

### Propiedades principales

| Propiedad | Tipo | Descripción |
|---|---|---|
| `content` | Control | Mensaje (típicamente `ft.Text`) |
| `duration` | Duration | Tiempo de visualización (default 4000 ms) |
| `bgcolor` | str | Color de fondo |
| `action` | str | Texto del botón de acción opcional |
| `show_close_icon` | bool | Mostrar botón de cierre |
| `behavior` | SnackBarBehavior | FIXED (default) o FLOATING |

### Evento
- `on_action` — se dispara al pulsar el botón de acción.

### Helper en este proyecto

```python
from gui.flet_compat import snack_open

snack_open(page, "Mensaje", colors["success"])
snack_open(page, "Error", colors["error"], 3000)
```

---

## FilePicker

Requiere handlers `async` en Flet 0.85. En Linux necesita tener instalado **Zenity**.

```python
async def _pick_folder(self, _e):
    path = await ft.FilePicker().get_directory_path(
        dialog_title="Seleccionar carpeta"
    )
    if path:
        self._field.value = path
        self.page.update()

async def _pick_files(self, _e):
    result = await ft.FilePicker().pick_files(
        allow_multiple=True,
        allowed_extensions=["pdf"],
    )
    if result and result.files:
        for f in result.files:
            print(f.path, f.name)
```

### Métodos principales

| Método | Descripción |
|---|---|
| `pick_files(...)` | Seleccionar uno o varios ficheros |
| `save_file(...)` | Diálogo de guardado |
| `get_directory_path(...)` | Seleccionar carpeta (solo escritorio) |
| `upload(files, upload_urls)` | Subir ficheros a URLs prefirmadas |

Docs: https://flet.dev/docs/services/filepicker/

---

## Breaking changes Flet 0.80 → 0.85

| API antigua | API correcta en 0.85 |
|---|---|
| `ft.padding.all(n)` | `ft.Padding(left=n, top=n, right=n, bottom=n)` |
| `ft.margin.symmetric(h=x, v=y)` | `ft.Margin(left=x, top=y, right=x, bottom=y)` |
| `ft.border.all(w, c)` | `ft.Border(top=ft.BorderSide(w,c), right=..., bottom=..., left=...)` |
| `ft.icons.X` | `ft.Icons.X` |
| `ft.app(target=main)` | `ft.run(target=main)` |
| `page.window_width` | `page.window.width` (o `page.width`) |
| `page.window_height` | `page.window.height` |
| `page.width = n; page.height = n` | `page.window.maximized = True` (arrancar maximizado) |
| `page.dialog = dlg` | `page.show_dialog(dlg)` |
| `page.open(dlg)` / `page.close(dlg)` | **no existen en 0.85** → usar `show_dialog` / `pop_dialog` |
| Abrir diálogo manualmente | `page.show_dialog(dlg)` |
| Cerrar diálogo manualmente | `page.pop_dialog()` |
| `ft.Icon(name=I.X, ...)` | `ft.Icon(I.X, ...)` — el parámetro se llama `icon`, no `name` |
| `icon_ctrl.name = I.X` | `icon_ctrl.icon = I.X` — la propiedad es `.icon`, no `.name` |

Todos los helpers para estos cambios están en `gui/flet_compat.py`:

| Helper | Equivale a |
|---|---|
| `pad(...)` | `ft.Padding(...)` |
| `mar(...)` | `ft.Margin(...)` |
| `border_all(w, c)` | `ft.Border(...)` con 4 lados iguales |
| `border_only(...)` | `ft.Border(...)` con lados selectivos |
| `I` | `ft.Icons` |
| `MC` | `ft.MouseCursor` |
| `tabs_control(...)` | `ft.Tabs` con API de 0.85 |
| `dlg_open(page, dlg)` | `page.show_dialog(dlg)` |
| `dlg_close(page)` | `page.pop_dialog()` |
| `snack_open(page, msg, bgcolor, ms)` | `page.show_dialog(ft.SnackBar(...))` |
| `safe_update(page)` | `page.update()` thread-safe (via `run_task`) |
| `accent_btn(text, *, icon, on_click, colors, disabled)` | `OutlinedButton` transparente, borde accent, hover iluminado — ver §accent_btn |
| `action_icon_btn(*, icon, icon_color, tooltip, on_click, disabled, icon_size, hover_color)` | `IconButton` con cursor pointer/forbidden y hover opcional |

---

## Servicios disponibles

Referencia: https://flet.dev/docs/services

| Servicio | Descripción |
|---|---|
| **FilePicker** | Selección de ficheros/carpetas ← usado en este proyecto |
| Clipboard | Portapapeles |
| UrlLauncher | Abrir URLs y apps externas |
| StoragePaths | Rutas de directorios del sistema |
| Audio | Reproducción de audio |
| AudioRecorder | Grabación de audio |
| Connectivity | Estado de red |
| Geolocator | Servicios de ubicación |
| HapticFeedback | Retroalimentación táctil |
| PermissionHandler | Permisos en tiempo de ejecución |
| SecureStorage | Almacenamiento seguro clave/valor |
| SharedPreferences | Preferencias persistentes |
| Share | Compartir contenido |
| ScreenBrightness | Brillo de pantalla |
| Wakelock | Evitar reposo del dispositivo |
| Accelerometer / Gyroscope / Magnetometer / Barometer | Sensores |
| Battery | Información de batería |
| Flashlight | Linterna |
| ShakeDetector | Detección de agitación |

---

## Actualización de UI desde hilos

**`page.update()` llamado directamente desde un `threading.Thread` NO dispara el render en Flet 0.85 desktop.** Flet usa asyncio internamente; llamar `page.update()` desde un hilo síncrono falla silenciosamente.

**Patrón correcto: usar `safe_update(page)`** del helper en `gui/flet_compat.py`:

```python
from gui.flet_compat import safe_update

def _worker_thread(self):
    self._label.value = "nuevo valor"
    safe_update(self.page)   # ← siempre esto en hilos de fondo
```

`safe_update` usa `page.run_task()` para programar el update en el event loop de Flet:

```python
def safe_update(page):
    async def _upd():
        page.update()
    page.run_task(_upd)
```

Si además necesitas llamar a `dlg_close`, `snack_open` u otras funciones de página desde el **final de un hilo**, envuélvelas también en `run_task`:

```python
def _worker():
    # ... trabajo pesado ...
    msg, col = "Completado", colors["success"]

    async def _finish(msg=msg, col=col):
        dlg_close(page)
        snack_open(page, msg, col, 4000)

    page.run_task(_finish)
```

> `page.run_task(coro_fn, *args)` es thread-safe y programa la corrutina en el event loop de Flet. Es la única forma fiable de actualizar la UI desde hilos secundarios en Flet 0.85.

---

## Tabs

```python
from gui.flet_compat import tabs_control

tabs = tabs_control(
    [
        ("Pestaña 1", contenido_1),
        ("Pestaña 2", contenido_2),
    ],
    selected_index=0,
    label_color=colors["text"],
    unselected_label_color=colors["text_dim"],
    indicator_color=colors["accent"],
)
```

Internamente construye `ft.Tabs` con `ft.TabBar` + `ft.TabBarView` (API de 0.85).

---

## Dropdown

Flet 0.85 tiene **dos controles de dropdown distintos** con APIs incompatibles:

| Control | Evento de cambio | Cuándo usarlo |
|---|---|---|
| `ft.Dropdown` | **`on_select`** | Control estándar (usado en este proyecto) |
| `ft.DropdownM2` | **`on_change`** | Variante Material 2, no usada aquí |

**Nunca usar `on_change` con `ft.Dropdown`** — el kwarg no existe y lanza `TypeError` al construir el control.

```python
# CORRECTO
ft.Dropdown(
    value="todos",
    options=[ft.dropdown.Option("todos", "Todos"), ...],
    on_select=self._handler,   # ← on_select, no on_change
)

# INCORRECTO — TypeError en runtime
ft.Dropdown(on_change=self._handler)
```

El handler recibe un `ControlEvent`; leer el valor con `e.control.value` o desde la referencia al dropdown:

```python
def _on_select(self, e):
    selected = self._dd.value   # ya actualizado cuando se dispara on_select
```

Referencia: https://flet.dev/docs/controls/dropdown/

---

## GestureDetector

Permite capturar gestos sobre cualquier control. Útil para hacer clicables elementos que no tienen `on_click` (p. ej. encabezados de tabla).

```python
ft.GestureDetector(
    content=ft.Container(
        width=80,
        content=ft.Text("Columna", size=10, weight=ft.FontWeight.W_700),
    ),
    mouse_cursor=ft.MouseCursor.CLICK,   # cursor de mano al pasar
    on_tap=lambda e: self._on_sort("columna"),
)
```

Propiedades principales:

| Propiedad | Descripción |
|---|---|
| `content` | Control envuelto |
| `mouse_cursor` | Cursor al pasar el ratón (`ft.MouseCursor.CLICK`, `BASIC`, etc.) |
| `on_tap` | Tap / clic izquierdo |
| `on_long_press_start` | Pulsación larga |
| `on_secondary_tap` | Clic derecho |
| `on_hover` | Entrada/salida del cursor |
| `on_pan_start/update/end` | Arrastre |

Referencia: https://flet.dev/docs/controls/gesturedetector/

---

## accent_btn — botón accent con hover iluminado

Helper centralizado en `gui/flet_compat.py`. **Todo botón de acción principal** (color accent) debe crearse con este helper en lugar de `ft.ElevatedButton` directo.

**Aspecto visual**: igual que el botón "Vaciar papelera" de `output.py`:
- Normal: fondo transparente, borde 1px `colors["accent"]`, texto `colors["accent"]`
- Hover: borde 2px `colors["accent_hover"]`, texto `colors["accent_hover"]`
- Disabled: borde 1px `colors["border"]`, texto `colors["text_dim"]`

**Implementación interna**: `ft.OutlinedButton` + `ButtonStyle`. Motivo: `ElevatedButton` tiene su propio `MouseRegion` que absorbe el cursor y bloquea `on_hover` del `GestureDetector` externo.

```python
from gui.flet_compat import accent_btn

# Uso básico
wrapper = accent_btn("Guardar", icon=I.SAVE, on_click=_on_save, colors=c)

# Con estado deshabilitado inicial
wrapper = accent_btn("Abrir carpeta", icon=I.FOLDER_OPEN,
                     on_click=_open, colors=c, disabled=True)
```

**Lo que devuelve**: `ft.GestureDetector` con cursor CLICK/FORBIDDEN y `on_hover` que ilumina borde + texto a `accent_hover` al entrar, y revierte al salir.

**Acceder al OutlinedButton interno** (para actualizar `disabled`, `style`, `text`, etc.):
```python
self._process_btn_wrapper = accent_btn(...)
self._process_btn = self._process_btn_wrapper.content  # OutlinedButton

# En _update_state — usar btn.style, NO btn.bgcolor/btn.color directamente:
self._process_btn.disabled = disabled
self._process_btn.style = ft.ButtonStyle(
    color=c["text_dim"] if disabled else c["accent"],
    side=ft.BorderSide(1, c["border"] if disabled else c["accent"]),
)
self._process_btn_wrapper.mouse_cursor = MC.FORBIDDEN if disabled else MC.CLICK
```

**Colores relevantes** (en `gui/theme.py`, en ambos temas):
- `accent`: color base del botón (texto + borde en reposo)
- `accent_hover`: color iluminado al hover (texto + borde más brillante/grueso)
- `border`: borde del botón deshabilitado
- `text_dim`: texto del botón deshabilitado
- `btn_hover_bg` / `btn_hover_text`: NO se usan en `accent_btn` (reservados para otros usos futuros)

**Regla**: no usar `ft.ElevatedButton` directamente con `bgcolor=c["accent"]` — usar siempre `accent_btn`. Sin parámetro `style` (el helper gestiona `ButtonStyle` internamente).
