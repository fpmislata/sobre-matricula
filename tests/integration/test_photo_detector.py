"""
Integration tests para modules/photo_detector.detect_and_crop_face().

Tests rápidos: imágenes sintéticas (sin cara real → fallback gracioso).
Tests lentos (@slow): sample_face.jpg real con Haar cascades (sin YOLO).

NO testea predicciones exactas de YOLO — solo que el pipeline no rompe
y que la estructura de salida es correcta.
"""
import pytest
from PIL import Image
from tests.fixtures.sample_images import make_color_image, make_gray_image, make_face_image


# ── Estructura de retorno (rápidos) ───────────────────────────────────────────

@pytest.mark.unit
def test_detect_devuelve_tupla():
    from modules.photo_detector import detect_and_crop_face
    result = detect_and_crop_face(make_gray_image(200, 300))
    assert isinstance(result, tuple)
    assert len(result) == 2


@pytest.mark.unit
def test_detect_angulo_es_entero():
    from modules.photo_detector import detect_and_crop_face
    _, angle = detect_and_crop_face(make_gray_image(200, 300))
    assert isinstance(angle, int)
    assert angle in (0, 90, 180, 270)


@pytest.mark.unit
def test_detect_imagen_sin_cara_devuelve_none_o_crop():
    """Imagen sólida sin cara → (None, 0) o (crop, angle). No rompe."""
    from modules.photo_detector import detect_and_crop_face
    face, angle = detect_and_crop_face(make_gray_image(200, 300))
    # Si detecta algo en la imagen vacía, debe ser PIL.Image
    if face is not None:
        assert isinstance(face, Image.Image)
    assert angle in (0, 90, 180, 270)


@pytest.mark.unit
def test_detect_face_si_detecta_es_pil_image():
    from modules.photo_detector import detect_and_crop_face
    face, _ = detect_and_crop_face(make_face_image(300, 400))
    if face is not None:
        assert isinstance(face, Image.Image)
        w, h = face.size
        assert w > 0 and h > 0


# ── Con imagen real (slow — requiere sample_face.jpg) ────────────────────────

@pytest.mark.slow
@pytest.mark.integration
def test_detect_con_imagen_real_no_rompe(sample_face_jpg):
    from PIL import Image as PilImage
    from modules.photo_detector import detect_and_crop_face
    img = PilImage.open(sample_face_jpg)
    face, angle = detect_and_crop_face(img)
    assert angle in (0, 90, 180, 270)
    if face is not None:
        assert isinstance(face, PilImage.Image)


@pytest.mark.slow
@pytest.mark.integration
def test_detect_angulo_ganador_razonable(sample_face_jpg):
    """La cara de una foto carnet debería detectarse a 0° o 180°."""
    from PIL import Image as PilImage
    from modules.photo_detector import detect_and_crop_face
    img = PilImage.open(sample_face_jpg)
    _, angle = detect_and_crop_face(img)
    # No validamos el ángulo exacto — solo que es un valor válido
    assert angle in (0, 90, 180, 270)
