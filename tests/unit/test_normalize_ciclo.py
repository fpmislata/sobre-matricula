"""
Unit tests para modules/form_extractor.normalize_ciclo().

Ciclos del catálogo (de config.py):
  SUPERIOR: ASIR, DAM, DAW, AVGE, GAT, GIAT, CI, MP, AF, OPT, LCB
  MEDIO:    AC, GA, CAE, SMR
"""
import pytest
import modules.form_extractor as fe


@pytest.fixture(autouse=True)
def reset_ciclos_globals():
    """Garantiza que los globals de form_extractor usan los valores reales de config."""
    from config import CICLOS, GRADO_SUPERIOR, GRADO_MEDIO
    fe.CICLOS = CICLOS
    fe.GRADO_SUPERIOR = GRADO_SUPERIOR
    fe.GRADO_MEDIO = GRADO_MEDIO
    yield


# ── Sin input ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_none_sin_hint_devuelve_codigo_none():
    r = fe.normalize_ciclo(None)
    assert r["codigo"] is None


@pytest.mark.unit
def test_string_vacio_sin_hint_devuelve_codigo_none():
    r = fe.normalize_ciclo("")
    assert r["codigo"] is None


# ── Coincidencia exacta por código ────────────────────────────────────────────

@pytest.mark.parametrize("codigo", ["DAW", "SMR", "ASIR", "DAM", "GA", "CAE"])
@pytest.mark.unit
def test_exact_match_codigo(codigo):
    r = fe.normalize_ciclo(codigo)
    assert r["codigo"] == codigo


@pytest.mark.parametrize("raw,codigo", [
    ("daw", "DAW"),
    ("smr", "SMR"),
    ("asir", "ASIR"),
])
@pytest.mark.unit
def test_exact_match_codigo_lowercase(raw, codigo):
    r = fe.normalize_ciclo(raw)
    assert r["codigo"] == codigo


# ── Coincidencia exacta por nombre completo ───────────────────────────────────

@pytest.mark.parametrize("nombre_completo,codigo_esperado", [
    ("Desarrollo de Aplicaciones Web", "DAW"),
    ("Sistemas Microinformáticos y Redes", "SMR"),
    ("Gestión Administrativa", "GA"),
])
@pytest.mark.unit
def test_exact_match_nombre_completo(nombre_completo, codigo_esperado):
    r = fe.normalize_ciclo(nombre_completo)
    assert r["codigo"] == codigo_esperado


# ── Coincidencia por token ────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,codigo_esperado", [
    ("SMR - Sistemas", "SMR"),
    ("DAW/Desarrollo", "DAW"),
    ("Ciclo GA,Gestión", "GA"),
    ("ASIR redes", "ASIR"),
])
@pytest.mark.unit
def test_token_match(raw, codigo_esperado):
    r = fe.normalize_ciclo(raw)
    assert r["codigo"] == codigo_esperado


# ── Coincidencia por contención (boundary) ───────────────────────────────────

@pytest.mark.parametrize("raw,codigo_esperado", [
    ("ciclo daw presencial", "DAW"),
    ("matricula SMR 2025", "SMR"),
])
@pytest.mark.unit
def test_containment_match(raw, codigo_esperado):
    r = fe.normalize_ciclo(raw)
    assert r["codigo"] == codigo_esperado


# ── Fuzzy matching ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,codigo_esperado", [
    ("Desrrollo de Aplicaciones Web", "DAW"),       # typo en 'Desarrollo'
    ("Sistemas Microinformaticos y Redes", "SMR"),  # sin tilde
    ("Administracion de Sistemas Informaticos en Red", "ASIR"),  # sin tildes (1 cambio)
])
@pytest.mark.unit
def test_fuzzy_match(raw, codigo_esperado):
    r = fe.normalize_ciclo(raw)
    assert r["codigo"] == codigo_esperado


# ── codigo_hint gana sobre raw ────────────────────────────────────────────────

@pytest.mark.unit
def test_codigo_hint_valido_gana():
    r = fe.normalize_ciclo("texto confuso irreconocible", codigo_hint="DAW")
    assert r["codigo"] == "DAW"


@pytest.mark.unit
def test_codigo_hint_invalido_cae_a_raw():
    r = fe.normalize_ciclo("DAW", codigo_hint="XXXXXXXX")
    # El hint no existe en CICLOS → se ignora → raw "DAW" resuelve por exact match
    assert r["codigo"] == "DAW"


@pytest.mark.unit
def test_codigo_hint_con_raw_none():
    r = fe.normalize_ciclo(None, codigo_hint="SMR")
    assert r["codigo"] == "SMR"


# ── Sin match → None ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "XXXXXXXX",
    "algo completamente irreconocible y muy largo",
])
@pytest.mark.unit
def test_sin_match_codigo_es_none(raw):
    r = fe.normalize_ciclo(raw)
    assert r["codigo"] is None


# ── Grado correcto ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("codigo,grado_esperado", [
    ("DAW",  "superior"),
    ("ASIR", "superior"),
    ("DAM",  "superior"),
    ("SMR",  "medio"),
    ("GA",   "medio"),
    ("CAE",  "medio"),
])
@pytest.mark.unit
def test_grado_correcto(codigo, grado_esperado):
    r = fe.normalize_ciclo(codigo)
    assert r["grado"] == grado_esperado


# ── Estructura del resultado ──────────────────────────────────────────────────

@pytest.mark.unit
def test_resultado_tiene_todos_los_campos():
    r = fe.normalize_ciclo("DAW")
    assert "codigo" in r
    assert "nombre_completo" in r
    assert "grado" in r
    assert "texto_original" in r


@pytest.mark.unit
def test_texto_original_preservado():
    raw = "daw presencial 2025"
    r = fe.normalize_ciclo(raw)
    assert r["texto_original"] == raw


@pytest.mark.unit
def test_nombre_completo_no_none_cuando_codigo_resuelto():
    r = fe.normalize_ciclo("DAW")
    assert r["nombre_completo"] is not None
    assert len(r["nombre_completo"]) > 3
