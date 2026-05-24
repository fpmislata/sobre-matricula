import os
from pathlib import Path

# Cargar .env si existe (sin dependencia externa)
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

INPUT_DIR = Path("/home/jevallo/workspace/IABD/dni2/pdf")
OUTPUT_DIR = Path("/home/jevallo/workspace/IABD/dni2/output")
REVIEW_DIR = OUTPUT_DIR / "revision"

# ── Modo de ejecución ──────────────────────────────────────────────────────────
# True  = producción  → usa Ollama (red interna del centro)
# False = desarrollo  → usa OpenRouter (acceso externo con API key)
MODO_DESARROLLO_PROD = False
# ── Flags de depuración ────────────────────────────────────────────────────────
# Si True, reprocesa PDFs aunque ya tengan el prefijo _!_ (ya procesados)
DEBUG_REPROCESS = True
# Número máximo de PDFs a procesar por ejecución (None = todos)
PDF_LIMIT = None

# ── Log a fichero ──────────────────────────────────────────────────────────────
# "nuevo"      → sobreescribe procesado.log en cada ejecución
# "acumular"   → añade al final del fichero existente
# "desactivado"→ no genera fichero de log (solo stdout)
MODO_LOG_FICHERO = "nuevo"


# ── Ollama ─────────────────────────────────────────────────────────────────────
OLLAMA_URL = "http://ollama.iabd.cip.fpmislata.com:80/api/generate"
OLLAMA_MODEL = "llama3.2-vision:11b"
OLLAMA_TIMEOUT = 120
OLLAMA_MAX_RETRIES = 3

# ── OpenRouter ─────────────────────────────────────────────────────────────────
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "qwen/qwen3-vl-8b-instruct"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

PDF_DPI = 200
YOLO_MODEL_PATH = Path("/home/jevallo/workspace/IABD/dni2/models/yolov8-face.pt")
YOLO_CONFIDENCE = 0.35
FACE_PADDING_RATIO = 0.35

OVERWRITE_EXISTING = True
MAX_PAGES_TO_ANALYZE = 6

# ── Preprocesado de imagen ─────────────────────────────────────────────────────
# Si True, convierte la página 1 a escala de grises + umbral Otsu antes del OCR
PASAR_A_GRISES = True



CICLOS = {
    "ASIR": "Administración de Sistemas Informáticos en Red",
    "DAM":  "Desarrollo de Aplicaciones Multiplataforma",
    "DAW":  "Desarrollo de Aplicaciones Web",
    "AVGE": "Agencias de Viajes y Gestión de Eventos",
    "GAT":  "Gestión de Alojamientos Turísticos",
    "GIAT": "Guía, Información y Asistencia Turística",
    "CI":   "Comercio Internacional",
    "MP":   "Marketing y Publicidad",
    "AF":   "Administración y Finanzas",
    "OPT":  "Óptica de Anteojería",
    "LCB":  "Laboratorio Clínico y Biomédico",
    "AC":   "Actividades Comerciales",
    "GA":   "Gestión Administrativa",
    "CAE":  "Cuidados Auxiliares de Enfermería",
    "SMR":  "Sistemas Microinformáticos y Redes",
}

GRADO_SUPERIOR = {"ASIR", "DAM", "DAW", "AVGE", "GAT", "GIAT", "CI", "MP", "AF", "OPT", "LCB"}
GRADO_MEDIO    = {"AC", "GA", "CAE", "SMR"}

# ── Nomenclatura de ficheros y carpetas ────────────────────────────────────────
# Formato: {nombre}_{apellido1}_{apellido2},{nombre}_E{expediente}_{asistencia}{año_ini}{año_fin}{sufijo}
# Ejemplo: JESUS_VALVERDE_LLOBREGAT,JESUS_E15001_P2526_M
# Código de 1-2 letras para cada tipo de asistencia (aparece antes del año en el nombre)
ASISTENCIA_CODE = {
    "presencial":     "P",
    "semipresencial": "S",
    "libre":          "L",
    "parcial":        "PA",
}

# Sufijo fijo al final del nombre de carpeta/fichero
DOCUMENT_NAME_SUFFIX = "_M"
