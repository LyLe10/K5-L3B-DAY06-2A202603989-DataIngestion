"""Lab approval tests: ephemeral synthetic issuer and temporary fake runtime only."""
from copy import deepcopy
import hashlib
import hmac
import json
import multiprocessing
from pathlib import Path
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from starter.src import lab_dev_runtime as lab, dev_authorization as auth, dev_bootstrap as boot
from starter.src.evaluation import digest
from starter.src.schema import canonical_json
from starter.tests.test_benchmark import sample, bundle, frozen_bundle
from starter.tests.test_dev_bootstrap import local
from starter.tests.test_store import profile as base_profile
from starter.tests.test_evaluation_runner import setup
from starter.tests.test_dev_authorization import profile, runtime, _consume_then_crash


class SyntheticManualVerifier:
    __test__=False
    scope=lab.LAB_SCOPE
    authority_id='synthetic-lab-reviewer'

    def __init__(self):self.key=secrets.token_bytes(32)

    def issue(self,request,*,reviewer='synthetic-human',executor='synthetic-executor',expires_at=4102444800):
        body=dict(grant=dict(approval_id='synthetic-manual-approval',authority_id=self.authority_id,
            request_sha256=digest(json.loads(request)),not_before=0,expires_at=expires_at),
            reviewer_id=reviewer,executor_id=executor,decision_id='synthetic-manual-decision')
        return dict(body=body,signature=hmac.new(self.key,canonical_json(body).encode(),hashlib.sha256).hexdigest())

    def verify(self,request_canonical,approval):
        signature=hmac.new(self.key,canonical_json(approval['body']).encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,approval['signature']):raise ValueError('Synthetic signature rejected')
        data=approval['body']
        return lab.LabDecision(auth.VerifiedGrant(**data['grant']),data['reviewer_id'],data['executor_id'],data['decision_id'])


@pytest.fixture
def lab_runtime(runtime):
    path=runtime.root/'starter/src/lab_dev_runtime.py';path.write_bytes(Path(lab.__file__).read_bytes())
    prepared=boot.prepare_dev(root=runtime.root,output=runtime.kwargs['output'])
    request=lab.lab_authorization_request(prepared,root=runtime.root,run_id='synthetic-run',
        output=runtime.kwargs['output'],executor_id='synthetic-executor')
    authority=SyntheticManualVerifier()
    kwargs={k:runtime.kwargs[k] for k in ('root','run_id','output','wiring')}
    kwargs.update(executor_id='synthetic-executor',request_canonical=request,
                  approval=authority.issue(request),authority=authority)
    return SimpleNamespace(base=runtime,root=runtime.root,request=request,authority=authority,kwargs=kwargs)


def events(lab_runtime):
    path=lab_runtime.root/'data/local/stage5/lab_audit/synthetic-run'
    return [json.loads(p.read_text()) for p in sorted(path.glob('*.json'))]


def test_lab_sequence_reuses_runner_with_no_extra_preparation_or_session(lab_runtime):
    state=lab_runtime.base.state
    result=lab.simulate_lab_dev(**lab_runtime.kwargs)
    assert result['status']=='COMPLETE' and result['scope']==lab.LAB_SCOPE
    assert len(lab_runtime.base.adapter.calls)==15
    assert len(state.searches)==45 and state.opens==state.closes==1 and not state.active
    assert [row[0] for row in state.searches]==['A','B','C']*15
    wiring=lab_runtime.base.wiring
    wiring.runner.call_args.kwargs['producer'].prepare.assert_called_once()
    for dependency in wiring.__dict__.values():dependency.assert_called_once()
    records=events(lab_runtime)
    assert records[0]['status']=='CONSUMED' and records[-1]['status']=='COMPLETED_VERIFIED'
    assert [r['stage'] for r in records if r['status']=='STAGE_STARTED']==[
        'MODEL_ARTIFACTS','MODEL_FACTORY','MODEL_PROFILE','QUERY_PRODUCER','DATABASE_PROBE',
        'STORE_FACTORY','EVALUATION_RUNNER','ARTIFACT_SAVE','ARTIFACT_VERIFY']
    assert records[-1]['artifact_sha256']==digest(result['artifact'])
    assert all(r['request_sha256']==digest(json.loads(lab_runtime.request)) for r in records)


def test_lab_request_binds_execution_module_and_exact_manual_identity(lab_runtime):
    request=json.loads(lab_runtime.request)
    assert request['authorization_version']==2 and request['single_execution'] is True
    assert request['split']=='dev' and len(request['question_ids'])==15
    assert request['configuration']['deadline_seconds']==120
    assert set(request)==lab.REQUEST_KEYS
    assert 'starter/src/lab_dev_runtime.py' in request['execution_source_hashes']
    decision=lab.verify_lab_approval(lab_runtime.request,lab_runtime.kwargs['approval'],authority=lab_runtime.authority)
    assert decision.executor_id!=decision.reviewer_id


@pytest.mark.parametrize('bad',['missing','forged','expired','future','self_approval','wrong_executor',
    'wrong_authority','missing_authority','nonfinite_expiry','synthetic_scope'])
def test_bad_manual_approval_fails_before_consumption(lab_runtime,bad):
    kw=lab_runtime.kwargs;a=lab_runtime.authority
    if bad=='missing':kw['approval']=None
    elif bad=='forged':kw['approval']={'approved':True,'reviewer':'self'}
    elif bad=='expired':kw['approval']=a.issue(lab_runtime.request,expires_at=0)
    elif bad=='future':
        kw['approval']=a.issue(lab_runtime.request)
        kw['approval']['body']['grant']['not_before']=4102444799
        # Re-sign this synthetic body, representing an authenticated but not-yet-valid decision.
        kw['approval']['signature']=hmac.new(a.key,canonical_json(kw['approval']['body']).encode(),hashlib.sha256).hexdigest()
    elif bad=='self_approval':kw['approval']=a.issue(lab_runtime.request,reviewer='synthetic-executor')
    elif bad=='wrong_executor':kw['approval']=a.issue(lab_runtime.request,executor='another-executor')
    elif bad=='wrong_authority':kw['authority']=SyntheticManualVerifier()
    elif bad=='missing_authority':kw['authority']=None
    elif bad=='nonfinite_expiry':kw['approval']=a.issue(lab_runtime.request,expires_at='not-a-time')
    else:kw['authority'].scope='SYNTHETIC_ONLY'
    with pytest.raises(auth.AuthorizationError):lab.simulate_lab_dev(**kw)
    lab_runtime.base.wiring.model_factory.assert_not_called()
    lab_runtime.base.wiring.database_probe.assert_not_called()
    assert not (lab_runtime.root/'data/local/stage5/authorization').exists()


@pytest.mark.parametrize('field',['freeze_sha256','code','model','database','snapshot_ids','descriptor_hashes',
                                 'configuration','question_ids','executor_id','output'])
def test_authenticated_wrong_request_rejected(lab_runtime,field):
    request=json.loads(lab_runtime.request);request[field]='tampered'
    modified=canonical_json(request)
    kw=lab_runtime.kwargs|dict(request_canonical=modified,approval=lab_runtime.authority.issue(modified))
    with pytest.raises(auth.AuthorizationError):lab.simulate_lab_dev(**kw)
    lab_runtime.base.wiring.model_factory.assert_not_called()


def test_independent_verification_rejects_wrong_request_hash(lab_runtime):
    request=json.loads(lab_runtime.request);request['run_id']='another-run'
    with pytest.raises(auth.AuthorizationError):
        lab.verify_lab_approval(canonical_json(request),lab_runtime.kwargs['approval'],authority=lab_runtime.authority)


def test_claim_before_factories_and_replay_rejected(lab_runtime):
    decision=lab.verify_lab_approval(lab_runtime.request,lab_runtime.kwargs['approval'],authority=lab_runtime.authority)
    adapter=lab_runtime.base.adapter
    def model(*args,**kwargs):
        with pytest.raises(auth.AuthorizationError):
            auth.ConsumptionLedger(root=lab_runtime.root).consume(lab_runtime.request,decision.grant)
        assert events(lab_runtime)[0]['status']=='CONSUMED'
        return adapter
    lab_runtime.base.wiring.model_factory.side_effect=model
    lab.simulate_lab_dev(**lab_runtime.kwargs)
    with pytest.raises((auth.AuthorizationError,FileExistsError)):lab.simulate_lab_dev(**lab_runtime.kwargs)
    lab_runtime.base.wiring.model_factory.assert_called_once()


def test_concurrent_lab_claims(lab_runtime):
    grant=lab.verify_lab_approval(lab_runtime.request,lab_runtime.kwargs['approval'],authority=lab_runtime.authority).grant
    barrier=threading.Barrier(2)
    def claim(_):
        barrier.wait()
        try:auth.ConsumptionLedger(root=lab_runtime.root).consume(lab_runtime.request,grant);return True
        except auth.AuthorizationError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(claim,range(2)))==[False,True]


def test_crash_after_lab_claim_leaves_consumed(lab_runtime):
    grant=lab.verify_lab_approval(lab_runtime.request,lab_runtime.kwargs['approval'],authority=lab_runtime.authority).grant
    process=multiprocessing.get_context('spawn').Process(target=_consume_then_crash,
        args=(lab_runtime.root,lab_runtime.request,grant))
    process.start();process.join(20)
    if process.is_alive():process.terminate();process.join();pytest.fail('Synthetic crash test timed out')
    assert process.exitcode==23
    with pytest.raises(auth.AuthorizationError):lab.simulate_lab_dev(**lab_runtime.kwargs)
    lab_runtime.base.wiring.model_factory.assert_not_called()


@pytest.mark.parametrize('failure',['artifact','profile','cache','producer','host','cluster','migration','catalog','role',
                                  'role_flag','connection','runner','timeout','save','verify'])
def test_failures_produce_sanitized_audit_without_reset(lab_runtime,failure):
    b=lab_runtime.base;w=b.wiring
    if failure=='artifact':(b.root/b.prepared.plan['model']['snapshot']/'fixture').write_text('tampered')
    elif failure=='profile':b.adapter.profile_id='0'*64
    elif failure=='cache':b.adapter._cache_dir=b.root/'data/local/stage4/cache'
    elif failure=='producer':w.producer_factory.side_effect=ValueError('synthetic producer failure')
    elif failure=='host':w.database_probe.return_value['database']='wrong-database'
    elif failure=='cluster':w.database_probe.return_value['cluster']='wrong-cluster'
    elif failure=='migration':w.database_probe.return_value['migration_sha256']='0'*64
    elif failure=='catalog':w.database_probe.return_value['catalog_sha256']='0'*64
    elif failure=='role':w.database_probe.return_value['role']='PRIVILEGED_READONLY_TRANSACTION'
    elif failure=='role_flag':w.database_probe.return_value['role_review_required']=True
    elif failure=='connection':w.database_probe.side_effect=ConnectionError('postgresql://fixture:DO_NOT_EXPORT@invalid/private')
    elif failure=='runner':w.runner.side_effect=RuntimeError('database_password=DO_NOT_EXPORT')
    elif failure=='timeout':w.runner.side_effect=TimeoutError('DO_NOT_EXPORT')
    elif failure=='save':w.save.side_effect=OSError('DO_NOT_EXPORT')
    else:w.verify.side_effect=ValueError('DO_NOT_EXPORT')
    with pytest.raises(lab.LabAuditError) as error:lab.simulate_lab_dev(**lab_runtime.kwargs)
    assert 'DO_NOT_EXPORT' not in str(error.value)
    records=events(lab_runtime);last=records[-1]
    expected={'save':'ARTIFACT_WRITE_FAILED','verify':'ARTIFACT_VERIFY_FAILED'}.get(failure,'FAILED_NO_RESULT')
    assert last['status']==expected and last['consumed'] is True
    assert 'summary' not in last and 'metrics' not in last
    assert 'DO_NOT_EXPORT' not in json.dumps(records) and 'postgresql://' not in json.dumps(records)
    for dep in w.__dict__.values():assert dep.call_count<=1
    calls=w.model_factory.call_count
    with pytest.raises((auth.AuthorizationError,FileExistsError)):lab.simulate_lab_dev(**lab_runtime.kwargs)
    assert w.model_factory.call_count==calls


def test_incomplete_preserves_partial_traces_and_cleanup(lab_runtime):
    lab_runtime.base.state.fail_at=2
    result=lab.simulate_lab_dev(**lab_runtime.kwargs)
    assert result['status']=='INCOMPLETE'
    state=lab_runtime.base.state
    assert state.opens==state.closes==1 and not state.active and len(state.searches)==2
    raw=json.loads((lab_runtime.root/lab_runtime.kwargs['output']/'private/raw_run.json').read_text())
    assert raw['summary'] is None
    assert events(lab_runtime)[-1]['status']=='RUN_INCOMPLETE'


def test_timeout_inside_existing_runner_closes_only_session(lab_runtime):
    original=lab_runtime.base.wiring.store_factory.return_value
    from contextlib import contextmanager
    @contextmanager
    def session(**kwargs):
        with original_session(**kwargs) as active:
            active.search=Mock(side_effect=TimeoutError('synthetic retrieval timeout'))
            yield active
    original_session=original.retrieval_session
    original.retrieval_session=session
    result=lab.simulate_lab_dev(**lab_runtime.kwargs)
    assert result['status']=='INCOMPLETE'
    assert lab_runtime.base.state.opens==lab_runtime.base.state.closes==1
    assert not lab_runtime.base.state.active


@pytest.mark.parametrize('point',['initial','stage','terminal'])
def test_audit_failure_stops_without_retry(lab_runtime,monkeypatch,point):
    original=lab._LabAudit._write;calls=[]
    def write(self,status,**kwargs):
        calls.append(status)
        if ((point=='initial' and status=='CONSUMED') or (point=='stage' and status=='STAGE_STARTED')
                or (point=='terminal' and status=='COMPLETED_VERIFIED')):
            raise OSError('synthetic audit disk failure')
        return original(self,status,**kwargs)
    monkeypatch.setattr(lab._LabAudit,'_write',write)
    with pytest.raises(lab.LabAuditError):lab.simulate_lab_dev(**lab_runtime.kwargs)
    assert calls[-1] in ('CONSUMED','STAGE_STARTED','COMPLETED_VERIFIED')
    if point!='terminal':lab_runtime.base.wiring.model_factory.assert_not_called()
    decision=lab.verify_lab_approval(lab_runtime.request,lab_runtime.kwargs['approval'],authority=lab_runtime.authority)
    with pytest.raises(auth.AuthorizationError):
        auth.ConsumptionLedger(root=lab_runtime.root).consume(lab_runtime.request,decision.grant)


def test_test_split_always_blocked(lab_runtime):
    with pytest.raises(auth.AuthorizationError):lab.simulate_lab_dev(**(lab_runtime.kwargs|dict(split='test')))
    lab_runtime.base.wiring.prepare.assert_not_called()


def test_live_gates_factories_and_issuance_remain_unavailable(lab_runtime):
    with pytest.raises(PermissionError):boot.execute_dev()
    factory=lab.DisabledLabFactories()
    calls=[lambda:factory.model_adapter('unit',revision='x',snapshot_path=Path('x'),cache_dir=Path('x')),
        lambda:factory.query_cache(root=Path('.'),profile_id='x'),
        lambda:factory.readonly_connection(target={},readonly=True),lambda:factory.database_probe({}),
        lambda:factory.namespace_store(dimensions=384,dataset_id='x',profile_id='x',profile=None,context=None)]
    for call in calls:
        with pytest.raises(PermissionError,match='DISABLED'):call()
    assert not hasattr(factory,'issue') and not hasattr(lab,'issue_approval')
    assert not hasattr(lab.ManualApprovalVerifier,'issue')
    w=auth.OfflineWiring(**(lab_runtime.base.wiring.__dict__|dict(model_factory=factory.model_adapter)))
    with pytest.raises(auth.AuthorizationError):lab.simulate_lab_dev(**(lab_runtime.kwargs|dict(wiring=w)))
    lab_runtime.base.wiring.prepare.assert_not_called()


def test_audit_symlink_blocks_runtime_without_modifying_target(lab_runtime):
    base=lab_runtime.root/'data/local/stage5/lab_audit';base.parent.mkdir(parents=True)
    outside=lab_runtime.root/'outside';outside.mkdir();(outside/'sentinel').write_text('unchanged')
    base.symlink_to(outside,target_is_directory=True)
    with pytest.raises(lab.LabAuditError):lab.simulate_lab_dev(**lab_runtime.kwargs)
    lab_runtime.base.wiring.model_factory.assert_not_called()
    assert (outside/'sentinel').read_text()=='unchanged' and len(list(outside.iterdir()))==1
