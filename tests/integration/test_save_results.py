"""
Integration tests para:
  - modules/output_manager.save_results()
  - modules/output_structure.reorganize_output()

Usa tmp_path (filesystem real, sin efectos en el proyecto).
"""
import json
import pytest
from pathlib import Path

from tests.fixtures.sample_images import make_color_image, make_gray_image
from tests.fixtures.sample_jsons import result_valido, result_en_revision


def _build_full_result_json(tmp_path):
    """Construye un result_json completo con OUTPUT_DIR parcheado."""
    r = result_valido()
    r["metadata"]["carpeta_salida"] = str(tmp_path / "output" / "DAW" / "ANA_MARTIN_RUIZ,ANA_E15001_P2526_M")
    return r


# ── save_results: caso normal ─────────────────────────────────────────────────

@pytest.mark.integration
def test_save_results_crea_carpeta_y_datos_json(tmp_path, monkeypatch):
    import modules.output_manager as om
    import modules.output_structure as os_

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(om, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(om, "REVIEW_DIR", output_dir / "revision")
    monkeypatch.setattr(os_, "OUTPUT_FOLDER_STRUCTURE", "{ciclo_codigo}")
    monkeypatch.setattr(om, "OUTPUT_FOLDER_STRUCTURE", "{ciclo_codigo}")
    monkeypatch.setattr(om, "DEBUG_REPROCESS", False)

    fake_pdf = tmp_path / "15001-01.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    r = result_valido()
    doc_info = r["documento"]
    face_img = make_color_image(50, 70)
    photos = [{"image": face_img, "tipo": "carnet", "es_color": True, "nitidez": 200.0}]
    best_photo = {**photos[0], "score": 10000200.0}

    out_dir = om.save_results(
        pdf_path=fake_pdf,
        doc_info=doc_info,
        result_json=r,
        photos=photos,
        best_photo=best_photo,
        needs_review_foto=False,
        pages=[make_gray_image()],
    )

    assert out_dir.exists()
    assert (out_dir / "datos.json").exists()


@pytest.mark.integration
def test_save_results_datos_json_es_valido(tmp_path, monkeypatch):
    import modules.output_manager as om
    import modules.output_structure as os_

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(om, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(om, "REVIEW_DIR", output_dir / "revision")
    monkeypatch.setattr(os_, "OUTPUT_FOLDER_STRUCTURE", "{ciclo_codigo}")
    monkeypatch.setattr(om, "OUTPUT_FOLDER_STRUCTURE", "{ciclo_codigo}")
    monkeypatch.setattr(om, "DEBUG_REPROCESS", False)

    fake_pdf = tmp_path / "15001-01.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    r = result_valido()
    doc_info = r["documento"]
    face_img = make_color_image(50, 70)
    photos = [{"image": face_img, "tipo": "carnet", "es_color": True, "nitidez": 200.0}]
    best_photo = {**photos[0], "score": 10000200.0}

    out_dir = om.save_results(
        pdf_path=fake_pdf, doc_info=doc_info, result_json=r,
        photos=photos, best_photo=best_photo, needs_review_foto=False,
        pages=[make_gray_image()],
    )

    data = json.loads((out_dir / "datos.json").read_text())
    assert data["expediente"] == "15001"
    assert data["nombre"] == "ANA"
    assert "metadata" in data
    assert data["metadata"]["en_revision"] is False


@pytest.mark.integration
def test_save_results_crea_debug_dir(tmp_path, monkeypatch):
    import modules.output_manager as om
    import modules.output_structure as os_

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(om, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(om, "REVIEW_DIR", output_dir / "revision")
    monkeypatch.setattr(os_, "OUTPUT_FOLDER_STRUCTURE", "{ciclo_codigo}")
    monkeypatch.setattr(om, "OUTPUT_FOLDER_STRUCTURE", "{ciclo_codigo}")
    monkeypatch.setattr(om, "DEBUG_REPROCESS", False)

    fake_pdf = tmp_path / "15001-01.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")
    r = result_valido()
    doc_info = r["documento"]

    out_dir = om.save_results(
        pdf_path=fake_pdf, doc_info=doc_info, result_json=r,
        photos=[], best_photo=None, needs_review_foto=True,
        pages=[make_gray_image(), make_gray_image()],
    )

    assert (out_dir / "debug").is_dir()
    debug_pages = list((out_dir / "debug").glob("pagina_*.jpg"))
    assert len(debug_pages) == 2


@pytest.mark.integration
def test_save_results_sin_foto_va_a_revision_foto(tmp_path, monkeypatch):
    import modules.output_manager as om
    import modules.output_structure as os_

    output_dir = tmp_path / "output"
    review_dir = output_dir / "revision"
    output_dir.mkdir()
    monkeypatch.setattr(om, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(om, "REVIEW_DIR", review_dir)
    monkeypatch.setattr(os_, "OUTPUT_FOLDER_STRUCTURE", "{ciclo_codigo}")
    monkeypatch.setattr(om, "OUTPUT_FOLDER_STRUCTURE", "{ciclo_codigo}")
    monkeypatch.setattr(om, "DEBUG_REPROCESS", False)

    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")
    r = result_valido()
    doc_info = r["documento"]

    out_dir = om.save_results(
        pdf_path=fake_pdf, doc_info=doc_info, result_json=r,
        photos=[], best_photo=None, needs_review_foto=True,
        pages=[make_gray_image()],
    )

    assert str(out_dir).startswith(str(review_dir))
    data = json.loads((out_dir / "datos.json").read_text())
    assert data["metadata"]["en_revision"] is True


# ── reorganize_output ─────────────────────────────────────────────────────────

def _create_expediente(base: Path, subfolder: str, expediente_name: str,
                       ciclo: str = "DAW", grado: str = "superior") -> Path:
    """Crea una carpeta de expediente con datos.json mínimo."""
    exp_dir = base / subfolder / expediente_name
    exp_dir.mkdir(parents=True)
    data = {
        "expediente": "15001",
        "nombre": "ANA", "apellido1": "MARTIN", "apellido2": "RUIZ",
        "tipo_asistencia": "presencial",
        "ciclo": {"codigo": ciclo, "nombre_completo": "...", "grado": grado},
        "curso": {"inicio": "2025", "fin": "2026"},
        "documento": {"numero_verificado": "12345678Z", "numero_extraido": "12345678Z"},
        "fotos": {"foto_seleccionada": "carnet"},
        "metadata": {"en_revision": False},
    }
    (exp_dir / "datos.json").write_text(json.dumps(data), encoding="utf-8")
    return exp_dir


@pytest.mark.integration
def test_reorganize_output_mueve_expedientes(tmp_path):
    from modules.output_structure import reorganize_output

    output_dir = tmp_path / "output"
    # Crear expediente en estructura plana (sin subcarpetas)
    exp_dir = _create_expediente(output_dir, "", "ANA_MARTIN_RUIZ,ANA_E15001_P2526_M")

    import threading
    stop_event = threading.Event()
    status, stats = reorganize_output(
        output_dir=output_dir,
        template="{ciclo_codigo}",
        on_progress=None,
        stop_event=stop_event,
    )

    assert status in ("completed", "partial")
    # Expediente debe haber sido movido a DAW/
    new_location = list((output_dir / "DAW").rglob("datos.json"))
    assert len(new_location) == 1


@pytest.mark.integration
def test_reorganize_output_idempotente(tmp_path):
    """Ejecutar dos veces no rompe ni duplica expedientes."""
    from modules.output_structure import reorganize_output

    output_dir = tmp_path / "output"
    _create_expediente(output_dir, "", "ANA_MARTIN_RUIZ,ANA_E15001_P2526_M")

    import threading
    stop = threading.Event()

    reorganize_output(output_dir, "{ciclo_codigo}", None, stop)
    reorganize_output(output_dir, "{ciclo_codigo}", None, stop)  # segunda vez

    jsons = list(output_dir.rglob("datos.json"))
    # Excluir _borrados y revision
    jsons = [j for j in jsons if "_borrados" not in str(j) and "revision" not in str(j)]
    assert len(jsons) == 1


@pytest.mark.integration
def test_reorganize_output_no_toca_revision(tmp_path):
    """La carpeta revision/ no se toca durante la reorganización."""
    from modules.output_structure import reorganize_output

    output_dir = tmp_path / "output"
    # Crear expediente normal
    _create_expediente(output_dir, "", "EXP_NORMAL")
    # Crear expediente en revision (no debe moverse)
    rev_dir = output_dir / "revision" / "datos" / "EXP_REVISION"
    rev_dir.mkdir(parents=True)
    datos_rev = {"ciclo": {"codigo": "SMR"}, "metadata": {"en_revision": True}}
    (rev_dir / "datos.json").write_text(json.dumps(datos_rev))

    import threading
    reorganize_output(output_dir, "{ciclo_codigo}", None, threading.Event())

    # El de revision sigue en su sitio
    assert (rev_dir / "datos.json").exists()
