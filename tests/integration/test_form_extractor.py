"""
Integration tests para modules/form_extractor.extract_form_data().

LLM mockeado via monkeypatch en modules.form_extractor.call_model.
No se hacen llamadas de red reales.
"""
import pytest
from tests.fixtures.sample_images import make_gray_image
from tests.fixtures.sample_jsons import llm_form_response


# ── Respuesta completa ────────────────────────────────────────────────────────

@pytest.mark.integration
def test_extract_form_respuesta_completa(mock_llm_form):
    mock_llm_form()
    from modules.form_extractor import extract_form_data
    result = extract_form_data(make_gray_image())

    assert result["expediente"] == "15001"
    assert result["nombre"] == "ANA"
    assert result["apellido1"] == "MARTIN"
    assert result["apellido2"] == "RUIZ"
    assert result["numero_documento"] == "87654321X"
    assert result["tipo_asistencia"] == "presencial"


@pytest.mark.integration
def test_extract_form_ciclo_codigo(mock_llm_form):
    mock_llm_form()
    from modules.form_extractor import extract_form_data
    result = extract_form_data(make_gray_image())
    assert result["ciclo_codigo"] == "DAW"


# ── LLM devuelve None ─────────────────────────────────────────────────────────

@pytest.mark.integration
def test_extract_form_llm_none_devuelve_dict_vacio(mock_llm_form):
    """Si el LLM falla completamente, la función devuelve {} sin excepción."""
    mock_llm_form(returns_none=True)
    from modules.form_extractor import extract_form_data
    result = extract_form_data(make_gray_image())
    assert isinstance(result, dict)
    assert result == {}


# ── Reintento por expediente ausente ─────────────────────────────────────────

@pytest.mark.integration
def test_reintento_expediente_ausente(monkeypatch):
    """Primera llamada devuelve sin expediente; segunda (reintento) lo proporciona."""
    llm_resp_base = llm_form_response()
    llm_resp_base["expediente"] = None  # primera llamada sin expediente
    llm_resp_retry = {"expediente": "15001"}

    call_count = {"n": 0}

    def fake_call_model(prompt, img_b64):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return llm_resp_base
        return llm_resp_retry

    monkeypatch.setattr("modules.form_extractor.call_model", fake_call_model)
    from modules.form_extractor import extract_form_data
    result = extract_form_data(make_gray_image())

    assert call_count["n"] == 2
    assert result["expediente"] == "15001"


# ── Reintento por nombre ausente ──────────────────────────────────────────────

@pytest.mark.integration
def test_reintento_nombre_ausente(monkeypatch):
    """Primera llamada sin nombre/apellido1; segunda lo recupera."""
    llm_resp_base = llm_form_response()
    llm_resp_base["nombre"] = None
    llm_resp_base["apellido1"] = None
    llm_resp_retry = {"nombre": "ANA", "apellido1": "MARTIN", "apellido2": "RUIZ"}

    call_count = {"n": 0}

    def fake_call_model(prompt, img_b64):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return llm_resp_base
        return llm_resp_retry

    monkeypatch.setattr("modules.form_extractor.call_model", fake_call_model)
    from modules.form_extractor import extract_form_data
    result = extract_form_data(make_gray_image())

    assert result["nombre"] == "ANA"
    assert result["apellido1"] == "MARTIN"


# ── Reintento por apellido2 ausente ───────────────────────────────────────────

@pytest.mark.integration
def test_reintento_apellido2_ausente(monkeypatch):
    """apellido1 existe pero no apellido2; tercer reintento lo recupera."""
    base = llm_form_response()
    base["apellido2"] = None
    retries = {"apellido2": "RUIZ"}

    call_count = {"n": 0}

    def fake_call_model(prompt, img_b64):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return base
        return retries

    monkeypatch.setattr("modules.form_extractor.call_model", fake_call_model)
    from modules.form_extractor import extract_form_data
    result = extract_form_data(make_gray_image())
    assert result["apellido2"] == "RUIZ"


# ── Respuesta malformada (campos extras, tipos incorrectos) ───────────────────

@pytest.mark.integration
def test_respuesta_con_campos_extra_no_rompe(mock_llm_form):
    """Respuesta con campos extra no causa excepción."""
    resp = llm_form_response()
    resp["campo_inventado"] = "valor_extra"
    mock_llm_form(response=resp)
    from modules.form_extractor import extract_form_data
    result = extract_form_data(make_gray_image())
    assert isinstance(result, dict)


@pytest.mark.integration
def test_respuesta_con_solo_None_no_rompe(mock_llm_form):
    """Respuesta con todos los campos a None es manejada."""
    resp = {k: None for k in llm_form_response()}
    mock_llm_form(response=resp)
    from modules.form_extractor import extract_form_data
    result = extract_form_data(make_gray_image())
    assert isinstance(result, dict)
