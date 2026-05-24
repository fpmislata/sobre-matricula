"""Factorías de imágenes PIL sintéticas para tests."""
import numpy as np
from PIL import Image, ImageFilter


def make_color_image(w: int = 200, h: int = 300, color: tuple = (200, 100, 50)) -> Image.Image:
    img = Image.new("RGB", (w, h), color=color)
    return img


def make_gray_image(w: int = 200, h: int = 300, value: int = 128) -> Image.Image:
    img = Image.new("L", (w, h), color=value).convert("RGB")
    return img


def make_blurry_image(base: Image.Image | None = None) -> Image.Image:
    if base is None:
        base = make_gray_image()
    return base.filter(ImageFilter.GaussianBlur(radius=8))


def make_sharp_image(base: Image.Image | None = None) -> Image.Image:
    """High-contrast alternating rows → high Laplacian variance."""
    if base is None:
        w, h = 200, 300
    else:
        w, h = base.size
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[::2, :] = 255
    return Image.fromarray(arr, "RGB")


def make_face_image(w: int = 200, h: int = 300) -> Image.Image:
    """Minimal synthetic image that mimics a face (oval on plain background).
    Not meant to fool YOLO — just provides a valid PIL Image for unit tests."""
    from PIL import ImageDraw
    img = Image.new("RGB", (w, h), color=(230, 210, 185))
    draw = ImageDraw.Draw(img)
    cx, cy = w // 2, h // 2
    rx, ry = w // 4, h // 3
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(210, 170, 130))
    return img
