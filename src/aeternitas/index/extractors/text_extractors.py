from __future__ import annotations

from pathlib import Path
from typing import Tuple

from aeternitas.common.text import safe_read_text

# Optional imports (only used when needed)
try:
    from pypdf import PdfReader  # type: ignore
except Exception:
    PdfReader = None

try:
    from odf.opendocument import load as odf_load  # type: ignore
    from odf import teletype  # type: ignore
except Exception:
    odf_load = None
    teletype = None

try:
    from PIL import Image, ImageOps, ImageEnhance  # type: ignore
except Exception:
    Image = None

try:
    import pytesseract  # type: ignore
except Exception:
    pytesseract = None


EXTRACTOR_VERSION = "aet.py/1"


def extract_text_from_pdf(path: Path) -> str:
    if PdfReader is None:
        raise RuntimeError("pypdf puuttuu (pip install pypdf)")
    reader = PdfReader(str(path))
    pages = []
    for p in reader.pages:
        t = p.extract_text() or ""
        pages.append(t)
    return "\n\n".join(pages)


def extract_text_from_odt(path: Path) -> str:
    if odf_load is None or teletype is None:
        raise RuntimeError("odfpy puuttuu (pip install odfpy)")
    doc = odf_load(str(path))
    return teletype.extractText(doc.text)


def extract_text_from_image_ocr(path: Path, lang: str = "fin") -> str:
    if Image is None or pytesseract is None:
        raise RuntimeError("pillow/pytesseract puuttuu (pip install pillow pytesseract)")
    img = Image.open(str(path))
    # Perus-esikäsittely: harmaasävy + kontrasti
    g = ImageOps.grayscale(img)
    g = ImageEnhance.Contrast(g).enhance(2.0)
    # Tesseract toimii usein paremmin ilman binarointia; käytä psm 6 (yhtenäinen tekstialue)
    config = "--psm 6"
    return pytesseract.image_to_string(g, lang=lang, config=config)


def extract_text(path: Path) -> Tuple[str, str, str]:
    """
    Returns: (text, encoding, extractor_name)
    """
    suf = path.suffix.lower()
    if suf in (".txt", ".md", ".csv", ".log"):
        t, enc = safe_read_text(path)
        return t, enc, "txt"
    if suf == ".odt":
        t = extract_text_from_odt(path)
        return t, "utf-8", "odt"
    if suf == ".pdf":
        t = extract_text_from_pdf(path)
        return t, "utf-8", "pdf"
    if suf in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
        t = extract_text_from_image_ocr(path)
        return t, "utf-8", "ocr"
    # fallback: yritä tekstiä
    t, enc = safe_read_text(path)
    return t, enc, "txt-fallback"
