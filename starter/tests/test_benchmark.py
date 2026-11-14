"""Synthetic fixtures only: no retrieval, model, database or real gold approval."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from starter.src.benchmark import validate_records, validate_benchmark, sha
from starter.src.models import DocumentPage

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT/'benchmark/question.schema.json').read_text())


@pytest.fixture
def sample():
    pages = []
    for i in range(1, 41):
        text = f'Synthetic English evidence for unit fixture number {i}, not corpus or evaluation evidence.'
        pages.append(DocumentPage('synthetic', 'synthetic://unit-fixture', i, text,
            dict(text_sha256=sha(text.encode()), section='Data Definition')))
    corpus = SimpleNamespace(pages=pages, sources=[dict(source_id='synthetic', sha256='a'*64)],
                             manifest_sha256=sha(b'{}'))
    rows = []
    for i, p in enumerate(pages[:20]):
        split = 'dev' if i < 15 else 'test'
        rows.append(dict(id=f'pg16-{"d" if i<15 else "t"}{i+1:02}', split=split, language='en',
            question=f'Which synthetic requirement applies to fixture number {i+1}?',
            expected_answer='The synthetic fixture requirement applies; this is not real gold.',
            gold_source_id='synthetic', gold_page=p.page, evidence_quote=p.text,
            evidence_start_char=0, evidence_end_char=len(p.text), source_sha256='a'*64,
            page_text_sha256=p.metadata['text_sha256'], category='direct', topic='synthetic',
            gold_alternatives=[], review_status='NEEDS_HUMAN_REVIEW', reviewer=None,
            review_notes='Synthetic fixture, never submitted as real gold.'))
    for i in (0, 1, 15):
        rows[i].update(filter={'section':'Data Definition'}, filter_context='User scope: Data Definition',
                       filter_rationale='Explicit synthetic user context')
        rows[i]['question'] = 'Within Data Definition, '+rows[i]['question']
    return rows, corpus


def check(sample):
    return validate_records(*sample, SCHEMA)


def test_valid_draft_never_certifies_semantics(sample):
    r=check(sample)
    assert r['structural_source_valid'] and len(r['needs_human_review'])==20
    assert not r['human_approved'] and not r['frozen'] and not r['retrieval_executed']
    assert r['semantic_gold_correctness']=='NOT_CERTIFIED'


@pytest.mark.parametrize('field', SCHEMA['required'])
def test_required_fields(sample, field):
    del sample[0][0][field]
    assert not check(sample)['structural_source_valid']


@pytest.mark.parametrize('field,value', [
    ('id','pg16-d02'), ('split','test'), ('language','vi'),
    ('question','C\u00e2u h\u1ecfi ti\u1ebfng Vi\u1ec7t'),
    ('expected_answer','Tr\u1ea3 l\u1eddi b\u1eb1ng ti\u1ebfng Vi\u1ec7t'),
    ('gold_source_id','unknown'), ('gold_page',99), ('gold_page',True),
    ('source_sha256','b'*64), ('page_text_sha256','b'*64),
    ('evidence_quote',''), ('evidence_quote','A fabricated quote that is absent from the synthetic source.'),
    ('evidence_start_char',1), ('evidence_end_char',9999),
    ('review_status','HUMAN_APPROVED'), ('reviewer','Invented reviewer'),
])
def test_invalid_fields(sample,field,value):
    sample[0][0][field]=value
    assert not check(sample)['structural_source_valid']


def test_exact_duplicate_question_rejected(sample):
    sample[0][2]['question']=sample[0][3]['question']
    assert any('duplicate question text' in e for e in check(sample)['errors'])


def test_near_duplicate_warning(sample):
    r=check(sample)
    assert any('Near-duplicate' in w for w in r['warnings'])


def test_wrong_split_count(sample):
    sample[0][2]['split']='test'
    assert any('15 dev / 5 test' in e for e in check(sample)['errors'])


def test_missing_question(sample):
    sample[0].pop()
    assert not check(sample)['structural_source_valid']


def test_filter_quota(sample):
    for k in ['filter','filter_context','filter_rationale']:sample[0][15].pop(k)
    assert any('>=3 filters' in e for e in check(sample)['errors'])


@pytest.mark.parametrize('mutation', ['context','question','section','key','rationale'])
def test_filter_provenance_and_scope(sample,mutation):
    q=sample[0][0]
    if mutation=='context':q['filter_context']='No scope was supplied'
    if mutation=='question':q['question']='Which synthetic requirement is applicable here?'
    if mutation=='section':q['filter']['section']='Data Manipulation'
    if mutation=='key':q['filter']={'gold_source_id':'synthetic'}
    if mutation=='rationale':del q['filter_rationale']
    assert not check(sample)['structural_source_valid']


def alternate(sample):
    p=sample[1].pages[20]
    return dict(gold_source_id=p.document_id,gold_page=p.page,evidence_quote=p.text,
                evidence_start_char=0,evidence_end_char=len(p.text),source_sha256='a'*64,
                page_text_sha256=p.metadata['text_sha256'])


def test_alternative_verified_independently(sample):
    sample[0][0]['gold_alternatives']=[alternate(sample)]
    assert check(sample)['structural_source_valid']


@pytest.mark.parametrize('field,value', [('gold_page',99),('source_sha256','b'*64),
                                      ('evidence_start_char',1),('evidence_quote','Missing source words')])
def test_invalid_alternatives(sample,field,value):
    a=alternate(sample);a[field]=value;sample[0][0]['gold_alternatives']=[a]
    assert not check(sample)['structural_source_valid']


def test_duplicate_alternative_rejected(sample):
    a=alternate(sample);sample[0][0]['gold_alternatives']=[a,deepcopy(a)]
    assert any('duplicate gold' in e for e in check(sample)['errors'])


def test_ambiguous_quote_flagged_for_review(sample):
    q=sample[0][0];p=sample[1].pages[0]
    p.text+=' '+p.text;p.metadata['text_sha256']=q['page_text_sha256']=sha(p.text.encode())
    assert any('quote repeats' in w for w in check(sample)['warnings'])


def test_cross_split_source_overlap_warns(sample):
    source=sample[0][3];target=sample[0][16]
    for k in ['gold_page','evidence_quote','evidence_start_char','evidence_end_char','page_text_sha256']:
        target[k]=source[k]
    assert any('Cross-split page overlap' in w for w in check(sample)['warnings'])


@pytest.fixture
def bundle(tmp_path,sample):
    rows,corpus=sample;folder=tmp_path/'benchmark';folder.mkdir();(tmp_path/'data').mkdir()
    (tmp_path/'data/manifest.json').write_bytes(b'{}')
    schema=(ROOT/'benchmark/question.schema.json').read_bytes();(folder/'question.schema.json').write_bytes(schema)
    (folder/'NOTICE.txt').write_bytes(b'Synthetic fixture notice')
    files={}
    for split in ('dev','test'):
        selected=[q for q in rows if q['split']==split]
        data=''.join(json.dumps(q)+'\n' for q in selected).encode();(folder/(split+'.jsonl')).write_bytes(data)
        files[split+'.jsonl']=dict(sha256=sha(data),count=len(selected))
    m=dict(schema_version=1,language='en',freeze_status='DRAFT_NOT_FROZEN',human_approval_recorded=False,
        retrieval_executed=False,quality_metrics_computed=False,corpus_manifest_sha256=sha(b'{}'),
        schema_sha256=sha(schema),notice_sha256=sha(b'Synthetic fixture notice'),files=files)
    (folder/'manifest.json').write_text(json.dumps(m))
    return tmp_path,folder,corpus


def test_bundle_integrity(bundle):
    root,folder,corpus=bundle
    assert validate_benchmark(folder,root=root,corpus=corpus)['structural_source_valid']


@pytest.mark.parametrize('name',['dev.jsonl','test.jsonl','question.schema.json','NOTICE.txt'])
def test_tampering_is_not_repaired(bundle,name):
    root,folder,corpus=bundle;p=folder/name;raw=p.read_bytes()+b' ';p.write_bytes(raw)
    with pytest.raises(ValueError):validate_benchmark(folder,root=root,corpus=corpus)
    assert p.read_bytes()==raw


def test_wrong_corpus_snapshot_rejected(bundle):
    root,folder,corpus=bundle;(root/'data/manifest.json').write_bytes(b'{"changed":true}')
    with pytest.raises(ValueError,match='Corpus manifest'):validate_benchmark(folder,root=root,corpus=corpus)


@pytest.mark.parametrize('key,value',[('freeze_status','FROZEN'),('language','vi'),
    ('human_approval_recorded',True),('retrieval_executed',True),('quality_metrics_computed',True)])
def test_draft_gate(bundle,key,value):
    root,folder,corpus=bundle;p=folder/'manifest.json';m=json.loads(p.read_text());m[key]=value;p.write_text(json.dumps(m))
    with pytest.raises(ValueError):validate_benchmark(folder,root=root,corpus=corpus)


@pytest.fixture
def frozen_bundle(bundle):
    root, folder, corpus = bundle
    words = ['amber aurora climate', 'cobalt river vessel', 'ivory meadow harvest',
             'bronze canyon compass', 'violet island orchard', 'silver desert lantern',
             'crimson forest compass', 'golden glacier meadow', 'indigo mountain shelter',
             'scarlet harbor voyage', 'copper valley blossom', 'emerald prairie summit',
             'azure rainfall pebble', 'ochre waterfall tunnel', 'coral sunrise basket',
             'ruby tundra horizon', 'saffron delta festival', 'jade peninsula waterfall',
             'magenta ocean terrace', 'beige savannah pottery']
    rows = []
    for name in ('dev.jsonl','test.jsonl'):
        for q in map(json.loads,(folder/name).read_text().splitlines()):
            q['question'] = ('Within Data Definition, ' if q.get('filter') else '') + words[len(rows)]+'?'
            rows.append(q)
    m=json.loads((folder/'manifest.json').read_text())
    for split in ('dev','test'):
        data=''.join(json.dumps(q)+'\n' for q in rows if q['split']==split).encode()
        (folder/(split+'.jsonl')).write_bytes(data);m['files'][split+'.jsonl']['sha256']=sha(data)
    result=validate_records(rows,corpus,SCHEMA)
    assert result['structural_source_valid'] and len(result['warnings'])==1
    f=dict(freeze_schema_version=1,question_schema_version=1,freeze_status='FROZEN',
        files=m['files'],schema_sha256=m['schema_sha256'],corpus_manifest_sha256=m['corpus_manifest_sha256'],
        notice_sha256=m['notice_sha256'],source_checksums={s['source_id']:s['sha256'] for s in corpus.sources},
        selected_pages=sorted([p.document_id,p.page,p.metadata['text_sha256']] for p in corpus.pages),
        counts=result['counts'],approved_question_ids=sorted(q['id'] for q in rows),
        holdout_rule='NO_TEST_ADJUSTMENT_FROM_RETRIEVAL_RESULTS',
        review=dict(reviewer='user-assisted review',ai_assisted=True,independent_verification_claimed=False,
                    approval_basis='Synthetic unit fixture, not actual benchmark approval'))
    raw=(json.dumps(f)+'\n').encode();(folder/'freeze_manifest.json').write_bytes(raw)
    m.update(freeze_status='FROZEN',human_approval_recorded=True,freeze_manifest_sha256=sha(raw))
    (folder/'manifest.json').write_text(json.dumps(m))
    return root,folder,corpus


def test_frozen_approval_is_recorded_not_independently_certified(frozen_bundle):
    root,folder,corpus=frozen_bundle;r=validate_benchmark(folder,root=root,corpus=corpus)
    assert r['frozen'] and r['human_approved'] and not r['needs_human_review']
    assert r['semantic_gold_correctness']=='USER_ASSISTED_REVIEW_RECORDED_NOT_INDEPENDENTLY_CERTIFIED'


@pytest.mark.parametrize('field,value', [('files',{}),('schema_sha256','b'*64),('source_checksums',{}),
    ('selected_pages',[]),('counts',{}),('approved_question_ids',[]),('holdout_rule','REUSE_TEST_FOR_TUNING'),
    ('review',{'reviewer':'invented','ai_assisted':False}),('question_schema_version',2)])
def test_freeze_binding_cannot_be_changed(frozen_bundle,field,value):
    root,folder,corpus=frozen_bundle;fpath=folder/'freeze_manifest.json';f=json.loads(fpath.read_text());f[field]=value
    raw=json.dumps(f).encode();fpath.write_bytes(raw)
    mpath=folder/'manifest.json';m=json.loads(mpath.read_text());m['freeze_manifest_sha256']=sha(raw);mpath.write_text(json.dumps(m))
    with pytest.raises(ValueError):validate_benchmark(folder,root=root,corpus=corpus)


def test_freeze_checksum_tampering_is_not_repaired(frozen_bundle):
    root,folder,corpus=frozen_bundle;p=folder/'freeze_manifest.json';raw=p.read_bytes()+b' ';p.write_bytes(raw)
    with pytest.raises(ValueError,match='Freeze manifest checksum'):validate_benchmark(folder,root=root,corpus=corpus)
    assert p.read_bytes()==raw
