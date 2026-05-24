"""
Integration tests para el pipeline completo: process_single_pdf().

LLM mockeado, YOLO/Haar mockeado, pdf_to_images mockeado.
El filesystem de salida usa tmp_path.

No se hacen llamadas de red ni se requiere el modelo YOLO.
"""
import json
import pytest
from pathlib import Path
from PIL import Image

from tests.fixtures.sample_images import make_gray_image, make_color_image
from tests.fixtures.sample_jsons import llm_form_response, llm_page_response_foto


@pytest.fixture
def setup_pipeline(monkeypatch, tmp_path):
    """
    Parchea todos los externos del pipeline:
      - pdf_to_images → 2 imágenes sintéticas
      - modules.form_extractor.call_model → respuesta completa
      - modules.page_analyzer.call_model  → foto_carnet
      - detect_and_crop_face              → (face_image, 0)
      - OUTPUT_DIR / REVIEW_DIR en output_manager
    Devuelve un objeto con helpers para el test.
    """
    import main
    import modules.output_manager as om
    import modules.output_structure as os_

    # Parchear directorios de salida
    output_dir = tmp_path / "output"
    review_dir = output_dir / "revision"
    output_dir.mkdir()
    monkeypatch.setattr(om, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(om, "REVIEW_DIR", review_dir)
    monkeypatch.setattr(os_, "OUTPUT_FOLDER_STRUCTURE", "{ciclo_codigo}")

    # Parchear pdf_to_images → [pagina1, pagina2]
    pagina1 = make_gray_image(300, 400)
    pagina2 = make_color_image(200, 300)
    monkeypatch.setattr("main.pdf_to_images", lambda p: [pagina1, pagina2])

    # Parchear LLM
    monkeypatch.setattr("modules.form_extractor.call_model", lambda p, i: llm_form_response())
    monkeypatch.setattr("modules.page_analyzer.call_model", lambda p, i: llm_page_response_foto())

    # Parchear detect_and_crop_face → devuelve cara sintética
    face_img = make_color_image(50, 70)
    monkeypatch.setattr("main.detect_and_crop_face", lambda img: (face_img, 0))

    # Crear PDF falso en tmp_path (process_single_pdf lo usa para nombre y copia)
    fake_pdf = tmp_path / "15001-01.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    return {
        "output_dir": output_dir,
        "review_dir": review_dir,
        "fake_pdf": fake_pdf,
        "face_img": face_img,
    }


# ── Pipeline completo → resultado OK ─────────────────────────────────────────

@pytest.mark.integration
def test_pipeline_resultado_ok(setup_pipeline):
    import main
    ctx = setup_pipeline
    result = main.process_single_pdf(ctx["fake_pdf"])
    assert result in ("ok", "revision")  # depende de config DEBUG_REPROCESS


@pytest.mark.integration
def test_pipeline_crea_datos_json(setup_pipeline):
    import main
    ctx = setup_pipeline
    main.process_single_pdf(ctx["fake_pdf"])

    jsons = list(ctx["output_dir"].rglob("datos.json"))
    assert len(jsons) == 1, f"Esperaba 1 datos.json, encontré: {jsons}"


@pytest.mark.integration
def test_pipeline_datos_json_estructura(setup_pipeline):
    import main
    ctx = setup_pipeline
    main.process_single_pdf(ctx["fake_pdf"])

    datos_json = list(ctx["output_dir"].rglob("datos.json"))[0]
    data = json.loads(datos_json.read_text())

    assert "expediente" in data
    assert "nombre" in data
    assert "ciclo" in data
    assert "metadata" in data
    assert "en_revision" in data["metadata"]


@pytest.mark.integration
def test_pipeline_crea_debug_dir(setup_pipeline):
    import main
    ctx = setup_pipeline
    main.process_single_pdf(ctx["fake_pdf"])

    debug_dirs = list(ctx["output_dir"].rglob("debug"))
    assert len(debug_dirs) >= 1


@pytest.mark.integration
def test_pipeline_marca_pdf_como_procesado(setup_pipeline):
    """El PDF original se renombra con el prefijo _!_."""
    import main
    ctx = setup_pipeline
    main.process_single_pdf(ctx["fake_pdf"])

    prefixed = ctx["fake_pdf"].parent / "_!_15001-01.pdf"
    assert prefixed.exists()


# ── Pipeline con LLM fallido ──────────────────────────────────────────────────

@pytest.mark.integration
def test_pipeline_llm_falla_completamente(monkeypatch, tmp_path):
    """LLM siempre devuelve None → resultado en revisión, sin excepción no controlada."""
    import main
    import modules.output_manager as om
    import modules.output_structure as os_

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(om, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(om, "REVIEW_DIR", output_dir / "revision")
    monkeypatch.setattr(os_, "OUTPUT_FOLDER_STRUCTURE", "{ciclo_codigo}")

    monkeypatch.setattr("main.pdf_to_images", lambda p: [make_gray_image()])
    monkeypatch.setattr("modules.form_extractor.call_model", lambda p, i: None)
    monkeypatch.setattr("modules.page_analyzer.call_model", lambda p, i: None)
    monkeypatch.setattr("main.detect_and_crop_face", lambda img: (None, 0))

    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    result = main.process_single_pdf(fake_pdf)
    assert result in ("ok", "revision", "error")  # no debe lanzar excepción


# ── Pipeline con DNI inválido → revisión/dni ─────────────────────────────────

@pytest.mark.integration
def test_pipeline_dni_erroneo_va_a_revision_dni(monkeypatch, tmp_path):
    import main
    import modules.output_manager as om
    import modules.output_structure as os_

    output_dir = tmp_path / "output"
    review_dir = output_dir / "revision"
    output_dir.mkdir()
    monkeypatch.setattr(om, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(om, "REVIEW_DIR", review_dir)
    monkeypatch.setattr(os_, "OUTPUT_FOLDER_STRUCTURE", "{ciclo_codigo}")

    resp_form = llm_form_response()
    resp_form["numero_documento"] = "XXXXXXXXX"  # DNI inválido
    monkeypatch.setattr("main.pdf_to_images", lambda p: [make_gray_image()])
    monkeypatch.setattr("modules.form_extractor.call_model", lambda p, i: resp_form)
    monkeypatch.setattr("modules.page_analyzer.call_model", lambda p, i: llm_page_response_foto())
    monkeypatch.setattr("main.detect_and_crop_face", lambda img: (make_color_image(50, 70), 0))

    fake_pdf = tmp_path / "test_invalid_dni.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")
    result = main.process_single_pdf(fake_pdf)

    assert result == "revision"
    jsons = list(review_dir.rglob("datos.json"))
    assert len(jsons) == 1
    data = json.loads(jsons[0].read_text())
    assert data["metadata"]["en_revision"] is True


# ── Pipeline sin fotos → revisión/foto ───────────────────────────────────────

@pytest.mark.integration
def test_pipeline_sin_foto_va_a_revision_foto(monkeypatch, tmp_path):
    import main
    import modules.output_manager as om
    import modules.output_structure as os_

    output_dir = tmp_path / "output"
    review_dir = output_dir / "revision"
    output_dir.mkdir()
    monkeypatch.setattr(om, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(om, "REVIEW_DIR", review_dir)
    monkeypatch.setattr(os_, "OUTPUT_FOLDER_STRUCTURE", "{ciclo_codigo}")

    monkeypatch.setattr("main.pdf_to_images", lambda p: [make_gray_image()])
    monkeypatch.setattr("modules.form_extractor.call_model", lambda p, i: llm_form_response())
    monkeypatch.setattr("modules.page_analyzer.call_model", lambda p, i: None)
    monkeypatch.setattr("main.detect_and_crop_face", lambda img: (None, 0))  # sin cara

    fake_pdf = tmp_path / "test_no_foto.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")
    result = main.process_single_pdf(fake_pdf)

    assert result == "revision"
