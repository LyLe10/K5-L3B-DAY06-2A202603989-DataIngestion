"""Read and normalize source data. TODO: implement functions."""
from pathlib import Path
import re
import unicodedata
from .models import DocumentPage


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """TODO: extract each physical page; keep its page number and source.

    Detect and record pages with no text. OCR, when needed, is a separate step.
    """
    raise NotImplementedError("TODO: load_pdf")


def normalize_text(text: str) -> str:
    """Apply nfc-whitespace-paragraphs-v1 without rewriting source content.

    Keep line/paragraph boundaries, headers, footers and SQL punctuation. The
    manifest hashes this exact UTF-8 text, with no added terminal newline.
    """
    text = unicodedata.normalize('NFC', text).replace('\r\n', '\n').replace('\r', '\n')
    lines = [re.sub(r'[^\S\n]+', ' ', line).strip() for line in text.split('\n')]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
