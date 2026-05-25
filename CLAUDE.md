# Procesador de PDFs de Matrículas — CLAUDE.md

## Qué hace este proyecto

Aplicación Python que procesa PDFs escaneados de matrículas de FP (Formación Profesional). Para cada PDF:

1. Extrae datos del formulario de la página 1 mediante OCR con visión (Ollama o OpenRouter / llama3.2-vision).
2. Valida y autocorrige el DNI/NIE con la letra de control del DNI español.
3. Clasifica las páginas siguientes (foto de carnet, copia de DNI/NIE/pasaporte, otro).
4. Detecta y recorta caras con YOLO en 4 rotaciones (fallback Haar cascades de OpenCV). Si el DNI está girado, re-analiza el texto con la orientación correcta.
5. Selecciona la mejor foto: primero color, luego nitidez (varianza del Laplaciano).
6. Genera carpeta de salida por expediente con PDF renombrado, JSON, fotos y carpeta de debug.
7. Marca el PDF procesado con un prefijo configurable (por defecto `_!_`) en la carpeta de entrada.
8. Si faltan campos obligatorios, envía el resultado a `output/revision/` para revisión manual.

## Entorno

- **Python**: 3.12, entorno virtual en `.venv/`
- **Flet**: 0.85.1 (fijado en `requirements.txt`)
- **Activar venv**: `source .venv/bin/activate`
- **Ejecutar pipeline CLI**: `.venv/bin/python main.py`
- **Ejecutar GUI**: `.venv/bin/python gui_main.py`
- **Instalar deps**: `.venv/bin/pip install -r requirements.txt`
- **Servidor Ollama**: `http://ollama.iabd.cip.fpmislata.com:80` — solo accesible desde la red interna del centro
- **OpenRouter**: acceso externo vía API key en `.env` (modo desarrollo)

## Estructura del proyecto

```
/home/jevallo/workspace/IABD/dni2/
├── main.py                  # Pipeline CLI. También expone run_pipeline() para la GUI.
├── gui_main.py              # Punto de entrada de la GUI Flet: ft.run(target=main)
├── config.py                # Toda la configuración (rutas, URLs, flags, catálogo de ciclos, nomenclatura).
├── config.json              # Config persistida por la GUI (se crea al guardar en Configuración)
├── config_default.json      # Config por defecto personalizada (opcional; la crea el usuario desde GUI)
├── .env                     # API key de OpenRouter (no commiteado — en .gitignore)
├── requirements.txt
├── models/
│   └── yolov8-face.pt       # Modelo YOLO de detección de caras (ya descargado)
├── pdf/                     # Carpeta de PDFs de entrada (configurable)
├── output/                  # Carpeta de resultados (configurable)
├── logs/                    # Logs por ejecución: procesado_YYYY-MM-DD_HH-MM-SS.log
├── gui/
│   ├── app.py               # DNIApp: layout principal, sidebar, navegación, toggle de tema
│   ├── config_manager.py    # Carga/guarda config.json (portable: junto al exe o script)
│   ├── flet_compat.py       # Helpers pad/mar/border_all para Flet 0.85+ (API cambió en 0.80)
│   ├── processing_manager.py # ProcessingManager: estado de proceso compartido (worker, timer, observers)
│   ├── processing_worker.py # Thread ProcessingWorker con pause/stop Events
│   ├── theme.py             # Colores dark/light (Catppuccin-inspired)
│   └── views/
│       ├── inicio_simple.py # Vista Inicio: selectores, 4 stats, botón procesar, progreso mínimo
│       ├── inicio.py        # Vista Avanzada: lista PDFs, filtros, log en vivo, pausa/stop
│       ├── configuracion.py # 6 tabs: IA, Procesado, Nomenclatura, Ciclos, General, Prompts LLM
│       └── logs.py          # Lista de ejecuciones + buscador case-insensitive
├── build/
│   ├── build.bat            # Compila con PyInstaller (Windows)
│   └── installer.iss        # Inno Setup: autoinstalable que preserva config.json
├── modules/
│   ├── pdf_processor.py     # PDF → lista de PIL.Image + preprocess_for_ocr() (grises + Otsu)
│   ├── form_extractor.py    # OCR formulario p.1 + normalización fuzzy de ciclo
│   ├── dni_validator.py     # Checksum DNI/NIE español + corrección de confusiones OCR
│   ├── page_analyzer.py     # Clasifica páginas 2..N + cross_check() con lógica de confianza DNI
│   ├── photo_detector.py    # YOLO face detection en 4 rotaciones + fallback Haar
│   ├── photo_selector.py    # Selección de mejor foto: color (bonus 10M) + nitidez
│   ├── output_manager.py    # Nombrado canónico, debug, revisión obligatoria, construye JSON
│   └── output_structure.py  # Jerarquía de carpetas: resolve, validate, preview, reorganize
└── utils/
    ├── ollama_client.py     # Dispatcher call_model(): Ollama o OpenRouter según MODO_DESARROLLO_PROD
    └── image_utils.py       # PIL↔CV2, base64, is_color_image, sharpness_score, rotate_pil
```

## Configuración principal (`config.py`)

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `INPUT_DIR` | `pdf/` | Carpeta de PDFs de entrada |
| `OUTPUT_DIR` | `output/` | Carpeta de resultados |
| `REVIEW_DIR` | `output/revision` | Subcarpeta para casos problemáticos |
| `MODO_DESARROLLO_PROD` | `True` | `True`=Ollama (producción), `False`=OpenRouter (desarrollo) |
| `DEBUG_REPROCESS` | `False` | Si `True`, reprocesa PDFs aunque ya tengan el prefijo `_!_` |
| `PASAR_A_GRISES` | `True` | Si `True`, preprocesa página 1 a gris+Otsu antes del OCR |
| `PDF_DPI` | `200` | Resolución de conversión PDF→imagen |
| `YOLO_MODEL_PATH` | `models/yolov8-face.pt` | Ruta al modelo YOLO de caras |
| `YOLO_CONFIDENCE` | `0.35` | Umbral de confianza YOLO |
| `FACE_PADDING_RATIO` | `0.35` | Expansión del recorte de cara (35%) |
| `OVERWRITE_EXISTING` | `True` | Si `True`, sobreescribe carpetas existentes |
| `MAX_PAGES_TO_ANALYZE` | `6` | Máximo de páginas a analizar por PDF |
| `OLLAMA_TIMEOUT` | `120` | Timeout en segundos por llamada |
| `OLLAMA_MAX_RETRIES` | `3` | Reintentos con backoff exponencial |
| `OPENROUTER_MODEL` | `meta-llama/llama-3.2-11b-vision-instruct` | Modelo usado en OpenRouter |
| `ASISTENCIA_CODE` | `{presencial:P, semipresencial:S, libre:L, parcial:PA}` | Códigos para el nombre de carpeta |
| `DOCUMENT_NAME_SUFFIX` | `_M` | Sufijo interno usado por output_manager; no expuesto en GUI (escríbelo directamente en el formato) |
| `DOCUMENT_NAME_FORMAT` | `{nombre}_{apellido1}_{apellido2},{nombre}_E{expediente}_{asistencia}{año_ini}{año_fin}_M` | Plantilla del nombre canónico (editable desde GUI) |
| `PROCESSED_PREFIX` | `_!_` | Prefijo que se añade al PDF tras procesarlo (configurable en GUI y en `config.json`) |
| `output_folder_structure` | `{ciclo_codigo}` | Plantilla de subcarpetas entre `output/` y el expediente (configurable en GUI → Nomenclatura) |

## Marcado de PDFs procesados

Al terminar cada PDF correctamente, se renombra en `pdf/` añadiendo el prefijo configurado (por defecto `_!_`):
```
15402-02.pdf  →  _!_15402-02.pdf
```
En la siguiente ejecución, los PDFs con ese prefijo se saltan automáticamente salvo que `DEBUG_REPROCESS = True`.

El prefijo se puede cambiar desde GUI → Configuración → Procesado → **"Prefijo de PDFs procesados"**. Al guardar un prefijo distinto, todos los PDFs de la carpeta de entrada que tengan el prefijo antiguo se renombran automáticamente al nuevo.

El prefijo se gestiona a través de la variable `PROCESSED_PREFIX` en `main.py` (por defecto `"_!_"`), que `run_pipeline()` parchea desde `config_dict["processed_prefix"]`. Las vistas `inicio_simple.py`, `inicio.py` y `output.py` lo leen de `app.cfg.get("processed_prefix", "_!_")`.

**Historial de prefijos (`processed_prefix_history`):** `config.json` acumula todos los prefijos usados (máx 10). Al cambiar el prefijo en GUI → Configuración → Procesado, el prefijo antiguo se añade al historial antes de renombrar los archivos. El historial se usa en `_is_in_index()` y en `_scan_output_thread` para reconocer y renombrar archivos con prefijos antiguos.

**`run_pipeline()` filtra prefijados:** la GUI también salta PDFs con el prefijo activo (igual que el CLI) salvo que `DEBUG_REPROCESS=True`. El filtro se aplica al principio del loop, antes de procesar ningún PDF.

**Auto-corrección de estado en disco (`_scan_output_thread`):** al escanear, el hilo de fondo aplica tres correcciones automáticas en orden:
1. **Crash-detection**: PDF con prefijo actual pero SIN datos en output → se le quita el prefijo (proceso interrumpido).
2. **Migración de prefijo**: PDF con prefijo antiguo (del historial) Y con datos en output → se renombra al prefijo actual.
3. **Marca faltante**: PDF SIN ningún prefijo conocido pero CON datos en output (pipeline completó pero rename falló) → se le añade el prefijo actual.

**`_is_in_index(pdf)`** (helper en ambas vistas): lookup bidireccional robusto. Para cada prefijo conocido (actual + histórico):
- **Dirección 1** (archivo tiene prefijo): `name[len(pfx):]` en `_output_index` → cubre archivos ya marcados
- **Dirección 2** (archivo SIN prefijo): `pfx + name` en `_output_index` → cubre cuando `pdf_original` se guardó con el prefijo como parte del nombre (ej. prefijo `#` con `pdf_original="#15406-02.pdf"`: si el disco tiene `15406-02.pdf`, prueba `"#15406-02.pdf"` en el índice)

Nota: el caso `_!_` (patrón `_X_`) está doblemente cubierto — `_build_output_index` ya añade entrada secundaria sin prefijo, la dirección 2 cubre prefijos no-`_X_` (ej. `#`, `DONE-`).

**Avanzada — checkbox y selección:** cuando `DEBUG_REPROCESS=False`, los PDFs ya procesados no muestran checkbox y no pueden seleccionarse (ni manualmente ni con "Seleccionar todos").

## Campos obligatorios para no ir a revisión

Si falta cualquiera de estos campos, el resultado va a `output/revision/` y `en_revision=True` en el JSON:

- `nombre`, `apellido1`, `apellido2`
- `ciclo.codigo`
- `tipo_asistencia` — si el modelo no lo extrae, el valor por defecto es `"presencial"`. Con `DEBUG_REPROCESS=True` este campo no provoca revisión aunque sea null.
- `curso.inicio`, `curso.fin`
- foto (alguna foto seleccionada)

## Lógica de confianza en datos del DNI

El DNI físico adjunto al expediente es más fiable que el formulario manuscrito.

**Para el número de documento** (tabla de prioridades):
| Situación | Número usado |
|---|---|
| DNI válido sin corrección | DNI (gana siempre) |
| DNI necesita corrección, formulario no | Formulario |
| Ambos necesitan corrección | DNI corregido |
| DNI no valida en absoluto | Formulario → caso a revisión |

**Para nombre/apellido1/apellido2:**
- Si el número del DNI **valida** (con o sin corrección) → datos del DNI prevalecen siempre
- Si el número del DNI **no valida** → datos del DNI ignorados (posible contaminación OCR del batch)
- **Excepción — swap de apellidos:** si formulario y DNI tienen los mismos apellidos pero en orden inverso (`apellido1`↔`apellido2`), se interpreta como error de orden del LLM al leer el DNI. Se preserva el orden del formulario y se registra en `correcciones_aplicadas`. La comparación normaliza acentos (MARTÍNEZ == MARTINEZ). Implementado en `_apellidos_swapped()` + `_ascii_key()` en `modules/page_analyzer.py`.

## Nomenclatura de carpetas y ficheros

El formato del nombre canónico se define mediante la plantilla `DOCUMENT_NAME_FORMAT` en `modules/output_manager.py` y es editable desde la GUI (pestaña Nomenclatura → "Formato del nombre canónico").

Formato por defecto:
```
{nombre}_{apellido1}_{apellido2},{nombre}_E{expediente}_{asistencia}{año_ini}{año_fin}_M
```

> **Nota:** el sufijo fijo (`_M`) se escribe directamente en la plantilla. No hay un campo `{sufijo}` en la GUI; `{sufijo}` se mantiene por retrocompatibilidad con configs antiguas pero no tiene chip ni control dedicado.

**Campos disponibles en la plantilla:**

| Campo | Descripción | Ejemplo |
|---|---|---|
| `{nombre}` | Nombre de pila, ASCII mayúsculas sin acentos | `ANA` |
| `{apellido1}` | Primer apellido | `MARTIN` |
| `{apellido2}` | Segundo apellido — se elimina junto a su separador si está vacío | `RUIZ` |
| `{expediente}` | Número de expediente de 5 dígitos | `16001` |
| `{documento}` | Número de DNI/NIE/pasaporte verificado | `87654321Z` |
| `{asistencia}` | Código de tipo de asistencia según `ASISTENCIA_CODE` | `P` |
| `{año_ini}` | Últimos 2 dígitos del año de inicio del curso | `25` |
| `{año_fin}` | Últimos 2 dígitos del año de fin del curso | `26` |

**Separadores permitidos entre campos:** `_` (guión bajo, incluyendo múltiples consecutivos `__`, `___`…) y `,` (coma). Texto fijo libre (p.ej. `_M`, `__2025`) puede escribirse directamente en la plantilla.

**Reglas de normalización:**
- Todos los valores se convierten a ASCII mayúsculas sin acentos; espacios y guiones → `_`; caracteres no alfanuméricos eliminados.
- Los campos vacíos (p. ej. `apellido2` null) se eliminan junto al separador inmediatamente anterior (solo uno).
- Los guiones bajos múltiples escritos literalmente en la plantilla se conservan tal cual.
- **La plantilla puede empezar por `_` o `__`** — los guiones bajos iniciales literales se preservan.
- Los separadores finales sobrantes se eliminan; las comas iniciales residuales también.
- El año se normaliza: mínimo el año en curso; `fin` siempre = `inicio + 1`.
- Si no hay ningún campo de nombre, se antepone `SINDATOS_` al resultado.

Ejemplos con el formato por defecto:
```
ANA_MARTIN_RUIZ,ANA_E16001_P2526_M              ← presencial, 2025-2026
CARLOS_LOPEZ,CARLOS_E15234_S2425_M              ← semipresencial, sin apellido2
SARA_EL_OUALI_BENALI,SARA_E16100_PA2425_M       ← parcial
```

El **grado (Medio/Superior)** no aparece en el nombre de carpeta — está en el JSON (`ciclo.grado`), pero sí puede usarse como nivel de jerarquía con `{grado}` en `output_folder_structure`.

## Jerarquía de carpetas output

Configurable desde GUI → Configuración → Nomenclatura → **"Estructura de carpetas output"**.

| Key config | Default | Descripción |
|---|---|---|
| `output_folder_structure` | `{ciclo_codigo}` | Template de subcarpetas entre `output/` y el expediente |
| `pending_reorganization` | `False` | `True` cuando hay expedientes pendientes de reorganizar |
| `skip_pending_reorganization` | `False` | Si `True`, no muestra avisos de reorganización pendiente |

**Módulo central: `modules/output_structure.py`**

| Función | Descripción |
|---|---|
| `resolve_hierarchy_path(template, result_json)` | `Path("DAW")` o `Path("SUPERIOR/DAW")` o `Path(".")` (plano) |
| `validate_structure_template(template)` | `(bool, msg)` — detecta rutas inválidas, campos desconocidos, nombres reservados |
| `render_structure_preview(template, samples)` | Árbol de texto para la UI |
| `cleanup_empty_dirs(start, stop_at)` | Limpia carpetas vacías hacia arriba tras mover un expediente |
| `reorganize_output(output_dir, template, on_progress, stop_event)` | Mueve todos los expedientes a la nueva jerarquía; idempotente y reanudable vía `.reorg_state.json` |

**Campos disponibles en el template:**

| Campo | Ejemplo | Notas |
|---|---|---|
| `{grado}` | `SUPERIOR` | `SUPERIOR` o `MEDIO`; vacío si desconocido → segmento omitido |
| `{ciclo_codigo}` | `DAW` | Código normalizado, siempre corto |
| `{ciclo_nombre}` | `DESARROLLO_DE_APLICACIONES_WEB` | Puede ser largo |
| `{año_ini}` | `25` | Últimos 2 dígitos del año de inicio |
| `{año_fin}` | `26` | Últimos 2 dígitos del año de fin |
| `{asistencia}` | `P` | P, S, L, PA |
| `{expediente}` | `16001` | Número normalizado |

**Invariantes:**
- `output/revision/` **siempre** fuera de jerarquía — expedientes en revisión carecen de campos completos.
- `output/_borrados/` **preserva** la jerarquía de origen al borrar.
- Template vacío → estructura plana retrocompatible.
- Segmentos vacíos (campo nulo) se descartan — el expediente cae a un nivel menos.
- Globals parcheados por `run_pipeline()`: `_om.OUTPUT_FOLDER_STRUCTURE` y `_os.OUTPUT_FOLDER_STRUCTURE`.
- Escaneo en `output.py` y `inicio.py` usa `rglob("datos.json")` excluyendo `_borrados`, `revision` y `debug`.

## Estructura de salida

Con jerarquía por defecto (`output_folder_structure = "{ciclo_codigo}"`):
```
output/
├── DAW/
│   └── {nombre_canonico}/
│       ├── {nombre_canonico}.pdf
│       ├── datos.json
│       ├── foto_carnet.jpg
│       ├── foto_dni.jpg
│       ├── foto.jpg
│       └── debug/
├── SMR/
│   └── {nombre_canonico}/
│       └── ...
├── _borrados/                  # Papelera: preserva jerarquía de origen
│   └── DAW/
│       └── {nombre_canonico}/
└── revision/                   # SIEMPRE fuera de jerarquía — estructura fija
    ├── dni/                    # DNI no extraído o erróneo
    ├── foto/                   # Foto no detectada
    └── datos/                  # Campo obligatorio ausente
```

Con `output_folder_structure = ""` (estructura plana, retrocompatible):
```
output/
├── {nombre_canonico}/
│   └── ...
└── revision/
```

## Anti-contaminación OCR en batch

El sistema toma múltiples medidas para evitar que el modelo reutilice datos de iteraciones anteriores:

1. **Prefijo de aislamiento** en todas las llamadas: "Analiza EXCLUSIVAMENTE la imagen adjunta..."
2. **Campo `system`** en OpenRouter con instrucción de aislamiento
3. **`context: []`** en Ollama para forzar contexto vacío
4. **Carpeta `debug/`** con las páginas extraídas para verificación manual
5. **Sección `datos_extraidos_dni`** en el JSON con los datos crudos del documento

## Modelo YOLO de caras

Ya descargado en `models/yolov8-face.pt`. Si se elimina o se cambia la ruta en `config.py`, el sistema usa automáticamente **Haar cascades de OpenCV** como fallback (sin descarga, menos preciso).

`detect_and_crop_face()` devuelve `(Image | None, int)` — recorte de cara y ángulo ganador (0, 90, 180 o 270).

**Uso del ángulo en páginas de documento de identidad:** si YOLO encontró la cara con rotación distinta de 0°, `main.py` re-analiza la misma página con esa rotación antes de extraer el texto, corrigiendo así DNIs escaneados en vertical.

**Fallback para páginas "otro":** si el LLM clasifica una página como `otro` pero YOLO detecta una cara, se reclasifica automáticamente como `foto_carnet`.

Fuente original: https://github.com/akanametov/yolo-face/releases

## Selección de mejor foto

Algoritmo en `photo_selector.py`:
1. Foto en **color** siempre gana sobre escala de grises (bonus de 10.000.000 puntos).
2. Entre fotos del mismo tipo (ambas color o ambas grises): gana la de mayor **nitidez** (varianza del Laplaciano sobre la versión en gris).

## Validación DNI/NIE

El módulo `dni_validator.py` implementa el checksum oficial español:

- **DNI**: 8 dígitos → módulo 23 → tabla `TRWAGMYFPDXBNJZSQVHLCKE`
- **NIE**: reemplaza X→0, Y→1, Z→2 en el primer carácter, luego igual que DNI
- **Pasaporte**: sin checksum, marcado como `no_verificable`
- **Corrección OCR posicional** (`_try_fix_ocr` + `_apply_subs`):
  - DNI: posiciones 0-7 → zona de dígitos (`O→0, I/L→1, B→8, S→5, G→6, Z→2, Q→0`); posición 8 → zona de letra
  - NIE: posición 0 → solo X/Y/Z, sin sustitución; posiciones 1-7 → zona de dígitos; posición 8 → zona de letra
  - La Z al inicio de un NIE nunca se convierte en 2
  - Dos pasadas: primero candidatos que pasan checksum completo, luego candidatos con formato válido

## Normalización de ciclos

`form_extractor.normalize_ciclo()` usa cuatro estrategias en orden:
1. Coincidencia exacta por código (`DAW`) o nombre completo.
2. Coincidencia por tokens — split por espacios/guiones/barras (`SMR - Sistemas` → `SMR`).
3. Coincidencia por contención — el código aparece como palabra dentro del texto (`daw presencial` → `DAW`).
4. Fuzzy matching con Levenshtein (umbral adaptativo: `max(4, len(texto)//3)`).

## Ciclos y grados

El campo `ciclo.grado` en el JSON distingue entre Grado Medio y Grado Superior:

**Grado Superior**: ASIR, DAM, DAW, AVGE, GAT, GIAT, CI, MP, AF, OPT, LCB

**Grado Medio**: AC, GA, CAE, SMR

## Flujo de llamadas al modelo

Todas las llamadas van por `utils/ollama_client.py → call_model()` que despacha según `MODO_DESARROLLO_PROD`.

1. **Página 1**: prompt FORM_PROMPT con esquema JSON completo + reintentos focalizados si faltan expediente, nombre o apellido2.
2. **Páginas 2..N**: prompt PAGE_PROMPT de clasificación + extracción de datos del documento de identidad. Si es `documento_identidad` y YOLO detectó la cara con rotación ≠ 0°, se hace una segunda llamada con la imagen ya rotada.

Todos los prompts incluyen instrucción de aislamiento al principio y al final. Reintentos con backoff exponencial (1s, 2s, 4s).

## Variable `{{ciclos}}` en el prompt de formulario

`FORM_PROMPT` (y su versión editable en la GUI) usa la variable `{{ciclos}}` como placeholder dinámico para la lista de ciclos formativos. Al procesar, `render_form_prompt(template)` en `modules/form_extractor.py` sustituye `{{ciclos}}` por el listado actual generado desde `CICLOS`, `GRADO_SUPERIOR` y `GRADO_MEDIO` (que `run_pipeline` parchea desde `config.json`).

**Formato renderizado:**
```
Ciclos posibles — GRADO SUPERIOR (grado = "superior"):
ASIR — Administración de Sistemas Informáticos en Red
DAM — Desarrollo de Aplicaciones Multiplataforma
...

Ciclos posibles — GRADO MEDIO (grado = "medio"):
AC — Actividades Comerciales
...
```

**Reglas de uso:**
- La lista de ciclos se edita exclusivamente en GUI → Configuración → **Ciclos**; no se escribe directamente en el prompt.
- Si el prompt guardado en `config.json` no contiene `{{ciclos}}` (configs antiguas con la lista hardcoded), `render_form_prompt` lo devuelve sin tocar — retrocompatibilidad garantizada.
- En la GUI → Configuración → Prompts LLM → **Formulario (página 1)**: botón **"Vista previa"** que muestra el prompt tal como se enviará al modelo, con `{{ciclos}}` ya sustituido por los ciclos actualmente configurados (incluyendo cambios no guardados en la pestaña «Ciclos»).

## Campos del `datos.json`

```json
{
  "expediente": "15234",
  "documento": {
    "tipo": "DNI|NIE|PASAPORTE|desconocido",
    "numero_extraido": "...",
    "numero_verificado": "...",
    "estado": "verificado|corregido|erroneo|no_verificable",
    "detalle_correccion": "..."
  },
  "nombre": "...",
  "apellido1": "...",
  "apellido2": "...",
  "ciclo": {
    "codigo": "DAW",
    "nombre_completo": "Desarrollo de Aplicaciones Web",
    "grado": "superior|medio",
    "texto_original": "texto tal como lo leyó el modelo"
  },
  "tipo_asistencia": "presencial|semipresencial|libre|parcial",
  "curso": { "inicio": "2024", "fin": "2025" },
  "cotejo_documento_identidad": {
    "realizado": true,
    "numero_coincide": true,
    "numero_usado": "dni|formulario|dni_corregido|formulario_dni_invalido",
    "nombre_coincide": true,
    "apellido1_coincide": true,
    "apellido2_coincide": true,
    "correcciones_aplicadas": []
  },
  "datos_extraidos_dni": {
    "nombre": "...",
    "apellido1": "...",
    "apellido2": "...",
    "numero_documento": "..."
  },
  "fotos": {
    "foto_carnet_encontrada": true,
    "foto_dni_encontrada": true,
    "foto_seleccionada": "carnet|dni",
    "detalle": {
      "foto_carnet": { "es_color": true,  "nitidez": 234.5 },
      "foto_dni":    { "es_color": false, "nitidez": 187.2 }
    }
  },
  "metadata": {
    "pdf_original": "15402-02.pdf",
    "procesado_en": "2026-05-07T12:05:58",
    "paginas_totales": 3,
    "nombre_documento": "ANA_MARTIN_RUIZ,ANA_E16001_P2526_M",
    "carpeta_salida": "/home/jevallo/workspace/IABD/dni2/output/...",
    "en_revision": false,
    "motivos_revision": [],
    "errores": []
  }
}
```

## Ficheros de log

El proceso escribe `procesado.log` en el directorio raíz además de stdout.

## Dependencias clave

- `pymupdf` (fitz): conversión PDF→imagen sin poppler externo
- `Pillow`: manipulación de imágenes
- `opencv-python`: Haar cascades, métricas de calidad, umbralización Otsu
- `ultralytics`: YOLO face detection
- `python-Levenshtein`: fuzzy matching de ciclos
- `requests`: cliente HTTP para Ollama y OpenRouter

## Tests rápidos desde línea de comandos

```bash
# Validación DNI con corrección OCR
.venv/bin/python -c "from modules.dni_validator import validate_and_correct; import json; print(json.dumps(validate_and_correct('1234567BA'), indent=2))"

# Normalización de ciclo
.venv/bin/python -c "from modules.form_extractor import normalize_ciclo; import json; print(json.dumps(normalize_ciclo('SMR - Sistemas'), indent=2))"

# Nombre canónico de carpeta
.venv/bin/python -c "
from modules.output_manager import build_document_name
print(build_document_name({'nombre':'Ana','apellido1':'Martin','apellido2':'Ruiz','expediente':'16001','tipo_asistencia':'presencial','ciclo':{'grado':'superior'},'curso':{'inicio':'2025','fin':'2026'},'documento':{'numero_verificado':'87654321Z'}}))
"

# Jerarquía de carpetas
.venv/bin/python -c "
from modules.output_structure import resolve_hierarchy_path, validate_structure_template
from pathlib import Path
data = {'ciclo':{'grado':'superior','codigo':'DAW'},'curso':{'inicio':'2025','fin':'2026'},
        'tipo_asistencia':'presencial','expediente':'16001','documento':{'numero_verificado':'12345678Z'}}
print(resolve_hierarchy_path('{ciclo_codigo}', data))         # DAW
print(resolve_hierarchy_path('{grado}/{ciclo_codigo}', data)) # SUPERIOR/DAW
print(validate_structure_template('{ciclo_codigo}'))          # (True, '✓ Template válido')
print(validate_structure_template('revision'))                # (False, ...)
"

# Pipeline completo CLI
.venv/bin/python main.py

# GUI (abre en navegador con Flet 0.85)
.venv/bin/python gui_main.py
```

## GUI — notas de implementación

> **REGLAS OBLIGATORIAS para código GUI:**
>
> 1. **Consultar siempre `FLET_GUIDE.md` antes de escribir o modificar cualquier control GUI.** Verificar el nombre exacto de eventos, propiedades y patrones para Flet 0.85. Los errores más comunes son usar el nombre de evento de otro control (p.ej. `on_change` en `ft.Dropdown` cuando el correcto es `on_select`) o llamar a métodos que no existen en esta versión.
>
> 2. **Si el control, servicio o patrón necesario NO está documentado en `FLET_GUIDE.md`:** consultar la documentación oficial en https://flet.dev/docs, crear un fichero `flet_docs/<NombreControl>.md` con las propiedades, eventos y ejemplos relevantes para este proyecto, y añadir una entrada en la sección "Índice de controles documentados" de `FLET_GUIDE.md` con un enlace a ese fichero. No asumir nombres de kwargs o métodos sin verificar en la documentación oficial.
>
> 3. **Feedback visual de interactividad — regla obligatoria:**
>    - `ft.Container` **no tiene `mouse_cursor`** en Flet 0.85 → siempre usar `ft.GestureDetector(mouse_cursor=..., content=container, on_hover=...)` para cambiar el cursor y el hover.
>    - **`on_hover` va en el `GestureDetector`, no en el Container interior.** El GestureDetector absorbe el evento hover y no lo propaga al hijo; si se pone `on_hover` en el Container interno no se dispara. El handler cambia `btn_inner.bgcolor` y llama a `btn_inner.update()`.
>    - **Elementos clickables habilitados**: envolver en `ft.GestureDetector(mouse_cursor=MC.CLICK, content=container, on_hover=_hover)`. En `_hover`, cambiar `container.bgcolor` a `c["hover"]` (entrar) o al color base (salir). Usar `e.data == "true"` para detectar entrada.
>    - **Elementos deshabilitados**: envolver en `ft.GestureDetector(mouse_cursor=MC.FORBIDDEN, ...)` y actualizar `gdetector.mouse_cursor` cuando cambie el estado. El color grisáceo lo gestiona Flet con `disabled=True`.
>    - **Para botones de acción principal (accent)**: usar siempre `accent_btn(text, *, icon, on_click, colors, disabled)` de `gui/flet_compat.py` — nunca `ft.ElevatedButton` directo. El helper usa `OutlinedButton` + `ButtonStyle` (fondo transparente, borde + texto `accent`, igual que "Vaciar papelera"). `ElevatedButton` bloqueaba el hover con su propio `MouseRegion`. Hover: ilumina borde + texto a `accent_hover`. Para acceder al `OutlinedButton` interno: `wrapper.content`. Para actualizar estado disabled: `btn.style = ft.ButtonStyle(color=c["text_dim"]/c["accent"], side=ft.BorderSide(1, c["border"]/c["accent"]))` — no usar `btn.bgcolor`/`btn.color` directos.
>    - Para `IconButton` con estado disabled dinámico, usar el helper `action_icon_btn(...)` de `gui/flet_compat.py`.
>    - **Colores de hover** en `gui/theme.py`: `"hover"` (containers sobre fondo normal), `"accent_hover"` (hover de botones accent — borde+texto más brillante), `"btn_hover_bg"` + `"btn_hover_text"` (reservados, no usados en `accent_btn`). No usar `card` ni `surface` como hover — son demasiado sutiles.
>    - Cuando el GestureDetector envuelve un Container con referencias persistentes (nav buttons, filter buttons), acceder a sus atributos como `gdetector.content.attr`, no directamente sobre el GestureDetector.
>
> Referencia del proyecto: `FLET_GUIDE.md` y `flet_docs/` — Documentación oficial: https://flet.dev/docs

**Flet 0.85+ breaking changes** (resueltos en `gui/flet_compat.py`):
- `ft.padding.all/symmetric/only()` → eliminados; usar `ft.Padding(left, top, right, bottom)`
- `ft.margin.symmetric/only()` → eliminados; usar `ft.Margin(left, top, right, bottom)`
- `ft.border.all/only()` → eliminados; usar `ft.Border(top=ft.BorderSide(...), ...)`
- `ft.icons.X` → `ft.Icons.X` (proxy de enum, no módulo con atributos)
- `ft.app()` → `ft.run()` (app() deprecated desde 0.80)
- `page.window_width` → `page.width` (o `page.window.width`)
- `page.window_width/height` → `page.window.width/height` o `page.window.maximized = True`
- `page.dialog = dlg` → **OBSOLETO**
- `page.overlay.append + dlg.open=True + page.update()` → funciona para mostrar, pero `page.update()` solo no cierra el diálogo en Flet 0.85
- `page.open(dlg)` / `page.close(dlg)` → **no existen en 0.85**
- `AlertDialog.on_dismiss` → **no usar**: se dispara antes que el `on_click` del botón, impidiendo que el handler se ejecute

**Patrón correcto para diálogos y snackbars (Flet 0.85):**
```python
# Mostrar diálogo:
page.show_dialog(dlg)

# Cerrar desde un botón:
on_click=lambda e: page.pop_dialog()

# Mostrar SnackBar:
page.show_dialog(ft.SnackBar(ft.Text("msg"), bgcolor=color, duration=ft.Duration(milliseconds=2500)))
```

O mediante los helpers de `gui/flet_compat.py`:
```python
from gui.flet_compat import dlg_open, dlg_close, snack_open, safe_update
dlg_open(page, dlg)
dlg_close(page)
snack_open(page, "Guardado", colors["success"])
safe_update(page)   # ← usar siempre en lugar de page.update() desde hilos de fondo
```

**Actualización de UI desde hilos de fondo — regla obligatoria:**
- `page.update()` llamado directamente desde un `threading.Thread` **no dispara el render** en Flet 0.85 desktop (falla silenciosamente por asyncio).
- Usar siempre `safe_update(page)` desde cualquier hilo de fondo (timer, worker, scan threads).
- Para llamar a `dlg_close`/`snack_open` al finalizar un hilo, envolverlas en `page.run_task(coro)`.
- Ver patrón completo en `FLET_GUIDE.md → §Actualización de UI desde hilos`.

**Arquitectura GUI:**
- `DNIApp` (gui/app.py): crea el layout, gestiona navegación y el toggle de tema. Al navegar fuera de Configuración con cambios sin guardar muestra diálogo de confirmación.
- **Navegación — 5 pestañas**: Inicio (simple) / Avanzada / Expedientes / Logs / Configuración. La app arranca siempre en "Inicio".
- **Botón recarga en cabecera**: en todas las vistas con `REFRESH`, el `IconButton` aparece **antes** del título de página (izquierda del `ft.Row`), no al final.
- Las vistas se instancian de forma perezosa al navegar: `InicioSimpleView`, `InicioView` (Avanzada), `ConfiguracionView`, `LogsView`, `OutputView`.
- `ProcessingManager` (gui/processing_manager.py) centraliza el estado de procesamiento en `app.processing_mgr`:
  - Gestiona el `ProcessingWorker`, contadores, log queue y el timer thread (cada 0.5 s).
  - Patrón observer: las vistas se registran con `add_observer(self)` y reciben callbacks: `on_proc_started()`, `on_pdf_start/done()`, `on_timer_tick()`, `on_finished()`.
  - El timer llama `safe_update(page)` una sola vez por tick (via `run_task`) garantizando actualizaciones en tiempo real desde el hilo del timer.
  - **ETA**: fórmula `max(0, avg - time_on_current) + avg × restantes`. Al arrancar, carga `avg_pdf_time` de `config.json` (EMA α=0.3 persistida entre sesiones); si no existe, parsea los últimos 5 logs. Al terminar, actualiza `avg_pdf_time` con EMA y guarda en `config.json`.
  - `InicioSimpleView` y `InicioView` (Avanzada) ambas se registran como observers y muestran progreso en tiempo real simultáneamente.
- `ProcessingWorker` corre en un `threading.Thread` con `threading.Event` para pausa/stop
- `run_pipeline()` en main.py parchea dinámicamente los globals de todos los módulos desde el `config_dict` de la GUI antes de procesar
- `config.json` se guarda junto al exe/script (portable); sobrevive reinstalaciones porque el Inno Setup lo respalda antes de instalar
- `gui/system_utils.py`: helpers `open_folder(path)` y `open_file(path)` para abrir carpetas/ficheros en el explorador del SO (Windows/Linux/Mac)

**Config de ciclos en GUI:**
Los ciclos se almacenan como `{"CODIGO": {"nombre": "...", "grado": "superior|medio"}}` en config.json.
`run_pipeline` descompone esto en `CICLOS`, `GRADO_SUPERIOR`, `GRADO_MEDIO` antes de llamar a form_extractor.

**Vista Inicio (`gui/views/inicio_simple.py`):**
- Vista de entrada simplificada, centrada en la pantalla (ancho fijo 560 px).
- Selectores de carpeta de entrada y salida con botones de picker y apertura en explorador.
- 4 cards de estadísticas: **Total** / **Pendientes** (sin procesar) / **Procesados** / **Revisión** (expedientes con `en_revision=True` en el output).
- Botón **"Procesar PDFs (N)"** activo solo si: carpeta entrada configurada ∧ carpeta salida configurada ∧ hay PDFs pendientes ∧ no hay proceso en curso. Procesa automáticamente todos los PDFs pendientes (sin selección manual).
- Sección de progreso (visible durante el proceso): barra de progreso, contador "X / N procesados", tiempo transcurrido, ETA.
- La vista escanea independientemente su propia `_output_index` para calcular las stats.
- **Diálogos de startup obligatorios** (`check_folders_on_startup()`): si la carpeta de PDFs o la de salida no están configuradas o no existen, aparece un diálogo modal sin botón Cancelar. Si el usuario cierra el FilePicker sin elegir nada, el mismo diálogo vuelve a aparecer. No se puede usar la app sin ambas rutas válidas. El check se lanza con 300 ms de delay (`page.run_task`) para garantizar que la ventana esté visible antes del primer diálogo. Los métodos usados en startup son `_show_input_folder_dialog_mandatory()` y `_show_output_folder_dialog_mandatory()`; los métodos con Cancelar (`_show_input_folder_dialog`, `_show_output_folder_dialog_if_needed`) se conservan para los botones manuales de la UI.
- Se registra como observer del `ProcessingManager`: recibe actualizaciones en tiempo real vía `on_timer_tick`.
- Al navegar de vuelta a esta vista (no primera vez), llama a `refresh()` para sincronizar las carpetas desde `app.cfg` y rescanear.

**Vista Avanzada (`gui/views/inicio.py`, clase `InicioView`):**
- Selector de carpeta de entrada y salida con botón "Abrir carpeta" (abre explorador del SO)
- Estadísticas: Total / Pendientes / Procesados / A procesar (seleccionados)
- Filtros de lista: Todos / Pendientes / Procesados
- Cada PDF muestra badge de estado: Pendiente / Correcto / Revisión / Procesando / Error
- **Estado calculado por cross-reference con output** (`_output_index`): el prefijo procesado es secundario. Al cargar, un hilo de fondo (`_scan_output_thread`) lee todos los `datos.json` del output y construye `{pdf_original → en_revision}`. La lista se muestra de inmediato; una barra de progreso "Cotejando con output… (N/M)" aparece encima de la lista mientras el hilo trabaja.
  - PDF cuyo nombre aparece en el índice y `en_revision=False` → "✅ Correcto"
  - PDF cuyo nombre aparece en el índice y `en_revision=True` → "⚠ Revisión"
  - PDF no encontrado en el índice → "⏳ Pendiente" (aunque tenga el prefijo — indica crash)
- **Auto-corrección de estado en disco**: `_scan_output_thread` aplica tres correcciones automáticas (ver sección "Marcado de PDFs procesados"). El botón Procesar permanece deshabilitado mientras `_scanning=True` para evitar race conditions.
- PDFs sin prefijo en disco pero en el índice de output aparecen como "✅ Correcto" (no como Pendiente).
- **Borrado desde Expedientes restaura pendiente**: al mover un expediente a la papelera desde la vista Expedientes, se llama `_scan_pdfs()` en ambas vistas (Inicio y Avanzada).
- Sección de procesamiento (visible durante el proceso):
  - Barra de progreso + contador X/Total
  - Contadores: Correctos / Revisión / Errores
  - Tiempo transcurrido + ETA en tiempo real (vía `ProcessingManager.on_timer_tick`)
  - Log en tiempo real con colores (INFO / WARNING / ERROR / SUCCESS), autoscroll, límite 1000 líneas
  - Botón Pausar/Reanudar (cambia icono y texto según estado)
  - Botón Detener (pide confirmación antes de parar)
- Al finalizar: diálogo flotante con resumen (procesados/correctos/revisión/errores/tiempo) y botón "Abrir carpeta"
- Se registra como observer del `ProcessingManager`. Al navegar a esta vista se llama `refresh()` para sincronizar carpetas y rescanear.

**Vista Configuración (`gui/views/configuracion.py`):**
- 6 tabs: Proveedor IA / Procesado / Nomenclatura / Ciclos / General / Prompts LLM
- **Protección con contraseña:** la sección de configuración está siempre bloqueada al navegar a ella. El candado en la cabecera indica el estado:
  - Candado rojo = bloqueado. Pulsar abre diálogo de contraseña.
  - Sin contraseña configurada: el primer clic pide crear la contraseña (dos campos + confirmación).
  - Con contraseña: pide introducirla; el hash MD5 se compara con `config_password_hash` en `config.json`.
  - Candado verde = desbloqueado (esta sesión). Pulsar vuelve a bloquear.
  - Tras autenticar: `ConfiguracionView` se reconstruye con `unlocked=True`; el estado persiste mientras la vista no se destruya.
- Detecta cambios sin guardar (`_dirty = True` al modificar cualquier campo; `_mark_dirty()` se conecta a `on_change` de cada campo)
- Botón "Restaurar guardados": recarga config.json descartando cambios actuales sin resetear a defaults
- Botón "Valores por defecto": resetea a `get_defaults()` — que carga `config_default.json` si existe, si no usa los valores hardcodeados
- Botón "Guardar como defaults": guarda la config actual en `config_default.json` (visible solo cuando desbloqueado)
- La intercepción de navegación con cambios sin guardar (`_show_unsaved_dialog`) está en `app.py`, no en la vista
- Al navegar a otra sección con `_dirty=True`: diálogo "Cambios sin guardar" con opciones Guardar / Descartar / Cancelar
- SnackBar de confirmación al guardar

**Tab Procesado:**
- Incluye el campo **"Prefijo de PDFs procesados"** (por defecto `_!_`). Al guardar con un prefijo distinto, `_rename_prefix_files()` renombra en la carpeta de entrada todos los PDFs que empiecen por el prefijo antiguo.

**Tab Nomenclatura — Formato del nombre canónico:**
- No hay campo de sufijo separado: el sufijo se escribe directamente en la plantilla (ej. `..._M` al final).
- Campo de texto editable (fuente monospace) con la plantilla `DOCUMENT_NAME_FORMAT`
- Chips con tooltip para cada campo: `{nombre}`, `{apellido1}`, `{apellido2}`, `{expediente}`, `{documento}`, `{asistencia}`, `{año_ini}`, `{año_fin}`
- Separadores permitidos: `_` (incluyendo múltiples consecutivos `__`) y `,`. Texto literal libre (ej. `_M`, `__`) se puede incluir en cualquier posición.
- Los guiones bajos múltiples literales se conservan tanto en vista previa como al generar el nombre real (se eliminó el colapso `_{2,}→_` de `_apply_fmt` y `build_document_name`).
- Validación en tiempo real: detecta campos desconocidos y exige `{expediente}`; muestra ✓/✗ con mensaje
- Vista previa en vivo con datos de ejemplo (con y sin `{apellido2}`)

**Tab Nomenclatura — Estructura de carpetas output:**
- Card adicional debajo del nombre canónico.
- Campo editable (monospace) con `output_folder_structure`; chips para `{grado}`, `{ciclo_codigo}`, `{ciclo_nombre}`, `{año_ini}`, `{año_fin}`, `{asistencia}`, `{expediente}`.
- Validación en tiempo real (campos desconocidos, nombres reservados `revision`/`_borrados`/`debug`, `//`, `/` inicial o final, `..`).
- Vista previa en árbol monospace con 3 expedientes de ejemplo.
- Botón **"Reorganizar output"** — mueve todos los expedientes existentes a la nueva jerarquía. Diálogo con barra de progreso, contador "N / M expedientes" en tiempo real, soporte de cancelación y reanudación (`.reorg_state.json`). El botón solo se activa si hay `output_dir` configurado y el template es válido y no vacío.
- `_has_reorganized_this_session`: flag que indica si el usuario pulsó el botón ANTES de guardar; si es `True`, al guardar se limpia `pending_reorganization`; si es `False`, se pone `True`.
- Al guardar con estructura modificada sin haber reorganizado: diálogo que ofrece "Mantener así" o "Cambiar carpeta output".
- `skip_pending_reorganization` checkbox en Tab General → card "Reorganización de output" para suprimir avisos.
- Startup snackbar en `inicio_simple.py` si `pending_reorganization=True` y `skip_pending_reorganization=False`.

**`gui/config_manager.py` — Gestión de configuración:**
- `CONFIG_FILE` = `config.json` junto al ejecutable/script — única fuente de verdad en runtime
- `CONFIG_DEFAULT_FILE` = `config_default.json` junto al ejecutable/script — base personalizable para "Valores por defecto"
- `load_config()`: merge de DEFAULTS hardcodeados + claves de `config.json`
- `save_config(cfg)`: escribe `config.json`
- `save_default_config(cfg)`: escribe `config_default.json`
- `get_defaults()`: si existe `config_default.json`, devuelve merge de DEFAULTS + ese fichero; si no, devuelve DEFAULTS hardcodeados
- Claves relevantes en `DEFAULTS`: `processed_prefix` (`"_!_"`), `processed_prefix_history` (`[]`), `avg_pdf_time` (float, persistido entre sesiones para ETA inicial), `config_password_hash` (`""`), `document_name_format` (sin `{sufijo}`), `output_folder_structure` (`"{ciclo_codigo}"`), `pending_reorganization` (`False`), `skip_pending_reorganization` (`False`)

**Tab Prompts LLM (`gui/views/configuracion.py → _tab_prompts`):**
- 5 prompts editables con área de texto multiline monospace y botón "Restaurar por defecto" individual:
  1. **Formulario (p.1)** — `prompt_form`: extrae expediente, DNI/NIE, nombre, ciclo, asistencia y curso
     - Contiene `{{ciclos}}` que se renderiza dinámicamente al procesar (ver sección "Variable `{{ciclos}}`")
     - Botón **"Vista previa"** muestra el prompt con `{{ciclos}}` ya sustituido por los ciclos actuales
     - Nota informativa en la card explica que los ciclos se editan en la pestaña «Ciclos»
  2. **Reintento: Expediente** — `prompt_retry_expediente`: focaliza en la esquina superior derecha
  3. **Reintento: Nombre y apellidos** — `prompt_retry_nombres`: pide los 3 campos por separado
  4. **Reintento: Segundo apellido** — `prompt_retry_apellido2`: busca solo el campo Apellido 2
  5. **Clasificador de páginas (p.2+)** — `prompt_page`: clasifica y extrae datos del documento de identidad
- Los prompts se guardan en `config.json` y se parchean en `run_pipeline` antes de procesar
- Los defaults son los textos definidos en `modules/form_extractor.py` y `modules/page_analyzer.py`
- `render_form_prompt(template)` en `form_extractor.py` hace la sustitución de `{{ciclos}}` antes de llamar al modelo

**Vista Logs (`gui/views/logs.py`):**
- Lista de ejecuciones (ficheros `procesado_YYYY-MM-DD_HH-MM-SS.log`) filtrable por Año / Mes / Día
- Panel derecho con contenido del log seleccionado, coloreado por nivel
- Buscador case-insensitive dentro del log seleccionado
- Botones "Borrar actual" y "Borrar todos" con confirmación (eliminan el fichero físico)

**Vista Expedientes (`gui/views/output.py`):**
- Lee todos los `datos.json` de la carpeta de salida con `rglob("datos.json")` — funciona con cualquier profundidad de jerarquía.
- Exclusiones del scan: carpetas `_borrados`, `revision` y `debug`.
- Tabla con columnas: Expediente / DNI / Nombre / Apellido1 / Apellido2 / Ciclo / Año / Asistencia / Estado
- Filtros: Estado (todos/correcto/revisión) / Ciclo / Año / Asistencia / búsqueda libre
- Por fila: botón PDF / botón JSON (diálogo con JSON formateado + botón abrir archivo) / botón Foto / botón Abrir carpeta / botón Borrar / botón Revisar (abre `ReviewDialog`)
- **`ReviewDialog` (`gui/views/review_dialog.py`):** modal de edición de un expediente. Título con botón icono PDF (abre el PDF en el visor del sistema vía `open_file()`; desactivado si no existe) y badge de estado. Formulario izquierdo con todos los campos editables; panel derecho con foto y previsualización de página 1. Detecta conflicto de carpeta al guardar y muestra diálogo de sobrescritura.
- Borrar mueve la carpeta del expediente a `{output_dir}/_borrados/<ruta_relativa>/` preservando la jerarquía de origen; llama a `cleanup_empty_dirs()` para eliminar carpetas vacías. El `datos.json` se lee **antes** de `shutil.move` (no después) para poder strip el prefijo procesado del PDF original.
- Botón papelera en cabecera: `"Vaciar papelera (N)"` cuando `_count_trash` devuelve N>0; `"Vaciar papelera"` cuando hay archivos pero sin `datos.json` (estructura antigua, devuelve -1); `"Papelera vacía"` (deshabilitado) cuando vacío. El `GestureDetector` wrapper siempre empieza `visible=True` — evita bug Flet 0.85 donde `visible:False→True` renderiza estado de construcción del hijo en vez del estado actualizado. Al vaciar elimina `_borrados/` permanentemente con confirmación.
- La carpeta `_borrados/` es ignorada por `_load_expedientes` y por `_build_output_index`.
- `_rebuild_table()` llama a `self._table_container.update()` al final para forzar el re-render en Flet 0.85 independientemente del ciclo de actualización del diálogo.
- Al aprobar un expediente de revisión (`ReviewDialog → Guardar`), la carpeta de destino se calcula con `resolve_hierarchy_path(output_folder_structure, datos)` — el expediente aprobado va directamente a la jerarquía configurada.

## Build e Instalador

### Compilar la aplicación (PyInstaller)

```bat
build\build.bat
```

Genera `dist\ExpedienteExtractor\ExpedienteExtractor.exe` y luego llama a Inno Setup si está disponible.

### Compilar solo el instalador (Inno Setup) con versión incremental

```bat
make installer          :: desde make.bat (Windows)
make installer          # desde Makefile (Windows con GNU Make)
```

Ambos invocan `build\bump_installer.ps1`, que ejecuta el build completo:

1. **Localiza `iscc.exe`** (PATH, `%ProgramFiles(x86)%`, `%ProgramFiles%`, `%LOCALAPPDATA%`). Si no está instalado, **descarga e instala Inno Setup 6 automáticamente** (silent install).
2. **Incrementa la versión** en `build/installer.iss`: tercer segmento de build (`"1.0"` → `"1.0.1"` → `"1.0.2"` …).
3. **Llama a `build\build.bat`** con la variable `NOPAUSE=1` (suprime los `pause` interactivos), que hace:
   - Compila la app con **PyInstaller** (`dist\ExpedienteExtractor\`)
   - Ejecuta **iscc** y genera `dist\ExpedienteExtractorSetup.exe`

Para cambiar la versión base (`1.0`) hay que editarla manualmente en `installer.iss`; el script solo toca el tercer segmento.

`build\build.bat` ejecutado manualmente sigue haciendo `pause` al final (comportamiento no cambia).

## Testing

### Ejecutar tests

**Linux / Mac** — vía `make` (requiere GNU Make):

```bash
make          # muestra lista de targets disponibles
make test     # suite completa
make unit     # solo unit tests (rápidos, sin efectos secundarios)
make integration  # solo integration tests
make fast     # todo excepto @slow
make cov      # suite completa + reporte de cobertura HTML
make clean    # limpia .coverage, htmlcov, __pycache__
```

**Windows** — vía `make.bat` (sin instalar nada adicional):

```bat
make          :: muestra lista de targets disponibles
make test
make unit
make integration
make fast
make cov
make clean
```

Vía **pytest directo**:

```bash
# Suite completa
.venv/bin/python -m pytest tests/ -v

# Solo unit tests (rápidos, sin efectos secundarios)
.venv/bin/python -m pytest tests/unit/ -v -m unit

# Solo integration tests
.venv/bin/python -m pytest tests/integration/ -v -m integration

# Excluir tests lentos (PDF real, YOLO/Haar real)
.venv/bin/python -m pytest tests/ -v -m "not slow"

# Con cobertura
.venv/bin/python -m pytest tests/ --cov=modules --cov=utils --cov-report=term-missing
```

### Estructura

```
tests/
├── conftest.py              # Fixtures globales: mock LLM, imágenes PIL, JSONs base
├── unit/                    # Lógica pura — sin mocks de FS ni LLM
│   ├── test_dni_validator.py
│   ├── test_normalize_ciclo.py
│   ├── test_cross_check.py
│   ├── test_output_manager.py
│   ├── test_output_structure.py
│   └── test_photo_selector.py
├── integration/             # Requieren mock LLM o tmp_path
│   ├── test_form_extractor.py
│   ├── test_page_analyzer.py
│   ├── test_pipeline.py
│   ├── test_pdf_processor.py  # @slow — usa tests/fixtures/sample.pdf
│   ├── test_photo_detector.py # @slow — usa tests/fixtures/sample_face.jpg + Haar
│   └── test_save_results.py
└── fixtures/
    ├── sample.pdf           # Copia de pdf/15402-02.pdf
    ├── sample_face.jpg      # Copia de output/.../foto.jpg
    ├── sample_jsons.py      # JSONs de resultado (válido, revisión, incompleto)
    └── sample_images.py     # Factorías PIL (color, grises, borroso, nítido)
```

### Reglas obligatorias

> **REGLAS DE MANTENIMIENTO DE TESTS:**
>
> 1. **Nueva funcionalidad en `modules/` o `utils/` → test obligatorio.** Añadir al menos un test en `tests/unit/` o `tests/integration/` según corresponda. La tarea no se considera completa hasta que el test existe y pasa.
>
> 2. **Modificación que afecta a un test → actualizar el test en la misma entrega.** No dejar tests en rojo ni desactivados.
>
> 3. **Ejecutar suite completa al terminar cualquier modificación:**
>    ```bash
>    .venv/bin/python -m pytest tests/ -v
>    ```
>    Si hay fallos, resolver antes de marcar la tarea como terminada.
>
> 4. **Modificación de `Makefile` → actualizar `make.bat` en la misma entrega.** Ambos ficheros deben tener exactamente los mismos targets con comportamiento equivalente. `Makefile` usa sintaxis GNU Make; `make.bat` replica cada target con comandos `cmd.exe` nativos (`.venv\Scripts\python.exe`, `rd /s /q`, `del /f`). No se considera completa una modificación del `Makefile` hasta que `make.bat` refleja los mismos cambios.
