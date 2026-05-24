"""
Fixtures globales reutilizables para toda la suite de tests.

Convenciones:
- mock_llm_form / mock_llm_page: parchean call_model en el módulo que lo usa
- img_color / img_gray / img_blurry / img_sharp: imágenes PIL sintéticas
- result_json: JSON de resultado completo y válido (base para variaciones)
"""
import pytest
from tests.fixtures.sample_images import (
    make_color_image,
    make_gray_image,
    make_blurry_image,
    make_sharp_image,
    make_face_image,
)
from tests.fixtures.sample_jsons import (
    result_valido,
    llm_form_response,
    llm_page_response_documento,
    llm_page_response_foto,
)


# ── Imágenes PIL sintéticas ───────────────────────────────────────────────────

@pytest.fixture
def img_color():
    return make_color_image()


@pytest.fixture
def img_gray():
    return make_gray_image()


@pytest.fixture
def img_blurry():
    return make_blurry_image(make_color_image())


@pytest.fixture
def img_sharp():
    return make_sharp_image()


@pytest.fixture
def img_face():
    return make_face_image()


# ── JSON de resultado base ────────────────────────────────────────────────────

@pytest.fixture
def result_json():
    return result_valido()


# ── Mock del LLM ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm_form(monkeypatch):
    """
    Parchea call_model en form_extractor para devolver una respuesta controlada.

    Uso:
        def test_algo(mock_llm_form):
            mock_llm_form()                          # usa defaults
            mock_llm_form(response={"expediente": None, ...})  # custom
            mock_llm_form(returns_none=True)         # simula fallo LLM
    """
    def _setup(response: dict | None = None, returns_none: bool = False):
        resp = None if returns_none else (response or llm_form_response())
        monkeypatch.setattr("modules.form_extractor.call_model", lambda p, i: resp)
    return _setup


@pytest.fixture
def mock_llm_page(monkeypatch):
    """
    Parchea call_model en page_analyzer para devolver una respuesta controlada.

    Uso:
        mock_llm_page()                         # respuesta documento_identidad
        mock_llm_page(page_type="foto_carnet")  # respuesta foto
        mock_llm_page(returns_none=True)        # simula fallo LLM
    """
    def _setup(page_type: str = "documento_identidad", returns_none: bool = False,
               response: dict | None = None):
        if returns_none:
            resp = None
        elif response is not None:
            resp = response
        elif page_type == "foto_carnet":
            resp = llm_page_response_foto()
        else:
            resp = llm_page_response_documento()
        monkeypatch.setattr("modules.page_analyzer.call_model", lambda p, i: resp)
    return _setup


@pytest.fixture
def mock_llm_both(monkeypatch):
    """Parchea call_model en ambos módulos a la vez (útil para pipeline completo)."""
    def _setup(form_resp: dict | None = None, page_resp: dict | None = None,
               returns_none: bool = False):
        fr = None if returns_none else (form_resp or llm_form_response())
        pr = None if returns_none else (page_resp or llm_page_response_foto())
        monkeypatch.setattr("modules.form_extractor.call_model", lambda p, i: fr)
        monkeypatch.setattr("modules.page_analyzer.call_model", lambda p, i: pr)
    return _setup


# ── Helpers de paths ──────────────────────────────────────────────────────────

@pytest.fixture
def fixtures_dir():
    from pathlib import Path
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_pdf(fixtures_dir):
    p = fixtures_dir / "sample.pdf"
    if not p.exists():
        pytest.skip("sample.pdf no disponible en tests/fixtures/")
    return p


@pytest.fixture
def sample_face_jpg(fixtures_dir):
    p = fixtures_dir / "sample_face.jpg"
    if not p.exists():
        pytest.skip("sample_face.jpg no disponible en tests/fixtures/")
    return p
