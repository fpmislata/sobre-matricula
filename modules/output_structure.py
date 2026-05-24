"""
Módulo de organización jerárquica del directorio output.

Resuelve, valida y previsualiza la plantilla `output_folder_structure`
que define subcarpetas entre output/ y la carpeta de cada expediente.

Ejemplos de template:
  "{ciclo_codigo}"             → output/DAW/EXPEDIENTE/
  "{grado}/{ciclo_codigo}"     → output/SUPERIOR/DAW/EXPEDIENTE/
  ""                           → output/EXPEDIENTE/  (estructura plana)
"""

import json
import logging
import re
import shutil
import threading
import unicodedata
from datetime import datetime
from pathlib import Path


# ── Globals parcheados por run_pipeline() desde config_dict ───────────────────
OUTPUT_FOLDER_STRUCTURE: str = "{ciclo_codigo}"
ASISTENCIA_CODE: dict = {
    "presencial": "P",
    "semipresencial": "S",
    "libre": "L",
    "parcial": "PA",
}

# ── Constantes ─────────────────────────────────────────────────────────────────
_VALID_FIELDS = frozenset({
    "grado", "ciclo_codigo", "ciclo_nombre",
    "año_ini", "año_fin", "asistencia",
    "expediente", "documento", "nombre", "apellido1",
})

_RESERVED_SEGMENTS = frozenset({"revision", "_borrados", "debug"})


# ── Normalización ──────────────────────────────────────────────────────────────

def normalize_segment(seg: str) -> str:
    """ASCII mayúsculas, espacios/guiones→_, solo alfanumérico+_. Idempotente."""
    nfkd   = unicodedata.normalize("NFKD", str(seg))
    ascii_ = nfkd.encode("ascii", "ignore").decode("ascii").upper()
    ascii_ = re.sub(r"[\s\-]+", "_", ascii_)
    ascii_ = re.sub(r"[^A-Z0-9_]", "", ascii_)
    ascii_ = re.sub(r"_+", "_", ascii_).strip("_")
    return ascii_


# ── Extracción de campos desde result_json ─────────────────────────────────────

def _extract_fields(result_json: dict) -> dict:
    ciclo  = result_json.get("ciclo") or {}
    curso  = result_json.get("curso") or {}
    doc    = result_json.get("documento") or {}

    grado_raw = (ciclo.get("grado") or "").lower()
    grado = {"superior": "SUPERIOR", "medio": "MEDIO"}.get(grado_raw, "")

    ciclo_codigo = normalize_segment(ciclo.get("codigo") or "")
    ciclo_nombre = normalize_segment(ciclo.get("nombre_completo") or "")

    ini_raw = str(curso.get("inicio") or "")
    fin_raw = str(curso.get("fin") or "")
    año_ini = ini_raw[-2:] if len(ini_raw) >= 2 else ini_raw
    año_fin = fin_raw[-2:] if len(fin_raw) >= 2 else fin_raw

    asist_raw  = (result_json.get("tipo_asistencia") or "").lower()
    asistencia = ASISTENCIA_CODE.get(asist_raw, "")

    expediente = normalize_segment(str(result_json.get("expediente") or ""))
    documento  = normalize_segment(
        doc.get("numero_verificado") or doc.get("numero_extraido") or ""
    )
    nombre    = normalize_segment(result_json.get("nombre") or "")
    apellido1 = normalize_segment(result_json.get("apellido1") or "")

    return {
        "grado":        grado,
        "ciclo_codigo": ciclo_codigo,
        "ciclo_nombre": ciclo_nombre,
        "año_ini":      año_ini,
        "año_fin":      año_fin,
        "asistencia":   asistencia,
        "expediente":   expediente,
        "documento":    documento,
        "nombre":       nombre,
        "apellido1":    apellido1,
    }


# ── Resolución del path jerárquico ─────────────────────────────────────────────

def resolve_hierarchy_path(template: str, result_json: dict) -> Path:
    """
    Devuelve un Path relativo (ej. Path("DAW") o Path("SUPERIOR/DAW")).
    Path(".") significa estructura plana.
    NUNCA devuelve Path absoluta.
    NUNCA contiene "revision" o "_borrados".
    """
    template = (template or "").strip()
    if not template:
        return Path(".")

    fields = _extract_fields(result_json)

    rendered = template
    for key, val in fields.items():
        rendered = rendered.replace("{" + key + "}", val)

    # Eliminar placeholders sin resolver (defensivo)
    rendered = re.sub(r'\{[^}]+\}', '', rendered)

    raw_segments = rendered.split("/")
    segments = []
    for seg in raw_segments:
        normalized = normalize_segment(seg)
        if normalized:
            segments.append(normalized)

    if not segments:
        return Path(".")

    result = Path(segments[0])
    for seg in segments[1:]:
        result = result / seg
    return result


# ── Validación del template ────────────────────────────────────────────────────

def validate_structure_template(template: str) -> tuple[bool, str]:
    """Valida la sintaxis y semántica del template. Retorna (válido, mensaje)."""
    template = (template or "").strip()
    if not template:
        return (True, "Estructura plana (sin subdirectorios)")

    if template.startswith("/") or template.endswith("/"):
        return (False, "No puede empezar ni terminar con '/'")
    if "//" in template:
        return (False, "No se permiten barras dobles (//)  ")
    parts = template.split("/")
    if any(p == ".." for p in parts):
        return (False, "No se permiten rutas con '..'")

    tokens = re.findall(r'\{([^}]+)\}', template)
    unknown = [t for t in tokens if t not in _VALID_FIELDS]
    if unknown:
        return (False, "Campo(s) desconocido(s): " + ", ".join(f"{{{t}}}" for t in unknown))

    for part in parts:
        literal = re.sub(r'\{[^}]+\}', '', part).strip().lower()
        if literal in _RESERVED_SEGMENTS:
            return (False, f"Nombre reservado en la ruta: '{literal}'")

    if not tokens:
        return (True, "⚠  Todos los expedientes irán a la misma subcarpeta")

    return (True, "✓  Template válido")


# ── Vista previa del árbol de carpetas ────────────────────────────────────────

def render_structure_preview(template: str, sample_list: list) -> str:
    """
    Genera un árbol de texto para mostrar en la UI.
    Cada sample debe incluir '_preview_label' con el nombre canónico ficticio.
    """
    if not (template or "").strip():
        lines = [
            "output/",
            "  ANA_MARTIN_RUIZ,ANA_E16001_P2526_M/",
            "  CARLOS_LOPEZ,CARLOS_E15234_S2526_M/",
            "  (estructura plana)",
        ]
        return "\n".join(lines)

    lines = ["output/"]
    seen_dirs: set = set()

    for sample in sample_list:
        hierarchy = resolve_hierarchy_path(template, sample)
        doc_name  = sample.get("_preview_label", "NOMBRE_E99999_P2526_M")

        if hierarchy == Path("."):
            lines.append(f"  {doc_name}/")
        else:
            parts = list(hierarchy.parts) + [doc_name]
            for depth, part in enumerate(parts):
                indent = "  " * (depth + 1)
                key    = "/".join(parts[:depth + 1])
                if key not in seen_dirs:
                    lines.append(f"{indent}{part}/")
                    seen_dirs.add(key)
                elif depth == len(parts) - 1:
                    lines.append(f"{indent}{part}/")

    return "\n".join(lines)


# ── Limpieza de carpetas vacías ────────────────────────────────────────────────

def cleanup_empty_dirs(start: Path, stop_at: Path) -> None:
    """Sube por la jerarquía haciendo rmdir() si el directorio está vacío, hasta stop_at."""
    current = start
    while current != stop_at:
        try:
            if not current.is_relative_to(stop_at):
                break
            if current.exists() and not any(current.iterdir()):
                current.rmdir()
                current = current.parent
            else:
                break
        except Exception:
            break


# ── Reorganización del output ──────────────────────────────────────────────────

def reorganize_output(
    output_dir: Path,
    template: str,
    on_progress=None,   # Callable[[int, int, str], None]
    stop_event=None,    # threading.Event
) -> tuple[str, dict]:
    """
    Mueve todos los expedientes bajo output_dir a la nueva jerarquía.
    Retorna ("completed"|"partial"|"aborted", stats_dict).
    Es IDEMPOTENTE y RESUMIBLE gracias a .reorg_state.json en output_dir.
    En conflicto (dest ya existe) SOBREESCRIBE.
    """
    state_file = output_dir / ".reorg_state.json"
    already_done: set = set()

    if state_file.exists():
        try:
            prev = json.loads(state_file.read_text(encoding="utf-8"))
            if prev.get("status") == "completed":
                return ("completed", {"message": "Ya reorganizado anteriormente"})
            for m in prev.get("completed_moves", []):
                already_done.add(m["src"])
        except Exception:
            pass

    json_files = [
        f for f in output_dir.rglob("datos.json")
        if "_borrados" not in f.parts
        and "revision" not in f.parts
        and "debug" not in f.parts
    ]
    expedientes = sorted(jp.parent for jp in json_files)
    total = len(expedientes)

    stats = {"total": total, "moved": 0, "skipped": 0, "failed": 0, "overwritten": 0}

    state: dict = {
        "version": 1,
        "template_at_start": template,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "total": total,
        "completed_moves": [],
        "failed_moves": [],
        "status": "in_progress",
    }
    try:
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    except Exception as e:
        logging.warning(f"No se pudo escribir .reorg_state.json: {e}")

    for i, folder in enumerate(expedientes):
        if stop_event and stop_event.is_set():
            state["status"] = "aborted"
            _save_state(state_file, state)
            return ("aborted", stats)

        if on_progress:
            on_progress(i + 1, total, folder.name)

        src_str = str(folder)
        if src_str in already_done:
            stats["skipped"] += 1
            continue

        try:
            data = json.loads((folder / "datos.json").read_text(encoding="utf-8"))
        except Exception as e:
            stats["failed"] += 1
            state["failed_moves"].append({"src": src_str, "error": f"datos.json ilegible: {e}"})
            continue

        hierarchy = resolve_hierarchy_path(template, data)
        doc_name  = folder.name
        if hierarchy == Path("."):
            dest = output_dir / doc_name
        else:
            dest = output_dir / hierarchy / doc_name

        if folder.resolve() == dest.resolve():
            stats["skipped"] += 1
            state["completed_moves"].append({"src": src_str, "dst": str(dest), "action": "no_move"})
            continue

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.exists():
                shutil.rmtree(str(dest))
                stats["overwritten"] += 1

            shutil.move(str(folder), str(dest))

            new_json = dest / "datos.json"
            jdata = json.loads(new_json.read_text(encoding="utf-8"))
            jdata["metadata"]["carpeta_salida"] = str(dest)
            new_json.write_text(json.dumps(jdata, indent=2, ensure_ascii=False))

            cleanup_empty_dirs(folder.parent, output_dir)

            stats["moved"] += 1
            state["completed_moves"].append({"src": src_str, "dst": str(dest)})

        except Exception as e:
            stats["failed"] += 1
            state["failed_moves"].append({"src": src_str, "error": str(e)})
            logging.error(f"Reorganización: error moviendo {folder}: {e}")

        if (i + 1) % 10 == 0:
            _save_state(state_file, state)

    final_status = "completed" if stats["failed"] == 0 else "partial"
    state["status"] = final_status
    state["completed_at"] = datetime.now().isoformat(timespec="seconds")
    _save_state(state_file, state)

    return (final_status, stats)


def _save_state(state_file: Path, state: dict) -> None:
    try:
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    except Exception as e:
        logging.warning(f"No se pudo persistir estado de reorganización: {e}")
