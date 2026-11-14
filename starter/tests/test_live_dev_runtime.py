"""Temporary synthetic DEV only; no real model, database, frozen benchmark run."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from contextlib import contextmanager
import json
import pytest

from starter.src import live_dev_runtime as live, lab_dev_runtime as lab, dev_authorization as auth
from starter.src import dev_bootstrap as boot, live_probe, database_probe, evaluation_runner
from starter.tests.test_lab_dev_runtime import SyntheticManualVerifier
from starter.tests.test_dev_authorization import runtime, profile
from starter.tests.test_dev_bootstrap import local
from starter.tests.test_evaluation_runner import setup
from starter.tests.test_benchmark import sample, bundle, frozen_bundle
from starter.tests.test_store import profile as base_profile

READONLY_STORE_CLASS=live._ReadOnlyStore


@pytest.fixture
def dev(runtime,monkeypatch):
    r=runtime;repo=Path(live.__file__).resolve().parents[2]
    for name in live.CODE_FILES:
        path=r.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((repo/name).read_bytes())
    # Explicit synthetic process metadata, never a live-entry override argument.
    monkeypatch.setattr(live,'_EXECUTING_ROOT',r.root)
    monkeypatch.setattr(live,'_loaded_module_origins',lambda: {
        name[:-3].replace('/','.'):str(r.root/name) for name in live.CODE_FILES})
    baseline=r.local.baseline_factory.return_value
    baseline.dataset_id='synthetic-runner';baseline.profile_id=r.adapter.profile_id
    monkeypatch.setattr(boot,'DATASET',baseline.dataset_id)
    for strategy,snap in zip(('A','B'),baseline.snapshots):
        snap.namespace=SimpleNamespace(dataset_id=baseline.dataset_id,profile_id=baseline.profile_id,
            strategy=strategy,parameters=(baseline.dataset_id,baseline.profile_id,strategy))
        snap.status='complete';snap.actual_count=snap.expected_count
    r.adapter.dimensions=384
    r.adapter.runtime=dict(device='cpu',dtype='float32',eval_mode=True,tokenizer_limit=512,sentence_transformers_limit=512)
    r.adapter._stats.update(calls=0,inputs=0,encode_batches=0)
    prepared=boot.prepare_dev(root=r.root,output=r.kwargs['output'])
    reader=Mock(side_effect=AssertionError('No real secret access'))
    channel=live_probe.CredentialChannel('synthetic-channel',reader)
    request=live.live_dev_request(root=r.root,prepared=prepared,run_id='synthetic-run',
        output=r.kwargs['output'],executor_id='synthetic-executor',selected_role='synthetic-reader',
        credential_channel_id='synthetic-channel')
    authority=SyntheticManualVerifier();authority.scope=live.SCOPE
    kwargs=dict(root=r.root,run_id='synthetic-run',output=r.kwargs['output'],executor_id='synthetic-executor',
        selected_role='synthetic-reader',credential_channel_id='synthetic-channel',credential_channel=channel,
        request_canonical=request,approval=authority.issue(request),authority=authority)
    def init(*args):
        auth.ConsumptionLedger(root=r.root).require_consumed(request)
        assert events(r.root)[0]['status']=='CONSUMED'
        return r.adapter
    initialize=Mock(side_effect=init);monkeypatch.setattr(live,'_initialize_model',initialize)
    backend=dict(status='PASS',warnings=[],identity=dict(database='day6_lab',postgresql='16.16',pgvector='0.8.7',
        cluster=boot.CLUSTER,migration_sha256=boot.MIGRATION_SHA256,catalog_sha256=boot.APPROVED_CATALOG,
        transaction_read_only=True,role='SELECT_ONLY_TABLE_GRANTS',role_review_required=False))
    inspect=Mock(return_value=backend);monkeypatch.setattr(database_probe,'_inspect',inspect)
    store=Mock(return_value=r.wiring.store_factory.return_value);monkeypatch.setattr(live,'_ReadOnlyStore',store)
    producers=[]
    def make_producer(*args,**kwargs):
        value=r.wiring.producer_factory(*args,**kwargs);producers.append(value);return value
    producer=Mock(side_effect=make_producer);monkeypatch.setattr(live,'QueryProducer',producer)
    return SimpleNamespace(r=r,kwargs=kwargs,request=request,authority=authority,initialize=initialize,
        inspect=inspect,store=store,producer=producer,producers=producers,reader=reader,prepared=prepared)


def events(root):
    return [json.loads(p.read_text()) for p in sorted((root/'data/local/stage5/lab_audit/synthetic-run').glob('*.json'))]


def test_complete_uses_real_runner_once_with_one_synthetic_session(dev):
    d=dev;result=live.execute_live_dev(**d.kwargs)
    assert result['status']=='COMPLETE' and result['scope']==live.SCOPE
    assert len(d.r.adapter.calls)==15 and len(d.r.state.searches)==45
    assert d.r.state.opens==d.r.state.closes==1 and not d.r.state.active
    assert [s[0] for s in d.r.state.searches]==['A','B','C']*15
    assert len(d.producers)==1
    d.producers[0].prepare.assert_called_once()
    d.initialize.assert_called_once();d.inspect.assert_called_once();d.reader.assert_not_called()
    raw=json.loads((d.r.root/d.kwargs['output']/'private/raw_run.json').read_text())
    assert raw['manifest']['run_id']=='synthetic-run' and len(raw['receipts'])==15
    assert events(d.r.root)[-1]['status']=='COMPLETED_VERIFIED'
    with pytest.raises((FileExistsError,auth.AuthorizationError)):live.execute_live_dev(**d.kwargs)
    d.initialize.assert_called_once()


@pytest.mark.parametrize('bad',['test','missing','forged','expired','scope','channel','role','hash','code'])
def test_rejects_before_consumption_and_runtime(dev,monkeypatch,bad):
    d=dev;kw=d.kwargs
    if bad=='test':kw['split']='test'
    elif bad=='missing':kw['authority']=None
    elif bad=='forged':kw['approval']={'approved':True}
    elif bad=='expired':kw['approval']=d.authority.issue(d.request,expires_at=0)
    elif bad=='scope':d.authority.scope='LAB_MODEL_LOAD_ONLY_LIVE'
    elif bad=='channel':kw['credential_channel']=live_probe.CredentialChannel('other-channel',d.reader)
    elif bad=='role':kw['selected_role']='other-reader'
    elif bad=='hash':kw['request_canonical']='{}'
    else:(d.r.root/'starter/src/live_dev_runtime.py').write_text('synthetic code drift')
    consume=Mock(side_effect=AssertionError('Must not consume'))
    monkeypatch.setattr(auth.ConsumptionLedger,'consume',consume)
    with pytest.raises((auth.AuthorizationError,ValueError)):live.execute_live_dev(**kw)
    consume.assert_not_called();d.initialize.assert_not_called();d.inspect.assert_not_called();d.reader.assert_not_called()


@pytest.mark.parametrize('failure',['model','profile','probe','privileged','save','verify','runner'])
def test_post_claim_failure_keeps_consumption_and_sanitizes(dev,monkeypatch,failure):
    d=dev
    if failure=='model':d.initialize.side_effect=RuntimeError('SECRET_DETAIL')
    elif failure=='profile':d.r.adapter.profile_id='0'*64
    elif failure=='probe':d.inspect.side_effect=RuntimeError('SECRET_DETAIL')
    elif failure=='privileged':d.inspect.return_value['identity']['role_review_required']=True
    elif failure=='save':monkeypatch.setattr(boot,'save_dev_artifacts',Mock(side_effect=OSError('SECRET_DETAIL')))
    elif failure=='verify':monkeypatch.setattr(boot,'verify_dev_artifacts',Mock(return_value={}))
    else:monkeypatch.setattr(live,'run_evaluation',Mock(side_effect=RuntimeError('SECRET_DETAIL')))
    with pytest.raises(lab.LabAuditError) as error:live.execute_live_dev(**d.kwargs)
    assert 'SECRET_DETAIL' not in str(error.value)
    auth.ConsumptionLedger(root=d.r.root).require_consumed(d.request)
    assert events(d.r.root)[-1]['status'] in ('FAILED_NO_RESULT','ARTIFACT_WRITE_FAILED','ARTIFACT_VERIFY_FAILED')
    assert 'SECRET_DETAIL' not in json.dumps(events(d.r.root))
    assert d.initialize.call_count==1 and d.inspect.call_count<=1


def test_incomplete_preserves_partial_artifacts_and_null_summary(dev):
    d=dev;d.r.state.fail_at=2
    result=live.execute_live_dev(**d.kwargs)
    assert result['status']=='INCOMPLETE'
    raw=json.loads((d.r.root/d.kwargs['output']/'private/raw_run.json').read_text())
    assert raw['summary'] is None and len(raw['traces'])==2
    assert d.r.state.opens==d.r.state.closes==1
    assert events(d.r.root)[-1]['status']=='RUN_INCOMPLETE'


def test_audit_failure_before_model_fails_closed(dev,monkeypatch):
    d=dev;monkeypatch.setattr(lab._LabAudit,'write',Mock(side_effect=OSError('SECRET_DETAIL')))
    with pytest.raises(lab.LabAuditError):live.execute_live_dev(**d.kwargs)
    auth.ConsumptionLedger(root=d.r.root).require_consumed(d.request)
    d.initialize.assert_not_called();d.inspect.assert_not_called()


def test_readback_tamper_rejected(dev,monkeypatch):
    original=lab._LabAudit.write
    def tamper(audit,status,**kw):
        digest=original(audit,status,**kw)
        (audit.path/f'{audit.sequence:04}.json').write_text('{}')
        return digest
    monkeypatch.setattr(lab._LabAudit,'write',tamper)
    with pytest.raises(lab.LabAuditError):live.execute_live_dev(**dev.kwargs)
    dev.initialize.assert_not_called()


def test_old_disabled_gates_unchanged():
    with pytest.raises(PermissionError):boot.execute_dev()
    with pytest.raises(PermissionError):evaluation_runner.authorize_test_execution('test')
    with pytest.raises(PermissionError):lab.DisabledLabFactories.model_adapter('anything',revision='x',snapshot_path=Path('.'),cache_dir=Path('.'))


def test_readonly_store_explicit_connector_and_wrong_connection_cleanup(monkeypatch):
    # Exercise the connector subclass independently of the orchestration fake.
    channel=live_probe.CredentialChannel('synthetic-channel',Mock())
    obj=object.__new__(live._ReadOnlyStore);obj._channel=channel;obj._role='synthetic-reader'
    connection=Mock();connection.info=SimpleNamespace(host='127.0.0.1',port=55433,dbname='day6_lab',user='synthetic-reader')
    connect=Mock(return_value=connection);monkeypatch.setattr(live_probe,'_connect',connect)
    with pytest.raises(auth.AuthorizationError):obj._connect(readonly=False)
    connect.assert_not_called()
    assert obj._connect(readonly=True) is connection
    assert connect.call_args.kwargs['credential_provider'] is channel
    assert connect.call_args.kwargs['user']=='synthetic-reader'
    connection.info.user='wrong-role'
    with pytest.raises(auth.AuthorizationError):obj._connect(readonly=True)
    connection.close.assert_called_once()


@pytest.mark.parametrize('field',['configuration','freeze_sha256','profile_id','snapshot_ids','descriptor_hashes',
    'credential_channel_id','selected_role','code_sha256'])
def test_signed_request_tampering_never_reaches_runtime(dev,monkeypatch,field):
    d=dev;request=json.loads(d.request)
    if field in ('credential_channel_id','selected_role','code_sha256'):
        request['runtime_binding'][field]='changed'
    elif field=='configuration':request[field]['deadline_seconds']=121
    elif field in ('snapshot_ids','descriptor_hashes'):request[field]=['0'*64,'1'*64]
    else:request[field]='0'*64
    from starter.src.schema import canonical_json
    d.kwargs['request_canonical']=canonical_json(request)
    d.kwargs['approval']=d.authority.issue(d.kwargs['request_canonical'])
    consume=Mock(side_effect=AssertionError('No consumption'))
    monkeypatch.setattr(auth.ConsumptionLedger,'consume',consume)
    with pytest.raises(auth.AuthorizationError):live.execute_live_dev(**d.kwargs)
    consume.assert_not_called();d.initialize.assert_not_called();d.inspect.assert_not_called()


def test_audit_failure_after_artifact_verification_never_reports_success(dev,monkeypatch):
    original=lab._LabAudit.write
    def write(audit,status,**kw):
        if status=='COMPLETED_VERIFIED':raise OSError('SECRET_DETAIL')
        return original(audit,status,**kw)
    monkeypatch.setattr(lab._LabAudit,'write',write)
    with pytest.raises(lab.LabAuditError):live.execute_live_dev(**dev.kwargs)
    auth.ConsumptionLedger(root=dev.r.root).require_consumed(dev.request)
    assert (dev.r.root/dev.kwargs['output']/'artifact_manifest.json').exists()
    assert events(dev.r.root)[-1]['status']!='COMPLETED_VERIFIED'
    dev.initialize.assert_called_once()


def test_two_workspaces_rejected_before_preparation_or_consumption(dev,monkeypatch,tmp_path):
    # Workspace A is executing; an otherwise prepared workspace B cannot authorize it.
    d=dev;other=tmp_path/'other-workspace';other.mkdir()
    kw=d.kwargs|dict(root=other)
    prepare=Mock(side_effect=AssertionError('Must reject root first'))
    consume=Mock(side_effect=AssertionError('Must not consume'))
    monkeypatch.setattr(boot,'prepare_dev',prepare)
    monkeypatch.setattr(auth.ConsumptionLedger,'consume',consume)
    with pytest.raises(auth.AuthorizationError,match='executing workspace'):live.execute_live_dev(**kw)
    prepare.assert_not_called();consume.assert_not_called();d.initialize.assert_not_called()


def test_loaded_module_from_another_workspace_rejected(dev,monkeypatch):
    origins=live._loaded_module_origins()
    origins['starter.src.embeddings']=str(dev.r.root/'other/embeddings.py')
    monkeypatch.setattr(live,'_loaded_module_origins',lambda:origins)
    with pytest.raises(auth.AuthorizationError,match='another workspace'):live.execute_live_dev(**dev.kwargs)
    dev.initialize.assert_not_called()


def test_real_loaded_origins_metadata_only():
    # No synthetic origin override here: validates actual __file__/__spec__ metadata.
    root=Path(live.__file__).resolve().parents[2]
    identity=live._workspace_identity(root)
    assert identity['module_origins']['starter.src.live_dev_runtime']=='starter/src/live_dev_runtime.py'
    assert identity['module_origins']['starter.src.embeddings']=='starter/src/embeddings.py'


def test_runtime_source_change_during_verification_blocks_consumption(dev,monkeypatch):
    original=dev.authority.verify
    def verify(*args):
        decision=original(*args)
        (dev.r.root/'starter/src/live_dev_runtime.py').write_text('synthetic source drift')
        return decision
    dev.authority.verify=verify
    consume=Mock(side_effect=AssertionError('Must not consume'))
    monkeypatch.setattr(auth.ConsumptionLedger,'consume',consume)
    with pytest.raises(auth.AuthorizationError,match='source changed'):live.execute_live_dev(**dev.kwargs)
    consume.assert_not_called();dev.initialize.assert_not_called()


def test_runtime_source_change_after_consumption_stops_model(dev,monkeypatch):
    original=lab._LabAudit.write
    def write(audit,status,**kw):
        result=original(audit,status,**kw)
        if status=='CONSUMED':(dev.r.root/'starter/src/live_dev_runtime.py').write_text('synthetic drift')
        return result
    monkeypatch.setattr(lab._LabAudit,'write',write)
    with pytest.raises(lab.LabAuditError):live.execute_live_dev(**dev.kwargs)
    dev.initialize.assert_not_called()
    auth.ConsumptionLedger(root=dev.r.root).require_consumed(dev.request)


@pytest.mark.parametrize('entry',['adapter_config.json','config_sentence_transformers.json','unapproved.py',
    'unapproved-directory','extra-symlink','artifact-symlink'])
def test_unsafe_inventory_blocks_dev_constructor(dev,entry):
    model=dev.prepared.plan['model'];snapshot=dev.r.root/model['snapshot']
    if entry=='unapproved-directory':(snapshot/entry).mkdir()
    elif entry=='extra-symlink':(snapshot/entry).symlink_to(snapshot/'fixture')
    elif entry=='artifact-symlink':
        outside=dev.r.root/'outside-model-artifact'
        artifact=snapshot/'fixture';outside.write_bytes(artifact.read_bytes());artifact.unlink();artifact.symlink_to(outside)
    else:(snapshot/entry).write_text('Synthetic unapproved configuration')
    with pytest.raises(lab.LabAuditError):live.execute_live_dev(**dev.kwargs)
    dev.initialize.assert_not_called();dev.inspect.assert_not_called()


@pytest.fixture
def retrieval_connection(monkeypatch):
    """Same fake connection owns BEGIN/rollback and the identity-check SQL."""
    connection=Mock()
    connection.info=SimpleNamespace(transaction_status=SimpleNamespace(name='INTRANS'))
    cursor=Mock();connection.cursor.return_value=cursor
    cursor.__enter__=Mock(return_value=cursor);cursor.__exit__=Mock(return_value=False)
    cursor._synthetic_connection=connection
    state=SimpleNamespace(active=False,rollbacks=0,closed=0,searches=0,
        identity=('day6_lab','160016',boot.CLUSTER,'0.8.7',boot.MIGRATION_SHA256,boot.APPROVED_CATALOG),
        permissions=('synthetic-reader','synthetic-reader',True,True,True,True,True,
            False,False,False,False,False,False,False,'on','repeatable read','30s'),
        tables=[(name,True) for name in sorted(database_probe.TABLES)])
    def one():
        assert state.active
        sql=cursor.execute.call_args.args[0]
        if sql==database_probe.PERMISSIONS_SQL:return state.permissions
        assert 'pg_control_system' in sql
        return state.identity
    cursor.fetchone.side_effect=one
    cursor.fetchall.side_effect=lambda:state.tables
    @contextmanager
    def parent(*args,**kwargs):
        state.active=True
        try:
            yield SimpleNamespace(_connection=connection,search=Mock(side_effect=search))
        except BaseException:state.rollbacks+=1;raise
        finally:state.active=False;state.closed+=1
    def search(*args,**kwargs):
        assert state.active;state.searches+=1;return []
    monkeypatch.setattr(live.PgVectorStore,'retrieval_session',parent)
    monkeypatch.setattr(live,'_assert_runtime_identity',Mock())
    obj=object.__new__(READONLY_STORE_CLASS);obj._role='synthetic-reader'
    obj._root=Path('.');obj._approved_request={}
    return obj,state,cursor


def test_actual_retrieval_guard_precedes_search_in_owned_transaction(retrieval_connection):
    obj,state,cursor=retrieval_connection
    with obj.retrieval_session() as session:
        assert cursor.execute.call_count==3
        session.search('A',[0.0]*384)
    assert state.searches==1 and state.closed==1 and state.rollbacks==0


@pytest.mark.parametrize('change',['cluster','database','postgresql','pgvector','catalog','role',
    'write','membership','owner','temp','missing_select','not_readonly','isolation'])
def test_changed_cluster_or_permissions_after_probe_block_search(retrieval_connection,change):
    obj,state,cursor=retrieval_connection
    # Earlier probe was successful; only the actual retrieval connection has changed.
    if change in ('cluster','database','postgresql','pgvector','catalog'):
        index={'cluster':2,'database':0,'postgresql':1,'pgvector':3,'catalog':5}[change]
        row=list(state.identity);row[index]='changed';state.identity=tuple(row)
    elif change=='missing_select':state.tables=[(name,False) for name in sorted(database_probe.TABLES)]
    else:
        index={'role':1,'write':11,'membership':8,'owner':12,'temp':13,'not_readonly':14,'isolation':15}[change]
        row=list(state.permissions);row[index]=('other-role' if change=='role' else
            'off' if change=='not_readonly' else 'read committed' if change=='isolation' else True)
        state.permissions=tuple(row)
    with pytest.raises(auth.AuthorizationError,match='Retrieval connection'):
        with obj.retrieval_session() as session:session.search('A',[0.0]*384)
    assert state.searches==0 and state.rollbacks==state.closed==1 and not state.active


@pytest.mark.parametrize('change',['cluster','privileges'])
def test_successful_probe_then_changed_retrieval_connection_is_incomplete(dev,retrieval_connection,monkeypatch,change):
    d=dev;obj,state,cursor=retrieval_connection
    backend=deepcopy(d.inspect.return_value)
    def successful_probe(*args,**kwargs):
        if change=='cluster':
            row=list(state.identity);row[2]='different-cluster';state.identity=tuple(row)
        else:
            row=list(state.permissions);row[11]=True;state.permissions=tuple(row)
        return backend
    d.inspect.side_effect=successful_probe
    base=d.r.wiring.store_factory.return_value
    class CheckedSyntheticStore:
        dataset_id=base.dataset_id;profile_id=base.profile_id
        @contextmanager
        def retrieval_session(self,**kwargs):
            with base.retrieval_session(**kwargs) as session:
                state.active=True
                try:
                    live._verify_retrieval_connection(obj_connection,'synthetic-reader')
                    yield session
                finally:state.active=False
    # Retrieve the fake connection through the cursor owner captured by the fixture.
    obj_connection=cursor._synthetic_connection
    monkeypatch.setattr(live,'_ReadOnlyStore',Mock(return_value=CheckedSyntheticStore()))
    result=live.execute_live_dev(**d.kwargs)
    assert result['status']=='INCOMPLETE'
    assert d.inspect.call_count==1 and len(d.r.adapter.calls)==15
    assert d.r.state.searches==[] and d.r.state.opens==d.r.state.closes==1
    raw=json.loads((d.r.root/d.kwargs['output']/'private/raw_run.json').read_text())
    assert raw['summary'] is None and raw['traces']==[]
