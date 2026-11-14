"""Isolated unit tests: mocked extraction, never submitted as corpus/evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import extract_corpus

SPEC = importlib.util.spec_from_file_location('check_corpus', Path(__file__).parents[1] / 'scripts/check_corpus.py')
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)
SCHEMA = json.loads((check.ROOT / 'data/manifest.schema.json').read_text())


class CorpusValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'data/local/raw').mkdir(parents=True)
        (self.root / 'data/local/normalized').mkdir()
        (self.root / 'rights.md').write_text('Unit test permission record')
        raw = self.root / 'data/local/raw/source.pdf'
        raw.write_bytes(b'unit-test reader mock; not a PDF or corpus')
        self.texts = [f'Unit test extraction {i}' for i in range(30)]
        pages = []
        for i, text in enumerate(self.texts, 1):
            path = f'data/local/normalized/{i}.txt'
            (self.root / path).write_bytes(text.encode())
            pages.append(dict(page_id=f'p{i}', physical_page=i, printed_page_label=None,
                              normalized_char_count=len(text), text_path=path,
                              text_sha256=check.digest(text.encode()), included=True,
                              exclusion_reason=None, extraction_status='ok', review_status='approved',
                              notes='', metadata=dict(section='A' if i < 15 else 'B', section_evidence='test locator')))
        source = dict(source_id='unit', title='Unit fixture', source_path_or_url='https://example.org/unit',
                      accessed_at='2026-01-01T00:00:00Z', local_path='data/local/raw/source.pdf',
                      format='pdf', version=None, sha256=check.digest(raw.read_bytes()),
                      physical_page_count=30, retrieval_instructions='Unit test only', pages=pages,
                      license_or_permission=dict(name='Unit fixture only', evidence_url='https://example.org/rights',
                          evidence_path='rights.md', review_status='verified', processing_allowed=True,
                          redistribution_allowed=False, reviewed_by='unittest', reviewed_at='2026-01-01T00:00:00Z'))
        self.manifest = dict(schema_version='1.0', counting_policy='pdf-content-pages-v1',
                             normalization_policy='nfc-whitespace-paragraphs-v1', sources=[source])
        self.manifest['$schema'] = 'manifest.schema.json'
        self.source, self.pages = source, pages

    def run_check(self):
        class Page:
            def __init__(self, text): self.text = text
            def extract_text(self): return self.text
        with patch('pypdf.PdfReader') as reader:
            reader.return_value.pages = [Page(t) for t in self.texts]
            return check.validate(self.manifest, SCHEMA, self.root)

    def test_valid_thirty_pages(self):
        self.assertTrue(self.run_check()['passed'])

    def test_empty_manifest(self):
        self.manifest['sources'] = []
        self.assertFalse(self.run_check()['passed'])

    def test_invalid_variants(self):
        original = copy.deepcopy(self.manifest)
        mutations = [
            lambda s: s.update(sha256='0' * 64),
            lambda s: s['license_or_permission'].update(review_status='pending'),
            lambda s: s['pages'][0]['metadata'].update(section=None),
            lambda s: s['pages'][0].update(physical_page=31),
            lambda s: s['pages'][0].update(normalized_char_count=0),
            lambda s: s['pages'][0].update(extraction_status='error'),
            lambda s: s['pages'][0].update(review_status='pending'),
            lambda s: s['pages'][0].update(page_id='p2'),
            lambda s: s['pages'][0].update(text_path='../escape.txt'),
            lambda s: s.pop('title'),
            lambda s: s.update(accessed_at='bad-date'),
            lambda s: s.update(physical_page_count=True),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                self.manifest = copy.deepcopy(original)
                mutate(self.manifest['sources'][0])
                self.assertFalse(self.run_check()['passed'])

    def test_duplicate_not_counted(self):
        self.texts[1] = self.texts[0]
        self.pages[1]['normalized_char_count'] = len(self.texts[0])
        self.pages[1]['text_sha256'] = check.digest(self.texts[0].encode())
        (self.root / self.pages[1]['text_path']).write_bytes(self.texts[0].encode())
        result = self.run_check()
        self.assertEqual(result['valid_unique_pages'], 29)
        self.assertEqual(result['duplicate_pages'], 1)
        self.assertFalse(result['passed'])

    def test_empty_page(self):
        self.texts[0] = ''
        self.assertFalse(self.run_check()['passed'])

    def test_missing_file(self):
        (self.root / self.pages[0]['text_path']).unlink()
        self.assertFalse(self.run_check()['passed'])

    def test_reextract_checksum_refusal(self):
        self.source['sha256'] = '0' * 64
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps(self.manifest))
        with patch.object(extract_corpus, 'ROOT', self.root), patch.object(sys, 'argv', ['extract', '--manifest', str(manifest)]), patch.object(extract_corpus, 'PdfReader') as reader:
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                extract_corpus.main()
            reader.assert_not_called()

    def test_reextract_content_mismatch(self):
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps(self.manifest))
        with patch.object(extract_corpus, 'ROOT', self.root), patch.object(sys, 'argv', ['extract', '--manifest', str(manifest)]), patch.object(extract_corpus, 'PdfReader') as reader:
            reader.return_value.pages = [unittest.mock.Mock() for _ in range(30)]
            reader.return_value.pages[0].extract_text.return_value = 'changed snapshot content'
            with self.assertRaisesRegex(ValueError, 'Extraction differs'):
                extract_corpus.main()

    def test_reextract_restores_text(self):
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps(self.manifest))
        target = self.root / self.pages[0]['text_path']
        target.unlink()
        with patch.object(extract_corpus, 'ROOT', self.root), patch.object(sys, 'argv', ['extract', '--manifest', str(manifest)]), patch.object(extract_corpus, 'PdfReader') as reader:
            reader.return_value.pages = [unittest.mock.Mock() for _ in range(30)]
            for page, text in zip(reader.return_value.pages, self.texts):
                page.extract_text.return_value = text
            self.assertEqual(extract_corpus.main(), 0)
        self.assertEqual(target.read_bytes(), self.texts[0].encode())

    def test_normalization(self):
        self.assertEqual(check.normalize_text('  e\u0301\t x\r\n\r\n\r\ny  '), 'é x\n\ny')


if __name__ == '__main__':
    unittest.main()
