"""
Unit tests para modules/page_analyzer.cross_check().

DNIs usados (todos válidos por checksum):
  12345678Z  → verificado sin corrección
  12345678A  → corregido (letra incorrecta, corrección → Z)
  I2345678Z  → corregido OCR (I→1, da 12345678Z)
  1234567BZ  → corregido OCR (B→8, da 12345678Z)
  XXXXXXXXX  → erroneo

Nota: cross_check modifica form_data IN PLACE.
"""
import pytest
from copy import deepcopy
from modules.page_analyzer import cross_check


def _form(num="12345678Z", nombre="JUAN", apellido1="GARCIA", apellido2="PEREZ"):
    return {
        "numero_documento": num,
        "nombre": nombre,
        "apellido1": apellido1,
        "apellido2": apellido2,
    }


def _doc(num="12345678Z", nombre="JUAN", apellido1="GARCIA", apellido2="PEREZ"):
    return {
        "numero_documento": num,
        "nombre": nombre,
        "apellido1": apellido1,
        "apellido2": apellido2,
    }


# ── doc_data None o vacío ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_doc_data_none_retorna_none():
    assert cross_check(_form(), None) is None


@pytest.mark.unit
def test_doc_data_sin_numero_se_trata_como_ninguno_valido():
    form = _form(num="12345678Z")
    doc = {"numero_documento": None, "nombre": "JUAN", "apellido1": "GARCIA", "apellido2": "PEREZ"}
    r = cross_check(form, doc)
    assert r is not None
    assert r["realizado"] is True


# ── Tabla de prioridades del número ──────────────────────────────────────────

@pytest.mark.unit
def test_dni_sin_correccion_gana_siempre():
    """DNI del documento válido sin corrección → numero_usado = 'dni'."""
    form = _form(num="12345678A")  # corregible
    doc  = _doc(num="12345678Z")   # verificado
    r = cross_check(form, doc)
    assert r["numero_usado"] == "dni"
    assert form["numero_documento"] == "12345678Z"


@pytest.mark.unit
def test_formulario_gana_si_dni_necesita_correccion_y_form_no():
    """DNI corregido, form verificado → numero_usado = 'formulario'."""
    form = _form(num="12345678Z")   # verificado
    doc  = _doc(num="I2345678Z")    # OCR corrección → corregido
    r = cross_check(form, doc)
    assert r["numero_usado"] == "formulario"
    assert form["numero_documento"] == "12345678Z"


@pytest.mark.unit
def test_dni_corregido_gana_si_ambos_necesitan_correccion():
    """Ambos con corrección → numero_usado = 'dni_corregido'."""
    form = _form(num="I2345678Z")   # OCR corregible
    doc  = _doc(num="1234567BZ")    # OCR corregible
    r = cross_check(form, doc)
    assert r["numero_usado"] == "dni_corregido"
    assert form["numero_documento"] == "12345678Z"


@pytest.mark.unit
def test_formulario_si_dni_invalido():
    """DNI erróneo, form OCR-corregible → numero_usado = 'formulario_dni_invalido'.

    Cuando doc es erróneo Y form también necesita corrección (no es verificado sin
    corrección), la rama 'elif form_valid' devuelve 'formulario_dni_invalido'.
    Si form es directamente verificado, la rama 'elif not doc_sin_correccion and
    form_sin_correccion' se activa antes y devuelve 'formulario' (comportamiento correcto
    del código — doc_sin_correccion=False satisface esa condición).
    """
    form = _form(num="I2345678Z")   # OCR, correcto → corregido (no verificado)
    doc  = _doc(num="XXXXXXXXX")    # erróneo
    r = cross_check(form, doc)
    assert r["numero_usado"] == "formulario_dni_invalido"


@pytest.mark.unit
def test_formulario_gana_si_dni_erroneo_y_form_verificado():
    """DNI erróneo, form directamente verificado → branch 'elif not doc_sin_correccion
    and form_sin_correccion' devuelve 'formulario' (rama 2, no rama 4)."""
    form = _form(num="12345678Z")   # verificado directo
    doc  = _doc(num="XXXXXXXXX")    # erróneo
    r = cross_check(form, doc)
    assert r["numero_usado"] == "formulario"


@pytest.mark.unit
def test_ninguno_valido():
    """Ambos inválidos → numero_usado = 'ninguno_valido'."""
    form = _form(num="XXXXXXXXX")
    doc  = _doc(num="YYYYYYYYY")
    r = cross_check(form, doc)
    assert r["numero_usado"] == "ninguno_valido"


# ── Nombres: DNI prevalece cuando número valida ───────────────────────────────

@pytest.mark.unit
def test_nombres_del_dni_prevalecen_cuando_numero_valida():
    form = _form(num="12345678Z", nombre="JUAN", apellido1="GARCIA", apellido2="PEREZ")
    doc  = _doc(num="12345678Z", nombre="JOHN", apellido1="GARCIA", apellido2="PEREZ")
    cross_check(form, doc)
    assert form["nombre"] == "JOHN"


@pytest.mark.unit
def test_apellidos_del_dni_prevalecen():
    form = _form(num="12345678Z", apellido1="GRCIA", apellido2="PEREZ")   # typo en form
    doc  = _doc(num="12345678Z", apellido1="GARCIA", apellido2="PEREZ")
    cross_check(form, doc)
    assert form["apellido1"] == "GARCIA"


@pytest.mark.unit
def test_nombres_ignorados_si_dni_numero_invalido():
    """DNI con número erróneo → nombres del DNI se ignoran."""
    form = _form(num="12345678Z", nombre="JUAN", apellido1="GARCIA")
    doc  = _doc(num="XXXXXXXXX", nombre="PEDRO", apellido1="LOPEZ")  # DNI inválido
    r = cross_check(form, doc)
    # nombre_coincide debe ser None (ignorado)
    assert r.get("nombre_coincide") is None
    # form mantiene su nombre original
    assert form["nombre"] == "JUAN"


@pytest.mark.unit
def test_nombres_ignorados_si_numeros_muy_diferentes():
    """Números completamente distintos (no OCR similares) → nombres descartados."""
    form = _form(num="12345678Z", nombre="JUAN")
    doc  = _doc(num="87654321X", nombre="PEDRO")   # DNI válido pero muy diferente
    cross_check(form, doc)
    assert form["nombre"] == "JUAN"  # nombre del DNI ignorado


# ── Estructura del resultado ──────────────────────────────────────────────────

@pytest.mark.unit
def test_resultado_tiene_campo_realizado():
    r = cross_check(_form(), _doc())
    assert r["realizado"] is True


@pytest.mark.unit
def test_resultado_tiene_correcciones_aplicadas():
    r = cross_check(_form(), _doc())
    assert "correcciones_aplicadas" in r
    assert isinstance(r["correcciones_aplicadas"], list)


@pytest.mark.unit
def test_numero_coincide_true_cuando_mismo_numero():
    form = _form(num="12345678Z")
    doc  = _doc(num="12345678Z")
    r = cross_check(form, doc)
    assert r["numero_coincide"] is True


@pytest.mark.unit
def test_numero_coincide_false_cuando_diferente():
    form = _form(num="12345678Z")
    doc  = _doc(num="I2345678Z")
    r = cross_check(form, doc)
    assert r["numero_coincide"] is False


# ── Apellido2 vacío en DNI → no sobreescribe form ────────────────────────────

@pytest.mark.unit
def test_apellido2_null_en_dni_no_sobreescribe():
    """Si el DNI no tiene apellido2, no se sobreescribe el del formulario."""
    form = _form(num="12345678Z", apellido2="RUIZ")
    doc  = _doc(num="12345678Z", apellido2=None)
    cross_check(form, doc)
    assert form["apellido2"] == "RUIZ"


# ── No modifica form_data cuando doc_data es None ────────────────────────────

@pytest.mark.unit
def test_no_modifica_form_si_doc_none():
    form = _form(num="12345678Z", nombre="JUAN")
    original = deepcopy(form)
    cross_check(form, None)
    assert form == original


# ── Swap detection: apellidos invertidos en DNI → se preserva orden del formulario ──

@pytest.mark.unit
def test_apellidos_swapped_preserva_orden_formulario():
    """DNI devuelve apellidos en orden inverso al formulario → se mantiene el orden del formulario."""
    form = _form(num="12345678Z", apellido1="MARTINEZ", apellido2="GOMEZ")
    doc  = _doc(num="12345678Z", apellido1="GOMEZ",    apellido2="MARTINEZ")
    r = cross_check(form, doc)
    assert form["apellido1"] == "MARTINEZ"
    assert form["apellido2"] == "GOMEZ"
    assert r["apellido1_coincide"] is False
    assert r["apellido2_coincide"] is False
    assert any("invertido" in c for c in r["correcciones_aplicadas"])


@pytest.mark.unit
def test_apellidos_swapped_con_acentos():
    """La normalización de acentos permite detectar el swap (MARTÍNEZ == MARTINEZ)."""
    form = _form(num="12345678Z", apellido1="MARTINEZ", apellido2="GOMEZ")
    doc  = _doc(num="12345678Z", apellido1="GÓMEZ",    apellido2="MARTÍNEZ")
    r = cross_check(form, doc)
    assert form["apellido1"] == "MARTINEZ"
    assert form["apellido2"] == "GOMEZ"
    assert any("invertido" in c for c in r["correcciones_aplicadas"])


@pytest.mark.unit
def test_apellidos_distintos_no_activa_swap():
    """Apellidos distintos (no swap) → el DNI sigue prevaleciendo."""
    form = _form(num="12345678Z", apellido1="GARCIA", apellido2="PEREZ")
    doc  = _doc(num="12345678Z", apellido1="LOPEZ",  apellido2="RUIZ")
    cross_check(form, doc)
    assert form["apellido1"] == "LOPEZ"
    assert form["apellido2"] == "RUIZ"


@pytest.mark.unit
def test_swap_no_activa_si_apellido2_vacio():
    """Sin apellido2 en formulario no se puede detectar swap — DNI prevalece normalmente."""
    form = _form(num="12345678Z", apellido1="GARCIA", apellido2=None)
    doc  = _doc(num="12345678Z", apellido1="GARCIA", apellido2=None)
    cross_check(form, doc)
    assert form["apellido1"] == "GARCIA"
