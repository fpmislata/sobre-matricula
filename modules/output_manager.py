import json
import re
import shutil
import logging
import unicodedata
from datetime import datetime
from pathlib import Path
from PIL import Image
from config import (
    OUTPUT_DIR, REVIEW_DIR, OVERWRITE_EXISTING,
    ASISTENCIA_CODE, DOCUMENT_NAME_SUFFIX, DEBUG_REPROCESS,
)
from modules.output_structure import resolve_hierarchy_path

# Global parcheado por run_pipeline() desde config_dict
OUTPUT_FOLDER_STRUCTURE: str = "{ciclo_codigo}"

# Campos obligatorios para no ir a revisión
_CAMPOS_OBLIGATORIOS = [
    ("nombre",         lambda j: j.get("nombre")),
    ("apellido1",      lambda j: j.get("apellido1")),
    ("apellido2",      lambda j: j.get("apellido2")),
    ("ciclo",          lambda j: (j.get("ciclo") or {}).get("codigo")),
    ("tipo_asistencia",lambda j: j.get("tipo_asistencia")),
    ("curso_inicio",   lambda j: (j.get("curso") or {}).get("inicio")),
    ("curso_fin",      lambda j: (j.get("curso") or {}).get("fin")),
    ("foto",           lambda j: (j.get("fotos") or {}).get("foto_seleccionada")),
]


DOCUMENT_NAME_FORMAT = (
    "{nombre}_{apellido1}_{apellido2},{nombre}_E{expediente}_{asistencia}{año_ini}{año_fin}{sufijo}"
)


# ── Utilidades de nombre ───────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s))
    ascii_s = nfkd.encode("ascii", "ignore").decode("ascii").upper()
    ascii_s = re.sub(r"[\s\-]+", "_", ascii_s)
    ascii_s = re.sub(r"[^A-Z0-9_]", "", ascii_s)
    return re.sub(r"_+", "_", ascii_s).strip("_")


def _year2(year_str) -> str:
    s = str(year_str or "")
    return s[-2:] if len(s) >= 2 else "XX"


def _normalize_curso_year(year_raw) -> str | None:
    """Expande año a 4 dígitos y garantiza que no esté en el pasado."""
    if year_raw is None:
        return None
    s = str(year_raw).strip()
    if not s.isdigit():
        return None
    y = int(s)
    if y < 100:
        y += 2000
    current = datetime.now().year
    if y < current:
        y = current
    return str(y)


def _build_curso(inicio_raw, fin_raw) -> dict:
    inicio = _normalize_curso_year(inicio_raw)
    fin = str(int(inicio) + 1) if inicio else None
    return {"inicio": inicio, "fin": fin}


def build_document_name(result_json: dict) -> str:
    nombre    = _normalize(result_json.get("nombre")    or "")
    apellido1 = _normalize(result_json.get("apellido1") or "")
    apellido2 = _normalize(result_json.get("apellido2") or "")
    expediente = _normalize(result_json.get("expediente") or "SINDATO")

    asistencia_raw = (result_json.get("tipo_asistencia") or "").lower()
    asistencia = ASISTENCIA_CODE.get(asistencia_raw, "X")

    curso = result_json.get("curso") or {}
    anio_ini = _year2(curso.get("inicio"))
    anio_fin = _year2(curso.get("fin"))

    doc_info = result_json.get("documento") or {}
    num_doc = doc_info.get("numero_verificado") or doc_info.get("numero_extraido") or ""
    documento = _normalize(num_doc)

    fields = {
        "nombre":     nombre,
        "apellido1":  apellido1,
        "apellido2":  apellido2,
        "expediente": expediente,
        "documento":  documento,
        "asistencia": asistencia,
        "año_ini":    anio_ini,
        "año_fin":    anio_fin,
        "sufijo":     DOCUMENT_NAME_SUFFIX,
    }

    result = DOCUMENT_NAME_FORMAT
    for key, val in fields.items():
        if not val:
            result = re.sub(r'[_,]?\{' + re.escape(key) + r'\}', '', result)
        else:
            result = result.replace(f'{{{key}}}', val)

    result = re.sub(r'_,', ',', result)
    result = re.sub(r',_', ',', result)
    result = result.strip('_,')

    if not (nombre or apellido1 or apellido2):
        fallback = f"SINDATOS_E{expediente}_{asistencia}{anio_ini}{anio_fin}{DOCUMENT_NAME_SUFFIX}"
        result = ("SINDATOS_" + result).lstrip("_") if result else fallback

    return result or f"SINDATOS_E{expediente}_{asistencia}{anio_ini}{anio_fin}{DOCUMENT_NAME_SUFFIX}"


def _fallback_name(pdf_path: Path) -> str:
    return _normalize(pdf_path.stem) or pdf_path.stem.upper()


# ── Revisión por campos obligatorios ──────────────────────────────────────────

def check_campos_obligatorios(result_json: dict) -> list[str]:
    """Devuelve lista de motivos de revisión. Vacía si todo está correcto."""
    motivos = []
    for nombre_campo, extractor in _CAMPOS_OBLIGATORIOS:
        if nombre_campo == "tipo_asistencia" and DEBUG_REPROCESS:
            continue
        if not extractor(result_json):
            motivos.append(f"campo obligatorio ausente: {nombre_campo}")
    return motivos


# ── Directorio de salida ───────────────────────────────────────────────────────

def determine_output_dir(doc_info: dict, result_json: dict, pdf_path: Path) -> tuple[Path, bool]:
    estado = doc_info.get("estado", "erroneo")
    numero = doc_info.get("numero_verificado") or doc_info.get("numero_extraido")
    in_review_dni = estado == "erroneo" or not numero

    doc_name = build_document_name(result_json)
    has_name = bool(result_json.get("nombre") or result_json.get("apellido1"))
    folder_name = doc_name if has_name else _fallback_name(pdf_path)

    if in_review_dni:
        return REVIEW_DIR / "dni" / folder_name, True

    hierarchy = resolve_hierarchy_path(OUTPUT_FOLDER_STRUCTURE, result_json)
    if hierarchy == Path("."):
        return OUTPUT_DIR / doc_name, False
    return OUTPUT_DIR / hierarchy / doc_name, False


# ── Debug: guardar páginas extraídas ──────────────────────────────────────────

def save_debug_pages(pages: list[Image.Image], out_dir: Path) -> None:
    debug_dir = out_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    for i, page in enumerate(pages, start=1):
        page.convert("RGB").save(debug_dir / f"pagina_{i}.jpg", "JPEG", quality=85)
    logging.info(f"Debug: {len(pages)} páginas guardadas en {debug_dir}")


# ── Guardado de resultados ─────────────────────────────────────────────────────

def save_results(
    pdf_path: Path,
    doc_info: dict,
    result_json: dict,
    photos: list[dict],
    best_photo: dict | None,
    needs_review_foto: bool,
    pages: list[Image.Image],
) -> Path:
    out_dir, needs_review_dni = determine_output_dir(doc_info, result_json, pdf_path)

    # Comprobar campos obligatorios
    motivos_revision = check_campos_obligatorios(result_json)
    en_revision = needs_review_dni or needs_review_foto or bool(motivos_revision)

    if en_revision:
        doc_name = build_document_name(result_json)
        has_name = bool(result_json.get("nombre") or result_json.get("apellido1"))
        folder_name = doc_name if has_name else _fallback_name(pdf_path)
        if needs_review_dni:
            out_dir = REVIEW_DIR / "dni" / folder_name
        elif needs_review_foto:
            out_dir = REVIEW_DIR / "foto" / folder_name
        else:
            out_dir = REVIEW_DIR / "datos" / folder_name

    if out_dir.exists() and not OVERWRITE_EXISTING:
        logging.info(f"Saltando (ya existe): {out_dir}")
        return out_dir

    out_dir.mkdir(parents=True, exist_ok=True)

    # Guardar páginas de debug siempre
    save_debug_pages(pages, out_dir)

    # PDF renombrado
    doc_name = build_document_name(result_json)
    has_name = bool(result_json.get("nombre") or result_json.get("apellido1"))
    pdf_base = doc_name if has_name else _fallback_name(pdf_path)
    shutil.copy2(pdf_path, out_dir / f"{pdf_base}.pdf")

    # Fotos individuales: foto_carnet.jpg, foto_dni.jpg
    for p in photos:
        tipo = p["tipo"]  # "carnet" o "dni"
        filename = f"foto_{tipo}.jpg"
        p["image"].convert("RGB").save(out_dir / filename, "JPEG", quality=92)

    # Mejor foto
    if best_photo is not None:
        best_photo["image"].convert("RGB").save(out_dir / "foto.jpg", "JPEG", quality=92)

    # Actualizar metadatos de revisión en el JSON
    result_json["metadata"]["en_revision"] = en_revision
    result_json["metadata"]["motivos_revision"] = motivos_revision
    result_json["metadata"]["carpeta_salida"] = str(out_dir)
    result_json["metadata"]["nombre_documento"] = pdf_base

    (out_dir / "datos.json").write_text(
        json.dumps(result_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if en_revision:
        logging.warning(f"Expediente en revisión: {motivos_revision}")
    logging.info(f"Resultados guardados en: {out_dir}")
    return out_dir


# ── Constructor del JSON de resultado ─────────────────────────────────────────

def build_result_json(
    form_data: dict,
    doc_info: dict,
    ciclo_info: dict,
    photos: list[dict],
    best_photo: dict | None,
    cotejo: dict | None,
    pdf_path: Path,
    paginas_totales: int,
    errores: list[str],
    datos_extraidos_dni: dict | None = None,
) -> dict:
    fotos_detail = {}
    for p in photos:
        tipo = p["tipo"]  # "carnet" o "dni"
        fotos_detail[f"foto_{tipo}"] = {
            "es_color": p.get("es_color"),
            "nitidez": p.get("nitidez"),
        }

    return {
        "expediente": form_data.get("expediente"),
        "documento": doc_info,
        "nombre": form_data.get("nombre"),
        "apellido1": form_data.get("apellido1"),
        "apellido2": form_data.get("apellido2"),
        "ciclo": ciclo_info,
        "tipo_asistencia": form_data.get("tipo_asistencia") or "presencial",
        "curso": _build_curso(form_data.get("curso_inicio"), form_data.get("curso_fin")),
        "cotejo_documento_identidad": cotejo or {"realizado": False},
        "datos_extraidos_dni": datos_extraidos_dni,
        "fotos": {
            "foto_carnet_encontrada": any(p["tipo"] == "carnet" for p in photos),
            "foto_dni_encontrada": any(p["tipo"] == "dni" for p in photos),
            "foto_seleccionada": best_photo["tipo"] if best_photo else None,
            "detalle": fotos_detail,
        },
        "metadata": {
            "pdf_original": pdf_path.name,
            "procesado_en": datetime.now().isoformat(timespec="seconds"),
            "paginas_totales": paginas_totales,
            "en_revision": False,
            "motivos_revision": [],
            "errores": errores,
        },
    }
