import json
import sys
from copy import deepcopy
from pathlib import Path

from modules.form_extractor import (
    FORM_PROMPT, EXPEDIENTE_RETRY_PROMPT, NOMBRES_RETRY_PROMPT, APELLIDO2_RETRY_PROMPT,
)
from modules.page_analyzer import PAGE_PROMPT


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


CONFIG_FILE = _app_root() / "config.json"
CONFIG_DEFAULT_FILE = _app_root() / "config_default.json"

_CICLOS_DEFAULT = {
    "ASIR": {"nombre": "Administración de Sistemas Informáticos en Red", "grado": "superior"},
    "DAM":  {"nombre": "Desarrollo de Aplicaciones Multiplataforma",      "grado": "superior"},
    "DAW":  {"nombre": "Desarrollo de Aplicaciones Web",                  "grado": "superior"},
    "AVGE": {"nombre": "Agencias de Viajes y Gestión de Eventos",         "grado": "superior"},
    "GAT":  {"nombre": "Gestión de Alojamientos Turísticos",              "grado": "superior"},
    "GIAT": {"nombre": "Guía, Información y Asistencia Turística",        "grado": "superior"},
    "CI":   {"nombre": "Comercio Internacional",                          "grado": "superior"},
    "MP":   {"nombre": "Marketing y Publicidad",                          "grado": "superior"},
    "AF":   {"nombre": "Administración y Finanzas",                       "grado": "superior"},
    "OPT":  {"nombre": "Óptica de Anteojería",                            "grado": "superior"},
    "LCB":  {"nombre": "Laboratorio Clínico y Biomédico",                 "grado": "superior"},
    "AC":   {"nombre": "Actividades Comerciales",                         "grado": "medio"},
    "GA":   {"nombre": "Gestión Administrativa",                          "grado": "medio"},
    "CAE":  {"nombre": "Cuidados Auxiliares de Enfermería",               "grado": "medio"},
    "SMR":  {"nombre": "Sistemas Microinformáticos y Redes",              "grado": "medio"},
}

DEFAULTS: dict = {
    "theme": "dark",
    "input_dir": "",
    "output_dir": "",
    "modo_desarrollo_prod": False,
    "debug_reprocess": False,
    "pdf_limit": None,
    "modo_log_fichero": "nuevo",
    "ollama_url": "http://ollama.iabd.cip.fpmislata.com:80/api/generate",
    "ollama_model": "llama3.2-vision:11b",
    "ollama_timeout": 120,
    "ollama_max_retries": 3,
    "openrouter_url": "https://openrouter.ai/api/v1/chat/completions",
    "openrouter_model": "qwen/qwen3-vl-8b-instruct",
    "openrouter_api_key": "",
    "pdf_dpi": 200,
    "yolo_confidence": 0.35,
    "face_padding_ratio": 0.35,
    "overwrite_existing": True,
    "max_pages_to_analyze": 6,
    "pasar_a_grises": True,
    "document_name_suffix": "_M",
    "processed_prefix": "_!_",
    "processed_prefix_history": [],
    "config_password_hash": "",
    "asistencia_code": {
        "presencial": "P",
        "semipresencial": "S",
        "libre": "L",
        "parcial": "PA",
    },
    "ciclos": deepcopy(_CICLOS_DEFAULT),
    "document_name_format": (
        "{nombre}_{apellido1}_{apellido2},{nombre}_E{expediente}_{asistencia}{año_ini}{año_fin}_M"
    ),
    # Template de jerarquía de carpetas entre output/ y la carpeta del expediente.
    # Vacío = estructura plana (retrocompatible). "/" separa niveles.
    # Campos válidos: {grado}, {ciclo_codigo}, {ciclo_nombre}, {año_ini}, {año_fin},
    #                 {asistencia}, {expediente}, {documento}
    "output_folder_structure":     "{ciclo_codigo}",
    # True mientras haya una reorganización pendiente o interrumpida
    "pending_reorganization":      False,
    # Si True, no mostrar avisos al guardar cuando haya reorganización pendiente
    "skip_pending_reorganization": False,
    "prompt_form":              FORM_PROMPT,
    "prompt_retry_expediente":  EXPEDIENTE_RETRY_PROMPT,
    "prompt_retry_nombres":     NOMBRES_RETRY_PROMPT,
    "prompt_retry_apellido2":   APELLIDO2_RETRY_PROMPT,
    "prompt_page":              PAGE_PROMPT,
}


def load_config() -> dict:
    cfg = deepcopy(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for k, v in saved.items():
                if k not in DEFAULTS:
                    continue
                if isinstance(DEFAULTS[k], dict) and isinstance(v, dict):
                    merged = deepcopy(DEFAULTS[k])
                    merged.update(v)
                    cfg[k] = merged
                else:
                    cfg[k] = v
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def save_default_config(cfg: dict) -> None:
    CONFIG_DEFAULT_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_defaults() -> dict:
    base = deepcopy(DEFAULTS)
    if CONFIG_DEFAULT_FILE.exists():
        try:
            saved = json.loads(CONFIG_DEFAULT_FILE.read_text(encoding="utf-8"))
            for k, v in saved.items():
                if k not in DEFAULTS:
                    continue
                if isinstance(DEFAULTS[k], dict) and isinstance(v, dict):
                    merged = deepcopy(DEFAULTS[k])
                    merged.update(v)
                    base[k] = merged
                else:
                    base[k] = v
        except Exception:
            pass
    return base


def get_logs_dir(cfg: dict | None = None) -> Path:
    return _app_root() / "logs"
