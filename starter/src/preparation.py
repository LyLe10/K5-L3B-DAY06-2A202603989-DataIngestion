"""Build A/B/C and measure source coverage without retrieval or embeddings."""
from collections import defaultdict
from statistics import mean

from .chunking import by_paragraph, fixed_size
from .models import Chunk, DocumentPage


def build_strategies(pages: list[DocumentPage]) -> dict[str, list[Chunk]]:
    a = [chunk for page in pages for chunk in fixed_size(page, 500, 50)]
    b = [chunk for page in pages for chunk in by_paragraph(page, 500)]
    return {'A': a, 'B': b, 'C': b}


def audit_chunks(pages: list[DocumentPage], chunks: list[Chunk], strategy: str) -> dict:
    """Verify exact slices, complete coverage and retained metadata per page."""
    errors = []
    page_map = {(page.document_id, page.source, page.page): page for page in pages}
    if len(page_map) != len(pages):
        errors.append('duplicate source page keys')
    groups = defaultdict(list)
    ids = set()
    for chunk in chunks:
        if chunk.chunk_id in ids:
            errors.append(f'duplicate chunk ID: {chunk.chunk_id}')
        ids.add(chunk.chunk_id)
        key = (chunk.document_id, chunk.source, chunk.page)
        if key not in page_map:
            errors.append(f'unknown source page: {key}')
            continue
        page = page_map[key]
        trace = chunk.metadata['_chunking']
        start, end = trace['start_char'], trace['end_char']
        if not (0 <= start < end <= len(page.text)) or chunk.text != page.text[start:end]:
            errors.append(f'{chunk.chunk_id}: source slice mismatch')
        if not chunk.text or len(chunk.text) > 500:
            errors.append(f'{chunk.chunk_id}: invalid chunk length')
        if trace['strategy'] != ('B' if strategy == 'C' else strategy):
            errors.append(f'{chunk.chunk_id}: strategy mismatch')
        for name, value in page.metadata.items():
            if name not in chunk.metadata or chunk.metadata[name] != value:
                errors.append(f'{chunk.chunk_id}: metadata lost: {name}')
        groups[key].append((start, end))
    covered = 0
    for key, page in page_map.items():
        cursor = 0
        spans = sorted(groups[key])
        previous = None
        for start, end in spans:
            if start > cursor:
                errors.append(f'{key}: uncovered characters {cursor}:{start}')
            if previous is not None:
                expected = previous[1] - 50 if strategy == 'A' else previous[1]
                if start != expected:
                    errors.append(f'{key}: invalid overlap or paragraph continuity')
            cursor = max(cursor, end)
            previous = (start, end)
        if cursor != len(page.text):
            errors.append(f'{key}: incomplete page coverage')
        covered += min(cursor, len(page.text))
    lengths = [len(c.text) for c in chunks]
    return {'chunks': len(chunks), 'min_chars': min(lengths, default=0),
            'mean_chars': round(mean(lengths), 3) if lengths else 0,
            'max_chars': max(lengths, default=0), 'chunk_characters': sum(lengths),
            'source_characters': sum(len(p.text) for p in pages), 'covered_characters': covered,
            'source_pages_with_chunks': len(groups),
            'sql_split_boundaries': (None if strategy == 'A' else sum(c.metadata['_chunking']['split_sql_statement'] for c in chunks)),
            'errors': errors}
