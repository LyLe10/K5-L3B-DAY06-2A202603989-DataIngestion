"""Offline PDF corpus audit. Never downloads sources or invents review decisions."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]


# Keep the corpus audit and ingestion on the same normalization policy.
sys.path.insert(0, str(ROOT))
from starter.src.ingestion import normalize_text


def digest(data):
    return hashlib.sha256(data).hexdigest()


def local_path(value, root):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('path escapes repository')
    return path


def validate(manifest, schema, root=ROOT):
    from jsonschema import Draft202012Validator, FormatChecker
    from pypdf import PdfReader
    errors, warnings = [], []
    report = {'physical_pages': 0, 'included_pages': 0, 'valid_unique_pages': 0,
              'excluded_pages': 0, 'duplicate_pages': 0, 'errors': errors, 'warnings': warnings}
    Draft202012Validator.check_schema(schema)
    for err in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest):
        errors.append(f"schema {'.'.join(map(str, err.absolute_path))}: {err.message}")
    if errors:
        report['passed'] = False
        return report
    source_ids, page_ids, seen_text, sections = set(), set(), set(), set()
    for source in manifest['sources']:
        sid = source['source_id']
        start_errors = len(errors)
        def fail(message):
            errors.append(f'{sid}: {message}')
        if sid in source_ids:
            fail('duplicate source_id')
        source_ids.add(sid)
        rights = source['license_or_permission']
        if rights['review_status'] != 'verified' or not rights['processing_allowed']:
            fail('permission not verified or processing not allowed')
        for label, value in [('accessed_at', source['accessed_at']),
                             ('reviewed_at', rights['reviewed_at'])]:
            try:
                timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if 'T' not in value or timestamp.tzinfo is None:
                    raise ValueError('timestamp needs time and timezone')
                if timestamp > datetime.now(timezone.utc):
                    fail(f'{label} is in the future')
            except ValueError:
                fail(f'{label} must be an ISO timestamp with timezone')
        try:
            evidence = local_path(rights['evidence_path'], root)
            if not evidence.is_file() or not evidence.read_text(encoding='utf-8').strip():
                fail('missing permission evidence note')
            pdf_path = local_path(source['local_path'], root)
            if not pdf_path.is_relative_to((root / 'data/local/raw').resolve()):
                fail('PDF must be under data/local/raw')
            if digest(pdf_path.read_bytes()) != source['sha256']:
                fail('PDF checksum mismatch')
            reader = PdfReader(pdf_path)
            count = len(reader.pages)
        except Exception as exc:
            fail(f'cannot read source/evidence: {type(exc).__name__}: {exc}')
            continue
        report['physical_pages'] += count
        numbers = [p['physical_page'] for p in source['pages']]
        if source['physical_page_count'] != count:
            fail('physical_page_count mismatch')
        if sorted(numbers) != list(range(1, count + 1)):
            fail('page records must cover every physical page exactly once')
        source_ok = len(errors) == start_errors
        for page in source['pages']:
            pid, n = page['page_id'], page['physical_page']
            page_errors = len(errors)
            if pid in page_ids:
                fail(f'{pid}: duplicate page_id')
            page_ids.add(pid)
            included = page['included']
            report['included_pages' if included else 'excluded_pages'] += 1
            if not included and not (page['exclusion_reason'] or '').strip():
                fail(f'{pid}: excluded page needs reason')
            if included and (page['review_status'] != 'approved' or page['extraction_status'] != 'ok' or page['exclusion_reason'] is not None):
                fail(f'{pid}: included page must be approved, extracted and not excluded')
            if not 1 <= n <= count:
                fail(f'{pid}: page outside PDF range')
                continue
            try:
                text = normalize_text(reader.pages[n - 1].extract_text() or '')
                status = 'ok' if text else 'empty'
            except Exception as exc:
                text, status = '', 'error'
                warnings.append(f'{pid}: extraction error: {type(exc).__name__}')
            if status != page['extraction_status']:
                fail(f'{pid}: extraction status mismatch')
            if status == 'error' and not page['notes'].strip():
                fail(f'{pid}: extraction error requires notes')
            if included and not text:
                fail(f'{pid}: empty or unreadable included page')
            try:
                path = local_path(page['text_path'], root)
                if not path.is_relative_to((root / 'data/local/normalized').resolve()):
                    fail(f'{pid}: text must be under data/local/normalized')
                saved = path.read_bytes()
                if saved != text.encode('utf-8'):
                    fail(f'{pid}: saved text differs from normalized PDF text')
                if digest(saved) != page['text_sha256']:
                    fail(f'{pid}: text checksum mismatch')
            except (OSError, ValueError) as exc:
                fail(f'{pid}: cannot read normalized text: {exc}')
            if len(text) != page['normalized_char_count']:
                fail(f'{pid}: normalized character count mismatch')
            if included:
                meta = page['metadata']
                section, evidence = meta['section'], meta['section_evidence']
                if not section or not section.strip() or not evidence or not evidence.strip():
                    fail(f'{pid}: missing section or section evidence locator')
                # Ignore whitespace differences when detecting exact content copies.
                key = digest(re.sub(r'\s+', ' ', text).encode('utf-8'))
                if text and key in seen_text:
                    report['duplicate_pages'] += 1
                    warnings.append(f'{pid}: duplicate content; not counted')
                elif source_ok and len(errors) == page_errors:
                    seen_text.add(key)
                    report['valid_unique_pages'] += 1
                    sections.add(section)
    if report['valid_unique_pages'] < 30:
        errors.append('corpus needs at least 30 valid unique content pages')
    if len(sections) < 2:
        errors.append('section filter needs at least two verified distinct values')
    report['filter_values'] = sorted(sections)
    report['selected_pages'] = [
        {'source_id': source['source_id'], 'page': page['physical_page'],
         'printed_page_label': page['printed_page_label'],
         'section': page['metadata']['section'], 'normalized_char_count': page['normalized_char_count']}
        for source in manifest['sources'] for page in source['pages'] if page['included']]
    report['excluded_by_reason'] = dict(Counter(
        page['exclusion_reason'] for source in manifest['sources']
        for page in source['pages'] if not page['included']))
    report['sources'] = [
        {'source_id': source['source_id'], 'url': source['source_path_or_url'],
         'version': source['version'], 'sha256': source['sha256']}
        for source in manifest['sources']]
    report['passed'] = not errors
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/manifest.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'results')
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
        schema = json.loads((ROOT / 'data/manifest.schema.json').read_text(encoding='utf-8'))
        report = validate(manifest, schema)
        report['checked_at'] = datetime.now(timezone.utc).isoformat()
        report['manifest_sha256'] = digest(args.manifest.read_bytes())
        output = args.output_dir.resolve()
        if not output.is_relative_to(ROOT):
            raise ValueError('output directory must be inside repository')
        output.mkdir(parents=True, exist_ok=True)
        (output / 'corpus_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        lines = ['# Corpus validation', '', f"Status: {'PASS' if report['passed'] else 'FAIL'}", '',
                 f"Physical: {report['physical_pages']}; included: {report['included_pages']}; valid unique: {report['valid_unique_pages']}; excluded: {report['excluded_pages']}; duplicates: {report['duplicate_pages']}", '',
                 'Errors:', *['- ' + e for e in report['errors']], '', 'Warnings:', *['- ' + w for w in report['warnings']]]
        lines += ['', '## Source snapshots', '']
        for source in report.get('sources', []):
            lines += [f"- {source['source_id']}: version {source['version']}",
                      f"  - URL: {source['url']}", f"  - SHA-256: `{source['sha256']}`"]
        lines += ['', '## Excluded pages by reason', '']
        lines += [f'- {reason}: {count}' for reason, count in report.get('excluded_by_reason', {}).items()]
        lines += ['', '## Selected physical pages', '',
                  '| Source | PDF page (1-based) | Printed label | Section | Characters |',
                  '|---|---:|---|---|---:|']
        for page in report.get('selected_pages', []):
            lines.append(f"| {page['source_id']} | {page['page']} | {page['printed_page_label']} | {page['section']} | {page['normalized_char_count']} |")
        lines += ['', 'Review note: selected content and section provenance reviewed by Codex; not a claim of human review.',
                  'PDF and extracted text remain under ignored data/local/.',
                  f"Checked at: {report['checked_at']}", f"Manifest SHA-256: `{report['manifest_sha256']}`"]
        (output / 'corpus_validation.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f"{'PASS' if report['passed'] else 'FAIL'}: {report['valid_unique_pages']} valid unique pages")
        return 0 if report['passed'] else 1
    except Exception as exc:
        print(f'Cannot validate corpus: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
