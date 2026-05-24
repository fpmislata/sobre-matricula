import fitz  # pymupdf
import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from config import PDF_DPI


def pdf_to_images(pdf_path: Path) -> list[Image.Image]:
    """Convert each page of a PDF to a PIL Image at the configured DPI."""
    doc = fitz.open(str(pdf_path))
    images = []
    scale = PDF_DPI / 72.0
    mat = fitz.Matrix(scale, scale)
    for page in doc:
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """Convierte a gris y aplica umbral Otsu para blanquear el fondo y realzar texto."""
    gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(thresh).convert("RGB")
