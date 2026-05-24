"""
Unit tests para modules/photo_selector.select_best_photo().

Criterio de selección:
  1. Color gana sobre grises (bonus 10_000_000)
  2. Entre iguales: mayor nitidez (Laplacian variance)

Imágenes sintéticas:
  make_color_image()  → is_color_image=True, nitidez moderada
  make_gray_image()   → is_color_image=False, nitidez baja-moderada
  make_sharp_image()  → alternating rows → alta nitidez, es gris
  make_blurry_image() → GaussianBlur → baja nitidez
"""
import pytest
from modules.photo_selector import select_best_photo
from tests.fixtures.sample_images import (
    make_color_image,
    make_gray_image,
    make_blurry_image,
    make_sharp_image,
)


def _photo(img, tipo="carnet", filename="foto.jpg"):
    return {"image": img, "tipo": tipo, "filename": filename}


# ── Lista vacía ───────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_lista_vacia_retorna_none():
    assert select_best_photo([]) is None


# ── Un solo elemento ──────────────────────────────────────────────────────────

@pytest.mark.unit
def test_un_elemento_retorna_ese_elemento():
    img = make_color_image()
    result = select_best_photo([_photo(img)])
    assert result is not None
    assert result["tipo"] == "carnet"


# ── Color gana sobre gris ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_color_beats_gray():
    fotos = [
        _photo(make_gray_image(),  tipo="carnet"),
        _photo(make_color_image(), tipo="documento"),
    ]
    result = select_best_photo(fotos)
    assert result["es_color"] is True
    assert result["tipo"] == "documento"


@pytest.mark.unit
def test_color_beats_sharp_gray():
    """Foto en color, aunque menos nítida, siempre gana sobre grises."""
    fotos = [
        _photo(make_sharp_image(), tipo="carnet"),     # alta nitidez, gris
        _photo(make_blurry_image(make_color_image()), tipo="documento"),  # borrosa, color
    ]
    result = select_best_photo(fotos)
    assert result["es_color"] is True


# ── Nitidez desempata entre mismos tipos ──────────────────────────────────────

@pytest.mark.unit
def test_sharp_beats_blurry_entre_colores():
    """make_sharp_image coloreada (alternating rows) tiene más nitidez que blurry."""
    from tests.fixtures.sample_images import make_sharp_image
    import numpy as np
    from PIL import Image as PilImage

    # Crear imagen de color con textura (alta varianza → alta nitidez)
    arr = np.zeros((100, 100, 3), dtype=np.uint8)
    arr[::2, :] = [200, 100, 50]   # filas pares: color vivo
    # filas impares: negro
    sharp_color = PilImage.fromarray(arr, "RGB")

    blurry_color = make_blurry_image(sharp_color)
    fotos = [
        _photo(blurry_color, tipo="carnet"),
        _photo(sharp_color,  tipo="documento"),
    ]
    result = select_best_photo(fotos)
    assert result["tipo"] == "documento"  # la nítida gana


@pytest.mark.unit
def test_sharp_beats_blurry_entre_grises():
    fotos = [
        _photo(make_blurry_image(make_gray_image()), tipo="carnet"),
        _photo(make_sharp_image(),                   tipo="documento"),
    ]
    result = select_best_photo(fotos)
    assert result["tipo"] == "documento"
    assert result["nitidez"] > 100  # sharp_image tiene varianza alta


# ── Estructura del resultado ──────────────────────────────────────────────────

@pytest.mark.unit
def test_resultado_tiene_campos_de_scoring():
    result = select_best_photo([_photo(make_color_image())])
    assert "score" in result
    assert "es_color" in result
    assert "nitidez" in result


@pytest.mark.unit
def test_resultado_tiene_campos_originales():
    img = make_color_image()
    result = select_best_photo([_photo(img, tipo="carnet", filename="mi_foto.jpg")])
    assert result["tipo"] == "carnet"
    assert result["filename"] == "mi_foto.jpg"
    assert result["image"] is img


@pytest.mark.unit
def test_score_color_mayor_que_gray():
    color = select_best_photo([_photo(make_color_image())])
    gray  = select_best_photo([_photo(make_gray_image())])
    assert color["score"] > gray["score"]


# ── Múltiples fotos ───────────────────────────────────────────────────────────

@pytest.mark.unit
def test_multiples_fotos_retorna_una():
    fotos = [_photo(make_gray_image(), tipo=f"t{i}") for i in range(5)]
    result = select_best_photo(fotos)
    assert result is not None
    assert result["tipo"] in [f"t{i}" for i in range(5)]


@pytest.mark.unit
def test_es_color_flag_correcto_para_gris():
    result = select_best_photo([_photo(make_gray_image())])
    assert result["es_color"] is False


@pytest.mark.unit
def test_nitidez_es_float():
    result = select_best_photo([_photo(make_color_image())])
    assert isinstance(result["nitidez"], float)
