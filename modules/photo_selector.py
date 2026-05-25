import logging
from PIL import Image
from utils.image_utils import is_color_image, sharpness_score


def select_best_photo(photos: list[dict]) -> dict | None:
    """
    photos: list of {'image': PIL.Image, 'tipo': 'carnet'|'dni', 'filename': str}
    Returns the best photo dict with added keys: score, es_color, nitidez

    Prioridad: fotos de carnet siempre ganan sobre fotos de DNI.
    Si no hay carnet, se usa la mejor foto de DNI disponible.
    Dentro del mismo tipo: color > gris, y entre iguales gana la más nítida.
    """
    if not photos:
        return None

    carnet_photos = [p for p in photos if p["tipo"] == "carnet"]
    pool = carnet_photos if carnet_photos else photos

    scored = []
    for p in pool:
        color = is_color_image(p["image"])
        sharp = sharpness_score(p["image"])
        color_bonus = 10_000_000.0 if color else 0.0
        score = color_bonus + sharp
        scored.append({**p, "score": score, "es_color": color, "nitidez": round(sharp, 2)})
        logging.info(f"  Foto '{p['tipo']}': color={color}, nitidez={sharp:.1f}, score={score:.1f}")

    best = max(scored, key=lambda x: x["score"])
    logging.info(f"Mejor foto seleccionada: tipo='{best['tipo']}', color={best['es_color']}, nitidez={best['nitidez']}")
    return best
