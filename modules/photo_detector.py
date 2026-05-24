import logging
import numpy as np
import cv2
from PIL import Image
from pathlib import Path
from utils.image_utils import pil_to_cv2, cv2_to_pil, rotate_pil
from config import YOLO_MODEL_PATH, YOLO_CONFIDENCE, FACE_PADDING_RATIO


def _load_yolo():
    if not Path(YOLO_MODEL_PATH).exists():
        logging.info(f"Modelo YOLO no encontrado en {YOLO_MODEL_PATH}, usando Haar cascades")
        return None
    try:
        from ultralytics import YOLO
        model = YOLO(str(YOLO_MODEL_PATH))
        logging.info("Modelo YOLO cargado correctamente")
        return model
    except Exception as e:
        logging.warning(f"No se pudo cargar YOLO: {e}. Usando Haar cascades")
        return None


_YOLO_MODEL = None
_YOLO_LOADED = False
_HAAR = None


def _get_yolo():
    global _YOLO_MODEL, _YOLO_LOADED
    if not _YOLO_LOADED:
        _YOLO_MODEL = _load_yolo()
        _YOLO_LOADED = True
    return _YOLO_MODEL


def _get_haar():
    global _HAAR
    if _HAAR is None:
        _HAAR = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    return _HAAR


def _detect_faces_yolo(img_cv2: np.ndarray) -> list[tuple[int, int, int, int, float]]:
    """Returns list of (x1, y1, x2, y2, confidence)."""
    model = _get_yolo()
    if model is None:
        return []
    try:
        results = model(img_cv2, conf=YOLO_CONFIDENCE, verbose=False)
        faces = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                faces.append((x1, y1, x2, y2, conf))
        return faces
    except Exception as e:
        logging.warning(f"YOLO error: {e}")
        return []


def _detect_faces_haar(img_cv2: np.ndarray) -> list[tuple[int, int, int, int, float]]:
    gray = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2GRAY)
    cascade = _get_haar()
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    result = []
    for (x, y, w, h) in faces:
        result.append((x, y, x + w, y + h, 0.6))
    return result


def _detect_faces(img_cv2: np.ndarray) -> list[tuple[int, int, int, int, float]]:
    faces = _detect_faces_yolo(img_cv2)
    if not faces:
        faces = _detect_faces_haar(img_cv2)
    return faces


def _crop_with_padding(img_cv2: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
    h, w = img_cv2.shape[:2]
    bw, bh = x2 - x1, y2 - y1
    pad_x = int(bw * FACE_PADDING_RATIO)
    pad_y = int(bh * FACE_PADDING_RATIO)
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(w, x2 + pad_x)
    y2 = min(h, y2 + pad_y)
    return img_cv2[y1:y2, x1:x2]


def detect_and_crop_face(img: Image.Image) -> tuple[Image.Image | None, int]:
    """
    Try all 4 rotations. Return (cropped_face, winning_angle) from the orientation
    with the highest-confidence detection, or (None, 0) if no face found.
    """
    best_crop = None
    best_conf = 0.0
    best_angle = 0

    for angle in [0, 90, 180, 270]:
        rotated = rotate_pil(img, angle)
        img_cv2 = pil_to_cv2(rotated)
        faces = _detect_faces(img_cv2)
        if not faces:
            continue
        best_face = max(faces, key=lambda f: f[4] * (f[2]-f[0]) * (f[3]-f[1]))
        x1, y1, x2, y2, conf = best_face
        if conf > best_conf:
            best_conf = conf
            best_angle = angle
            best_crop = cv2_to_pil(_crop_with_padding(img_cv2, x1, y1, x2, y2))

    if best_crop is None:
        logging.info("No se detectó ninguna cara")
    return best_crop, best_angle
