"""Synthetic authority, adapters and DB doubles only. Never execute frozen benchmark."""
from copy import deepcopy
import hashlib
import hmac
import json
import multiprocessing
import os
from pathlib import Path
import secrets
from types import SimpleNamespace
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from starter.src import dev_authorization as auth, dev_bootstrap as boot
from starter.src.evaluation import digest
from starter.src.evaluation_runner import QueryProducer, run_evaluation
from starter.src.schema import canonical_json
from starter.tests.test_benchmark import sample, bundle, frozen_bundle
from starter.tests.test_store import profile as base_profile
from starter.tests.test_dev_bootstrap import local
from starter.tests.test_evaluation_runner import setup


@pytest.fixture
def profile(base_profile):
    from starter.src.schema import EmbeddingProfile
    config=base_profile.config
    config['artifact_sha256']={'fixture':hashlib.sha256(b'Synthetic model artifact, not weights').hexdigest()}
    return EmbeddingProfile.from_config(config)


class TestAuthority:
    __test__=False
    authority_id='synthetic-authority'
    scope='SYNTHETIC_ONLY'

    def __init__(self):self._key=secrets.token_bytes(32)

    def issue(self,request,*,approval_id='synthetic-approval',not_before=100,expires_at=200):
        body=dict(approval_id=approval_id,authority_id=self.authority_id,request_sha256=digest(json.loads(request)),
                  not_before=not_before,expires_at=expires_at)
        return dict(body=body,signature=hmac.new(self._key,canonical_json(body).encode(),hashlib.sha256).hexdigest())

    def verify(self,request_canonical,approval):
        expected=hmac.new(self._key,canonical_json(approval['body']).encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,approval['signature']):raise ValueError('Synthetic signature rejected')
        return auth.VerifiedGrant(**approval['body'])


@pytest.fixture
def runtime(local,setup):
    # All corpus/questions originate from the existing temporary synthetic fixture.
    local.baseline_factory.return_value=setup.baseline
    for snap,count in zip(setup.baseline.snapshots,(246,264)):
        snap.expected_count=count;snap.selected_page_count=40
    root=local.root
    code=root/'starter/src/dev_authorization.py'
    code.write_bytes(Path(auth.__file__).read_bytes())
    output='data/local/stage5/runs/synthetic-run'
    prepared=boot.prepare_dev(root=root,output=output)
    snapshot=root/prepared.plan['model']['snapshot'];snapshot.mkdir(parents=True)
    (snapshot/'fixture').write_bytes(b'Synthetic model artifact, not weights')
    setup.adapter._cache_dir=root/'data/local/stage5/embedding_cache'
    backend=dict(database='day6_lab',cluster=boot.CLUSTER,postgresql='16.16',pgvector='0.8.7',
        migration_sha256=boot.MIGRATION_SHA256,catalog_sha256=boot.APPROVED_CATALOG,
        transaction_read_only=True,role='SELECT_ONLY_TABLE_GRANTS',role_review_required=False,
        scope='SYNTHETIC_FIXTURE')
    def producer_factory(*args,**kwargs):
        producer=QueryProducer(*args,**kwargs)
        producer.prepare=Mock(wraps=producer.prepare)
        return producer
    wiring=auth.OfflineWiring(prepare=Mock(side_effect=lambda **kw:boot.prepare_dev(**kw)),
        model_factory=Mock(return_value=setup.adapter),producer_factory=Mock(side_effect=producer_factory),
        database_probe=Mock(return_value=backend),store_factory=Mock(return_value=setup.store),
        runner=Mock(side_effect=run_evaluation),save=Mock(wraps=boot.save_dev_artifacts),
        verify=Mock(wraps=boot.verify_dev_artifacts))
    request=auth.authorization_request(prepared,root=root,run_id='synthetic-run',output=output)
    authority=TestAuthority()
    kwargs=dict(root=root,run_id='synthetic-run',output=output,request_canonical=request,
                approval=authority.issue(request),authority=authority,wiring=wiring,now=150)
    return SimpleNamespace(root=root,prepared=prepared,request=request,authority=authority,
        wiring=wiring,kwargs=kwargs,state=setup.state,adapter=setup.adapter,local=local)


def test_complete_mock_wiring_owns_one_session_and_fifteen_queries(runtime):
    result=auth.simulate_authorized_dev(**runtime.kwargs)
    assert result['status']=='COMPLETE' and result['scope']=='SYNTHETIC_ONLY'
    assert len(runtime.adapter.calls)==15
    assert runtime.state.opens==runtime.state.closes==1
    assert len(runtime.state.searches)==45
    assert [s[0] for s in runtime.state.searches]==['A','B','C']*15
    for dependency in runtime.wiring.__dict__.values():dependency.assert_called_once()
    assert runtime.wiring.runner.call_args.kwargs['output_directory'] is None
    runtime.wiring.runner.call_args.kwargs['producer'].prepare.assert_called_once()
    for i in range(15):
        assert len({row[1] for row in runtime.state.searches[i*3:i*3+3]})==1
    raw=json.loads((runtime.root/runtime.kwargs['output']/'private/raw_run.json').read_text())
    assert raw['manifest']['run_id']=='synthetic-run'
    assert not runtime.state.active


@pytest.mark.parametrize('bad',['missing','forged','expired','future','wrong_authority','no_authority'])
def test_invalid_approval_never_reaches_runtime(runtime,bad):
    kw=runtime.kwargs
    if bad=='missing':kw['approval']=None
    elif bad=='forged':kw['approval']={'approved':True,'reviewer':'self','hash':digest(json.loads(runtime.request))}
    elif bad=='expired':kw['now']=200
    elif bad=='future':kw['now']=99
    elif bad=='wrong_authority':kw['authority']=TestAuthority()
    else:kw['authority']=None
    with pytest.raises(auth.AuthorizationError):auth.simulate_authorized_dev(**kw)
    runtime.wiring.model_factory.assert_not_called();runtime.wiring.database_probe.assert_not_called()
    assert not (runtime.root/'data/local/stage5/authorization').exists()


@pytest.mark.parametrize('field',['freeze_sha256','configuration','code','profile_id','snapshot_ids','database',
                                 'question_ids','execution_source_hashes','output','run_id'])
def test_identity_tamper_fails_before_factories(runtime,field):
    request=json.loads(runtime.request)
    request[field]='tampered'
    runtime.kwargs['request_canonical']=canonical_json(request)
    # Even an authenticated approval for changed identities cannot bypass fresh preparation.
    runtime.kwargs['approval']=runtime.authority.issue(runtime.kwargs['request_canonical'])
    with pytest.raises(auth.AuthorizationError):auth.simulate_authorized_dev(**runtime.kwargs)
    runtime.wiring.model_factory.assert_not_called();runtime.wiring.database_probe.assert_not_called()


def test_missing_authority_authentication_and_mismatched_request(runtime):
    approval=runtime.authority.issue(runtime.request)
    changed=json.loads(runtime.request);changed['run_id']='different'
    with pytest.raises(auth.AuthorizationError):
        auth.verify_authorization(canonical_json(changed),approval,authority=runtime.authority,now=150)


def test_execution_code_changed_after_request_is_rejected(runtime):
    path=runtime.root/'starter/src/dev_authorization.py'
    path.write_bytes(path.read_bytes()+b'\n# synthetic post-approval mutation\n')
    with pytest.raises(auth.AuthorizationError):auth.simulate_authorized_dev(**runtime.kwargs)
    runtime.wiring.model_factory.assert_not_called()
    assert not (runtime.root/'data/local/stage5/authorization').exists()


def test_consumption_precedes_model_and_database(runtime):
    original=runtime.wiring.model_factory.return_value
    def model(*args,**kwargs):
        grant=auth.verify_authorization(runtime.request,runtime.kwargs['approval'],authority=runtime.authority,now=150)
        with pytest.raises(auth.AuthorizationError):
            auth.ConsumptionLedger(root=runtime.root).consume(runtime.request,grant)
        return original
    runtime.wiring.model_factory.side_effect=model
    auth.simulate_authorized_dev(**runtime.kwargs)


def test_concurrent_consumption_has_exactly_one_winner(runtime):
    grant=auth.verify_authorization(runtime.request,runtime.kwargs['approval'],authority=runtime.authority,now=150)
    barrier=threading.Barrier(2)
    def consume():
        barrier.wait()
        try:auth.ConsumptionLedger(root=runtime.root).consume(runtime.request,grant);return True
        except auth.AuthorizationError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(lambda _:consume(),range(2)))==[False,True]
    with pytest.raises(auth.AuthorizationError):auth.ConsumptionLedger(root=runtime.root).consume(runtime.request,grant)


def _consume_then_crash(root,request,grant):
    auth.ConsumptionLedger(root=root).consume(request,grant)
    os._exit(23)


def test_process_crash_after_consumption_does_not_reopen_approval(runtime):
    grant=auth.verify_authorization(runtime.request,runtime.kwargs['approval'],authority=runtime.authority,now=150)
    process=multiprocessing.get_context('spawn').Process(target=_consume_then_crash,args=(runtime.root,runtime.request,grant))
    process.start();process.join(20)
    if process.is_alive():process.terminate();process.join();pytest.fail('Synthetic crash process timed out')
    assert process.exitcode==23
    with pytest.raises(auth.AuthorizationError):auth.simulate_authorized_dev(**runtime.kwargs)
    runtime.wiring.model_factory.assert_not_called()


@pytest.mark.parametrize('path',['../escape','data/local/stage4/ledger','data/local/stage5/authorization/../escape'])
def test_ledger_rejects_path_escape(runtime,path):
    grant=auth.verify_authorization(runtime.request,runtime.kwargs['approval'],authority=runtime.authority,now=150)
    with pytest.raises(ValueError):auth.ConsumptionLedger(root=runtime.root,path=path).consume(runtime.request,grant)


@pytest.mark.parametrize('target',['directory','file','journal'])
def test_ledger_rejects_symlink(runtime,target):
    base=runtime.root/'data/local/stage5/authorization';base.parent.mkdir(parents=True)
    outside=runtime.root/'outside';outside.mkdir();sentinel=outside/'sentinel';sentinel.write_text('unchanged')
    if target=='directory':base.symlink_to(outside,target_is_directory=True)
    else:
        base.mkdir()
        (base/('consumption.sqlite3' if target=='file' else 'consumption.sqlite3-journal')).symlink_to(sentinel)
    grant=auth.verify_authorization(runtime.request,runtime.kwargs['approval'],authority=runtime.authority,now=150)
    with pytest.raises(ValueError):auth.ConsumptionLedger(root=runtime.root).consume(runtime.request,grant)
    assert sentinel.read_text()=='unchanged'


@pytest.mark.parametrize('failure',['artifact','model','profile','probe','role','database','backend_payload',
                                  'store','runner','timeout','save','verify'])
def test_failure_burns_approval_without_retry(runtime,failure):
    w=runtime.wiring
    if failure=='artifact':(runtime.root/runtime.prepared.plan['model']['snapshot']/'fixture').write_bytes(b'tampered')
    elif failure=='model':w.model_factory.side_effect=RuntimeError('synthetic load failure')
    elif failure=='profile':runtime.adapter.profile_id='0'*64
    elif failure=='probe':w.database_probe.side_effect=ConnectionError('synthetic connection failure')
    elif failure=='role':w.database_probe.return_value['role_review_required']=True
    elif failure=='database':w.database_probe.return_value['cluster']='wrong'
    elif failure=='backend_payload':w.database_probe.return_value['dsn']='synthetic-forbidden-payload'
    elif failure=='store':w.store_factory.return_value=SimpleNamespace(dataset_id='wrong',profile_id='wrong')
    elif failure=='runner':w.runner.side_effect=ConnectionError('synthetic retrieval failure')
    elif failure=='timeout':w.runner.side_effect=TimeoutError('synthetic deadline')
    elif failure=='save':w.save.side_effect=OSError('synthetic write failure')
    else:w.verify.return_value={'tampered':True}
    with pytest.raises((auth.AuthorizationError,RuntimeError,ConnectionError,TimeoutError,OSError)):
        auth.simulate_authorized_dev(**runtime.kwargs)
    for dep in w.__dict__.values():assert dep.call_count<=1
    model_count=w.model_factory.call_count
    # Existing output can also block a replay before reaching the durable ledger.
    with pytest.raises((auth.AuthorizationError,FileExistsError)):
        auth.simulate_authorized_dev(**runtime.kwargs)
    assert w.model_factory.call_count==model_count


def test_incomplete_has_no_summary_and_no_retry(runtime):
    runtime.state.fail_at=2
    result=auth.simulate_authorized_dev(**runtime.kwargs)
    assert result['status']=='INCOMPLETE'
    assert len(runtime.state.searches)==2 and runtime.state.opens==runtime.state.closes==1
    raw=json.loads((runtime.root/runtime.kwargs['output']/'private/raw_run.json').read_text())
    assert raw['summary'] is None


def test_incomplete_quality_summary_rejected(runtime):
    runtime.wiring.runner.side_effect=None
    runtime.wiring.runner.return_value={'status':'INCOMPLETE','summary':{'forged':True}}
    with pytest.raises(auth.AuthorizationError):auth.simulate_authorized_dev(**runtime.kwargs)
    runtime.wiring.save.assert_not_called()


def test_execution_gates_and_mock_only_dependencies(runtime):
    with pytest.raises(PermissionError):boot.execute_dev()
    with pytest.raises(auth.AuthorizationError):auth.simulate_authorized_dev(**(runtime.kwargs|dict(split='test')))
    runtime.wiring.prepare.assert_not_called()
    wiring=auth.OfflineWiring(**(runtime.wiring.__dict__|dict(model_factory=lambda:None)))
    with pytest.raises(auth.AuthorizationError):auth.simulate_authorized_dev(**(runtime.kwargs|dict(wiring=wiring)))
    assert not (runtime.root/'data/local/stage5').exists()


@pytest.mark.parametrize('change',['approval','run','request'])
def test_ledger_uniqueness_across_new_authenticated_grants(runtime,change):
    request=json.loads(runtime.request)
    original=auth.verify_authorization(runtime.request,runtime.kwargs['approval'],authority=runtime.authority,now=150)
    ledger=auth.ConsumptionLedger(root=runtime.root);ledger.consume(runtime.request,original)
    # Vary two identities, preserving the third uniqueness guard under test.
    approval_id='synthetic-approval' if change=='approval' else 'different-approval'
    if change!='request':
        request['output']='data/local/stage5/runs/different'
    if change=='approval':request['run_id']='different-run'
    modified=canonical_json(request)
    grant=auth.verify_authorization(modified,runtime.authority.issue(modified,approval_id=approval_id),
                                   authority=runtime.authority,now=150)
    with pytest.raises(auth.AuthorizationError):ledger.consume(modified,grant)


def test_model_artifact_symlink_rejected_before_factory(runtime):
    artifact=runtime.root/runtime.prepared.plan['model']['snapshot']/'fixture'
    target=runtime.root/'external-artifact';target.write_bytes(artifact.read_bytes())
    artifact.unlink();artifact.symlink_to(target)
    with pytest.raises(auth.AuthorizationError):auth.simulate_authorized_dev(**runtime.kwargs)
    runtime.wiring.model_factory.assert_not_called();runtime.wiring.database_probe.assert_not_called()


def test_protected_sentinels_unchanged(runtime):
    paths=['.env','data/local/stage4/sentinel','results/local-sentinel.diff']
    for name in paths:
        path=runtime.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'protected synthetic sentinel')
    before={name:(runtime.root/name).read_bytes() for name in paths}
    auth.simulate_authorized_dev(**runtime.kwargs)
    assert all((runtime.root/name).read_bytes()==value for name,value in before.items())
