import logging
import sys
import re
from pathlib import Path

from config import (
    INPUT_DIR, OVERWRITE_EXISTING, MAX_PAGES_TO_ANALYZE, PASAR_A_GRISES,
    DEBUG_REPROCESS, PDF_LIMIT, MODO_LOG_FICHERO,
)

PROCESSED_PREFIX = "_!_"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from modules.pdf_processor import pdf_to_images, preprocess_for_ocr
from modules.form_extractor import extract_form_data, normalize_ciclo
from modules.dni_validator import validate_and_correct
from modules.page_analyzer import analyze_page, cross_check
from modules.photo_detector import detect_and_crop_face
from modules.photo_selector import select_best_photo
from modules.output_manager import (
    build_result_json, save_results, determine_output_dir, save_debug_pages,
)
from utils.image_utils import rotate_pil


def process_single_pdf(pdf_path: Path) -> str:
    """Process one PDF. Returns 'ok', 'revision', or 'error'."""
    logging.info(f"{'='*60}")
    logging.info(f"Procesando: {pdf_path.name}")
    errores = []
    photos = []
    cotejo = None
    datos_extraidos_dni = None

    # ── 1. PDF → imágenes ────────────────────────────────────────
    try:
        pages = pdf_to_images(pdf_path)
    except Exception as e:
        logging.error(f"Error leyendo PDF: {e}")
        return "error"
    logging.info(f"Páginas encontradas: {len(pages)}")

    # ── 2. Preprocesar página 1 si PASAR_A_GRISES ────────────────
    page1_for_ocr = pages[0]
    if PASAR_A_GRISES:
        try:
            page1_for_ocr = preprocess_for_ocr(pages[0])
            logging.info("Página 1 preprocesada a escala de grises (Otsu)")
        except Exception as e:
            logging.warning(f"Error en preprocesado a grises: {e} — usando imagen original")

    # ── 3. Extraer formulario (página 1) ─────────────────────────
    try:
        form_data = extract_form_data(page1_for_ocr)
    except Exception as e:
        logging.error(f"Error extrayendo formulario: {e}")
        form_data = {}
        errores.append(f"Error extrayendo formulario: {e}")

    # ── 4. Validar DNI/NIE del formulario ────────────────────────
    doc_info = validate_and_correct(form_data.get("numero_documento"))
    logging.info(f"Documento: tipo={doc_info['tipo']} estado={doc_info['estado']} verificado={doc_info['numero_verificado']}")

    # ── 5. Normalizar ciclo ───────────────────────────────────────
    ciclo_info = normalize_ciclo(form_data.get("ciclo_detectado"), form_data.get("ciclo_codigo"))
    logging.info(f"Ciclo: {ciclo_info.get('codigo')} ({ciclo_info.get('grado')})")

    # ── 6. Check OVERWRITE ────────────────────────────────────────
    _preview_json = {
        "expediente": form_data.get("expediente"),
        "nombre": form_data.get("nombre"),
        "apellido1": form_data.get("apellido1"),
        "apellido2": form_data.get("apellido2"),
        "tipo_asistencia": form_data.get("tipo_asistencia"),
        "curso": {"inicio": form_data.get("curso_inicio"), "fin": form_data.get("curso_fin")},
    }
    out_dir_preview, _ = determine_output_dir(doc_info, _preview_json, pdf_path)
    if out_dir_preview.exists() and not OVERWRITE_EXISTING:
        logging.info(f"Saltando (ya existe): {out_dir_preview}")
        return "ok"

    # ── 7. Analizar páginas 2..N ──────────────────────────────────
    for i, page_img in enumerate(pages[1:MAX_PAGES_TO_ANALYZE], start=2):
        logging.info(f"Analizando página {i}/{len(pages)}")
        try:
            analysis = analyze_page(page_img)
        except Exception as e:
            logging.warning(f"Error analizando página {i}: {e}")
            errores.append(f"Página {i}: {e}")
            continue

        tipo = analysis.get("tipo_pagina", "otro")

        if tipo == "foto_carnet":
            face, _ = detect_and_crop_face(page_img)
            if face:
                photos.append({"image": face, "tipo": "carnet"})
                logging.info(f"  Foto de carnet detectada en página {i}")
            else:
                logging.info(f"  Página {i} clasificada como carnet pero sin cara detectada")
                errores.append(f"Página {i}: carnet sin cara detectada")

        elif tipo == "documento_identidad":
            face, face_angle = detect_and_crop_face(page_img)
            if face:
                photos.append({"image": face, "tipo": "dni"})
                logging.info(f"  Foto de documento de identidad detectada en página {i} (rotación={face_angle}°)")
            doc_data = analysis.get("datos_documento")
            if face_angle != 0:
                logging.info(f"  Reintentando OCR con rotación {face_angle}° (orientación de cara YOLO)")
                rotated_page = rotate_pil(page_img, face_angle)
                retry = analyze_page(rotated_page)
                if retry.get("datos_documento"):
                    analysis = retry
                    doc_data = analysis.get("datos_documento")
                    logging.info(f"  OCR corregido tras rotación: {doc_data}")
            doc_numero = (doc_data or {}).get("numero_documento") or ""
            doc_numero_valido = bool(
                re.match(r'^\d{8}[A-Z]$', doc_numero) or
                re.match(r'^[XYZ]\d{7}[A-Z]$', doc_numero) or
                re.match(r'^[A-Z]{1,3}\d{5,9}$', doc_numero)
            )
            if doc_data and doc_numero_valido:
                datos_extraidos_dni = doc_data
                cotejo = cross_check(form_data, doc_data)
                logging.info(f"  Cotejo realizado: número usado={cotejo.get('numero_usado')}")
            elif doc_data and not doc_numero_valido:
                logging.warning(f"  Página {i}: documento sin número válido — cotejo omitido")
        else:
            face, _ = detect_and_crop_face(page_img)
            if face:
                photos.append({"image": face, "tipo": "carnet"})
                logging.info(f"  Página {i}: reclasificada como foto_carnet por YOLO (LLM dijo '{tipo}')")
            else:
                logging.info(f"  Página {i}: tipo '{tipo}', ignorada")

    # ── 8. Seleccionar mejor foto ─────────────────────────────────
    from utils.image_utils import is_color_image, sharpness_score
    for p in photos:
        p["es_color"] = is_color_image(p["image"])
        p["nitidez"] = round(sharpness_score(p["image"]), 2)

    best_photo = select_best_photo(photos)
    needs_review_foto = best_photo is None

    if needs_review_foto:
        logging.warning("No se encontró ninguna foto en el documento")
        errores.append("No se detectó ninguna foto de carnet ni de documento de identidad")

    # ── 9. Construir JSON y guardar ───────────────────────────────
    result_json = build_result_json(
        form_data=form_data,
        doc_info=doc_info,
        ciclo_info=ciclo_info,
        photos=photos,
        best_photo=best_photo,
        cotejo=cotejo,
        pdf_path=pdf_path,
        paginas_totales=len(pages),
        errores=errores,
        datos_extraidos_dni=datos_extraidos_dni,
    )

    out_dir = save_results(
        pdf_path=pdf_path,
        doc_info=doc_info,
        result_json=result_json,
        photos=photos,
        best_photo=best_photo,
        needs_review_foto=needs_review_foto,
        pages=pages,
    )

    # ── 10. Marcar PDF como procesado ────────────────────────────
    if not pdf_path.name.startswith(PROCESSED_PREFIX):
        new_name = pdf_path.parent / f"{PROCESSED_PREFIX}{pdf_path.name}"
        pdf_path.rename(new_name)
        logging.info(f"PDF marcado como procesado: {new_name.name}")
    else:
        logging.info(f"PDF ya tenía prefijo {PROCESSED_PREFIX!r}, no se renombra")

    logging.info(f"Completado: {pdf_path.name} → {out_dir}")

    # Detect revision by checking if output landed under REVIEW_DIR
    import modules.output_manager as _om
    en_revision = str(out_dir).startswith(str(_om.REVIEW_DIR))
    return "revision" if en_revision else "ok"


def main():
    # Add file handler for standalone execution
    modo = MODO_LOG_FICHERO
    if modo == "nuevo":
        logging.getLogger().addHandler(
            logging.FileHandler("procesado.log", mode="w", encoding="utf-8")
        )
    elif modo == "acumular":
        logging.getLogger().addHandler(
            logging.FileHandler("procesado.log", mode="a", encoding="utf-8")
        )

    pdfs = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        logging.error(f"No se encontraron PDFs en {INPUT_DIR}")
        return

    if not DEBUG_REPROCESS:
        pdfs_a_procesar = [p for p in pdfs if not p.name.startswith(PROCESSED_PREFIX)]
        saltados = len(pdfs) - len(pdfs_a_procesar)
        if saltados:
            logging.info(f"Saltando {saltados} PDFs ya procesados (prefijo {PROCESSED_PREFIX!r})")
    else:
        pdfs_a_procesar = pdfs
        logging.info("DEBUG_REPROCESS=True — reprocesando todos los PDFs")

    if not pdfs_a_procesar:
        logging.info("No hay PDFs pendientes de procesar")
        return

    if PDF_LIMIT is not None:
        pdfs_a_procesar = pdfs_a_procesar[:PDF_LIMIT]
        logging.info(f"PDF_LIMIT={PDF_LIMIT} — procesando {len(pdfs_a_procesar)} PDF(s)")
    else:
        logging.info(f"PDFs a procesar: {len(pdfs_a_procesar)}")

    for pdf in pdfs_a_procesar:
        try:
            process_single_pdf(pdf)
        except Exception as e:
            logging.error(f"Error fatal procesando {pdf.name}: {e}", exc_info=True)


def run_pipeline(
    config_dict: dict,
    pdf_list: list,
    on_log=None,
    on_pdf_start=None,
    on_pdf_done=None,
    stop_event=None,
    pause_event=None,
):
    """Pipeline entry point for the GUI. Applies config_dict to all modules,
    sets up timestamped logging, and processes pdf_list with pause/stop support."""
    import time
    from datetime import datetime

    # ── Apply config to module-level globals ─────────────────────
    global PASAR_A_GRISES, OVERWRITE_EXISTING, MAX_PAGES_TO_ANALYZE, DEBUG_REPROCESS, PROCESSED_PREFIX

    PROCESSED_PREFIX = config_dict.get("processed_prefix", "_!_")
    PASAR_A_GRISES = config_dict.get("pasar_a_grises", PASAR_A_GRISES)
    OVERWRITE_EXISTING = config_dict.get("overwrite_existing", OVERWRITE_EXISTING)
    MAX_PAGES_TO_ANALYZE = config_dict.get("max_pages_to_analyze", MAX_PAGES_TO_ANALYZE)
    DEBUG_REPROCESS = config_dict.get("debug_reprocess", DEBUG_REPROCESS)

    import modules.output_manager as _om
    import modules.output_structure as _os
    out_dir = Path(config_dict["output_dir"]) if config_dict.get("output_dir") else Path("output")
    _om.OUTPUT_DIR = out_dir
    _om.REVIEW_DIR = out_dir / "revision"
    _om.OVERWRITE_EXISTING = config_dict.get("overwrite_existing", True)
    _om.ASISTENCIA_CODE = config_dict.get("asistencia_code", _om.ASISTENCIA_CODE)
    _om.DOCUMENT_NAME_SUFFIX = config_dict.get("document_name_suffix", "_M")
    _om.DEBUG_REPROCESS = config_dict.get("debug_reprocess", False)
    if config_dict.get("document_name_format"):
        _om.DOCUMENT_NAME_FORMAT = config_dict["document_name_format"]
    _om.OUTPUT_FOLDER_STRUCTURE = config_dict.get("output_folder_structure", "{ciclo_codigo}")
    _os.OUTPUT_FOLDER_STRUCTURE = config_dict.get("output_folder_structure", "{ciclo_codigo}")
    _os.ASISTENCIA_CODE = config_dict.get("asistencia_code", _os.ASISTENCIA_CODE)

    import modules.form_extractor as _fe
    ciclos_cfg = config_dict.get("ciclos", {})
    if ciclos_cfg:
        _fe.CICLOS = {k: v["nombre"] for k, v in ciclos_cfg.items()}
        _fe.GRADO_SUPERIOR = frozenset(k for k, v in ciclos_cfg.items() if v["grado"] == "superior")
        _fe.GRADO_MEDIO = frozenset(k for k, v in ciclos_cfg.items() if v["grado"] == "medio")
    if config_dict.get("prompt_form"):
        _fe.FORM_PROMPT = config_dict["prompt_form"]
    if config_dict.get("prompt_retry_expediente"):
        _fe.EXPEDIENTE_RETRY_PROMPT = config_dict["prompt_retry_expediente"]
    if config_dict.get("prompt_retry_nombres"):
        _fe.NOMBRES_RETRY_PROMPT = config_dict["prompt_retry_nombres"]
    if config_dict.get("prompt_retry_apellido2"):
        _fe.APELLIDO2_RETRY_PROMPT = config_dict["prompt_retry_apellido2"]

    import modules.page_analyzer as _pa
    if config_dict.get("prompt_page"):
        _pa.PAGE_PROMPT = config_dict["prompt_page"]

    import modules.pdf_processor as _pp
    _pp.PDF_DPI = config_dict.get("pdf_dpi", 200)

    import modules.photo_detector as _pd
    _pd.YOLO_CONFIDENCE = config_dict.get("yolo_confidence", 0.35)
    _pd.FACE_PADDING_RATIO = config_dict.get("face_padding_ratio", 0.35)

    import utils.ollama_client as _oc
    _oc.OLLAMA_URL = config_dict.get("ollama_url", _oc.OLLAMA_URL)
    _oc.OLLAMA_MODEL = config_dict.get("ollama_model", _oc.OLLAMA_MODEL)
    _oc.OLLAMA_TIMEOUT = config_dict.get("ollama_timeout", _oc.OLLAMA_TIMEOUT)
    _oc.OLLAMA_MAX_RETRIES = config_dict.get("ollama_max_retries", _oc.OLLAMA_MAX_RETRIES)
    _oc.OPENROUTER_URL = config_dict.get("openrouter_url", _oc.OPENROUTER_URL)
    _oc.OPENROUTER_MODEL = config_dict.get("openrouter_model", _oc.OPENROUTER_MODEL)
    _oc.OPENROUTER_API_KEY = config_dict.get("openrouter_api_key", _oc.OPENROUTER_API_KEY)
    _oc.MODO_DESARROLLO_PROD = config_dict.get("modo_desarrollo_prod", _oc.MODO_DESARROLLO_PROD)

    # ── Set up logging for this run ───────────────────────────────
    from gui.config_manager import get_logs_dir
    logs_dir = get_logs_dir(config_dict)
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = logs_dir / f"procesado_{timestamp}.log"

    root_logger = logging.getLogger()
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, mode="w", encoding="utf-8"),
    ]
    if on_log:
        class _GuiHandler(logging.Handler):
            def emit(self, record):
                try:
                    on_log(self.format(record))
                except Exception:
                    pass
        gh = _GuiHandler()
        gh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        handlers.append(gh)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
        force=True,
    )

    # ── Filtrar PDFs ya procesados (misma lógica que en main() CLI) ──
    if not DEBUG_REPROCESS:
        original_len = len(pdf_list)
        pdf_list = [p for p in pdf_list if not Path(p).name.startswith(PROCESSED_PREFIX)]
        saltados = original_len - len(pdf_list)
        if saltados:
            logging.info(f"Saltando {saltados} PDFs ya procesados (prefijo {PROCESSED_PREFIX!r})")
    if not pdf_list:
        logging.info("No hay PDFs pendientes de procesar")
        return

    # ── Run pipeline with pause/stop support ─────────────────────
    logging.info(f"Iniciando pipeline: {len(pdf_list)} PDF(s)")
    for pdf_path in pdf_list:
        if stop_event and stop_event.is_set():
            logging.info("Procesamiento detenido por el usuario")
            break

        while pause_event and pause_event.is_set():
            time.sleep(0.1)

        if on_pdf_start:
            on_pdf_start(pdf_path)

        status = "error"
        try:
            status = process_single_pdf(pdf_path)
        except Exception as e:
            logging.error(f"Error fatal procesando {pdf_path.name}: {e}", exc_info=True)

        if on_pdf_done:
            on_pdf_done(pdf_path, status)

    logging.info("Pipeline finalizado")


if __name__ == "__main__":
    main()
