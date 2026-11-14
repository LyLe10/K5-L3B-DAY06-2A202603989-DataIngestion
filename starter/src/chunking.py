"""Deterministic character chunking with exact source offsets."""
from copy import deepcopy
import hashlib
import json
import re

from .models import Chunk, DocumentPage

# Recognize likely SQL at line starts. This is a boundary heuristic, not a SQL
# validator; page-start continuations without a command cannot be reconstructed.
_SQL_START = re.compile(
    r'(?im)^[^\S\n]*(?:CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|ROLE|POLICY|SCHEMA|FUNCTION|VIEW|TYPE|INDEX|TRIGGER|SEQUENCE)\b'
    r'|ALTER\s+(?:TABLE|ROLE|SCHEMA|FUNCTION|POLICY)\b|INSERT\s+INTO\b|DELETE\s+FROM\b'
    r'|UPDATE\s+\S+\s+SET\b|SELECT\s+|WITH\s+\w+\s+AS\b|GRANT\s+|REVOKE\s+|COPY\s+|SET\s+ROLE\b)')


def _statement_end(text: str, start: int) -> int:
    """Find a terminator outside SQL strings, identifiers and comments."""
    i, quote, dollar, block, line_comment = start, None, None, 0, False
    while i < len(text):
        char, pair = text[i], text[i:i + 2]
        if line_comment:
            if char == '\n':
                line_comment = False
        elif block:
            if pair == '/*':
                block += 1
                i += 1
            elif pair == '*/':
                block -= 1
                i += 1
        elif dollar:
            if text.startswith(dollar, i):
                i += len(dollar) - 1
                dollar = None
        elif quote:
            if char == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    i += 1
                else:
                    quote = None
            elif char == '\\' and quote == "'":
                # Conservatively protect escaped quotes (e.g. E'...').
                i += 1
        elif pair == '--':
            line_comment = True
            i += 1
        elif pair == '/*':
            block = 1
            i += 1
        elif char in "'\"":
            quote = char
        elif char == '$' and (match := re.match(r'\$(?:[A-Za-z_]\w*)?\$', text[i:])):
            dollar = match.group()
            i += len(dollar) - 1
        elif char == ';':
            return i + 1
        i += 1
    return len(text)


def _sql_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for match in _SQL_START.finditer(text):
        if spans and match.start() < spans[-1][1]:
            continue
        start = match.start()
        while start < len(text) and text[start] in ' \t':
            start += 1
        end = _statement_end(text, start)
        spans.append((start, end))
        # Protect subsequent statements sharing the same line as a terminator.
        cursor = end
        while cursor < len(text) and text[cursor] in ' \t':
            cursor += 1
        while cursor < len(text) and _SQL_START.match(text[cursor:]):
            end = _statement_end(text, cursor)
            spans.append((cursor, end))
            cursor = end
            while cursor < len(text) and text[cursor] in ' \t':
                cursor += 1
    return spans


def _positive_integer(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f'{name} must be a positive integer')


def _chunk(page: DocumentPage, start: int, end: int, strategy: str,
           parameters: dict, sql_split: bool | None = None) -> Chunk:
    if '_chunking' in page.metadata:
        raise ValueError('page metadata reserves _chunking for chunk provenance')
    payload = {'algorithm_version': 1, 'strategy': strategy, 'parameters': parameters,
               'document_id': page.document_id, 'source': page.source, 'page': page.page,
               'page_text_sha256': hashlib.sha256(page.text.encode('utf-8')).hexdigest(),
               'start': start, 'end': end}
    stable = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                      separators=(',', ':')).encode('utf-8')).hexdigest()
    metadata = deepcopy(page.metadata)
    metadata['_chunking'] = {'strategy': strategy, 'algorithm_version': 1,
                             'unit': 'characters', 'start_char': start, 'end_char': end,
                             'parameters': dict(parameters), 'split_sql_statement': sql_split}
    return Chunk(f'{strategy}:{stable}', page.document_id, page.source, page.page,
                 page.text[start:end], metadata)


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Exact, overlapping character windows; retain text and all page metadata."""
    _positive_integer(size, 'size')
    if type(overlap) is not int or not 0 <= overlap < size:
        raise ValueError('overlap must be an integer with 0 <= overlap < size')
    chunks = []
    start = 0
    while start < len(page.text):
        end = min(start + size, len(page.text))
        chunks.append(_chunk(page, start, end, 'A', {'size': size, 'overlap': overlap}))
        if end == len(page.text):
            break
        start = end - overlap
    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Pack paragraphs; split long ones at safe sentence/line/word boundaries.

    Never rewrite text or join across physical pages. Prefer blank-line paragraph
    boundaries. When pypdf provides only single newlines, use sentence/line/word
    boundaries. Protect SQL statements that fit within max_size; longer statements
    must split and are flagged. Exact slices retain even separator whitespace.
    """
    _positive_integer(max_size, 'max_size')
    text = page.text
    sql = _sql_spans(text)
    paragraphs = [m.end() for m in re.finditer(r'\n[ \t]*\n+', text)]
    sentences = [m.end() for m in re.finditer(r'[.!?][ \t\n]+', text)]
    lines = [m.end() for m in re.finditer(r'\n', text)]
    words = [m.end() for m in re.finditer(r'\s+', text)]
    sql_edges = [edge for span in sql for edge in span]

    def safe(cut):
        return not any(left < cut < right and right - left <= max_size for left, right in sql)

    chunks, start = [], 0
    while start < len(text):
        limit = min(start + max_size, len(text))
        end = limit
        if limit < len(text):
            for candidates in [paragraphs, sentences, sorted(lines + sql_edges), words]:
                choices = [cut for cut in candidates if start < cut <= limit and safe(cut)]
                if choices:
                    end = max(choices)
                    break
            else:
                # Before a short SQL statement that straddles the hard limit.
                before_sql = [left for left, right in sql if start < left <= limit < right
                              and right - left <= max_size]
                end = max(before_sql) if before_sql else limit
        split_sql = any(left < end < right for left, right in sql)
        chunks.append(_chunk(page, start, end, 'B', {'max_size': max_size}, split_sql))
        start = end
    return chunks
