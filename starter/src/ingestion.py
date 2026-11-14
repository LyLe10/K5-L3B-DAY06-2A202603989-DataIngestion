"""PDF parsing and the versioned, corpus-compatible normalization policy."""
import logging
from pathlib import Path
import re
import unicodedata

from .models import DocumentPage

LOGGER = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """Apply nfc-whitespace-paragraphs-v1 without rewriting source content.

    Keep line/paragraph boundaries, headers, footers and SQL punctuation. The
    manifest hashes this exact UTF-8 text, with no added terminal newline.
    """
    text = unicodedata.normalize('NFC', text).replace('\r\n', '\n').replace('\r', '\n')
    lines = [re.sub(r'[^\S\n]+', ' ', line).strip() for line in text.split('\n')]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def _parse_page(pdf_page, document_id: str, source: str, physical_page: int,
                printed_page_label: str | None) -> DocumentPage:
    """Shared parser; retain failed/empty physical pages rather than renumber."""
    metadata = {'physical_page': physical_page, 'printed_page_label': printed_page_label}
    try:
        text = normalize_text(pdf_page.extract_text() or '')
        metadata['extraction_status'] = 'ok' if text else 'empty'
        if not text:
            LOGGER.warning('%s page %s: empty extracted text', document_id, physical_page)
    except Exception as exc:
        text = ''
        metadata.update(extraction_status='error', extraction_error=f'{type(exc).__name__}: {exc}')
        LOGGER.error('%s page %s: %s', document_id, physical_page, metadata['extraction_error'])
    return DocumentPage(document_id, source, physical_page, text, metadata)


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Read all physical pages, numbered from 1, using pypdf.

    Empty/error pages remain in the result with extraction_status in metadata.
    File-level errors propagate. Manifest selection is a separate orchestration
    step; it uses the same parser but extracts only the approved page records.
    """
    from pypdf import PdfReader

    reader = PdfReader(path)
    labels = reader.page_labels if "/PageLabels" in reader.root_object else [None] * len(reader.pages)
    return [_parse_page(pdf_page, document_id, source, number, labels[number - 1])
            for number, pdf_page in enumerate(reader.pages, 1)]
