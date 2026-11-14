"""Tiny synthetic artifacts/adapters only: no real model, tokenizer or benchmark."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import weakref
import gc
import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from starter.src import model_load_only as model, dev_bootstrap as boot, dev_authorization as auth
from starter.src import lab_dev_runtime as lab, database_probe
from starter.src.schema import EmbeddingProfile, canonical_json
from starter.src.evaluation import digest
from starter.tests.test_store import profile as template_profile
from starter.tests.test_lab_dev_runtime import SyntheticManualVerifier
from starter.tests.test_dev_authorization import _consume_then_crash


class FakeAdapter:
    def __init__(self,profile,cache):
        self.profile=profile;self.profile_id=profile.profile_id;self.dimensions=384;self._cache_dir=cache
        self.runtime=dict(device='cpu',dtype='float32',eval_mode=True,tokenizer_limit=512,sentence_transformers_limit=512)
        self.stats=dict(calls=0,inputs=0,encoded_inputs=0,encode_batches=0,token_lengths=[])
        self.embed_query=Mock(side_effect=AssertionError('Encoding forbidden'))
        self.embed_documents=Mock(side_effect=AssertionError('Encoding forbidden'))


@pytest.fixture
def setup_model(tmp_path,template_profile,monkeypatch):
    repo=Path(model.__file__).resolve().parents[2]
    for name in model.CODE_FILES:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((repo/name).read_bytes())
    contents={name:('Synthetic artifact only, not model weights: '+name).encode() for name in model.ARTIFACTS}
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in contents.items()}
    config=template_profile.config;config['artifact_sha256']=hashes
    profile=EmbeddingProfile.from_config(config)
    monkeypatch.setattr(model,'MODEL',config['model_name']);monkeypatch.setattr(model,'REVISION',config['revision'])
    monkeypatch.setattr(model,'ARTIFACTS',hashes);monkeypatch.setattr(boot,'STAGE4_PROFILE',profile.profile_id)
    evidence=tmp_path/'results/full_corpus_embedding_preflight.json';evidence.parent.mkdir()
    evidence.write_text(json.dumps(dict(passed=True,profile_id=profile.profile_id,profile=config)))
    snapshot=tmp_path/'data/local/models/intfloat--multilingual-e5-small'/config['revision']
    for name,data in contents.items():
        path=snapshot/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    request=model.model_load_request(root=tmp_path,run_id='synthetic-load',executor_id='synthetic-executor')
    authority=SyntheticManualVerifier();authority.scope=model.SCOPE
    adapter=FakeAdapter(profile,tmp_path/'data/local/stage5/embedding_cache')
    factory=Mock(return_value=adapter)
    kw=dict(root=tmp_path,run_id='synthetic-load',executor_id='synthetic-executor',request_canonical=request,
            approval=authority.issue(request),authority=authority,model_factory=factory)
    return SimpleNamespace(root=tmp_path,profile=profile,request=request,authority=authority,adapter=adapter,
                           factory=factory,kw=kw,snapshot=snapshot)


def audit_events(s):
    return [json.loads(p.read_text()) for p in sorted((s.root/'data/local/stage5/lab_audit/synthetic-load').glob('*.json'))]


def test_request_is_only_model_load_and_binds_ten_artifacts_and_code(setup_model):
    r=json.loads(setup_model.request)
    assert r['scope']==model.SCOPE and r['execution_mode']=='OFFLINE_SYNTHETIC'
    assert len(r['model']['profile']['artifact_sha256'])==10
    assert r['runtime']==dict(device='cpu',dtype='float32',eval_mode=True)
    assert set(r['code_hashes'])==set(model.CODE_FILES)
    assert r['model']['cache']=='data/local/stage5/embedding_cache'
    assert not {'question_ids','database','split','configuration'}&r.keys()
    assert model.verify_model_load_approval(setup_model.request,setup_model.kw['approval'],authority=setup_model.authority)


def test_verified_synthetic_load_never_encodes_or_connects(setup_model,monkeypatch):
    s=setup_model
    from starter.src import evaluation_runner, store
    forbidden=Mock(side_effect=AssertionError('Forbidden operation'))
    monkeypatch.setattr(evaluation_runner.QueryProducer,'prepare',forbidden)
    monkeypatch.setattr(evaluation_runner,'run_evaluation',forbidden)
    monkeypatch.setattr(store.PgVectorStore,'_connect',forbidden)
    monkeypatch.setattr(boot,'probe_database',forbidden)
    result=model.simulate_model_load_only(**s.kw)
    assert result['status']=='MODEL_LOAD_VERIFIED' and result['execution_mode']=='OFFLINE_SYNTHETIC'
    assert result['encoded_inputs']==0
    s.factory.assert_called_once_with(model.MODEL,revision=model.REVISION,snapshot_path=s.snapshot,
                                     cache_dir=s.root/'data/local/stage5/embedding_cache')
    s.adapter.embed_query.assert_not_called();s.adapter.embed_documents.assert_not_called();forbidden.assert_not_called()
    records=audit_events(s)
    assert records[-1]['status']=='MODEL_LOAD_VERIFIED'
    assert all(r['execution_mode']=='OFFLINE_SYNTHETIC' and r['profile_id']==s.profile.profile_id
               and r['model_name']==model.MODEL and r['model_revision']==model.REVISION
               and r['consumption_identity'] and r['request_sha256']==digest(json.loads(s.request)) for r in records)
    assert not (s.root/'data/local/stage5/embedding_cache').exists()


@pytest.mark.parametrize('bad',['missing','forged','expired','wrong_request','wrong_scope','self_approval'])
def test_approval_rejections_before_factory_and_ledger(setup_model,bad):
    s=setup_model
    if bad=='missing':s.kw['approval']=None
    elif bad=='forged':s.kw['approval']={'approved':True}
    elif bad=='expired':s.kw['approval']=s.authority.issue(s.request,expires_at=0)
    elif bad=='wrong_request':
        r=json.loads(s.request);r['run_id']='wrong';s.kw['request_canonical']=canonical_json(r)
        s.kw['approval']=s.authority.issue(s.kw['request_canonical'])
    elif bad=='wrong_scope':s.authority.scope=lab.LAB_SCOPE
    else:s.kw['approval']=s.authority.issue(s.request,reviewer='synthetic-executor')
    with pytest.raises(auth.AuthorizationError):model.simulate_model_load_only(**s.kw)
    s.factory.assert_not_called();assert not (s.root/'data/local/stage5/authorization').exists()


@pytest.mark.parametrize('change',['model','revision','artifact','profile','code','cache'])
def test_request_tampering_rejected_even_if_signed(setup_model,change):
    s=setup_model;r=json.loads(s.request)
    if change=='model':r['model']['model_name']='other/model'
    elif change=='revision':r['model']['revision']='0'*40
    elif change=='artifact':r['model']['profile']['artifact_sha256']['README.md']='0'*64
    elif change=='profile':r['profile_id']='0'*64
    elif change=='code':r['code_hashes']['starter/src/model_load_only.py']='0'*64
    else:r['model']['cache']='data/local/stage4/embedding_cache'
    s.kw['request_canonical']=canonical_json(r);s.kw['approval']=s.authority.issue(s.kw['request_canonical'])
    with pytest.raises(auth.AuthorizationError):model.simulate_model_load_only(**s.kw)
    s.factory.assert_not_called()


def test_claim_is_consumed_before_model_factory_and_duplicate_blocked(setup_model):
    s=setup_model
    decision=model.verify_model_load_approval(s.request,s.kw['approval'],authority=s.authority)
    def factory(*args,**kwargs):
        with pytest.raises(auth.AuthorizationError):auth.ConsumptionLedger(root=s.root).consume(s.request,decision.grant)
        assert audit_events(s)[0]['status']=='CONSUMED'
        return s.adapter
    s.factory.side_effect=factory
    model.simulate_model_load_only(**s.kw)
    with pytest.raises((auth.AuthorizationError,FileExistsError)):model.simulate_model_load_only(**s.kw)
    s.factory.assert_called_once()


@pytest.mark.parametrize('failure',['artifact','initialization','timeout','profile','cache','dtype','eval','dimension','encoding'])
def test_failures_are_classified_sanitized_and_never_retried(setup_model,failure):
    s=setup_model
    if failure=='artifact':(s.snapshot/'README.md').write_bytes(b'tampered')
    elif failure=='initialization':s.factory.side_effect=RuntimeError('password=DO_NOT_EXPORT')
    elif failure=='timeout':s.factory.side_effect=TimeoutError('DO_NOT_EXPORT')
    elif failure=='profile':s.adapter.profile_id='0'*64
    elif failure=='cache':s.adapter._cache_dir=s.root/'data/local/stage4/embedding_cache'
    elif failure=='dtype':s.adapter.runtime['dtype']='float16'
    elif failure=='eval':s.adapter.runtime['eval_mode']=False
    elif failure=='dimension':s.adapter.dimensions=385
    else:s.adapter.stats['encoded_inputs']=1
    expected=('ARTIFACT_MISMATCH' if failure=='artifact' else 'MODEL_LOAD_FAILED'
              if failure in ('initialization','timeout') else 'MODEL_PROFILE_MISMATCH')
    with pytest.raises(model.ModelLoadPreparationError) as error:model.simulate_model_load_only(**s.kw)
    assert error.value.status==expected
    records=audit_events(s);assert records[-1]['status']==expected
    assert 'DO_NOT_EXPORT' not in json.dumps(records) and 'password=' not in json.dumps(records)
    assert not any(k in records[-1] for k in ('exception','traceback','weights','vector','token','summary'))
    calls=s.factory.call_count
    with pytest.raises((auth.AuthorizationError,FileExistsError)):model.simulate_model_load_only(**s.kw)
    assert s.factory.call_count==calls


@pytest.mark.parametrize('point',['initial','stage','success','failure','corrupt'])
def test_audit_write_or_readback_failure_never_reports_success(setup_model,monkeypatch,point):
    s=setup_model;original=lab._LabAudit._write;calls=[]
    if point=='failure':s.factory.side_effect=RuntimeError('synthetic initialization failure')
    def write(self,status,**kwargs):
        calls.append(status)
        if ((point=='initial' and status=='CONSUMED') or (point=='stage' and status=='STAGE_STARTED')
                or (point=='success' and status=='MODEL_LOAD_VERIFIED') or (point=='failure' and status=='MODEL_LOAD_FAILED')):
            raise OSError('DO_NOT_EXPORT')
        receipt=original(self,status,**kwargs)
        if point=='corrupt':
            path=self.path/f'{self.sequence:04}.json';path.write_bytes(path.read_bytes()+b' ')
        return receipt
    monkeypatch.setattr(lab._LabAudit,'_write',write)
    with pytest.raises(model.ModelLoadPreparationError) as error:model.simulate_model_load_only(**s.kw)
    assert error.value.status=='AUDIT_WRITE_FAILED'
    if point in ('initial','stage','corrupt'):s.factory.assert_not_called()
    # Exactly one failed write attempt, never an automatic audit retry.
    assert len(calls)==len(set(calls)) if point in ('initial','stage','corrupt') else True
    decision=model.verify_model_load_approval(s.request,s.kw['approval'],authority=s.authority)
    with pytest.raises(auth.AuthorizationError):auth.ConsumptionLedger(root=s.root).consume(s.request,decision.grant)


def test_success_does_not_return_or_retain_adapter_handle(setup_model):
    s=setup_model;refs=[]
    def factory(*args,**kwargs):
        adapter=FakeAdapter(s.profile,s.root/'data/local/stage5/embedding_cache')
        refs.append(weakref.ref(adapter));return adapter
    s.factory.side_effect=factory
    result=model.simulate_model_load_only(**s.kw);gc.collect()
    assert refs[0]() is None and 'adapter' not in result and 'model' not in result


def test_failed_verification_releases_local_adapter_reference(setup_model):
    s=setup_model;refs=[]
    def factory(*args,**kwargs):
        adapter=FakeAdapter(s.profile,s.root/'data/local/stage5/embedding_cache');adapter.dimensions=1
        refs.append(weakref.ref(adapter));return adapter
    s.factory.side_effect=factory
    # Do not retain the exception traceback; it can extend Python local lifetimes.
    try:model.simulate_model_load_only(**s.kw)
    except model.ModelLoadPreparationError:pass
    gc.collect();assert refs[0]() is None


def test_live_gates_and_issuer_remain_absent(setup_model):
    with pytest.raises(PermissionError):model.execute_model_load_only(approved=True,force=True)
    with pytest.raises(PermissionError):boot.execute_dev()
    with pytest.raises(PermissionError):database_probe.execute_live_probe()
    with pytest.raises(auth.AuthorizationError):
        model.simulate_model_load_only(**(setup_model.kw|dict(model_factory=lambda:None)))
    assert not hasattr(model,'issue_approval')
    setup_model.factory.assert_not_called()


def test_path_symlink_rejected_without_runtime(setup_model):
    s=setup_model
    base=s.root/'data/local/stage5';base.mkdir(parents=True)
    outside=s.root/'outside';outside.mkdir()
    (base/'embedding_cache').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError):model.simulate_model_load_only(**s.kw)
    s.factory.assert_not_called()


def test_model_only_crash_after_claim_never_makes_approval_reusable(setup_model):
    s=setup_model
    grant=model.verify_model_load_approval(s.request,s.kw['approval'],authority=s.authority).grant
    process=multiprocessing.get_context('spawn').Process(target=_consume_then_crash,args=(s.root,s.request,grant))
    process.start();process.join(20)
    if process.is_alive():process.terminate();process.join();pytest.fail('Synthetic crash process timed out')
    assert process.exitcode==23
    with pytest.raises(auth.AuthorizationError):model.simulate_model_load_only(**s.kw)
    s.factory.assert_not_called()


def test_concurrent_model_only_attempts_allow_one_factory(setup_model):
    s=setup_model;barrier=threading.Barrier(2)
    def attempt(_):
        barrier.wait()
        try:model.simulate_model_load_only(**s.kw);return True
        except (auth.AuthorizationError,FileExistsError):return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(attempt,range(2)))==[False,True]
    s.factory.assert_called_once()
