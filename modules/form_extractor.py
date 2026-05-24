import logging
from Levenshtein import distance as levenshtein_distance
from utils.image_utils import image_to_base64
from utils.ollama_client import call_model
from config import CICLOS, GRADO_SUPERIOR, GRADO_MEDIO
from PIL import Image

FORM_PROMPT = """ATENCIÓN: Analiza EXCLUSIVAMENTE la imagen que se adjunta en este mensaje.
No uses ningún dato de imágenes anteriores ni de otras llamadas.
No inventes ni rellenes campos con datos que no veas claramente en ESTA imagen.
Cada campo que no puedas leer con certeza debe ser null.

Eres un sistema OCR especializado en formularios de matrícula de centros de formación profesional españoles.
El formulario está escaneado, puede estar torcido, con ruido o escrito a mano en bolígrafo.

NÚMERO DE EXPEDIENTE — prioridad máxima:
- Está escrito A MANO en la esquina SUPERIOR DERECHA del formulario.
- Es un número de 5 cifras, SIEMPRE mayor de 15000 (ejemplos: 15402, 16237, 17089).
- Puede aparecer junto a la palabra "Expediente", "Exp.", "Nº" o solo el número.
- Busca con atención en la zona superior derecha antes de declararlo null.
- Si ves dígitos manuscritos en esa zona aunque estén torcidos o con mala tinta, es el expediente.

Extrae los datos del formulario y devuelve ÚNICAMENTE un objeto JSON válido con EXACTAMENTE este esquema:

{
  "expediente": "número de 5 cifras escrito a mano en la esquina superior derecha (mayor de 15000) o null",
  "tipo_documento": "DNI o NIE o PASAPORTE o null",
  "numero_documento": "string exacto sin espacios en mayúsculas o null",
  "nombre": "string o null",
  "apellido1": "string o null",
  "apellido2": "string o null",
  "ciclo_detectado": "texto exacto del formulario tal como aparece escrito o null",
  "ciclo_codigo": "código exacto del catálogo (DAW, SMR, GIAT, etc.) que mejor corresponde al ciclo escrito, o null si no puedes determinarlo con seguridad",
  "grado": "medio o superior o null",
  "tipo_asistencia": "presencial o semipresencial o libre o parcial o null",
  "curso_inicio": "año como string, ej: 2024, o null",
  "curso_fin": "año como string, ej: 2025, o null"
}

IMPORTANTE — tipo de documento:
- Si el número empieza por X, Y o Z → es SIEMPRE un NIE, nunca un pasaporte.
- Si el número son 8 dígitos seguidos de una letra → es DNI.
- PASAPORTE solo si el formato no encaja con DNI ni NIE (alfanumérico libre sin esa estructura).

IMPORTANTE para DNI/NIE/Pasaporte — estructura posicional:

DNI (9 caracteres: 8 dígitos + 1 letra):
- Posiciones 1-8: SIEMPRE dígitos. Si dudas entre dígito y letra similar, elige el dígito: O→0, I/L→1, B→8, S→5, G→6, Z→2, Q→0
- Posición 9: SIEMPRE una letra de control. Si dudas entre letra y dígito similar, elige la letra: 0→O, 1→I, 8→B, 5→S, 6→G
- Ejemplo: 12345678A

NIE (9 caracteres: 1 letra + 7 dígitos + 1 letra):
- Posición 1: SIEMPRE X, Y o Z. Si ves algo parecido a X, Y o Z, interpreta como la letra correspondiente.
- Posiciones 2-8: SIEMPRE dígitos. Aplica las mismas sustituciones que en el DNI: O→0, I/L→1, B→8, S→5, G→6
- Posición 9: SIEMPRE una letra de control. Si dudas, elige la letra: 0→O, 1→I, 8→B, 5→S, 6→G
- Ejemplo: X1234567A

Pasaporte español (formato variable, alfanumérico):
- No tiene una estructura posicional fija de dígitos y letras. Transcribe exactamente lo que ves sin aplicar sustituciones.

Para los tres tipos: transcribe lo que ves con estas reglas. No calcules ni verifiques la letra de control.
Si el campo tiene letras tanto al inicio como al final (formato incorrecto), transcríbelo tal cual sin intentar corregirlo.

{{ciclos}}

El campo "grado" se deduce del ciclo detectado. Si el formulario también tiene una casilla o texto indicando "Grado Superior" o "Grado Medio", úsalo para confirmar.
tipo_asistencia: el formulario tiene checkboxes para presencial, semipresencial, libre y parcial.
Si un campo no es legible usa null. No inventes datos.

RECUERDA: Solo puedes devolver datos que veas claramente en la imagen adjunta. No uses datos de otras imágenes.

PALABRAS TACHADAS: si una palabra en cualquier campo está tachada (barrada con línea o garabato encima), ignórala completamente.
Usa solo el texto NO tachado que esté escrito junto a ella (el estudiante escribe el valor correcto al lado del tachado).
"""


EXPEDIENTE_RETRY_PROMPT = """ATENCIÓN: Analiza SOLO la imagen adjunta en este mensaje. No uses datos de imágenes anteriores.

Mira SOLO la esquina SUPERIOR DERECHA de esta imagen.
Hay un número escrito A MANO de 5 cifras (mayor de 15000). Es el número de expediente.
Devuelve ÚNICAMENTE un JSON con este esquema:
{"expediente": "número de 5 cifras o null"}
No añadas ningún otro campo. No inventes datos."""

NOMBRES_RETRY_PROMPT = """ATENCIÓN: Analiza SOLO la imagen adjunta en este mensaje. No uses datos de imágenes anteriores.

Esta imagen es un formulario de matrícula manuscrito.
Localiza los tres campos de nombre y transcribe exactamente lo que está escrito a mano en cada línea.

- "NOMBRE:" → nombre de pila → campo "nombre"
- "APELLIDO 1:" o "PRIMER APELLIDO:" → primer apellido → campo "apellido1"
- "APELLIDO 2:" o "SEGUNDO APELLIDO:" → segundo apellido → campo "apellido2"

Son tres campos COMPLETAMENTE SEPARADOS. Aunque el estudiante haya escrito dos palabras
en la misma línea, identifica a qué campo pertenece cada zona del formulario.
Transcribe cualquier nombre: japonés, árabe, chino, europeo… letra por letra como aparece.
Si un campo está en blanco usa null.

PALABRAS TACHADAS: si una palabra está tachada (barrada con línea o garabato encima), ignórala completamente.
Usa solo el texto NO tachado que esté escrito junto a ella (el texto correcto se escribe al lado del tachado).

Devuelve ÚNICAMENTE un JSON:
{"nombre": "string o null", "apellido1": "string o null", "apellido2": "string o null"}"""

APELLIDO2_RETRY_PROMPT = """ATENCIÓN: Analiza SOLO la imagen adjunta en este mensaje. No uses datos de imágenes anteriores.

Esta imagen es un formulario de matrícula manuscrito.
Busca ÚNICAMENTE el campo "APELLIDO 2" o "SEGUNDO APELLIDO" del formulario.
Es el tercer campo de nombre, debajo de "APELLIDO 1" y de "NOMBRE".
El campo puede contener un apellido de cualquier origen (japonés, árabe, chino, europeo, etc.).
Transcribe exactamente lo que ves escrito a mano en ese campo, letra por letra.
Si el campo está en blanco o no ves nada escrito, usa null.

PALABRAS TACHADAS: si una palabra está tachada (barrada con línea o garabato encima), ignórala completamente.
Usa solo el texto NO tachado que esté escrito junto a ella (el texto correcto se escribe al lado del tachado).

Devuelve ÚNICAMENTE un JSON con un solo campo:
{"apellido2": "string o null"}"""


def render_form_prompt(template: str) -> str:
    """Replace {{ciclos}} with the current ciclos list from config globals."""
    if "{{ciclos}}" not in template:
        return template
    sup_lines = [f"{c} — {CICLOS[c]}" for c in CICLOS if c in GRADO_SUPERIOR]
    med_lines = [f"{c} — {CICLOS[c]}" for c in CICLOS if c in GRADO_MEDIO]
    ciclos_text = 'Ciclos posibles — GRADO SUPERIOR (grado = "superior"):\n'
    ciclos_text += "\n".join(sup_lines)
    ciclos_text += '\n\nCiclos posibles — GRADO MEDIO (grado = "medio"):\n'
    ciclos_text += "\n".join(med_lines)
    return template.replace("{{ciclos}}", ciclos_text)


def extract_form_data(page_img: Image.Image) -> dict:
    img_b64 = image_to_base64(page_img)
    data = call_model(render_form_prompt(FORM_PROMPT), img_b64)
    if data is None:
        logging.error("El modelo no devolvió datos del formulario")
        return {}

    if not data.get("expediente"):
        logging.warning("Expediente no detectado en primera pasada — reintentando con prompt focalizado")
        retry = call_model(EXPEDIENTE_RETRY_PROMPT, img_b64)
        if retry and retry.get("expediente"):
            data["expediente"] = retry["expediente"]
            logging.info(f"Expediente recuperado en reintento: {data['expediente']}")
        else:
            logging.warning("Expediente no encontrado tras reintento")

    if not data.get("nombre") and not data.get("apellido1"):
        logging.warning("Nombre/apellido no detectados — reintentando con prompt focalizado")
        retry = call_model(NOMBRES_RETRY_PROMPT, img_b64)
        if retry and (retry.get("nombre") or retry.get("apellido1")):
            for field in ("nombre", "apellido1", "apellido2"):
                if retry.get(field):
                    data[field] = retry[field]
            logging.info(f"Nombre recuperado en reintento: {data.get('nombre')} {data.get('apellido1')}")
        else:
            logging.warning("Nombre/apellido no encontrados tras reintento")

    if data.get("apellido1") and not data.get("apellido2"):
        logging.warning("Apellido2 no detectado — reintentando con prompt focalizado")
        retry2 = call_model(APELLIDO2_RETRY_PROMPT, img_b64)
        if retry2 and retry2.get("apellido2"):
            data["apellido2"] = retry2["apellido2"]
            logging.info(f"Apellido2 recuperado en reintento: {data['apellido2']}")
        else:
            logging.info("Apellido2 no encontrado en reintento (puede ser campo en blanco)")

    logging.info(f"Datos formulario extraídos: expediente={data.get('expediente')}, doc={data.get('numero_documento')}")
    return data


def normalize_ciclo(raw: str | None, codigo_hint: str | None = None) -> dict:
    """Resolve ciclo code from raw OCR text and optional LLM-provided code hint."""
    if not raw and not codigo_hint:
        return {"codigo": None, "nombre_completo": None, "grado": None, "texto_original": raw}

    import re as _re

    if codigo_hint:
        hint_upper = str(codigo_hint).strip().upper()
        if hint_upper in CICLOS:
            logging.info(f"Ciclo resuelto por LLM: '{raw}' → '{hint_upper}'")
            return _ciclo_result(raw, hint_upper)

    if not raw:
        return {"codigo": None, "nombre_completo": None, "grado": None, "texto_original": raw}

    raw_upper = raw.strip().upper()

    if raw_upper in CICLOS:
        return _ciclo_result(raw, raw_upper)

    for codigo, nombre in CICLOS.items():
        if raw_upper == nombre.upper():
            return _ciclo_result(raw, codigo)

    tokens = _re.split(r"[\s\-/,;]+", raw_upper)
    for token in tokens:
        if token in CICLOS:
            logging.info(f"Ciclo token match: '{raw}' → '{token}'")
            return _ciclo_result(raw, token)

    for codigo in CICLOS:
        if _re.search(rf'\b{_re.escape(codigo)}\b', raw_upper):
            logging.info(f"Ciclo containment match: '{raw}' → '{codigo}'")
            return _ciclo_result(raw, codigo)

    best_code = None
    best_dist = 999
    for codigo, nombre in CICLOS.items():
        d_code = levenshtein_distance(raw_upper, codigo)
        d_name = levenshtein_distance(raw_upper, nombre.upper())
        d = min(d_code, d_name)
        if d < best_dist:
            best_dist = d
            best_code = codigo

    if best_code and best_dist <= max(4, len(raw_upper) // 3):
        logging.info(f"Ciclo fuzzy match: '{raw}' → '{best_code}' (dist={best_dist})")
        return _ciclo_result(raw, best_code)

    logging.warning(f"Ciclo no reconocido: '{raw}'")
    return {"codigo": None, "nombre_completo": None, "grado": None, "texto_original": raw}


def _ciclo_result(raw, codigo):
    grado = "superior" if codigo in GRADO_SUPERIOR else "medio"
    return {
        "codigo": codigo,
        "nombre_completo": CICLOS[codigo],
        "grado": grado,
        "texto_original": raw,
    }
