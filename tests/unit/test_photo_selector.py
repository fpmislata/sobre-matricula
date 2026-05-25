"""
Unit tests para modules/photo_selector.select_best_photo().

Criterio de selección:
  1. Fotos de carnet siempre ganan sobre fotos de DNI (si hay alguna de carnet).
  2. Si no hay carnet, se usa la mejor foto de DNI.
  3. Dentro del mismo tipo: color gana sobre gris (bonus 10_000_000).
  4. Entre iguales: mayor nitidez (Laplacian variance).

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


# ── Preferencia de tipo: carnet siempre sobre DNI ────────────────────────────

@pytest.mark.unit
def test_carnet_beats_dni_gray_vs_gray():
    """carnet en gris gana sobre DNI en gris."""
    fotos = [
        _photo(make_gray_image(), tipo="carnet"),
        _photo(make_gray_image(), tipo="dni"),
    ]
    result = select_best_photo(fotos)
    assert result["tipo"] == "carnet"


@pytest.mark.unit
def test_carnet_gray_beats_dni_color():
    """carnet en gris gana sobre DNI en color."""
    fotos = [
        _photo(make_gray_image(),  tipo="carnet"),
        _photo(make_color_image(), tipo="dni"),
    ]
    result = select_best_photo(fotos)
    assert result["tipo"] == "carnet"
    assert result["es_color"] is False


@pytest.mark.unit
def test_carnet_sharp_gray_beats_dni_blurry_color():
    """carnet nítida en gris gana sobre DNI borrosa en color."""
    fotos = [
        _photo(make_sharp_image(),                    tipo="carnet"),
        _photo(make_blurry_image(make_color_image()), tipo="dni"),
    ]
    result = select_best_photo(fotos)
    assert result["tipo"] == "carnet"


# ── Color gana dentro del mismo tipo ─────────────────────────────────────────

@pytest.mark.unit
def test_color_beats_gray_entre_carnets():
    """Entre carnets, color gana sobre gris."""
    fotos = [
        _photo(make_gray_image(),  tipo="carnet"),
        _photo(make_color_image(), tipo="carnet"),
    ]
    result = select_best_photo(fotos)
    assert result["es_color"] is True


@pytest.mark.unit
def test_color_beats_gray_entre_dnis_sin_carnet():
    """Sin carnet disponible, entre DNIs color gana sobre gris."""
    fotos = [
        _photo(make_gray_image(),  tipo="dni"),
        _photo(make_color_image(), tipo="dni"),
    ]
    result = select_best_photo(fotos)
    assert result["es_color"] is True


@pytest.mark.unit
def test_color_beats_sharp_gray_entre_carnets():
    """Entre carnets: color borrosa gana sobre gris nítida."""
    fotos = [
        _photo(make_sharp_image(),                    tipo="carnet"),
        _photo(make_blurry_image(make_color_image()), tipo="carnet"),
    ]
    result = select_best_photo(fotos)
    assert result["es_color"] is True


# ── Nitidez desempata entre mismos tipos ──────────────────────────────────────

@pytest.mark.unit
def test_sharp_beats_blurry_entre_colores():
    """Dentro del mismo tipo y color, la más nítida gana."""
    import numpy as np
    from PIL import Image as PilImage

    arr = np.zeros((100, 100, 3), dtype=np.uint8)
    arr[::2, :] = [200, 100, 50]
    sharp_color = PilImage.fromarray(arr, "RGB")

    blurry_color = make_blurry_image(sharp_color)
    fotos = [
        _photo(blurry_color, tipo="carnet"),
        _photo(sharp_color,  tipo="carnet"),
    ]
    result = select_best_photo(fotos)
    assert result["es_color"] is True
    assert result["nitidez"] > 100  # la nítida ganó (alta varianza Laplaciana)


@pytest.mark.unit
def test_sharp_beats_blurry_entre_grises():
    """Dentro del mismo tipo, la más nítida gana."""
    fotos = [
        _photo(make_blurry_image(make_gray_image()), tipo="carnet"),
        _photo(make_sharp_image(),                   tipo="carnet"),
    ]
    result = select_best_photo(fotos)
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
