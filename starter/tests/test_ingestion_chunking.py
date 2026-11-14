"""Unit fixtures are temporary test PDFs, never lab corpus or benchmark data."""
from copy import deepcopy
from dataclasses import fields
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from starter.src.chunking import fixed_size, by_paragraph
from starter.src.corpus import CorpusError, ROOT, load_manifest_pages
from starter.src.ingestion import _parse_page, load_pdf, normalize_text
from starter.src.models import Chunk, DocumentPage
from starter.src.preparation import audit_chunks, build_strategies


def write_test_pdf(path, texts):
    """Minimal actual PDF pages exercise pypdf, independently of reader mocks."""
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=595, height=842)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        content = ['BT /F1 12 Tf 50 780 Td']
        for index, line in enumerate(text.split('\n')):
            escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            if index:
                content.append('0 -14 Td')
            content.append(f'({escaped}) Tj')
        content.append('ET')
        stream = DecodedStreamObject()
        stream.set_data('\n'.join(content).encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    writer.set_page_label(0, len(texts) - 1, style="/D")
    path.parent.mkdir(parents=True, exist_ok=True)
    writer.write(path)


@pytest.fixture
def manifest_fixture(tmp_path):
    raw = tmp_path / 'data/local/raw/unit.pdf'
    write_test_pdf(raw, ['Unit cover', 'First unit content.\nSELECT 1;', 'Second unit content.\nSELECT 2;'])
    normalized = tmp_path / 'data/local/normalized'
    normalized.mkdir(parents=True)
    reader = PdfReader(raw)
    pages = []
    for number, page in enumerate(reader.pages, 1):
        text = normalize_text(page.extract_text() or '')
        path = normalized / f'{number}.txt'
        path.write_bytes(text.encode())
        pages.append(dict(page_id=f'unit:p{number}', physical_page=number,
                          printed_page_label=str(number), normalized_char_count=len(text),
                          text_path=path.relative_to(tmp_path).as_posix(),
                          text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                          included=number > 1, exclusion_reason='cover' if number == 1 else None,
                          extraction_status='ok', review_status='approved' if number > 1 else 'rejected',
                          notes='', metadata=dict(section='One' if number == 2 else 'Two', section_evidence='unit fixture heading')))
    source = dict(source_id='unit', title='Temporary unit PDF', source_path_or_url='https://example.org/unit.pdf',
                  license_or_permission=dict(name='Unit fixture', evidence_url='https://example.org/rights',
                      evidence_path='rights.md', review_status='verified', processing_allowed=True,
                      redistribution_allowed=False, reviewed_by='pytest', reviewed_at='2026-01-01T00:00:00Z'),
                  accessed_at='2026-01-01T00:00:00Z', local_path=raw.relative_to(tmp_path).as_posix(),
                  format='pdf', version=None, sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                  physical_page_count=3, retrieval_instructions='Temporary test fixture only', pages=pages)
    manifest = {'$schema': 'manifest.schema.json', 'schema_version': '1.0',
                'counting_policy': 'pdf-content-pages-v1',
                'normalization_policy': 'nfc-whitespace-paragraphs-v1', 'sources': [source]}
    shutil.copyfile(ROOT / 'data/manifest.schema.json', tmp_path / 'data/manifest.schema.json')
    path = tmp_path / 'data/manifest.json'
    path.write_text(json.dumps(manifest))
    return tmp_path, path, manifest


def test_public_dataclasses_unchanged():
    assert [f.name for f in fields(DocumentPage)] == ['document_id', 'source', 'page', 'text', 'metadata']
    assert [f.name for f in fields(Chunk)] == ['chunk_id', 'document_id', 'source', 'page', 'text', 'metadata']


def test_load_pdf_real_parser_and_physical_mapping(tmp_path):
    pdf = tmp_path / 'unit.pdf'
    write_test_pdf(pdf, ['First physical page', '', 'Third physical page'])
    pages = load_pdf(pdf, 'unit', 'unit-source')
    assert [p.page for p in pages] == [1, 2, 3]
    assert [p.text for p in pages] == ['First physical page', '', 'Third physical page']
    assert [p.metadata['extraction_status'] for p in pages] == ['ok', 'empty', 'ok']
    assert [p.metadata['printed_page_label'] for p in pages] == ['1', '2', '3']
    assert all(p.document_id == 'unit' and p.source == 'unit-source' for p in pages)


def test_missing_printed_label_is_not_invented(tmp_path):
    pdf = tmp_path / 'unlabelled.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(pdf)
    assert load_pdf(pdf, 'unit', 'unit-source')[0].metadata['printed_page_label'] is None


def test_parse_error_keeps_page_identity(caplog):
    def broken():
        raise RuntimeError('unit extraction failure')
    page = _parse_page(SimpleNamespace(extract_text=broken), 'unit', 'source', 7, 'vii')
    assert page.page == 7 and page.text == ''
    assert page.metadata['physical_page'] == 7
    assert page.metadata['printed_page_label'] == 'vii'
    assert page.metadata['extraction_status'] == 'error'
    assert 'unit extraction failure' in page.metadata['extraction_error']
    assert 'page 7' in caplog.text


def test_missing_pdf_does_not_fallback(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_pdf(tmp_path / 'missing.pdf', 'unit', 'source')


@pytest.mark.parametrize(('raw', 'expected'), [
    ('  e\u0301\t x\r\n\r\n\r\ny  ', 'é x\n\ny'),
    ('SELECT\t1;\n\n-- comment\n', 'SELECT 1;\n\n-- comment'),
    ('\u00a0\u2003\t\r\n', ''),
    ('Heading\nfirst line\nsecond line\n42', 'Heading\nfirst line\nsecond line\n42'),
])
def test_cleaning_is_exact_and_idempotent(raw, expected):
    assert normalize_text(raw) == expected
    assert normalize_text(expected) == expected


def test_manifest_selection_and_metadata(manifest_fixture):
    root, path, manifest = manifest_fixture
    before = path.read_bytes()
    # Records may be listed out of order; physical mapping must not change.
    manifest['sources'][0]['pages'].reverse()
    path.write_text(json.dumps(manifest))
    result = load_manifest_pages(path, root=root)
    assert [p.page for p in result.pages] == [2, 3]
    assert len(result.skipped_pages) == 1
    assert result.pages[0].metadata['section'] == 'One'
    assert result.pages[0].metadata['source_id'] == 'unit'
    assert result.pages[0].metadata['printed_page_label'] == '2'
    assert result.pages[0].metadata['physical_page'] == result.pages[0].page
    assert result.pages[0].metadata['version'] is None  # never infer missing values
    assert result.pages[0].metadata['section_evidence'] == 'unit fixture heading'
    assert path.read_bytes() == json.dumps(manifest).encode()


@pytest.mark.parametrize('flag,value', [('included', False), ('extraction_status', 'error'), ('review_status', 'pending')])
def test_selection_requires_all_three_flags(manifest_fixture, flag, value):
    root, path, manifest = manifest_fixture
    manifest['sources'][0]['pages'][1][flag] = value
    path.write_text(json.dumps(manifest))
    result = load_manifest_pages(path, root=root)
    assert [p.page for p in result.pages] == [3]
    assert len(result.skipped_pages) == 2


@pytest.mark.parametrize('change', ['pdf', 'stored_text', 'text_checksum', 'character_count', 'label', 'page_map', 'schema', 'section', 'permission'])
def test_manifest_mismatches_fail_without_repair(manifest_fixture, change):
    root, path, manifest = manifest_fixture
    source = manifest['sources'][0]
    page = source['pages'][1]
    if change == 'pdf':
        raw = root / source['local_path']
        raw.write_bytes(raw.read_bytes() + b'changed')
    elif change == 'stored_text':
        (root / page['text_path']).write_text('changed normalized text')
    elif change == 'text_checksum':
        page['text_sha256'] = '0' * 64
    elif change == 'character_count':
        page['normalized_char_count'] += 1
    elif change == 'label':
        page['printed_page_label'] = '99'
    elif change == 'page_map':
        page['physical_page'] = 1
    elif change == 'schema':
        source['format'] = 'markdown'
    elif change == 'section':
        page['metadata']['section'] = None
    elif change == 'permission':
        source['license_or_permission']['processing_allowed'] = False
    path.write_text(json.dumps(manifest))
    before = path.read_bytes()
    with pytest.raises(CorpusError):
        load_manifest_pages(path, root=root)
    assert path.read_bytes() == before


def page_with(text):
    return DocumentPage('unit', 'unit-source', 7, text,
                        {'physical_page': 7, 'printed_page_label': 'vii', 'section': 'Unit',
                         'nested': {'items': ['original']}})


def assert_slices_cover(page, chunks, overlap=0):
    if not page.text:
        assert chunks == []
        return
    cursor = 0
    ids = set()
    for index, chunk in enumerate(chunks):
        trace = chunk.metadata['_chunking']
        start, end = trace['start_char'], trace['end_char']
        assert start == (0 if index == 0 else cursor - overlap)
        assert chunk.text == page.text[start:end] and chunk.text
        assert (chunk.document_id, chunk.source, chunk.page) == (page.document_id, page.source, page.page)
        assert all(chunk.metadata[key] == value for key, value in page.metadata.items())
        assert chunk.chunk_id not in ids
        ids.add(chunk.chunk_id)
        cursor = end
    assert cursor == len(page.text)


@pytest.mark.parametrize('text', ['', 'x', 'x' * 500, 'x' * 501, 'é🙂\n' * 240, ' leading\n\ntrailing  '])
@pytest.mark.parametrize('size,overlap', [(500, 50), (7, 0), (7, 6)])
def test_fixed_windows_coverage_and_limits(text, size, overlap):
    page = page_with(text)
    chunks = fixed_size(page, size, overlap)
    assert_slices_cover(page, chunks, overlap)
    assert all(len(chunk.text) <= size for chunk in chunks)


@pytest.mark.parametrize('size,overlap', [(0, 0), (-1, 0), (1, 1), (500, -1), (500, 500), (True, 0), (500, 1.5)])
def test_invalid_fixed_parameters(size, overlap):
    with pytest.raises(ValueError):
        fixed_size(page_with('text'), size, overlap)


@pytest.mark.parametrize('size', [0, -1, True, 1.5])
def test_invalid_paragraph_parameters(size):
    with pytest.raises(ValueError):
        by_paragraph(page_with('text'), size)


@pytest.mark.parametrize('text', ['', 'x', 'x' * 1300, 'First paragraph.\n\nSecond paragraph.\n\nThird.',
                                  'Single newline\nwith sentence. Next sentence.\nSQL follows:\nSELECT 1;',
                                  'é🙂 test\n' * 100, ' leading and trailing  '])
def test_paragraph_coverage_and_limits(text):
    page = page_with(text)
    chunks = by_paragraph(page, 50)
    assert_slices_cover(page, chunks)
    assert ''.join(chunk.text for chunk in chunks) == text
    assert all(len(chunk.text) <= 50 for chunk in chunks)


def test_whole_paragraphs_when_they_fit():
    text = 'First paragraph.\n\nSecond paragraph.\n\nThird paragraph.'
    chunks = by_paragraph(page_with(text), 37)
    assert chunks[0].text == 'First paragraph.\n\nSecond paragraph.\n\n'
    assert chunks[1].text == 'Third paragraph.'


@pytest.mark.parametrize('sql', [
    'CREATE TABLE t (\na integer,\nb text\n);',
    "INSERT INTO t VALUES ('a;b', 'x''y');",
    'CREATE FUNCTION f() RETURNS text AS $$BEGIN RETURN \';\'; END;$$ LANGUAGE plpgsql;',
    'SELECT /* ; /* nested ; */ ; */\n1 -- ; comment\n;',
])
def test_short_sql_is_not_split(sql):
    max_size = max(len(sql), 80)
    prefix = 'Prose. ' * 9 + '\n'
    page = page_with(prefix + sql + '\nFollowing prose.')
    chunks = by_paragraph(page, max_size)
    assert any(sql in chunk.text for chunk in chunks)
    assert not any(chunk.metadata['_chunking']['split_sql_statement'] for chunk in chunks)
    assert_slices_cover(page, chunks)


def test_multiple_sql_statements_same_line():
    first, second = 'INSERT INTO t VALUES (1);', 'UPDATE t SET a = 2;'
    chunks = by_paragraph(page_with(first + ' ' + second), 30)
    assert any(first in c.text for c in chunks)
    assert any(second in c.text for c in chunks)


def test_oversized_sql_is_bounded_and_flagged():
    text = 'CREATE TABLE t (\n' + ',\n'.join(f'column_{i} text' for i in range(90)) + '\n);'
    page = page_with(text)
    chunks = by_paragraph(page, 500)
    assert_slices_cover(page, chunks)
    assert max(len(c.text) for c in chunks) <= 500
    assert any(c.metadata['_chunking']['split_sql_statement'] for c in chunks)


def test_deterministic_ids_and_strategy_namespace():
    page = page_with('Long paragraph sentence. ' * 60)
    a, b = fixed_size(page, 500, 50), by_paragraph(page, 500)
    assert a == fixed_size(deepcopy(page), 500, 50)
    assert b == by_paragraph(deepcopy(page), 500)
    assert {c.chunk_id for c in a}.isdisjoint(c.chunk_id for c in b)
    assert [c.chunk_id for c in a] != [c.chunk_id for c in fixed_size(page, 500, 0)]
    page.text += '!'
    assert a[0].chunk_id != fixed_size(page, 500, 50)[0].chunk_id


@pytest.mark.parametrize('builder', [lambda p: fixed_size(p, 50, 5), lambda p: by_paragraph(p, 50)])
def test_metadata_is_deepcopied_without_loss(builder):
    page = page_with('Content sentence. ' * 30)
    original = deepcopy(page.metadata)
    chunks = builder(page)
    chunks[0].metadata['nested']['items'].append('changed')
    assert page.metadata == original
    assert chunks[1].metadata['nested'] == original['nested']
    page.metadata['_chunking'] = {'existing': 'must not overwrite'}
    with pytest.raises(ValueError):
        builder(page)


def test_c_reuses_exact_b_and_audit_detects_lost_coverage():
    pages = [page_with('Test sentence. ' * 100)]
    strategies = build_strategies(pages)
    assert strategies['C'] is strategies['B']
    assert not audit_chunks(pages, strategies['A'], 'A')['errors']
    assert not audit_chunks(pages, strategies['B'], 'B')['errors']
    assert audit_chunks(pages, strategies['B'][1:], 'B')['errors']


def test_audit_detects_loss_of_nullable_metadata():
    page = page_with('Content. ' * 80)
    page.metadata['version'] = None
    chunks = fixed_size(page, 500, 50)
    del chunks[0].metadata['version']
    assert any('metadata lost: version' in e for e in audit_chunks([page], chunks, 'A')['errors'])


@pytest.fixture(scope='module')
def real_corpus():
    path = ROOT / 'data/manifest.json'
    if not (ROOT / 'data/local/raw/postgresql-16-A4.pdf').is_file():
        pytest.skip('Real local corpus absent; restore the approved snapshot to run integration tests')
    before = path.read_bytes()
    result = load_manifest_pages(path)
    assert path.read_bytes() == before
    return result


@pytest.mark.integration
def test_real_corpus_pages_metadata_and_coverage(real_corpus):
    assert [p.page for p in real_corpus.pages] == list(range(97, 133)) + list(range(148, 152))
    assert len(real_corpus.skipped_pages) == 3034
    assert {p.metadata['section'] for p in real_corpus.pages} == {'Data Definition', 'Data Manipulation'}
    assert sum(len(p.text) for p in real_corpus.pages) == 103371
    strategies = build_strategies(real_corpus.pages)
    for name, chunks in strategies.items():
        audit = audit_chunks(real_corpus.pages, chunks, name)
        assert not audit['errors']
        assert audit['covered_characters'] == 103371
        assert audit['source_pages_with_chunks'] == 40
        assert audit['max_chars'] <= 500
    assert strategies['B'] is strategies['C']
    assert {c.chunk_id for c in strategies['A']}.isdisjoint(c.chunk_id for c in strategies['B'])


@pytest.mark.integration
def test_real_page_mapping_and_ids_independent_of_page_order(real_corpus):
    first = build_strategies(real_corpus.pages)
    repeated = build_strategies(list(reversed(real_corpus.pages)))
    manifest = json.loads((ROOT / 'data/manifest.json').read_text(encoding='utf-8'))
    records = {p['physical_page']: p for p in manifest['sources'][0]['pages']}
    for strategy in first:
        assert sorted(c.chunk_id for c in first[strategy]) == sorted(c.chunk_id for c in repeated[strategy])
        for chunk in first[strategy]:
            record = records[chunk.page]
            assert record['included'] and record['review_status'] == 'approved'
            assert chunk.metadata['printed_page_label'] == record['printed_page_label']
            assert chunk.metadata['physical_page'] == chunk.page
            assert chunk.metadata['section'] == record['metadata']['section']
            assert chunk.document_id == chunk.metadata['source_id'] == 'postgresql-16.16-a4'
