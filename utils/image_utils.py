import base64
import io
import numpy as np
import cv2
from PIL import Image


def pil_to_cv2(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def cv2_to_pil(img: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


def image_to_base64(img: Image.Image, format: str = "JPEG", quality: int = 85) -> str:
    buf = io.BytesIO()
    if format == "JPEG":
        img.convert("RGB").save(buf, format=format, quality=quality)
    else:
        img.save(buf, format=format)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def is_color_image(img: Image.Image) -> bool:
    arr = np.array(img.convert("RGB")).astype(float)
    diff_rg = np.mean(np.abs(arr[:, :, 0] - arr[:, :, 1]))
    diff_rb = np.mean(np.abs(arr[:, :, 0] - arr[:, :, 2]))
    return bool((diff_rg + diff_rb) / 2 > 8.0)


def sharpness_score(img: Image.Image) -> float:
    gray = np.array(img.convert("L"))
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def rotate_pil(img: Image.Image, angle: int) -> Image.Image:
    """Rotate by 0, 90, 180, or 270 degrees without distortion."""
    rotations = {
        0:   lambda x: x,
        90:  lambda x: x.rotate(90, expand=True),
        180: lambda x: x.rotate(180, expand=True),
        270: lambda x: x.rotate(270, expand=True),
    }
    return rotations[angle](img)
