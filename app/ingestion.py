import shutil
from pathlib import Path

import fitz

from app.config import settings


class PDFIngestionError(ValueError):
    pass


def extract_pdf_text(path: str) -> tuple[str, str]:
    file_path = Path(path)
    if not file_path.is_file() or file_path.suffix.lower() != ".pdf":
        raise PDFIngestionError("A readable .pdf file is required.")
    try:
        with fitz.open(file_path) as doc:
            if doc.is_encrypted:
                raise PDFIngestionError("Encrypted PDFs are not supported.")
            text = "\n".join(page.get_text("text") for page in doc)
    except (fitz.FileDataError, RuntimeError) as exc:
        raise PDFIngestionError(f"Invalid or unreadable PDF: {exc}") from exc
    if text.strip():
        return text, "pymupdf"
    if not shutil.which(settings.tesseract_cmd):
        raise PDFIngestionError(
            "PDF contains no extractable text and Tesseract is unavailable; OCR is BLOCKED."
        )
    try:
        import io

        import pytesseract
        from PIL import Image

        pages_text = []
        with fitz.open(file_path) as doc:
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                pages_text.append(
                    pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))))
                )
        result = "\n".join(pages_text)
        if not result.strip():
            raise PDFIngestionError("OCR produced no text.")
        return result, "tesseract"
    except ImportError as exc:
        raise PDFIngestionError("Install pytesseract and Pillow for OCR fallback.") from exc
