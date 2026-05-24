import requests
import json
import logging
import time
from config import (
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, OLLAMA_MAX_RETRIES,
    OPENROUTER_URL, OPENROUTER_MODEL, OPENROUTER_API_KEY,
    MODO_DESARROLLO_PROD,
)

_ISOLATION_PREFIX = (
    "INSTRUCCIÓN CRÍTICA: Analiza ÚNICAMENTE la imagen adjunta en este mensaje. "
    "No uses ningún dato, nombre, número ni información de imágenes anteriores. "
    "Cada llamada es completamente independiente. "
    "Si no puedes leer algo en esta imagen, devuelve null — nunca inventes ni reutilices datos previos. "
    "Responde únicamente con JSON válido.\n\n"
)


def call_ollama(prompt: str, image_b64: str) -> dict | None:
    full_prompt = _ISOLATION_PREFIX + prompt
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": full_prompt,
        "images": [image_b64],
        "stream": False,
        "format": "json",
        "context": [],
        "keep_alive": 0,
        "options": {"temperature": 0.1},
    }
    for attempt in range(OLLAMA_MAX_RETRIES):
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
            resp.raise_for_status()
            raw = resp.json().get("response", "{}")
            return _parse_json(raw)
        except (requests.RequestException, json.JSONDecodeError) as e:
            wait = 2 ** attempt
            logging.warning(f"Ollama intento {attempt+1}/{OLLAMA_MAX_RETRIES} fallido: {e}. Esperando {wait}s")
            if attempt < OLLAMA_MAX_RETRIES - 1:
                time.sleep(wait)
    logging.error("Ollama no respondió tras todos los reintentos")
    return None


def _call_openrouter(prompt: str, image_b64: str) -> dict | None:
    if not OPENROUTER_API_KEY:
        logging.error("OPENROUTER_API_KEY no configurada")
        return None

    full_prompt = _ISOLATION_PREFIX + prompt
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres un sistema OCR. Analiza ÚNICAMENTE la imagen del mensaje actual. "
                    "No recuerdes ni uses datos de mensajes o imágenes anteriores. "
                    "Responde siempre con JSON válido y nada más."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                    {
                        "type": "text",
                        "text": full_prompt,
                    },
                ],
            },
        ],
        "temperature": 0.1,
        "stream": False,
    }

    for attempt in range(OLLAMA_MAX_RETRIES):
        try:
            resp = requests.post(
                OPENROUTER_URL, headers=headers, json=payload, timeout=OLLAMA_TIMEOUT
            )
            resp.raise_for_status()
            raw = _extract_openrouter_content(resp.text)
            return _parse_json(raw)
        except requests.RequestException as e:
            wait = 2 ** attempt
            logging.warning(f"OpenRouter intento {attempt+1}/{OLLAMA_MAX_RETRIES} error HTTP: {e}. Esperando {wait}s")
            if attempt < OLLAMA_MAX_RETRIES - 1:
                time.sleep(wait)
            continue
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            body_text = locals().get("resp")
            body_preview = body_text.text[:200].replace('\n', '↵') if body_text else "(sin respuesta)"
            wait = 2 ** attempt
            logging.warning(f"OpenRouter intento {attempt+1}/{OLLAMA_MAX_RETRIES} respuesta inválida: {e} | body={body_preview}. Esperando {wait}s")
            if attempt < OLLAMA_MAX_RETRIES - 1:
                time.sleep(wait)
    logging.error("OpenRouter no respondió tras todos los reintentos")
    return None


def _resize_for_openrouter(image_b64: str, max_side: int = 1024, quality: int = 75) -> str:
    """Reduce image size for OpenRouter to avoid payload limits."""
    import base64, io
    from PIL import Image
    data = base64.b64decode(image_b64)
    img = Image.open(io.BytesIO(data)).convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def call_model(prompt: str, image_b64: str) -> dict | None:
    """Dispatcher: usa Ollama en producción, OpenRouter en desarrollo."""
    if MODO_DESARROLLO_PROD:
        return call_ollama(prompt, image_b64)
    return _call_openrouter(prompt, _resize_for_openrouter(image_b64))


def _extract_openrouter_content(body: str) -> str:
    """Extrae el campo content del body de OpenRouter.

    El body puede llegar con basura/SSE antes del JSON (newlines, espacios).
    Usamos raw_decode para parsear desde el primer '{' ignorando lo demás.
    """
    start = body.find('{')
    if start == -1:
        raise ValueError(f"No hay JSON en la respuesta de OpenRouter (len={len(body)})")
    try:
        data, _ = json.JSONDecoder().raw_decode(body, idx=start)
        content = data["choices"][0]["message"]["content"]
        if not content or not content.strip():
            raise ValueError("Modelo devolvió content vacío")
        return content
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        raise ValueError(f"JSON inválido en OpenRouter desde pos {start}: {e}")


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)
