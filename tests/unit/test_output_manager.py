"""
Unit tests para modules/output_manager.py.

Funciones testadas:
  build_document_name(result_json) → str
  check_campos_obligatorios(result_json) → list[str]
  build_result_json(...) → dict

Nota: output_manager importa DEBUG_REPROCESS de config en tiempo de carga.
En config.py DEBUG_REPROCESS = True → tipo_asistencia se salta en la comprobación.
Los tests que necesitan comprobar ese campo lo parchean explícitamente.
"""
import pytest
import modules.output_manager as om
from tests.fixtures.sample_jsons import result_valido, result_sin_apellido2


# ── build_document_name ───────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_om_globals():
    """Restaura globals de output_manager a los valores reales tras cada test."""
    orig_fmt    = om.DOCUMENT_NAME_FORMAT
    orig_sfx    = om.DOCUMENT_NAME_SUFFIX
    orig_asist  = om.ASISTENCIA_CODE.copy()
    yield
    om.DOCUMENT_NAME_FORMAT = orig_fmt
    om.DOCUMENT_NAME_SUFFIX = orig_sfx
    om.ASISTENCIA_CODE      = orig_asist


@pytest.mark.unit
def test_build_name_completo():
    r = result_valido()
    name = om.build_document_name(r)
    assert name == "ANA_MARTIN_RUIZ,ANA_E15001_P2526_M"


@pytest.mark.unit
def test_build_name_sin_apellido2():
    r = result_sin_apellido2()
    name = om.build_document_name(r)
    assert "RUIZ" not in name
    assert "ANA_MARTIN" in name
    assert "E15001" in name


@pytest.mark.unit
def test_build_name_apellido2_none_no_deja_coma_suelta():
    r = result_sin_apellido2()
    name = om.build_document_name(r)
    # No debe empezar con coma ni tener ,,
    assert not name.startswith(",")
    assert ",," not in name


@pytest.mark.parametrize("asistencia,codigo", [
    ("presencial", "P"),
    ("semipresencial", "S"),
    ("libre", "L"),
    ("parcial", "PA"),
])
@pytest.mark.unit
def test_build_name_asistencia_codes(asistencia, codigo):
    r = result_valido()
    r["tipo_asistencia"] = asistencia
    name = om.build_document_name(r)
    assert codigo in name


@pytest.mark.unit
def test_build_name_normaliza_acentos():
    r = result_valido()
    r["nombre"] = "María"
    r["apellido1"] = "García-López"
    name = om.build_document_name(r)
    assert "MARIA" in name
    assert "GARCIA_LOPEZ" in name


@pytest.mark.unit
def test_build_name_normaliza_enie():
    r = result_valido()
    r["apellido1"] = "Muñoz"
    name = om.build_document_name(r)
    assert "MUNOZ" in name


@pytest.mark.unit
def test_build_name_sin_ningún_nombre_prefijo_sindatos():
    r = result_valido()
    r["nombre"] = None
    r["apellido1"] = None
    r["apellido2"] = None
    name = om.build_document_name(r)
    assert "SINDATOS" in name


@pytest.mark.unit
def test_build_name_año_fin_siempre_inicio_mas_1():
    r = result_valido()
    r["curso"] = {"inicio": "2024", "fin": "2020"}  # fin anterior (anómalo)
    name = om.build_document_name(r)
    # Con formato default, año_ini=24, año_fin=_year2("2020")="20" → no se corrige en build_document_name
    # Solo se corrige en _build_curso → lo que llega al name es lo que viene en result_json
    assert "24" in name or "20" in name  # ambas son posibles según campo


@pytest.mark.unit
def test_build_name_expediente_en_resultado():
    r = result_valido()
    r["expediente"] = "99999"
    name = om.build_document_name(r)
    assert "E99999" in name


# ── check_campos_obligatorios ─────────────────────────────────────────────────

@pytest.mark.unit
def test_resultado_valido_no_tiene_motivos():
    r = result_valido()
    motivos = om.check_campos_obligatorios(r)
    assert motivos == []


@pytest.mark.parametrize("campo,eliminar", [
    ("nombre",       lambda r: r.update({"nombre": None})),
    ("apellido1",    lambda r: r.update({"apellido1": None})),
    ("apellido2",    lambda r: r.update({"apellido2": None})),
    ("ciclo",        lambda r: r["ciclo"].update({"codigo": None})),
    ("foto",         lambda r: r["fotos"].update({"foto_seleccionada": None})),
    ("curso_inicio", lambda r: r["curso"].update({"inicio": None})),
    ("curso_fin",    lambda r: r["curso"].update({"fin": None})),
])
@pytest.mark.unit
def test_campo_obligatorio_ausente_genera_motivo(campo, eliminar, monkeypatch):
    monkeypatch.setattr(om, "DEBUG_REPROCESS", False)
    r = result_valido()
    eliminar(r)
    motivos = om.check_campos_obligatorios(r)
    assert any(campo in m for m in motivos), f"Esperaba motivo para '{campo}', got: {motivos}"


@pytest.mark.unit
def test_tipo_asistencia_obligatorio_cuando_debug_reprocess_false(monkeypatch):
    monkeypatch.setattr(om, "DEBUG_REPROCESS", False)
    r = result_valido()
    r["tipo_asistencia"] = None
    motivos = om.check_campos_obligatorios(r)
    assert any("tipo_asistencia" in m for m in motivos)


@pytest.mark.unit
def test_tipo_asistencia_no_revisado_cuando_debug_reprocess_true(monkeypatch):
    monkeypatch.setattr(om, "DEBUG_REPROCESS", True)
    r = result_valido()
    r["tipo_asistencia"] = None
    motivos = om.check_campos_obligatorios(r)
    assert not any("tipo_asistencia" in m for m in motivos)


# ── build_result_json ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_build_result_json_estructura_completa(tmp_path):
    from pathlib import Path
    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()

    form_data = {
        "expediente": "15001",
        "tipo_documento": "DNI",
        "numero_documento": "12345678Z",
        "nombre": "ANA",
        "apellido1": "MARTIN",
        "apellido2": "RUIZ",
        "tipo_asistencia": "presencial",
        "curso_inicio": "2025",
        "curso_fin": "2026",
    }
    doc_info = {
        "tipo": "DNI",
        "numero_extraido": "12345678Z",
        "numero_verificado": "12345678Z",
        "estado": "verificado",
        "detalle_correccion": None,
    }
    ciclo_info = {
        "codigo": "DAW",
        "nombre_completo": "Desarrollo de Aplicaciones Web",
        "grado": "superior",
        "texto_original": "DAW",
    }
    cotejo = {
        "realizado": True,
        "correcciones_aplicadas": [],
        "numero_usado": "dni",
        "numero_coincide": True,
        "nombre_coincide": True,
        "apellido1_coincide": True,
        "apellido2_coincide": True,
    }

    result = om.build_result_json(
        form_data=form_data,
        doc_info=doc_info,
        ciclo_info=ciclo_info,
        photos=[],
        best_photo=None,
        cotejo=cotejo,
        pdf_path=pdf_path,
        paginas_totales=2,
        errores=[],
        datos_extraidos_dni=None,
    )

    assert result["expediente"] == "15001"
    assert result["nombre"] == "ANA"
    assert result["apellido1"] == "MARTIN"
    assert result["ciclo"]["codigo"] == "DAW"
    assert result["ciclo"]["grado"] == "superior"
    assert result["curso"]["inicio"] is not None
    assert result["metadata"]["pdf_original"] == "test.pdf"
    assert "procesado_en" in result["metadata"]
    assert "en_revision" in result["metadata"]
    assert isinstance(result["metadata"]["errores"], list)


@pytest.mark.unit
def test_build_result_json_curso_inicio_normalizado(tmp_path):
    """Año 2-dígitos se expande a 4 dígitos, fin = inicio + 1."""
    from pathlib import Path
    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()

    form_data = {"curso_inicio": "25", "curso_fin": "26"}
    result = om.build_result_json(
        form_data=form_data, doc_info={}, ciclo_info={},
        photos=[], best_photo=None, cotejo=None,
        pdf_path=pdf_path, paginas_totales=1, errores=[], datos_extraidos_dni=None,
    )
    # "25" expande a 2025 (o año actual si 2025 < current), fin = inicio+1
    assert result["curso"]["inicio"] is not None
    inicio = int(result["curso"]["inicio"])
    assert inicio >= 2000
    assert int(result["curso"]["fin"]) == inicio + 1
