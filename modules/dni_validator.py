import re
import logging

LETTER_TABLE = "TRWAGMYFPDXBNJZSQVHLCKE"
NIE_FIRST = {"X": "0", "Y": "1", "Z": "2"}

# Common OCR confusions: char that was read → what it might actually be
DIGIT_SUBS = {"O": "0", "I": "1", "L": "1", "B": "8", "S": "5", "G": "6", "Z": "2", "Q": "0"}
LETTER_SUBS = {"0": "O", "1": "I", "8": "B", "5": "S", "6": "G", "2": "Z", "7": "Z"}


def _expected_letter(number_str: str) -> str:
    return LETTER_TABLE[int(number_str) % 23]


def _check_nie(s: str) -> dict:
    nie_num = NIE_FIRST[s[0]] + s[1:8]
    expected = _expected_letter(nie_num)
    letra = s[8]
    if letra == expected:
        return _result("NIE", s, s, "verificado", None)
    corrected = s[:8] + expected
    return _result("NIE", s, corrected, "corregido", f"Letra corregida: '{letra}' → '{expected}'")


def _check_dni(s: str) -> dict:
    expected = _expected_letter(s[:8])
    letra = s[8]
    if letra == expected:
        return _result("DNI", s, s, "verificado", None)
    corrected = s[:8] + expected
    return _result("DNI", s, corrected, "corregido", f"Letra corregida: '{letra}' → '{expected}'")


def _result(tipo, extraido, verificado, estado, detalle):
    return {
        "tipo": tipo,
        "numero_extraido": extraido,
        "numero_verificado": verificado,
        "estado": estado,
        "detalle_correccion": detalle,
    }


def _apply_subs(s: str, pos_subs: dict) -> list[str]:
    """
    Generate all substitution variants of s applying per-position substitution dicts.
    pos_subs: {position_index: {char_read: char_corrected}}
    """
    candidates = [s]
    for i, ch in enumerate(s):
        subs = pos_subs.get(i, {})
        if ch in subs and subs[ch] != ch:
            candidates = candidates + [c[:i] + subs[ch] + c[i+1:] for c in candidates]
    return candidates


def _try_fix_ocr(s: str) -> str | None:
    """
    Try OCR correction applying positional rules for each document type:
      DNI  — pos 0-7: digit zone (DIGIT_SUBS), pos 8: letter zone (LETTER_SUBS)
      NIE  — pos 0: must be X/Y/Z (no substitution), pos 1-7: digit zone, pos 8: letter zone
    Returns the first format-valid candidate (checksum corrected later), or None.
    """
    if len(s) != 9:
        return None

    # -- Intentar como DNI: posiciones 0-7 dígitos, posición 8 letra --
    dni_subs = {i: DIGIT_SUBS for i in range(8)}
    dni_subs[8] = LETTER_SUBS
    for cand in _apply_subs(s, dni_subs):
        if cand == s:
            continue
        if re.match(r'^\d{8}[A-Z]$', cand):
            # Prefer candidates that also pass checksum
            if cand[8] == _expected_letter(cand[:8]):
                return cand

    for cand in _apply_subs(s, dni_subs):
        if cand == s:
            continue
        if re.match(r'^\d{8}[A-Z]$', cand):
            return cand  # _check_dni corregirá la letra si hace falta

    # -- Intentar como NIE: posición 0 solo X/Y/Z, posiciones 1-7 dígitos, posición 8 letra --
    nie_subs = {i: DIGIT_SUBS for i in range(1, 8)}
    nie_subs[8] = LETTER_SUBS
    # posición 0: no aplicamos sustituciones genéricas, solo dejamos pasar X/Y/Z
    for cand in _apply_subs(s, nie_subs):
        if cand == s:
            continue
        if re.match(r'^[XYZ]\d{7}[A-Z]$', cand):
            nie_num = NIE_FIRST[cand[0]] + cand[1:8]
            if cand[8] == _expected_letter(nie_num):
                return cand

    for cand in _apply_subs(s, nie_subs):
        if cand == s:
            continue
        if re.match(r'^[XYZ]\d{7}[A-Z]$', cand):
            return cand  # _check_nie corregirá la letra si hace falta

    return None


def validate_and_correct(raw: str | None) -> dict:
    if not raw:
        return _result("desconocido", "", None, "erroneo", "Campo vacío")

    s = str(raw).strip().upper().replace(" ", "").replace("-", "").replace(".", "")

    if re.match(r'^\d{8}[A-Z]$', s):
        return _check_dni(s)

    if re.match(r'^[XYZ]\d{7}[A-Z]$', s):
        return _check_nie(s)

    # Formulario relleno mal: letra extra al inicio de un DNI (ej: "A12345678Z")
    if re.match(r'^[A-Z]\d{8}[A-Z]$', s):
        candidate = s[1:]  # quitar letra inicial → 8 dígitos + letra
        base = _check_dni(candidate)
        base["numero_extraido"] = s
        base["estado"] = "corregido"
        base["detalle_correccion"] = f"Letra extra al inicio eliminada: '{s}' → '{candidate}'" + (f"; {base['detalle_correccion']}" if base["detalle_correccion"] else "")
        return base

    # Formulario relleno mal: letra extra al final de un DNI (ej: "12345678AB")
    if re.match(r'^\d{8}[A-Z]{2}$', s):
        for candidate in (s[:9], s[:8] + s[9]):  # probar con primera o segunda letra final
            if re.match(r'^\d{8}[A-Z]$', candidate):
                base = _check_dni(candidate)
                base["numero_extraido"] = s
                base["estado"] = "corregido"
                base["detalle_correccion"] = f"Letra extra al final eliminada: '{s}' → '{candidate}'" + (f"; {base['detalle_correccion']}" if base["detalle_correccion"] else "")
                return base

    # Formulario relleno mal: letra extra al inicio de un NIE (ej: "AX1234567Z")
    if re.match(r'^[A-Z][XYZ]\d{7}[A-Z]$', s):
        candidate = s[1:]  # quitar letra inicial → NIE estándar
        base = _check_nie(candidate)
        base["numero_extraido"] = s
        base["estado"] = "corregido"
        base["detalle_correccion"] = f"Letra extra al inicio eliminada: '{s}' → '{candidate}'" + (f"; {base['detalle_correccion']}" if base["detalle_correccion"] else "")
        return base

    # Try OCR correction
    fixed = _try_fix_ocr(s)
    if fixed:
        base = _check_dni(fixed) if re.match(r'^\d{8}[A-Z]$', fixed) else _check_nie(fixed)
        base["numero_extraido"] = s
        base["estado"] = "corregido"
        base["detalle_correccion"] = f"Corrección OCR: '{s}' → '{fixed}'" + (f"; {base['detalle_correccion']}" if base["detalle_correccion"] else "")
        return base

    # Passport: alphanumeric, no checksum
    if re.match(r'^[A-Z]{1,3}\d{5,9}$', s):
        return _result("PASAPORTE", s, s, "no_verificable", "Formato pasaporte, sin checksum")

    logging.warning(f"Documento no reconocido: '{s}'")
    return _result("desconocido", s, None, "erroneo", "Formato no reconocido")
