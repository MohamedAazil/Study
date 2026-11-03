"""PDF text extraction: pdfplumber first, PyMuPDF as fallback."""

import io
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageText:
    page: int  # 1-based
    text: str


class PDFParseError(ValueError):
    pass


def _extract_pdfplumber(data: bytes) -> list[PageText]:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return [PageText(page=i + 1, text=(p.extract_text() or "").strip()) for i, p in enumerate(pdf.pages)]


def _extract_pymupdf(data: bytes) -> list[PageText]:
    import fitz

    with fitz.open(stream=data, filetype="pdf") as doc:
        return [PageText(page=i + 1, text=page.get_text("text").strip()) for i, page in enumerate(doc)]


def extract_pages(data: bytes) -> list[PageText]:
    pages: list[PageText] = []
    try:
        pages = _extract_pdfplumber(data)
    except Exception as exc:  # noqa: BLE001
        logger.info("pdfplumber failed, falling back to PyMuPDF: %s", exc)
    if not any(p.text for p in pages):
        try:
            pages = _extract_pymupdf(data)
        except Exception as exc:  # noqa: BLE001
            raise PDFParseError(f"Could not read PDF: {exc}") from exc
    if not any(p.text for p in pages):
        raise PDFParseError("PDF contains no extractable text (scanned images are not supported yet)")
    return pages


def extract_tables(data: bytes) -> list[list[list[str | None]]]:
    """Return every table pdfplumber can find (list of rows of cells)."""
    import pdfplumber

    tables: list[list[list[str | None]]] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                tables.extend(page.extract_tables() or [])
    except Exception as exc:  # noqa: BLE001
        logger.info("pdfplumber table extraction failed: %s", exc)
    return tables


def full_text(data: bytes) -> str:
    return "\n\n".join(p.text for p in extract_pages(data) if p.text)
