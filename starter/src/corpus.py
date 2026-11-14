"""Read-only manifest orchestration, separate from the public PDF loader."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from pypdf import PdfReader

from .ingestion import _parse_page
from .models import DocumentPage

ROOT = Path(__file__).resolve().parents[2]


class CorpusError(ValueError):
    """A source, schema or checksum mismatch; never repair it automatically."""


@dataclass
class IngestionResult:
    pages: list[DocumentPage]
    skipped_pages: list[dict]
    sources: list[dict]
    manifest_sha256: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _local(root: Path, value: str, directory: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to((root / directory).resolve()):
        raise CorpusError(f'Path must stay inside {directory}: {value}')
    return path


def load_manifest_pages(manifest_path: Path, *, root: Path | None = None) -> IngestionResult:
    """Load only included/ok/approved pages and verify their immutable snapshot.

    All page records remain available as skip provenance, but unselected pages
    are not text-extracted. The source PDF hash and complete physical page map
    are checked before selection. No file, checksum or review flag is rewritten.
    """
    root = (root or ROOT).resolve()
    raw_manifest = manifest_path.read_bytes()
    manifest = json.loads(raw_manifest.decode('utf-8-sig'))
    schema_path = root / 'data/manifest.schema.json'
    schema = json.loads(schema_path.read_text(encoding='utf-8-sig'))
    Draft202012Validator.check_schema(schema)
    violations = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest))
    if violations:
        first = violations[0]
        raise CorpusError(f"Manifest/schema conflict at {list(first.absolute_path)}: {first.message}")
    pages, skipped, snapshots = [], [], []
    source_ids, page_ids = set(), set()
    for source in sorted(manifest['sources'], key=lambda s: s['source_id']):
        sid = source['source_id']
        if sid in source_ids:
            raise CorpusError(f'Duplicate source_id: {sid}')
        source_ids.add(sid)
        rights = source['license_or_permission']
        if rights['review_status'] != 'verified' or not rights['processing_allowed']:
            raise CorpusError(f'{sid}: processing permission is not verified')
        path = _local(root, source['local_path'], 'data/local/raw')
        if _sha256(path.read_bytes()) != source['sha256']:
            raise CorpusError(f'{sid}: PDF SHA-256 mismatch; source unchanged by ingestion')
        reader = PdfReader(path)
        count = len(reader.pages)
        if count != source['physical_page_count']:
            raise CorpusError(f'{sid}: physical page count mismatch')
        records = source['pages']
        if sorted(p['physical_page'] for p in records) != list(range(1, count + 1)):
            raise CorpusError(f'{sid}: page records must map every physical page exactly once')
        labels = reader.page_labels if "/PageLabels" in reader.root_object else None
        snapshots.append({'source_id': sid, 'source': source['source_path_or_url'],
                          'sha256': source['sha256'], 'physical_pages': count})
        for record in sorted(records, key=lambda p: p['physical_page']):
            pid, number = record['page_id'], record['physical_page']
            if pid in page_ids:
                raise CorpusError(f'Duplicate page_id: {pid}')
            page_ids.add(pid)
            if not (record['included'] and record['extraction_status'] == 'ok'
                    and record['review_status'] == 'approved'):
                skipped.append({'source_id': sid, 'page_id': pid, 'physical_page': number,
                                'reason': record['exclusion_reason'] or 'not_included_ok_approved',
                                'included': record['included'], 'extraction_status': record['extraction_status'],
                                'review_status': record['review_status']})
                continue
            if record['exclusion_reason'] is not None:
                raise CorpusError(f'{pid}: included page also has exclusion reason')
            if not record['metadata']['section'] or not record['metadata']['section_evidence']:
                raise CorpusError(f'{pid}: missing verified section metadata')
            label = record['printed_page_label']
            if label is not None and labels is not None and label != labels[number - 1]:
                raise CorpusError(f'{pid}: printed page label differs from PDF')
            page = _parse_page(reader.pages[number - 1], sid, source['source_path_or_url'],
                               number, label)
            if page.metadata['extraction_status'] != 'ok':
                raise CorpusError(f'{pid}: selected PDF page is empty or cannot be extracted')
            data = page.text.encode('utf-8')
            if _sha256(data) != record['text_sha256']:
                raise CorpusError(f'{pid}: normalized PDF text SHA-256 mismatch')
            saved = _local(root, record['text_path'], 'data/local/normalized').read_bytes()
            if saved != data or _sha256(saved) != record['text_sha256']:
                raise CorpusError(f'{pid}: saved normalized text/checksum mismatch')
            if len(page.text) != record['normalized_char_count']:
                raise CorpusError(f'{pid}: normalized character count mismatch')
            page.metadata.update(deepcopy(record['metadata']))
            page.metadata.update(source_id=sid, page_id=pid, physical_page=number,
                                 printed_page_label=label, version=source['version'],
                                 normalized_char_count=record['normalized_char_count'],
                                 text_sha256=record['text_sha256'])
            pages.append(page)
    if manifest_path.read_bytes() != raw_manifest:
        raise CorpusError('Manifest changed during ingestion')
    return IngestionResult(pages, skipped, snapshots, _sha256(raw_manifest))
