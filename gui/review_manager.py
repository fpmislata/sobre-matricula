"""
Backend logic for manual expediente review:
- Format validation (blocking errors)
- Revision-status computation (which required fields are missing)
- Conflict detection
- Filesystem save with rollback on failure
"""

import json
import shutil
import logging
import time
from pathlib import Path

from modules.dni_validator import validate_and_correct


# ── Helpers ───────────────────────────────────────────────────────────────────

def _patch_build_name(result_json: dict, app_cfg: dict) -> str:
    """Call build_document_name with app_cfg overrides, restoring globals after."""
    import modules.output_manager as _om
    old_fmt = _om.DOCUMENT_NAME_FORMAT
    old_sfx = _om.DOCUMENT_NAME_SUFFIX
    old_asi = _om.ASISTENCIA_CODE
    try:
        fmt = app_cfg.get("document_name_format")
        if fmt:
            _om.DOCUMENT_NAME_FORMAT = fmt
        sfx = app_cfg.get("document_name_suffix")
        if sfx is not None:
            _om.DOCUMENT_NAME_SUFFIX = sfx
        asi = app_cfg.get("asistencia_code")
        if asi:
            _om.ASISTENCIA_CODE = asi
        return _om.build_document_name(result_json)
    finally:
        _om.DOCUMENT_NAME_FORMAT = old_fmt
        _om.DOCUMENT_NAME_SUFFIX = old_sfx
        _om.ASISTENCIA_CODE = old_asi


def _detect_existing_foto(folder: Path) -> str | None:
    """Return 'carnet' or 'dni' if any photo file exists in folder, else None."""
    if (folder / "foto.jpg").exists() or (folder / "foto_carnet.jpg").exists():
        return "carnet"
    if (folder / "foto_dni.jpg").exists():
        return "dni"
    return None


# ── Validation ────────────────────────────────────────────────────────────────

def validate_review_data(data: dict, ciclos: dict) -> list[str]:
    """
    Format-level validation only.  Missing fields keep the expediente in revision
    but are not blocking errors here.
    Returns a list of user-facing error messages.
    """
    errors: list[str] = []

    curso = data.get("curso") or {}
    ini = str(curso.get("inicio") or "").strip()
    fin = str(curso.get("fin") or "").strip()
    if ini and not ini.isdigit():
        errors.append("Año de inicio debe ser un número (ej: 2025)")
    if fin and not fin.isdigit():
        errors.append("Año de fin debe ser un número (ej: 2026)")
    if ini.isdigit() and fin.isdigit() and int(ini) >= int(fin):
        errors.append("El año de inicio debe ser anterior al de fin")

    ciclo_cod = (data.get("ciclo") or {}).get("codigo", "").strip()
    if ciclo_cod and ciclo_cod not in ciclos:
        errors.append(f"Ciclo '{ciclo_cod}' no está en el catálogo")

    doc_num = (data.get("documento") or {}).get("numero_verificado", "").strip()
    if doc_num:
        result = validate_and_correct(doc_num)
        if result["estado"] == "erroneo":
            errors.append(f"Documento inválido: {result.get('detalle_correccion', '')}")

    return errors


def check_still_in_revision(data: dict, foto_exists: bool) -> tuple[bool, list[str]]:
    """
    Check which required fields are missing (always strict, ignores DEBUG_REPROCESS).
    Returns (en_revision, motivos).
    """
    motivos: list[str] = []
    if not data.get("nombre"):
        motivos.append("campo obligatorio ausente: nombre")
    if not data.get("apellido1"):
        motivos.append("campo obligatorio ausente: apellido1")
    if not data.get("apellido2"):
        motivos.append("campo obligatorio ausente: apellido2")
    if not (data.get("ciclo") or {}).get("codigo"):
        motivos.append("campo obligatorio ausente: ciclo")
    if not data.get("tipo_asistencia"):
        motivos.append("campo obligatorio ausente: tipo_asistencia")
    if not (data.get("curso") or {}).get("inicio"):
        motivos.append("campo obligatorio ausente: curso_inicio")
    if not (data.get("curso") or {}).get("fin"):
        motivos.append("campo obligatorio ausente: curso_fin")
    if not (data.get("fotos") or {}).get("foto_seleccionada") and not foto_exists:
        motivos.append("campo obligatorio ausente: foto")
    return bool(motivos), motivos


# ── Conflict detection ────────────────────────────────────────────────────────

def find_conflict(new_folder_name: str, output_dir: Path, current_folder: Path) -> Path | None:
    """Return the path of a folder with new_folder_name (anywhere under output_dir)
    that is NOT the current_folder.  Returns None when no conflict.
    Búsqueda recursiva para soportar jerarquía de subcarpetas."""
    for candidate in output_dir.rglob(new_folder_name):
        if not candidate.is_dir():
            continue
        if "_borrados" in candidate.parts or "revision" in candidate.parts:
            continue
        if candidate.resolve() != current_folder.resolve():
            return candidate
    revision_base = output_dir / "revision"
    if revision_base.exists():
        for subdir in revision_base.iterdir():
            if not subdir.is_dir():
                continue
            candidate = subdir / new_folder_name
            if candidate.exists() and candidate.resolve() != current_folder.resolve():
                return candidate
    return None


def load_folder_summary(folder: Path) -> dict:
    """Extract key fields from folder/datos.json for conflict comparison."""
    json_path = folder / "datos.json"
    if not json_path.exists():
        return {"folder": str(folder)}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return {"folder": str(folder)}

    doc   = data.get("documento") or {}
    ciclo = data.get("ciclo") or {}
    curso = data.get("curso") or {}
    meta  = data.get("metadata") or {}

    foto_path = ""
    for fname in ("foto.jpg", "foto_carnet.jpg", "foto_dni.jpg"):
        p = folder / fname
        if p.exists():
            foto_path = str(p)
            break

    return {
        "expediente":   str(data.get("expediente") or ""),
        "documento":    str(doc.get("numero_verificado") or ""),
        "nombre":       str(data.get("nombre") or ""),
        "apellido1":    str(data.get("apellido1") or ""),
        "apellido2":    str(data.get("apellido2") or ""),
        "ciclo":        str(ciclo.get("codigo") or ""),
        "asistencia":   str(data.get("tipo_asistencia") or ""),
        "curso_inicio": str(curso.get("inicio") or ""),
        "curso_fin":    str(curso.get("fin") or ""),
        "en_revision":  bool(meta.get("en_revision", False)),
        "folder":       str(folder),
        "foto_path":    foto_path,
    }


def summary_from_data(data: dict, folder: Path, new_photo_path: str | None) -> dict:
    """Build a summary dict from in-memory data (used for the 'new' side of conflict UI)."""
    doc   = data.get("documento") or {}
    ciclo = data.get("ciclo") or {}
    curso = data.get("curso") or {}
    meta  = data.get("metadata") or {}

    foto_path = new_photo_path or ""
    if not foto_path:
        for fname in ("foto.jpg", "foto_carnet.jpg", "foto_dni.jpg"):
            p = folder / fname
            if p.exists():
                foto_path = str(p)
                break

    return {
        "expediente":   str(data.get("expediente") or ""),
        "documento":    str(doc.get("numero_verificado") or ""),
        "nombre":       str(data.get("nombre") or ""),
        "apellido1":    str(data.get("apellido1") or ""),
        "apellido2":    str(data.get("apellido2") or ""),
        "ciclo":        str(ciclo.get("codigo") or ""),
        "asistencia":   str(data.get("tipo_asistencia") or ""),
        "curso_inicio": str(curso.get("inicio") or ""),
        "curso_fin":    str(curso.get("fin") or ""),
        "en_revision":  bool(meta.get("en_revision", False)),
        "folder":       str(folder),
        "foto_path":    foto_path,
    }


# ── Save ──────────────────────────────────────────────────────────────────────

def save_review_changes(
    current_folder: Path,
    json_path: Path,
    new_data: dict,
    new_photo_path: str | None,
    app_cfg: dict,
    force_overwrite: bool = False,
) -> tuple[str, any]:
    """
    Persist manual review changes for an expediente.

    Returns one of:
        ("ok",       new_folder_path)  — success
        ("conflict", conflict_dict)    — name collision; UI must confirm
        ("error",    message_str)      — unrecoverable filesystem error
    """
    output_dir = Path(app_cfg.get("output_dir", ""))
    ciclos     = app_cfg.get("ciclos", {})

    # ── Load original JSON ────────────────────────────────────────────
    try:
        orig_json_text = json_path.read_text(encoding="utf-8")
        updated_json   = json.loads(orig_json_text)
    except Exception as exc:
        return ("error", f"No se pudo leer datos.json: {exc}")

    # ── Apply form changes ────────────────────────────────────────────
    updated_json["expediente"]      = new_data.get("expediente") or updated_json.get("expediente")
    updated_json["nombre"]          = new_data.get("nombre") or None
    updated_json["apellido1"]       = new_data.get("apellido1") or None
    updated_json["apellido2"]       = new_data.get("apellido2") or None
    updated_json["tipo_asistencia"] = (
        new_data.get("tipo_asistencia") or updated_json.get("tipo_asistencia")
    )

    new_curso = new_data.get("curso") or {}
    updated_json["curso"] = {
        "inicio": new_curso.get("inicio") or None,
        "fin":    new_curso.get("fin") or None,
    }

    new_ciclo_data = new_data.get("ciclo") or {}
    ciclo_cod = new_ciclo_data.get("codigo", "")
    if ciclo_cod and ciclo_cod in ciclos:
        info       = ciclos[ciclo_cod]
        orig_ciclo = updated_json.get("ciclo") or {}
        updated_json["ciclo"] = {
            "codigo":          ciclo_cod,
            "nombre_completo": info.get("nombre", ""),
            "grado":           info.get("grado", ""),
            "texto_original":  orig_ciclo.get("texto_original", ciclo_cod),
        }

    new_doc_num = (new_data.get("documento") or {}).get("numero_verificado", "").strip()
    if new_doc_num:
        updated_json["documento"] = validate_and_correct(new_doc_num)

    # ── Foto status ───────────────────────────────────────────────────
    foto_exists = bool(new_photo_path) or bool(_detect_existing_foto(current_folder))
    if new_photo_path:
        updated_json.setdefault("fotos", {})["foto_seleccionada"] = "carnet"
        updated_json["fotos"]["foto_carnet_encontrada"] = True
    elif not (updated_json.get("fotos") or {}).get("foto_seleccionada"):
        detected = _detect_existing_foto(current_folder)
        if detected:
            fotos = updated_json.setdefault("fotos", {})
            fotos["foto_seleccionada"] = detected
            if detected == "carnet":
                fotos["foto_carnet_encontrada"] = True
            else:
                fotos["foto_dni_encontrada"] = True

    # ── Revision status ───────────────────────────────────────────────
    en_revision, motivos = check_still_in_revision(updated_json, foto_exists)
    updated_json.setdefault("metadata", {})
    updated_json["metadata"]["en_revision"]      = en_revision
    updated_json["metadata"]["motivos_revision"] = motivos

    # ── Build new canonical name ──────────────────────────────────────
    new_canonical = _patch_build_name(updated_json, app_cfg)

    # ── Determine target folder ───────────────────────────────────────
    doc        = updated_json.get("documento") or {}
    doc_estado = doc.get("estado", "erroneo")
    doc_num    = doc.get("numero_verificado") or doc.get("numero_extraido")

    if en_revision:
        if doc_estado == "erroneo" or not doc_num:
            new_folder = output_dir / "revision" / "dni"   / new_canonical
        elif not (updated_json.get("fotos") or {}).get("foto_seleccionada"):
            new_folder = output_dir / "revision" / "foto"  / new_canonical
        else:
            new_folder = output_dir / "revision" / "datos" / new_canonical
    else:
        from modules.output_structure import resolve_hierarchy_path
        structure_tpl = app_cfg.get("output_folder_structure", "") if app_cfg else ""
        hierarchy = resolve_hierarchy_path(structure_tpl, updated_json)
        if hierarchy == Path("."):
            new_folder = output_dir / new_canonical
        else:
            new_folder = output_dir / hierarchy / new_canonical

    # ── Conflict detection ────────────────────────────────────────────
    conflict_folder = find_conflict(new_canonical, output_dir, current_folder)
    if not conflict_folder and (
        new_folder.exists() and new_folder.resolve() != current_folder.resolve()
    ):
        conflict_folder = new_folder

    if conflict_folder:
        if not force_overwrite:
            return ("conflict", {
                "existing_folder":  conflict_folder,
                "new_canonical":    new_canonical,
                "new_summary":      summary_from_data(updated_json, current_folder, new_photo_path),
                "existing_summary": load_folder_summary(conflict_folder),
            })
        # Move conflicting folder to trash before continuing
        trash_dir  = output_dir / "_borrados"
        trash_dir.mkdir(parents=True, exist_ok=True)
        trash_dest = trash_dir / f"{conflict_folder.name}_{int(time.time())}"
        try:
            shutil.move(str(conflict_folder), str(trash_dest))
        except Exception as exc:
            return ("error", f"No se pudo mover el expediente existente a papelera: {exc}")

    # ── Filesystem operations with rollback ───────────────────────────
    rollback_ops: list[tuple] = []

    try:
        # 1. Copy new photo (before JSON so JSON can reference it)
        if new_photo_path:
            foto_dest = current_folder / "foto.jpg"
            shutil.copy2(new_photo_path, foto_dest)
            # Not added to rollback_ops — photo overwrite is low-risk

        # 2. Finalize metadata fields in JSON
        updated_json["metadata"]["nombre_documento"] = new_canonical
        updated_json["metadata"]["carpeta_salida"]   = str(new_folder)

        # 3. Write JSON
        new_json_text = json.dumps(updated_json, ensure_ascii=False, indent=2)
        json_path.write_text(new_json_text, encoding="utf-8")
        rollback_ops.append(("json", json_path, orig_json_text))

        # 4. Rename PDF inside folder
        pdf_candidates = sorted(current_folder.glob("*.pdf"))
        if pdf_candidates:
            old_pdf = pdf_candidates[0]
            new_pdf = current_folder / f"{new_canonical}.pdf"
            if old_pdf.resolve() != new_pdf.resolve():
                old_pdf.rename(new_pdf)
                rollback_ops.append(("pdf", new_pdf, old_pdf))

        # 5. Move/rename folder (highest risk — always last)
        if new_folder.resolve() != current_folder.resolve():
            new_folder.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(current_folder), str(new_folder))
            rollback_ops.append(("folder", new_folder, current_folder))

        return ("ok", new_folder)

    except Exception as exc:
        logging.error(f"Error guardando revisión '{new_canonical}': {exc}. Iniciando rollback.")
        for op in reversed(rollback_ops):
            try:
                if op[0] == "json":
                    op[1].write_text(op[2], encoding="utf-8")
                elif op[0] == "pdf":
                    if op[1].exists():
                        op[1].rename(op[2])
                elif op[0] == "folder":
                    if op[1].exists():
                        shutil.move(str(op[1]), str(op[2]))
            except Exception as rb_exc:
                logging.warning(f"Rollback {op[0]} fallido: {rb_exc}")
        return ("error", str(exc))
