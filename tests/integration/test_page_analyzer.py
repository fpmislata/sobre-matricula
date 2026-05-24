"""
Integration tests para modules/page_analyzer.analyze_page().

LLM mockeado via monkeypatch en modules.page_analyzer.call_model.
"""
import pytest
from tests.fixtures.sample_images import make_gray_image
from tests.fixtures.sample_jsons import (
    llm_page_response_documento,
    llm_page_response_foto,
    llm_page_response_otro,
)


# ── analyze_page: respuestas normales ────────────────────────────────────────

@pytest.mark.integration
def test_analyze_page_documento_identidad(mock_llm_page):
    mock_llm_page("documento_identidad")
    from modules.page_analyzer import analyze_page
    result = analyze_page(make_gray_image())

    assert result["tipo_pagina"] == "documento_identidad"
    assert result["subtipo_documento"] == "DNI"
    assert result["datos_documento"]["numero_documento"] == "87654321X"


@pytest.mark.integration
def test_analyze_page_foto_carnet(mock_llm_page):
    mock_llm_page("foto_carnet")
    from modules.page_analyzer import analyze_page
    result = analyze_page(make_gray_image())
    assert result["tipo_pagina"] == "foto_carnet"


@pytest.mark.integration
def test_analyze_page_otro(mock_llm_page):
    mock_llm_page(response=llm_page_response_otro())
    from modules.page_analyzer import analyze_page
    result = analyze_page(make_gray_image())
    assert result["tipo_pagina"] == "otro"


# ── analyze_page: LLM falla ───────────────────────────────────────────────────

@pytest.mark.integration
def test_analyze_page_llm_none_devuelve_otro(mock_llm_page):
    """Si el LLM devuelve None, la página se clasifica como 'otro' (fallback seguro)."""
    mock_llm_page(returns_none=True)
    from modules.page_analyzer import analyze_page
    result = analyze_page(make_gray_image())
    assert result["tipo_pagina"] == "otro"
    assert result["datos_documento"] is None


@pytest.mark.integration
def test_analyze_page_respuesta_con_tipo_desconocido(mock_llm_page):
    resp = {"tipo_pagina": "tipo_no_valido", "subtipo_documento": None, "datos_documento": None}
    mock_llm_page(response=resp)
    from modules.page_analyzer import analyze_page
    result = analyze_page(make_gray_image())
    assert isinstance(result, dict)
    assert "tipo_pagina" in result


# ── analyze_page: estructura de respuesta ─────────────────────────────────────

@pytest.mark.integration
def test_analyze_page_estructura_resultado(mock_llm_page):
    mock_llm_page("documento_identidad")
    from modules.page_analyzer import analyze_page
    result = analyze_page(make_gray_image())
    assert "tipo_pagina" in result
    assert "subtipo_documento" in result
    assert "datos_documento" in result


# ── cross_check integrado ─────────────────────────────────────────────────────

@pytest.mark.integration
def test_cross_check_con_datos_reales():
    """cross_check no usa LLM — test de integración con validate_and_correct real."""
    from modules.page_analyzer import cross_check

    form = {
        "numero_documento": "12345678Z",
        "nombre": "JUAN",
        "apellido1": "GARCIA",
        "apellido2": "PEREZ",
    }
    doc = {
        "numero_documento": "12345678Z",
        "nombre": "JUAN",
        "apellido1": "GARCIA",
        "apellido2": "PEREZ",
    }
    result = cross_check(form, doc)
    assert result["realizado"] is True
    assert result["numero_coincide"] is True
    assert result["nombre_coincide"] is True


@pytest.mark.integration
def test_cross_check_corrige_numero_ocr():
    """OCR en doc (I→1) se corrige; form verificado gana → numero_usado=formulario."""
    from modules.page_analyzer import cross_check
    form = {"numero_documento": "12345678Z", "nombre": "ANA", "apellido1": "MARTIN", "apellido2": "RUIZ"}
    doc  = {"numero_documento": "I2345678Z", "nombre": "ANA", "apellido1": "MARTIN", "apellido2": "RUIZ"}
    result = cross_check(form, doc)
    assert result["numero_usado"] == "formulario"
