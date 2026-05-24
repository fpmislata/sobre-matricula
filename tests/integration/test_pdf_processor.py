"""
Integration tests para modules/pdf_processor.

Usa tests/fixtures/sample.pdf (PDF real). Marcados @slow — se excluyen con -m "not slow".
También testea preprocess_for_ocr() con imágenes sintéticas (no slow).
"""
import pytest
from PIL import Image
from tests.fixtures.sample_images import make_color_image, make_gray_image


# ── preprocess_for_ocr (rápido, sin PDF) ─────────────────────────────────────

@pytest.mark.unit
def test_preprocess_for_ocr_devuelve_pil_image():
    from modules.pdf_processor import preprocess_for_ocr
    img = make_color_image(200, 300)
    result = preprocess_for_ocr(img)
    assert isinstance(result, Image.Image)


@pytest.mark.unit
def test_preprocess_for_ocr_mismo_size():
    from modules.pdf_processor import preprocess_for_ocr
    img = make_gray_image(150, 200)
    result = preprocess_for_ocr(img)
    assert result.size == img.size


@pytest.mark.unit
def test_preprocess_for_ocr_no_rompe_con_gris():
    from modules.pdf_processor import preprocess_for_ocr
    img = make_gray_image()
    result = preprocess_for_ocr(img)
    assert result is not None


# ── pdf_to_images (slow — usa PDF real) ──────────────────────────────────────

@pytest.mark.slow
@pytest.mark.integration
def test_pdf_to_images_devuelve_lista(sample_pdf):
    from modules.pdf_processor import pdf_to_images
    pages = pdf_to_images(sample_pdf)
    assert isinstance(pages, list)
    assert len(pages) >= 1


@pytest.mark.slow
@pytest.mark.integration
def test_pdf_to_images_paginas_son_pil(sample_pdf):
    from modules.pdf_processor import pdf_to_images
    pages = pdf_to_images(sample_pdf)
    for p in pages:
        assert isinstance(p, Image.Image)


@pytest.mark.slow
@pytest.mark.integration
def test_pdf_to_images_resolucion_razonable(sample_pdf):
    from modules.pdf_processor import pdf_to_images
    pages = pdf_to_images(sample_pdf)
    w, h = pages[0].size
    assert w >= 100
    assert h >= 100


@pytest.mark.slow
@pytest.mark.integration
def test_pdf_to_images_preprocess_chain(sample_pdf):
    """PDF → imágenes → preprocesar. Sin excepción = test válido."""
    from modules.pdf_processor import pdf_to_images, preprocess_for_ocr
    pages = pdf_to_images(sample_pdf)
    processed = preprocess_for_ocr(pages[0])
    assert isinstance(processed, Image.Image)
    assert processed.size == pages[0].size
