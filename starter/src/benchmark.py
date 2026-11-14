"""Offline benchmark integrity checks, not semantic gold approval or retrieval."""
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator
from .corpus import ROOT, load_manifest_pages


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _tokens(text):
    stop = {'a','an','the','is','are','of','in','to','for','and','or','does','do',
            'what','which','how','when','can','postgresql','table','column'}
    return set(re.findall(r'[a-z0-9]+', text.lower())) - stop


def validate_records(records, corpus, schema):
    """Structural/source checks; return pending human review for every draft."""
    Draft202012Validator.check_schema(schema)
    errors, warnings, pending = [], [], []
    validator = Draft202012Validator(schema)
    pages = {(p.document_id, p.page): p for p in corpus.pages}
    sources = {s['source_id']: s for s in corpus.sources}
    ids, normalized_questions = set(), {}
    split_counts, filters, topics, categories = Counter(), Counter(), Counter(), Counter()
    for index, q in enumerate(records):
        label = q.get('id', f'row:{index}') if isinstance(q, dict) else f'row:{index}'
        violations = list(validator.iter_errors(q))
        if violations:
            errors.extend(f'{label}: schema {list(e.path)}: {e.message}' for e in violations)
            continue
        if q['id'] in ids:
            errors.append(f'{label}: duplicate question ID')
        ids.add(q['id'])
        split_counts[q['split']] += 1
        topics[q['topic']] += 1
        categories[q['category']] += 1
        # This rejects obvious non-English script, but cannot identify every language.
        # English-only is a declared structure plus human language review, not a proof.
        for field in ('question', 'expected_answer', 'evidence_quote'):
            value = q[field]
            if not any(c.isascii() and c.isalpha() for c in value) or any(
                    c.isalpha() and not c.isascii() for c in value):
                errors.append(f'{label}: English-structure check failed for {field}')
        normalized = ' '.join(re.findall(r'[a-z0-9]+', q['question'].lower()))
        if normalized in normalized_questions:
            errors.append(f'{label}: duplicate question text with {normalized_questions[normalized]}')
        normalized_questions[normalized] = label
        if q['review_status'] == 'NEEDS_HUMAN_REVIEW':
            pending.append(label)
        entries = [q, *q.get('gold_alternatives', [])]
        seen_gold = set()
        for gold_index, gold in enumerate(entries):
            key = (gold['gold_source_id'], gold['gold_page'])
            page = pages.get(key)
            if page is None or gold['gold_source_id'] not in sources:
                errors.append(f'{label}: gold {gold_index}: source/page is not selected and verified')
                continue
            if gold['source_sha256'] != sources[key[0]]['sha256']:
                errors.append(f'{label}: gold {gold_index}: source checksum mismatch')
            if gold['page_text_sha256'] != page.metadata['text_sha256']:
                errors.append(f'{label}: gold {gold_index}: page checksum mismatch')
            start, end = gold['evidence_start_char'], gold['evidence_end_char']
            quote = gold['evidence_quote']
            if any(c.isalpha() and not c.isascii() for c in quote):
                errors.append(f'{label}: gold {gold_index}: English-structure check failed')
            if not (0 <= start < end <= len(page.text)) or page.text[start:end] != quote:
                errors.append(f'{label}: gold {gold_index}: quote/offset mismatch')
            if not quote.strip() or len(quote.strip()) < 20:
                errors.append(f'{label}: gold {gold_index}: missing or too short evidence')
            identity = (*key, start, end)
            if identity in seen_gold:
                errors.append(f'{label}: duplicate gold alternative')
            seen_gold.add(identity)
            if page.text.count(quote) > 1:
                warnings.append(f'{label}: gold {gold_index}: quote repeats on page; review offsets/context')
            if q.get('filter') and q['filter']['section'] != page.metadata['section']:
                errors.append(f'{label}: gold {gold_index}: section filter conflicts with evidence')
        if q.get('filter'):
            filters[q['split']] += 1
            section = q['filter']['section']
            # Context is a separately recorded pre-retrieval input, never derived here.
            if section not in q['filter_context'] or section not in q['question']:
                errors.append(f'{label}: filter lacks explicit question/context provenance')
        elif q.get('filter_context') or q.get('filter_rationale'):
            errors.append(f'{label}: context/rationale without filter')
    for i, left in enumerate(records):
        if not isinstance(left, dict) or not isinstance(left.get('question'), str):
            continue
        for right in records[i+1:]:
            if not isinstance(right, dict) or not isinstance(right.get('question'), str):
                continue
            a, b = _tokens(left['question']), _tokens(right['question'])
            jaccard = len(a & b) / len(a | b) if a | b else 1
            similarity = SequenceMatcher(None, left['question'].lower(), right['question'].lower()).ratio()
            if jaccard >= .55 or similarity >= .82:
                warnings.append(f"Near-duplicate candidate {left.get('id')} / {right.get('id')}: "
                                f'jaccard={jaccard:.3f}, sequence={similarity:.3f}; semantic review required')
            if left.get('split') != right.get('split') and (left.get('gold_source_id'), left.get('gold_page')) == (
                    right.get('gold_source_id'), right.get('gold_page')):
                warnings.append(f"Cross-split page overlap {left.get('id')} / {right.get('id')}; not document-independent")
    if len(records) != 20 or split_counts != {'dev': 15, 'test': 5}:
        errors.append('Benchmark must contain exactly 20 valid records: 15 dev / 5 test')
    if sum(filters.values()) < 3 or filters['dev'] < 2 or filters['test'] < 1:
        errors.append('Need >=3 filters, including >=2 dev and >=1 test')
    warnings.append('Automatic checks do not establish English-language semantics, answer sufficiency, '
                    'alternative completeness or holdout independence; human review required')
    return dict(structural_source_valid=not errors, errors=errors, warnings=warnings,
                counts=dict(total=len(records), splits=dict(split_counts), filters=dict(filters),
                            topics=dict(topics), categories=dict(categories)),
                needs_human_review=pending, human_approved=False, frozen=False,
                retrieval_executed=False, semantic_gold_correctness='NOT_CERTIFIED')


def validate_benchmark(directory=None, *, root=ROOT, corpus=None):
    root = Path(root).resolve()
    directory = Path(directory or root/'benchmark').resolve()
    manifest = json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    schema_bytes = (directory/'question.schema.json').read_bytes()
    frozen = manifest.get('freeze_status') == 'FROZEN'
    if manifest['schema_version'] != 1 or manifest['freeze_status'] not in ('DRAFT_NOT_FROZEN', 'FROZEN'):
        raise ValueError('Unsupported Stage 5.2 benchmark state/version')
    if (manifest.get('language') != 'en' or manifest.get('human_approval_recorded') is not frozen
            or manifest.get('retrieval_executed') is not False
            or manifest.get('quality_metrics_computed') is not False):
        raise ValueError('Benchmark must declare English, consistent approval and no retrieval/quality run')
    if manifest['schema_sha256'] != sha(schema_bytes):
        raise ValueError('Benchmark schema checksum mismatch')
    if manifest['corpus_manifest_sha256'] != sha((root/'data/manifest.json').read_bytes()):
        raise ValueError('Corpus manifest checksum mismatch')
    if manifest['notice_sha256'] != sha((directory/'NOTICE.txt').read_bytes()):
        raise ValueError('Source notice checksum mismatch')
    if set(manifest['files']) != {'dev.jsonl', 'test.jsonl'}:
        raise ValueError('Expected separate dev.jsonl and test.jsonl')
    records = []
    for name in ('dev.jsonl', 'test.jsonl'):
        data = (directory/name).read_bytes()
        if sha(data) != manifest['files'][name]['sha256']:
            raise ValueError(f'{name}: benchmark checksum mismatch; never rewrite checksums to hide it')
        rows = [json.loads(line) for line in data.decode('utf-8').splitlines() if line.strip()]
        if len(rows) != manifest['files'][name]['count'] or any(q.get('split') != name[:-6] for q in rows):
            raise ValueError(f'{name}: split/count mismatch')
        records.extend(rows)
    corpus = corpus if corpus is not None else load_manifest_pages(root/'data/manifest.json', root=root)
    if len(corpus.pages) != 40 or corpus.manifest_sha256 != manifest['corpus_manifest_sha256']:
        raise ValueError('Expected independently verified 40-page corpus')
    result = validate_records(records, corpus, json.loads(schema_bytes))
    if frozen:
        freeze_bytes = (directory/'freeze_manifest.json').read_bytes()
        if sha(freeze_bytes) != manifest.get('freeze_manifest_sha256'):
            raise ValueError('Freeze manifest checksum mismatch')
        freeze = json.loads(freeze_bytes)
        expected_ids = sorted(q['id'] for q in records)
        pages = sorted([p.document_id, p.page, p.metadata['text_sha256']] for p in corpus.pages)
        if (not result['structural_source_valid']
                or any(not w.startswith('Automatic checks') for w in result['warnings'])
                or freeze.get('freeze_schema_version') != 1 or freeze.get('question_schema_version') != 1
                or freeze.get('freeze_status') != 'FROZEN'
                or freeze.get('files') != manifest['files']
                or freeze.get('schema_sha256') != manifest['schema_sha256']
                or freeze.get('corpus_manifest_sha256') != manifest['corpus_manifest_sha256']
                or freeze.get('notice_sha256') != manifest['notice_sha256']
                or freeze.get('source_checksums') != {s['source_id']: s['sha256'] for s in corpus.sources}
                or freeze.get('selected_pages') != pages
                or freeze.get('counts') != result['counts']
                or freeze.get('approved_question_ids') != expected_ids
                or freeze.get('holdout_rule') != 'NO_TEST_ADJUSTMENT_FROM_RETRIEVAL_RESULTS'
                or freeze.get('review', {}).get('reviewer') != 'user-assisted review'
                or freeze.get('review', {}).get('ai_assisted') is not True
                or freeze.get('review', {}).get('independent_verification_claimed') is not False
                or not freeze.get('review', {}).get('approval_basis')):
            raise ValueError('Frozen identity/counts/review/holdout mismatch or unresolved validation warning')
        result.update(frozen=True, human_approved=True, needs_human_review=[],
                      semantic_gold_correctness='USER_ASSISTED_REVIEW_RECORDED_NOT_INDEPENDENTLY_CERTIFIED',
                      draft_record_review_status_retained=True,
                      freeze_manifest_sha256=sha(freeze_bytes), review=freeze['review'])
        result['warnings'] = ['User-assisted approval is recorded; automatic checks do not independently '
                              'certify semantics, exhaustive alternatives or holdout independence']
    result['benchmark_manifest_sha256'] = sha((directory/'manifest.json').read_bytes())
    return result
