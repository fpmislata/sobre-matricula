# ExpedienteExtractor

Aplicación Windows que procesa PDFs escaneados de matrículas de FP (Formación Profesional). Extrae datos del formulario mediante OCR con visión (LLaMA), valida el DNI, detecta y recorta fotos de carnet, y organiza los expedientes en carpetas.

---

## Requisitos previos

- **Python 3.12** — [python.org/downloads](https://www.python.org/downloads/)
- **Git**
- **Windows 10/11** (el instalador es solo para Windows; la app en Python también funciona en Linux/Mac)
- **Inno Setup 6** *(solo para generar el instalador)* — se instala automáticamente si no está presente al ejecutar `make installer`

---

## Configurar el entorno de desarrollo

```bat
REM 1. Clonar el repositorio
git clone <url-del-repo>
cd sobre-matricula

REM 2. Crear el entorno virtual
python -m venv .venv

REM 3. Instalar dependencias
.venv\Scripts\pip install -r requirements.txt
```

### Variables de entorno

Crea un fichero `.env` en la raíz del proyecto (no se sube al repositorio):

```env
OPENROUTER_API_KEY=sk-or-...
```

Esta clave se usa en **modo desarrollo** (OpenRouter) cuando `MODO_DESARROLLO_PROD = False` en `config.py`. En producción la app usa el servidor Ollama interno del centro.

### Modelo YOLO

El modelo `models/yolov8-face.pt` ya está incluido en el repositorio. Si lo borras accidentalmente, el sistema usará automáticamente los Haar cascades de OpenCV como fallback.

---

## Ejecutar la aplicación

```bat
REM GUI (interfaz gráfica)
.venv\Scripts\python gui_main.py

REM Pipeline CLI (sin interfaz)
.venv\Scripts\python main.py
```

Al arrancar la GUI por primera vez pedirá seleccionar la carpeta de PDFs de entrada y la carpeta de salida.

---

## Ejecutar los tests

```bat
make test          :: suite completa
make unit          :: solo tests unitarios (rápidos)
make integration   :: solo tests de integración
make fast          :: todo excepto los lentos (@slow)
make cov           :: suite + reporte de cobertura HTML en htmlcov/
make clean         :: limpia .coverage, htmlcov, __pycache__
```

O directamente con pytest:

```bat
.venv\Scripts\python -m pytest tests/ -v
```

---

## Generar el instalador (Windows)

El proceso completo (tests → PyInstaller → Inno Setup) se lanza con un solo comando:

```bat
make installer
```

Esto ejecuta `build\bump_installer.ps1`, que:

1. Localiza `iscc.exe` (Inno Setup). Si no está instalado, **lo descarga e instala automáticamente**.
2. Incrementa el número de build en `build/installer.iss` (`1.0` → `1.0.1` → `1.0.2` …).
3. Ejecuta `build\build.bat`, que:
   - Pasa los tests (`make fast`). Si alguno falla, pregunta si continuar.
   - Compila la app con **PyInstaller** → `dist\ExpedienteExtractor\`
   - Genera el instalador con **Inno Setup** → `dist\ExpedienteExtractor_1.0.X.exe`

Para cambiar la versión base (`1.0`) edítala manualmente en `build/installer.iss`; el script solo toca el tercer segmento.

### Compilar solo la app (sin instalador)

```bat
build\build.bat
```

Genera `dist\ExpedienteExtractor\ExpedienteExtractor.exe` y llama a Inno Setup si está disponible.

---

## Estructura principal

```
.
├── main.py              # Pipeline CLI / expone run_pipeline() para la GUI
├── gui_main.py          # Punto de entrada GUI (Flet)
├── config.py            # Configuración global
├── modules/             # Lógica de procesamiento (OCR, DNI, fotos, output…)
├── utils/               # Cliente LLM, utilidades de imagen
├── gui/                 # Interfaz gráfica (vistas, tema, estado)
├── models/              # yolov8-face.pt
├── tests/               # Suite de tests (unit + integration)
├── build/               # Scripts de compilación e instalador
├── requirements.txt
└── .env                 # API key OpenRouter (no commiteado)
```
