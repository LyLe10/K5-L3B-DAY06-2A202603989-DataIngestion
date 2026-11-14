"""Runner tests use only temporary synthetic benchmark bundles and fake backends."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import hashlib
import json
import pytest

from starter.src.evaluation_runner import (DEFAULT_CONFIG,QueryProducer,approval_gate,load_benchmark,
    run_evaluation,write_artifacts,redact,digest,validate_config,export_trace,verify_exported_trace)
from starter.src.evaluation import METRIC_VERSION
from starter.tests.test_benchmark import sample,bundle,frozen_bundle
from starter.tests.test_store import profile

IDENTITY=dict(code_revision='a'*40,dirty=True,source_hashes={'synthetic.py':'b'*64},evaluator_sha256='c'*64)

def approval(freeze,config):
    return dict(approval_version=1,approved=True,split='test',freeze_sha256=freeze,
        evaluator_sha256=IDENTITY['evaluator_sha256'],config_sha256=digest(config),selected_strategy=config['selected_strategy'],
        reviewer='synthetic supplied approver',rationale='Synthetic fixture approval, not actual holdout permission')

class Adapter:
    def __init__(self,profile,path):
        self.profile,self.profile_id,self._cache_dir=profile,profile.profile_id,Path(path)
        self._stats=dict(token_lengths=[],cache_hits=0,encoded_inputs=0)
        self.calls=[]
    @property
    def stats(self):return deepcopy(self._stats)
    def embed_query(self,question):
        self.calls.append(question)
        self._stats['token_lengths'].append(10)
        self._stats['encoded_inputs']+=1
        vector=[0.0]*384;vector[(len(self.calls)-1)%384]=1.0
        return vector

@pytest.fixture
def setup(frozen_bundle,profile,tmp_path):
    root,folder,corpus=frozen_bundle
    config=deepcopy(DEFAULT_CONFIG)
    loaded=load_benchmark(folder,'dev',config=config,identity=IDENTITY,root=root,corpus=corpus)
    cache=tmp_path/'stage5-query-cache'
    adapter=Adapter(profile,cache)
    producer=QueryProducer(adapter,profile,cache)
    snapshots=tuple(SimpleNamespace(snapshot_id=s*64,manifest_sha256=corpus.manifest_sha256,corpus_sha256='d'*64) for s in ('a','b'))
    baseline=SimpleNamespace(dataset_id='synthetic-runner',profile_id=profile.profile_id,snapshots=snapshots,
                             descriptor_hashes=('e'*64,'f'*64),validate_approved_identity=lambda:None)
    state=SimpleNamespace(active=False,opens=0,closes=0,searches=[],fail_at=None,empty=False)
    by_index=loaded['questions']
    pages={(p.document_id,p.page):p for p in corpus.pages}
    class Session:
        integrity=('STRUCTURAL_INTEGRITY_VERIFIED','VECTOR_INTEGRITY_NOT_REVERIFIED')
        def __init__(self):self.snapshots=snapshots
        def search(self,strategy,vector,top_k,filters):
            assert state.active and len(adapter.calls)==15  # all embedding before transaction
            state.searches.append((strategy,id(vector),filters))
            if state.fail_at==len(state.searches):raise RuntimeError('postgresql://fixture:DO_NOT_EXPORT@private/secret')
            if state.empty:return []
            i=vector.index(1.0);q=by_index[i];p=pages[(q['gold_source_id'],q['gold_page'])]
            sha=lambda t:hashlib.sha256(t.encode()).hexdigest()
            return [dict(rank=1,chunk_id=('A' if strategy=='A' else 'B')+':'+str(i),
                document_id=p.document_id,physical_page=p.page,source=p.source,section=p.metadata['section'],
                start_char=0,end_char=len(p.text),text=p.text,text_sha256=sha(p.text),
                source_sha256=corpus.sources[0]['sha256'],page_text_sha256=p.metadata['text_sha256'],
                printed_page_label=None,page_id='synthetic-page',metadata=dict(source_id=p.document_id,
                    physical_page=p.page,section=p.metadata['section']),
                snapshot_id=snapshots[0 if strategy=='A' else 1].snapshot_id,
                manifest_sha256=corpus.manifest_sha256,corpus_sha256='d'*64,dataset_id=baseline.dataset_id,
                profile_id=profile.profile_id,stored_strategy='B' if strategy=='C' else strategy,
                requested_strategy=strategy,cosine_distance=0.0,score=1.0,
                embedding=[1.0]*384,unexpected_secret='DO_NOT_EXPORT')]
    class Store:
        dataset_id=baseline.dataset_id
        profile_id=profile.profile_id
        @contextmanager
        def retrieval_session(self,**kwargs):
            assert len(adapter.calls)==15
            assert kwargs['baseline'] is baseline and kwargs['deadline_seconds']==config['deadline_seconds']
            state.active=True;state.opens+=1
            try:yield Session()
            finally:state.active=False;state.closes+=1
    return SimpleNamespace(root=root,folder=folder,corpus=corpus,config=config,loaded=loaded,adapter=adapter,
        producer=producer,baseline=baseline,state=state,store=Store(),cache=cache)

def run(s,**kwargs):
    return run_evaluation(s.loaded,store=s.store,producer=s.producer,baseline=s.baseline,
        config=s.config,identity=IDENTITY,backend_identity=dict(postgresql='16.16',pgvector='0.8.7',
        migration_checksum='a'*64,catalog_fingerprint='b'*64,verification='SYNTHETIC_FIXTURE'),**kwargs)

def test_loading_split_isolation(setup):
    s=setup
    assert len(s.loaded['questions'])==15 and all(q['split']=='dev' for q in s.loaded['questions'])
    assert all(q['gold_source_id']=='synthetic' for q in s.loaded['questions'])
    with pytest.raises(ValueError,match='approval'):
        load_benchmark(s.folder,'test',config=s.config,identity=IDENTITY,root=s.root,corpus=s.corpus)

def test_test_plan_metadata_is_not_execution_authorization(setup):
    s=setup;config=dict(s.config,selected_strategy='B');a=approval(s.loaded['freeze_sha256'],config)
    b=load_benchmark(s.folder,'test',config=config,identity=IDENTITY,approval=a,root=s.root,corpus=s.corpus)
    assert len(b['questions'])==5 and all(q['split']=='test' for q in b['questions'])
    with pytest.raises(PermissionError,match='TEST_EXECUTION_BLOCKED'):
        run_evaluation(b,store=s.store,producer=s.producer,baseline=s.baseline,
                       config=config,identity=IDENTITY,backend_identity={})
    assert s.state.opens==0 and s.adapter.calls==[]

@pytest.mark.parametrize('field,value',[('approved',False),('freeze_sha256','f'*64),
    ('evaluator_sha256','e'*64),('config_sha256','d'*64),('selected_strategy','A'),('reviewer','')])
def test_approval_cannot_be_bypassed(setup,field,value):
    config=dict(setup.config,selected_strategy='B');a=approval(setup.loaded['freeze_sha256'],config);a[field]=value
    with pytest.raises(ValueError):approval_gate('test',a,setup.loaded['freeze_sha256'],IDENTITY['evaluator_sha256'],config)

@pytest.mark.parametrize('name',['dev.jsonl','test.jsonl','freeze_manifest.json'])
def test_frozen_tamper_rejected(setup,name):
    s=setup;p=s.folder/name;p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(ValueError):load_benchmark(s.folder,'dev',config=s.config,identity=IDENTITY,root=s.root,corpus=s.corpus)

def test_draft_not_executable(bundle):
    root,folder,corpus=bundle
    with pytest.raises(ValueError,match='frozen'):
        load_benchmark(folder,'dev',config=DEFAULT_CONFIG,identity=IDENTITY,root=root,corpus=corpus)

def test_complete_run_same_vectors_gold_separation_and_no_payload(setup):
    s=setup;out=run(s)
    assert out['status']=='COMPLETE' and out['error'] is None
    assert len(out['traces'])==45 and len(out['receipts'])==15
    assert s.state.opens==s.state.closes==1 and not s.state.active
    for i in range(15):
        calls=s.state.searches[i*3:i*3+3]
        assert [c[0] for c in calls]==['A','B','C'] and len({c[1] for c in calls})==1
        assert calls[0][2] is None and calls[1][2] is None
    assert all(not t.startswith('query: ') for t in s.adapter.calls)
    assert [r['question_id'] for r in out['receipts']]==[q['id'] for q in s.loaded['questions']]
    assert 'DO_NOT_EXPORT' not in json.dumps(out) and '"embedding"' not in json.dumps(out)
    assert all(t['trace_sha256'] for t in out['traces'])
    assert len(out['summary']['groups'])==3

@pytest.mark.parametrize('position',[1,5,45])
def test_backend_errors_partial_no_retry(setup,position):
    s=setup;s.state.fail_at=position;out=run(s)
    assert out['status']=='INCOMPLETE' and out['summary'] is None
    assert len(out['traces'])==position and s.state.opens==s.state.closes==1
    assert len(s.state.searches)==position and not s.state.active
    assert 'DO_NOT_EXPORT' not in json.dumps(out)

def test_empty_results_are_misses_not_filter_violations(setup):
    s=setup;s.state.empty=True;out=run(s)
    assert out['status']=='COMPLETE'
    for g in out['summary']['groups']:
        assert g['questions']==15 and g['exact_evidence_hit_at_3']['numerator']==0
        assert g['empty_results']['rate']==1 and g['filter_diagnostics']['violations']==0
        assert g['filter_diagnostics']['compliance'] is None

def test_receipt_order_mismatch_stops_before_session(setup,monkeypatch):
    s=setup;real=s.producer.prepare
    def wrong(q):
        v,r=real(q);return v,list(reversed(r))
    monkeypatch.setattr(s.producer,'prepare',wrong)
    out=run(s);assert out['status']=='INCOMPLETE' and s.state.opens==0

def test_bad_source_text_is_not_a_quality_miss(setup,monkeypatch):
    import starter.src.evaluation_runner as module
    monkeypatch.setattr(module,'validate_hits',Mock(side_effect=ValueError('fixture corruption')))
    out=run(setup);assert out['status']=='INCOMPLETE' and out['summary'] is None

def test_wrapper_profile_and_cache_guards(setup):
    s=setup;s.adapter.profile_id='0'*64
    with pytest.raises(ValueError):QueryProducer(s.adapter,s.producer.profile,s.cache)
    s.adapter.profile_id=s.producer.profile.profile_id
    with pytest.raises(ValueError):QueryProducer(s.adapter,s.producer.profile,s.cache/'different')

def test_wrapper_token_overflow_prevents_retrieval(setup,monkeypatch):
    s=setup;real=s.adapter.embed_query
    def overflow(q):
        v=real(q);s.adapter._stats['token_lengths'][-1]=513;return v
    monkeypatch.setattr(s.adapter,'embed_query',overflow)
    out=run(s);assert out['status']=='INCOMPLETE' and s.state.opens==0

def test_wrapper_bad_vector_prevents_retrieval(setup,monkeypatch):
    monkeypatch.setattr(setup.adapter,'embed_query',lambda q:[0.0]*384)
    assert run(setup)['status']=='INCOMPLETE' and setup.state.opens==0

def test_receipt_hash_and_no_raw_vectors(setup):
    s=setup;out=run(s);r=out['receipts'][0];q=s.loaded['questions'][0]
    assert r['input_sha256']==hashlib.sha256(('query: '+q['question']).encode()).hexdigest()
    assert r['token_count']==10 and r['producer_profile_id']==s.producer.profile.profile_id
    assert 'vector' not in r and len(r['vector_sha256'])==64

def test_artifacts_no_overwrite_and_redaction(setup,tmp_path):
    out=run(setup);out['debug']=dict(password='DO_NOT_EXPORT',database_url='postgresql://fixture:DO_NOT_EXPORT@host/db',
        path='C:/Users/Private/secret',vector=[1]*384)
    directory=tmp_path/'run'
    write_artifacts(out,directory)
    raw=(directory/'run.json').read_text();assert 'DO_NOT_EXPORT' not in raw and 'Private' not in raw
    assert '"vector"' not in raw and 'vector_sha256' in raw
    assert json.loads(raw)['publication_redacted']
    with pytest.raises(FileExistsError):write_artifacts(out,directory)


def test_loaded_records_cannot_change_before_execution(setup):
    setup.loaded['questions'][0]['expected_answer']='Changed fixture gold'
    with pytest.raises(ValueError,match='split execution'):
        run(setup)
    assert setup.state.opens==0 and not setup.adapter.calls


def test_run_deadline_keeps_partial_and_closes_session(setup,monkeypatch):
    import time
    s=setup;s.config['deadline_seconds']=.01
    original=s.store.retrieval_session
    @contextmanager
    def slow_session(**kwargs):
        with original(**kwargs) as session:
            search=session.search
            def slow(*args,**kw):
                time.sleep(.03)
                return search(*args,**kw)
            session.search=slow
            yield session
    monkeypatch.setattr(s.store,'retrieval_session',slow_session)
    out=run(s)
    assert out['status']=='INCOMPLETE' and out['summary'] is None
    assert len(out['traces'])==1 and s.state.opens==s.state.closes==1


def test_no_gold_reaches_producer(setup,monkeypatch):
    s=setup;real=s.producer.prepare
    def checked(rows):
        assert all(set(q)=={'id','question','filter'} for q in rows)
        return real(rows)
    monkeypatch.setattr(s.producer,'prepare',checked)
    assert run(s)['status']=='COMPLETE'


def test_backend_unavailable_no_reconnect(setup,monkeypatch):
    unavailable=Mock(side_effect=RuntimeError('credential-bearing exception not exported'))
    monkeypatch.setattr(setup.store,'retrieval_session',unavailable)
    out=run(setup)
    assert out['status']=='INCOMPLETE' and not out['traces'] and out['summary'] is None
    unavailable.assert_called_once()
    assert 'credential-bearing' not in json.dumps(out)


@pytest.mark.parametrize('field,value',[('deadline_seconds',True),('deadline_seconds',float('inf')),
    ('deadline_seconds',0),('top_k',True),('top_k',4),('strategies',['C']),('config_version',True)])
def test_invalid_config(field,value):
    config=deepcopy(DEFAULT_CONFIG);config[field]=value
    with pytest.raises(ValueError):validate_config(config)


def test_sensitive_strings_and_nested_payload_are_redacted():
    obj=dict(note='password=DO_NOT_EXPORT Bearer DO_NOT_EXPORT',access_token='DO_NOT_EXPORT',
             nested={'embeddings':[[1.0]*384]},vector_sha256='a'*64)
    safe=redact(obj)
    assert 'DO_NOT_EXPORT' not in json.dumps(safe)
    assert safe['nested']=={} and safe['vector_sha256']=='a'*64


def test_cli_help_has_no_execution_or_approval_bypass():
    import subprocess,sys
    root=Path(__file__).resolve().parents[2]
    help_text=subprocess.check_output([sys.executable,'-B',str(root/'starter/scripts/run_evaluation.py'),'--help'],text=True)
    assert '--force' not in help_text and '--approve-test' not in help_text
    assert 'execution is not enabled' in help_text


def test_partial_traces_persist_without_retry(setup,tmp_path):
    setup.state.fail_at=5
    path=tmp_path/'partial-run'
    result=run(setup,output_directory=path)
    saved=json.loads((path/'run.json').read_text())
    assert result['status']==saved['status']=='INCOMPLETE'
    assert len(saved['traces'])==5 and saved['summary'] is None
    assert saved['manifest']['retrieved']==4 and saved['manifest']['failed']==1
    assert setup.state.opens==setup.state.closes==1


def test_raw_and_exported_hashes_survive_redaction_and_detect_tampering():
    from starter.src.evaluation import trace_identity
    raw=dict(question_id='synthetic',note='password=DO_NOT_EXPORT',embedding=[1]*384,
             hits=[dict(text='Synthetic evidence')])
    raw['raw_trace_sha256']=trace_identity(raw)
    raw['trace_sha256']=raw['raw_trace_sha256']
    before=deepcopy(raw)
    exported=export_trace(raw)
    assert raw==before and 'DO_NOT_EXPORT' not in json.dumps(exported)
    assert 'embedding' not in exported and 'trace_sha256' not in exported
    assert exported['raw_trace_sha256']==raw['raw_trace_sha256']
    assert exported['exported_trace_sha256']!=raw['raw_trace_sha256']
    assert verify_exported_trace(exported) and verify_exported_trace(exported,raw)
    tampered=deepcopy(exported);tampered['hits'][0]['text']='Changed'
    assert not verify_exported_trace(tampered)
    wrong_raw=deepcopy(raw);wrong_raw['question_id']='other'
    with pytest.raises(ValueError,match='Raw trace'):
        verify_exported_trace(exported,wrong_raw)


def test_canonical_export_identity_independent_of_key_order():
    a=export_trace(dict(question_id='fixture',hits=[],status='SUCCESS'))
    b=export_trace(dict(status='SUCCESS',hits=[],question_id='fixture'))
    assert a==b and verify_exported_trace(json.loads(json.dumps(a)))
