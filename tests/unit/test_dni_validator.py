"""
Unit tests para modules/dni_validator.py.

DNIs válidos calculados (num % 23 → LETTER_TABLE[n]):
  12345678Z  (12345678 % 23 = 14 → Z)
  00000000T  (0 % 23 = 0 → T)
  11111111H  (11111111 % 23 = 18 → H)
  87654321X  (87654321 % 23 = 10 → X)

NIEs válidos:
  X1234567L  (01234567 % 23 = 19 → L)
  Y1234567X  (11234567 % 23 = 10 → X)
  Z1234567R  (21234567 % 23 = 1 → R)
"""
import pytest
from modules.dni_validator import validate_and_correct, _expected_letter, LETTER_TABLE


# ── _expected_letter ──────────────────────────────────────────────────────────

class TestExpectedLetter:
    def test_modulo_0_returns_T(self):
        assert _expected_letter("00000000") == "T"

    def test_modulo_14_returns_Z(self):
        assert _expected_letter("12345678") == "Z"

    def test_modulo_10_returns_X(self):
        assert _expected_letter("87654321") == "X"

    def test_letter_table_has_23_entries(self):
        assert len(LETTER_TABLE) == 23


# ── DNI válido (verificado) ───────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "12345678Z",
    "00000000T",
    "11111111H",
    "87654321X",
])
@pytest.mark.unit
def test_dni_valido_verificado(raw):
    r = validate_and_correct(raw)
    assert r["tipo"] == "DNI"
    assert r["estado"] == "verificado"
    assert r["numero_verificado"] == raw


@pytest.mark.unit
def test_dni_lowercase_normalizado():
    r = validate_and_correct("12345678z")
    assert r["estado"] == "verificado"
    assert r["numero_verificado"] == "12345678Z"


@pytest.mark.unit
def test_dni_con_puntos_y_guion():
    r = validate_and_correct("12.345.678-Z")
    assert r["estado"] == "verificado"
    assert r["numero_verificado"] == "12345678Z"


@pytest.mark.unit
def test_dni_con_espacios():
    r = validate_and_correct("12345678 Z")
    assert r["estado"] == "verificado"


# ── DNI letra incorrecta → corregida ─────────────────────────────────────────

@pytest.mark.unit
def test_dni_letra_incorrecta_se_corrige():
    r = validate_and_correct("12345678A")  # A ≠ Z
    assert r["tipo"] == "DNI"
    assert r["estado"] == "corregido"
    assert r["numero_verificado"] == "12345678Z"
    assert "detalle_correccion" in r and r["detalle_correccion"]


# ── Corrección OCR en dígitos ─────────────────────────────────────────────────

@pytest.mark.parametrize("raw_ocr,expected_verificado", [
    ("I2345678Z", "12345678Z"),   # I→1 en posición 0
    ("1234567BZ", "12345678Z"),   # B→8 en posición 7
    ("S2345678Z", "52345678Z") if False else pytest.param(
        "I2345678Z", "12345678Z", id="I_to_1"
    ),  # skipped, just two good ones
])
@pytest.mark.unit
def test_dni_ocr_digit_corrected(raw_ocr, expected_verificado):
    r = validate_and_correct(raw_ocr)
    assert r["estado"] == "corregido"
    assert r["numero_verificado"] == expected_verificado


@pytest.mark.unit
def test_ocr_I_to_1():
    r = validate_and_correct("I2345678Z")
    assert r["estado"] == "corregido"
    assert r["numero_verificado"] == "12345678Z"


@pytest.mark.unit
def test_ocr_B_to_8():
    r = validate_and_correct("1234567BZ")
    assert r["estado"] == "corregido"
    assert r["numero_verificado"] == "12345678Z"


# ── Corrección OCR en la letra (posición 8) ───────────────────────────────────

@pytest.mark.unit
def test_ocr_digit_in_letter_position():
    # '2' en pos 8 → LETTER_SUBS[2] = 'Z' → 12345678Z válido
    r = validate_and_correct("123456782")
    assert r["estado"] == "corregido"
    assert r["numero_verificado"] == "12345678Z"


# ── Letra extra al inicio ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_letra_extra_al_inicio_de_dni():
    r = validate_and_correct("A12345678Z")  # 10 chars: A + DNI
    assert r["estado"] == "corregido"
    assert r["tipo"] == "DNI"
    assert r["numero_verificado"] == "12345678Z"


# ── NIE válido ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected_tipo", [
    ("X1234567L", "NIE"),
    ("Y1234567X", "NIE"),
    ("Z1234567R", "NIE"),
])
@pytest.mark.unit
def test_nie_valido_verificado(raw, expected_tipo):
    r = validate_and_correct(raw)
    assert r["tipo"] == expected_tipo
    assert r["estado"] == "verificado"
    assert r["numero_verificado"] == raw


@pytest.mark.unit
def test_nie_letra_incorrecta_se_corrige():
    r = validate_and_correct("X1234567A")  # A ≠ L
    assert r["tipo"] == "NIE"
    assert r["estado"] == "corregido"
    assert r["numero_verificado"] == "X1234567L"


@pytest.mark.unit
def test_nie_z_inicial_no_se_convierte_en_2():
    # Z al inicio de NIE debe mantenerse como Z (NIE), no convertirse a 2 (dígito)
    r = validate_and_correct("Z1234567R")
    assert r["tipo"] == "NIE"
    assert r["numero_verificado"][0] == "Z"


# ── Pasaporte ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "ABC123456",
    "AAA12345678",
    "A12345678",
])
@pytest.mark.unit
def test_pasaporte_no_verificable(raw):
    r = validate_and_correct(raw)
    assert r["tipo"] == "PASAPORTE"
    assert r["estado"] == "no_verificable"
    assert r["numero_verificado"] == raw  # se devuelve tal cual


# ── Erróneos ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    None,
    "",
    "XXXXXXXXX",
    "123",
    "!@#$%^&*()",
    "ABCDEFGHI",
])
@pytest.mark.unit
def test_erroneo(raw):
    r = validate_and_correct(raw)
    assert r["estado"] == "erroneo"
    assert r["numero_verificado"] is None


# ── Estructura del resultado ──────────────────────────────────────────────────

@pytest.mark.unit
def test_resultado_tiene_todos_los_campos():
    r = validate_and_correct("12345678Z")
    assert "tipo" in r
    assert "numero_extraido" in r
    assert "numero_verificado" in r
    assert "estado" in r
    assert "detalle_correccion" in r


@pytest.mark.unit
def test_estado_valido_es_uno_de_los_esperados():
    estados = {"verificado", "corregido", "no_verificable", "erroneo"}
    for raw in ["12345678Z", "X1234567L", "ABC123456", None, "XXXX"]:
        r = validate_and_correct(raw)
        assert r["estado"] in estados
