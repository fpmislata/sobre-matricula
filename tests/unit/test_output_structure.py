"""
Unit tests para modules/output_structure.py.

Funciones testadas:
  normalize_segment(seg) → str
  resolve_hierarchy_path(template, result_json) → Path
  validate_structure_template(template) → tuple[bool, str]
"""
import pytest
from pathlib import Path
from modules.output_structure import (
    normalize_segment,
    resolve_hierarchy_path,
    validate_structure_template,
)


def _datos_daw():
    return {
        "ciclo": {"codigo": "DAW", "nombre_completo": "Desarrollo de Aplicaciones Web", "grado": "superior"},
        "curso": {"inicio": "2025", "fin": "2026"},
        "tipo_asistencia": "presencial",
        "expediente": "15001",
        "nombre": "ANA",
        "apellido1": "MARTIN",
        "documento": {"numero_verificado": "12345678Z"},
    }


def _datos_smr():
    return {
        "ciclo": {"codigo": "SMR", "nombre_completo": "Sistemas Microinformáticos y Redes", "grado": "medio"},
        "curso": {"inicio": "2024", "fin": "2025"},
        "tipo_asistencia": "semipresencial",
        "expediente": "15002",
        "nombre": "PEDRO",
        "apellido1": "LOPEZ",
        "documento": {"numero_verificado": "X1234567L"},
    }


# ── normalize_segment ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("DAW",                    "DAW"),
    ("daw",                    "DAW"),
    ("Desarrollo de Apps",     "DESARROLLO_DE_APPS"),
    ("García-López",           "GARCIA_LOPEZ"),
    ("con  espacios  dobles",  "CON_ESPACIOS_DOBLES"),
    ("con-guiones-y_bajo",     "CON_GUIONES_Y_BAJO"),
    ("Ñoño",                   "NONO"),
    ("__bordes__",             "BORDES"),
    ("",                       ""),
    ("!!@#",                   ""),
])
@pytest.mark.unit
def test_normalize_segment(raw, expected):
    assert normalize_segment(raw) == expected


@pytest.mark.unit
def test_normalize_segment_idempotente():
    seg = "García-López 2025"
    once = normalize_segment(seg)
    twice = normalize_segment(once)
    assert once == twice


# ── resolve_hierarchy_path ────────────────────────────────────────────────────

@pytest.mark.parametrize("template,expected", [
    ("{ciclo_codigo}",              Path("DAW")),
    ("{grado}/{ciclo_codigo}",      Path("SUPERIOR/DAW")),
    ("{ciclo_codigo}/{año_ini}{año_fin}", Path("DAW/2526")),
    ("",                            Path(".")),
])
@pytest.mark.unit
def test_resolve_hierarchy_path(template, expected):
    result = resolve_hierarchy_path(template, _datos_daw())
    assert result == expected


@pytest.mark.unit
def test_resolve_estructura_plana_devuelve_punto():
    r = resolve_hierarchy_path("", _datos_daw())
    assert r == Path(".")


@pytest.mark.unit
def test_resolve_campo_grado_superior():
    r = resolve_hierarchy_path("{grado}", _datos_daw())
    assert r == Path("SUPERIOR")


@pytest.mark.unit
def test_resolve_campo_grado_medio():
    r = resolve_hierarchy_path("{grado}", _datos_smr())
    assert r == Path("MEDIO")


@pytest.mark.unit
def test_resolve_campo_vacio_segmento_omitido():
    """Campo {grado} vacío → segmento descartado, resultado menos profundo."""
    datos = _datos_daw()
    datos["ciclo"]["grado"] = None
    r = resolve_hierarchy_path("{grado}/{ciclo_codigo}", datos)
    assert r == Path("DAW")  # grado vacío → solo ciclo_codigo


@pytest.mark.unit
def test_resolve_todos_campos_vacios_devuelve_punto():
    datos = {"ciclo": {}, "curso": {}, "tipo_asistencia": None, "expediente": None, "documento": {}}
    r = resolve_hierarchy_path("{grado}/{ciclo_codigo}", datos)
    assert r == Path(".")


@pytest.mark.unit
def test_resolve_path_no_absoluta():
    r = resolve_hierarchy_path("{ciclo_codigo}", _datos_daw())
    assert not r.is_absolute()


@pytest.mark.unit
def test_resolve_campo_ciclo_nombre():
    r = resolve_hierarchy_path("{ciclo_nombre}", _datos_daw())
    assert "DESARROLLO" in str(r)
    assert "APLICACIONES" in str(r)


@pytest.mark.unit
def test_resolve_campo_asistencia():
    r = resolve_hierarchy_path("{asistencia}", _datos_daw())
    assert r == Path("P")


@pytest.mark.unit
def test_resolve_campo_expediente():
    r = resolve_hierarchy_path("{expediente}", _datos_daw())
    assert r == Path("15001")


# ── validate_structure_template ───────────────────────────────────────────────

@pytest.mark.parametrize("template,expected_valid", [
    ("{ciclo_codigo}",          True),
    ("{grado}/{ciclo_codigo}",  True),
    ("{ciclo_codigo}/{año_ini}{año_fin}", True),
    ("",                        True),   # plana → válida
    ("{expediente}",            True),
    ("{nombre}/{ciclo_codigo}", True),
])
@pytest.mark.unit
def test_template_valido(template, expected_valid):
    valid, _ = validate_structure_template(template)
    assert valid is expected_valid


@pytest.mark.parametrize("template,reason_contains", [
    ("revision",               "reservad"),
    ("_borrados",              "reservad"),
    ("debug",                  "reservad"),
    ("/empieza_slash",         "/"),
    ("termina_slash/",         "/"),
    ("doble//slash",           "//"),
    ("con/../puntos",          ".."),
    ("{campo_desconocido}",    "desconocid"),
    ("{ciclo_codigo}/{unknown_field}", "desconocid"),
])
@pytest.mark.unit
def test_template_invalido(template, reason_contains):
    valid, msg = validate_structure_template(template)
    assert valid is False
    assert reason_contains.lower() in msg.lower()


@pytest.mark.unit
def test_template_vacio_es_valido_estructura_plana():
    valid, msg = validate_structure_template("")
    assert valid is True
    assert "plana" in msg.lower() or "sin subdir" in msg.lower()
