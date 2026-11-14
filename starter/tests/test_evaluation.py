"""Synthetic evidence/metric/adjudication tests, never actual benchmark scores."""
from copy import deepcopy
import hashlib
import pytest
from starter.src.evaluation import (evaluate_query,summarize,adjudicate,digest,
                                    trace_identity,manual_review_template,validate_hits)

def sha(text): return hashlib.sha256(text.encode()).hexdigest()

@pytest.fixture
def example():
    text='Before. Exact evidence sentence. After.'
    quote='Exact evidence sentence.'
    start=text.index(quote)
    q=dict(id='synthetic-q',split='dev',gold_source_id='doc',gold_page=7,
           source_sha256='a'*64,page_text_sha256=sha(text),evidence_quote=quote,
           evidence_start_char=start,evidence_end_char=start+len(quote),gold_alternatives=[])
    h=dict(rank=1,chunk_id='synthetic-1',document_id='doc',physical_page=7,
           source_sha256='a'*64,page_text_sha256=sha(text),start_char=0,end_char=len(text),
           text=text,text_sha256=sha(text),section='scope')
    return q,h

def test_exact_metrics(example):
    q,h=example;e=evaluate_query(q,[h])
    assert (e['exact_hit_at_1'],e['exact_evidence_hit_at_3'],e['mrr_at_3'])==(1,1,1)
    assert e['diagnostics'][0]['alternatives'][0]['exact_match']

@pytest.mark.parametrize('field,value',[('document_id','other'),('physical_page',8),
    ('source_sha256','b'*64),('page_text_sha256','c'*64),('text_sha256','f'*64)])
def test_not_page_only_or_checksum_match(example,field,value):
    q,h=example;h[field]=value
    assert evaluate_query(q,[h])['exact_evidence_hit_at_3']==0

def test_page_only_and_partial_span(example):
    q,h=example
    h.update(text='Before.',start_char=0,end_char=7,text_sha256=sha('Before.'))
    assert evaluate_query(q,[h])['exact_hit_at_1']==0

def test_wrong_quote_not_fuzzy(example):
    q,h=example;q['evidence_quote']=q['evidence_quote'].lower()
    assert evaluate_query(q,[h])['exact_hit_at_1']==0

def test_split_evidence_is_not_single_chunk_hit(example):
    q,h=example;middle=q['evidence_start_char']+5
    left=deepcopy(h);left.update(text=h['text'][:middle],end_char=middle)
    right=deepcopy(h);right.update(rank=2,chunk_id='synthetic-2',text=h['text'][middle:],start_char=middle)
    for hit in (left,right):hit['text_sha256']=sha(hit['text'])
    assert evaluate_query(q,[left,right])['exact_evidence_hit_at_3']==0

def test_alternative_is_or_not_and(example):
    q,h=example
    alternative={k:v for k,v in q.items() if k not in ('id','split','gold_alternatives')}
    q['gold_page']=99;q['gold_alternatives']=[alternative]
    e=evaluate_query(q,[h]);assert e['exact_hit_at_1']==1
    assert e['diagnostics'][0]['alternatives'][1]['exact_match']

@pytest.mark.parametrize('rank',[1,2,3])
def test_mrr_ranks(example,rank):
    q,h=example;hits=[]
    for i in range(1,rank+1):
        item=deepcopy(h);item.update(rank=i,chunk_id=f'synthetic-{i}')
        if i!=rank:item['physical_page']=99
        hits.append(item)
    e=evaluate_query(q,hits)
    assert e['mrr_at_3']==pytest.approx(1/rank)
    assert e['exact_hit_at_1']==int(rank==1)

@pytest.mark.parametrize('section,expected',[('scope','COMPLIANT'),('other','VIOLATION')])
def test_filter_nonempty(example,section,expected):
    q,h=example;q['filter']={'section':'scope'};h['section']=section
    assert evaluate_query(q,[h])['filter_compliance']==expected

def test_empty_filter_not_violation_or_compliant(example):
    q,h=example;q['filter']={'section':'scope'}
    e=evaluate_query(q,[])
    assert e['filter_compliance']=='NOT_APPLICABLE' and e['mrr_at_3']==0
    rows=[dict(question_id=q['id'],split='dev',strategy='C',status='SUCCESS',evaluation=e)]
    g=summarize(rows)['groups'][0]
    assert g['exact_hit_at_1']['denominator']==1 and g['empty_results']['rate']==1
    assert g['filter_diagnostics']['nonempty_denominator']==0
    assert g['filter_diagnostics']['compliance'] is None
    assert g['filter_diagnostics']['violations']==0

def test_summary_denominator_and_groups(example):
    q,h=example;yes=evaluate_query(q,[h]);no=evaluate_query(q,[])
    rows=[dict(question_id=str(i),split=split,strategy=s,status='SUCCESS',evaluation=e)
          for split in ('dev','test') for s in ('A','B','C') for i,e in enumerate((yes,no))]
    groups=summarize(rows)['groups'];assert len(groups)==6
    assert all(g['exact_evidence_hit_at_3']==dict(numerator=1,denominator=2,rate=.5) for g in groups)

@pytest.mark.parametrize('bad',['duplicate','failed'])
def test_reject_bad_summary(example,bad):
    q,h=example;t=dict(question_id=q['id'],split='dev',strategy='A',status='SUCCESS',evaluation=evaluate_query(q,[h]))
    rows=[t,t] if bad=='duplicate' else [dict(t,status='FAILED')]
    with pytest.raises(ValueError):summarize(rows)

def test_adjudication_separate_and_exact_immutable(example):
    q,h=example;h['physical_page']=99
    trace=dict(question_id=q['id'],split='dev',strategy='A',status='SUCCESS',hits=[h],evaluation=evaluate_query(q,[h]))
    trace['trace_sha256']=trace_identity(trace);before=deepcopy(trace)
    decision=dict(trace_sha256=trace['trace_sha256'],rank=1,relevant=True,reviewer='synthetic supplied reviewer',rationale='fixture judgement only')
    result=adjudicate([trace],[decision])
    assert trace==before and trace['evaluation']['exact_hit_at_1']==0
    assert result['metrics']['groups'][0]['adjudicated_hit_at_1']['rate']==1
    assert 'exact_hit_at_1' not in result['metrics']['groups'][0]
    diagnostic=result['diagnostics'][0]['ranks'][0]
    assert diagnostic['exact_match'] is False and diagnostic['adjudicated_relevant'] is True
    assert diagnostic['alternatives']==before['evaluation']['diagnostics'][0]['alternatives']


def test_adjudication_negative_does_not_change_exact_diagnostics(example):
    q,h=example
    t=dict(question_id=q['id'],split='dev',strategy='A',status='SUCCESS',hits=[h],evaluation=evaluate_query(q,[h]))
    before=deepcopy(t)
    d=dict(trace_sha256=trace_identity(t),rank=1,relevant=False,reviewer='fixture',rationale='fixture')
    result=adjudicate([t],[d])
    assert t==before and result['diagnostics'][0]['ranks'][0]['exact_match'] is True
    assert result['diagnostics'][0]['ranks'][0]['adjudicated_relevant'] is False
    assert result['metrics']['groups'][0]['adjudicated_hit_at_1']['rate']==0

@pytest.mark.parametrize('field,value',[('reviewer',''),('rationale',None),('trace_sha256','f'*64),('relevant',1),('rank',True)])
def test_adjudication_requires_bound_explicit_decision(example,field,value):
    q,h=example;t=dict(question_id=q['id'],split='dev',strategy='A',status='SUCCESS',hits=[h],evaluation=evaluate_query(q,[h]))
    decision=dict(trace_sha256=trace_identity(t),rank=1,relevant=True,reviewer='fixture',rationale='fixture')
    decision[field]=value
    with pytest.raises(ValueError):adjudicate([t],[decision])

def test_template_has_no_fabricated_labels():
    template=manual_review_template(['synthetic-t1'])
    assert len(template['coherence'])==30 and len(template['grounding'])==3
    for rows in template.values():
        for row in (rows if isinstance(rows,list) else [rows]):
            assert row.get('reviewer') is None and row.get('rationale') is None
            assert row.get('label') is None and row.get('conclusion') is None


def test_full_chunk_must_match_independent_page(example):
    from types import SimpleNamespace
    q,h=example
    page=SimpleNamespace(document_id='doc',page=7,text=h['text'],source='synthetic://fixture',
                         metadata=dict(text_sha256=h['page_text_sha256'],section='scope'))
    h.update(source=page.source,metadata=dict(source_id='doc',physical_page=7,section='scope'))
    pages={('doc',7):page};sources={'doc':{'sha256':'a'*64}}
    validate_hits([h],pages,sources)
    # Fabricated surrounding text preserves gold quote and recalculates its own
    # checksum, yet must fail independent-page verification.
    h['text']='Altered'+h['text'][7:];h['text_sha256']=sha(h['text'])
    with pytest.raises(ValueError,match='independent'):
        validate_hits([h],pages,sources)


def test_duplicate_adjudication_rejected(example):
    q,h=example;t=dict(question_id=q['id'],split='dev',strategy='A',status='SUCCESS',hits=[h],evaluation=evaluate_query(q,[h]))
    d=dict(trace_sha256=trace_identity(t),rank=1,relevant=False,reviewer='fixture',rationale='fixture')
    with pytest.raises(ValueError,match='Duplicate'):
        adjudicate([t],[d,d])
