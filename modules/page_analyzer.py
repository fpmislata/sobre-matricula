import logging
import unicodedata
from PIL import Image
from Levenshtein import distance as levenshtein_distance
from utils.image_utils import image_to_base64
from utils.ollama_client import call_model
from modules.dni_validator import validate_and_correct

PAGE_PROMPT = """ATENCIÓN: Analiza EXCLUSIVAMENTE la imagen adjunta en este mensaje.
No uses ningún dato, nombre, número ni información de imágenes o llamadas anteriores.
Cada llamada es completamente independiente. No recuerdes nada de imágenes previas.
Si no ves algo con claridad en ESTA imagen, devuelve null — nunca inventes ni reutilices datos.

Analiza esta imagen escaneada de un expediente académico.
Determina qué tipo de contenido contiene y extrae datos si es un documento de identidad.
Devuelve ÚNICAMENTE un objeto JSON válido con EXACTAMENTE este esquema:

{
  "tipo_pagina": "foto_carnet o documento_identidad o otro",
  "subtipo_documento": "DNI o NIE o PASAPORTE o null",
  "datos_documento": {
    "nombre": "string o null",
    "apellido1": "string o null",
    "apellido2": "string o null",
    "numero_documento": "string en mayúsculas sin espacios o null"
  }
}

REGLA CRÍTICA para clasificar el tipo de página:

"documento_identidad": la imagen muestra un DNI, NIE o pasaporte español (cara delantera, dorso, o ambas).
  - CARA DELANTERA: foto de la persona, nombre, apellidos, número de documento, fecha nacimiento/caducidad, chip dorado (DNI).
  - DORSO: código MRZ (dos líneas de caracteres alfanuméricos con <<), número de soporte, domicilio, firma, o código de barras.
  - Tanto la cara delantera como el dorso son "documento_identidad".
  - El documento puede tener una foto de cara dentro — eso NO lo convierte en foto_carnet.
  - Si ves texto de documento, MRZ, número de DNI/NIE o cualquier campo oficial → "documento_identidad".
  - Aunque la imagen esté girada, sea una fotocopia o esté recortada → "documento_identidad".

"foto_carnet": la imagen muestra SOLO una fotografía de una persona, sin ningún texto de documento alrededor.
  - Fondo liso o neutro, cara centrada, sin número de DNI/NIE ni campos de texto visibles.
  - Si hay CUALQUIER texto de documento visible → NO es foto_carnet, es documento_identidad.

"otro": formularios adicionales, hojas en blanco, texto sin cara ni documento de identidad.

Para "documento_identidad" extrae en datos_documento ÚNICAMENTE el texto que sea DIRECTAMENTE VISIBLE en esta imagen:
- nombre: solo el nombre de pila que aparezca impreso en el documento (ej: "KENJI"). Si no ves un nombre claramente, escribe null.
- apellido1: primer apellido impreso en el documento. Si no lo ves claramente, escribe null.
- apellido2: segundo apellido si aparece impreso, o null.
- numero_documento: número completo en mayúsculas sin espacios ni guiones tal como aparece en el documento.

ORDEN DE APELLIDOS en DNI/NIE español — regla crítica:
- Si ves etiquetas explícitas "PRIMER APELLIDO" / "SEGUNDO APELLIDO": úsalas directamente como apellido1 y apellido2.
- Si ves un campo unificado "APELLIDOS" con ambos apellidos: el primero (izquierda/arriba) es apellido1, el segundo es apellido2.
- Si ves la zona MRZ al pie del documento (líneas con <<): el formato es APELLIDO1<<APELLIDO2<<NOMBRE<... — úsalo como referencia de orden si es legible.
- NUNCA inviertas el orden de los apellidos respecto a cómo aparecen en el documento.

REGLAS ABSOLUTAS para datos_documento:
- Devuelve ÚNICAMENTE el texto visible en la imagen. No infieras, no completes, no inventes.
- Si un campo no es legible con certeza, escribe null. Es preferible null a un dato incorrecto.
- NO copies datos de imágenes anteriores ni de ninguna otra fuente.
- NO rellenes campos basándote en lo que "debería" aparecer — solo lo que ves.

Si el documento es un DNI/NIE aplica las mismas reglas posicionales que para el formulario:
- DNI posiciones 1-8 dígitos (O→0, I/L→1, B→8, S→5, G→6), posición 9 letra de control
- NIE: posición 1 X/Y/Z, posiciones 2-8 dígitos, posición 9 letra de control

Si la imagen está girada o inclinada analiza igualmente el contenido.
datos_documento solo se rellena si tipo_pagina == "documento_identidad", en otro caso null en todos los subcampos.

RECUERDA FINAL: Solo puedes devolver datos que veas físicamente en la imagen adjunta. Cualquier dato que no aparezca en esta imagen debe ser null.
"""


def analyze_page(page_img: Image.Image) -> dict:
    img_b64 = image_to_base64(page_img)
    data = call_model(PAGE_PROMPT, img_b64)
    if data is None:
        logging.warning("El modelo no pudo clasificar la página")
        return {"tipo_pagina": "otro", "subtipo_documento": None, "datos_documento": None}
    logging.info(f"Página clasificada como: {data.get('tipo_pagina')}")
    return data


def cross_check(form_data: dict, doc_data: dict | None) -> dict | None:
    """Compare form data with identity document data and update form_data in place.

    Lógica de confianza acordada:
    - Número: sin corrección gana sobre con corrección; ante empate gana el DNI.
    - Nombres: si el número del DNI valida (con o sin corrección), los nombres del DNI
      siempre prevalecen. Si el número del DNI no valida, se ignoran sus nombres.
    """
    if not doc_data:
        return None

    result = {
        "realizado": True,
        "correcciones_aplicadas": [],
    }

    # ── Determinar número fiable y cuál usar ──────────────────────────────────
    form_num_raw = (form_data.get("numero_documento") or "").strip().upper()
    doc_num_raw = (doc_data.get("numero_documento") or "").strip().upper()

    form_validation = validate_and_correct(form_num_raw) if form_num_raw else None
    doc_validation = validate_and_correct(doc_num_raw) if doc_num_raw else None

    form_valid = form_validation and form_validation.get("estado") in ("verificado", "corregido", "no_verificable")
    form_sin_correccion = form_validation and form_validation.get("estado") == "verificado"

    doc_valid = doc_validation and doc_validation.get("estado") in ("verificado", "corregido", "no_verificable")
    doc_sin_correccion = doc_validation and doc_validation.get("estado") == "verificado"

    # El número del DNI valida Y es OCR-similar al del formulario → nombres fiables
    # Si los números son completamente distintos, el modelo está alucinando (contaminación)
    numeros_similares = _numeros_ocr_similares(form_num_raw, doc_num_raw)
    dni_nombres_fiables = doc_valid and numeros_similares

    # Seleccionar el número ganador según la tabla de prioridades
    if doc_sin_correccion:
        # DNI sin corrección → gana siempre (incluso si formulario también sin corrección)
        numero_ganador = doc_validation["numero_verificado"]
        result["numero_usado"] = "dni"
    elif not doc_sin_correccion and form_sin_correccion:
        # DNI necesita corrección, formulario no → gana formulario
        numero_ganador = form_validation["numero_verificado"]
        result["numero_usado"] = "formulario"
    elif doc_valid:
        # Ambos necesitan corrección → gana DNI corregido
        numero_ganador = doc_validation["numero_verificado"]
        result["numero_usado"] = "dni_corregido"
    elif form_valid:
        # DNI no valida → formulario
        numero_ganador = form_validation["numero_verificado"]
        result["numero_usado"] = "formulario_dni_invalido"
        dni_nombres_fiables = False
    else:
        numero_ganador = form_num_raw or doc_num_raw
        result["numero_usado"] = "ninguno_valido"
        dni_nombres_fiables = False

    if numero_ganador and numero_ganador != form_num_raw:
        result["correcciones_aplicadas"].append(
            f"numero_documento: {form_num_raw} → {numero_ganador} (fuente: {result['numero_usado']})"
        )
    form_data["numero_documento"] = numero_ganador

    result["numero_coincide"] = (
        (form_num_raw == doc_num_raw) if form_num_raw and doc_num_raw else None
    )

    if not dni_nombres_fiables:
        motivo = (
            "número del DNI no es variante OCR del formulario — posible contaminación del modelo"
            if doc_valid and not numeros_similares
            else "número del DNI no valida"
        )
        logging.warning(f"Nombres del DNI ignorados: {motivo}")
        result["nombre_coincide"] = None
        result["apellido1_coincide"] = None
        result["apellido2_coincide"] = None
        result["correcciones_aplicadas"].append(f"nombres: DNI descartado ({motivo})")
        return result

    # ── Nombres: DNI siempre prevalece si valida ──────────────────────────────
    # Excepción: si los apellidos son los mismos pero intercambiados, el LLM
    # cometió un error de orden al leer el DNI → preservar el orden del formulario.
    swapped = _apellidos_swapped(form_data, doc_data)
    if swapped:
        fa1 = _ascii_key(form_data.get("apellido1"))
        fa2 = _ascii_key(form_data.get("apellido2"))
        da1 = _ascii_key(doc_data.get("apellido1"))
        da2 = _ascii_key(doc_data.get("apellido2"))
        logging.warning(
            f"Apellidos del DNI en orden invertido (formulario: {fa1}/{fa2}, "
            f"dni: {da1}/{da2}) — se preserva el orden del formulario"
        )
        result["correcciones_aplicadas"].append(
            f"apellidos: orden del DNI ({da1}/{da2}) invertido respecto al formulario "
            f"({fa1}/{fa2}) — se preserva orden del formulario"
        )

    for field in ("nombre", "apellido1", "apellido2"):
        form_val = (form_data.get(field) or "").strip().upper() or None
        doc_val = (doc_data.get(field) or "").strip().upper() or None

        if not doc_val:
            result[f"{field}_coincide"] = None
            continue

        if swapped and field in ("apellido1", "apellido2"):
            result[f"{field}_coincide"] = False
            continue

        coincide = (form_val == doc_val) if form_val else None
        result[f"{field}_coincide"] = coincide

        if doc_val != form_val:
            accion = "rellenado" if not form_val else "corregido"
            result["correcciones_aplicadas"].append(
                f"{field}: {accion} desde DNI — formulario='{form_val}' → dni='{doc_val}'"
            )
        form_data[field] = doc_val

    return result


def _ascii_key(s: str | None) -> str:
    """Normalize string to ASCII uppercase without accents for comparison."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s.strip().upper())
    return nfkd.encode("ascii", "ignore").decode("ascii")


def _apellidos_swapped(form_data: dict, doc_data: dict) -> bool:
    """True si los apellidos del formulario y del DNI son los mismos pero intercambiados."""
    fa1 = _ascii_key(form_data.get("apellido1"))
    fa2 = _ascii_key(form_data.get("apellido2"))
    da1 = _ascii_key(doc_data.get("apellido1"))
    da2 = _ascii_key(doc_data.get("apellido2"))
    return bool(fa1 and fa2 and da1 and da2 and fa1 == da2 and fa2 == da1)


def _compare(a: str | None, b: str | None) -> bool | None:
    if a is None or b is None:
        return None
    return a.strip().upper() == b.strip().upper()


def _ocr_similar(a: str, b: str) -> bool:
    a_up, b_up = a.strip().upper(), b.strip().upper()
    return levenshtein_distance(a_up, b_up) <= 2


def _numeros_ocr_similares(form_num: str, doc_num: str) -> bool:
    """True si los dos números parecen variantes OCR del mismo documento.

    Compara usando distancia de Levenshtein con umbral proporcional a la longitud.
    Un NIE completamente inventado (X1234567A vs Y9876543Z) da distancia alta → False.
    Un número con 1-2 caracteres confundidos por OCR (Y9876543Z vs Y9876543N) → True.
    Si alguno de los dos está vacío, se asume similares (no podemos contrastar).
    """
    if not form_num or not doc_num:
        return True
    a, b = form_num.strip().upper(), doc_num.strip().upper()
    max_len = max(len(a), len(b))
    # Umbral: hasta 3 caracteres diferentes para documentos de 9 caracteres
    threshold = max(3, max_len // 3)
    return levenshtein_distance(a, b) <= threshold
