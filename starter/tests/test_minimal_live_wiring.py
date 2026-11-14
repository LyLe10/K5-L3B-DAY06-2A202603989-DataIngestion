"""Synthetic live-wiring tests: replace every heavy/runtime boundary."""
import json
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace
import sys
import pytest

from starter.src import model_load_only as model, live_probe as live, database_probe as probe
from starter.src import dev_authorization as auth, embeddings, dev_bootstrap as boot
from starter.tests.test_model_load_only import setup_model, template_profile, audit_events
from starter.tests.test_database_probe import db_probe
from starter.tests.test_store import profile, ingestion, store
from starter.tests.test_lab_dev_runtime import SyntheticManualVerifier


def model_args(s):
    request=model.model_load_request(root=s.root,run_id='synthetic-load',executor_id='synthetic-executor',live=True)
    s.authority.scope=model.LIVE_SCOPE
    return dict(root=s.root,run_id='synthetic-load',executor_id='synthetic-executor',
        request_canonical=request,approval=s.authority.issue(request),authority=s.authority)


def test_model_real_wiring_with_only_synthetic_constructor(setup_model,monkeypatch):
    s=setup_model;kw=model_args(s)
    def initialize(*args,**kwargs):
        auth.ConsumptionLedger(root=s.root).require_consumed(kw['request_canonical'])
        assert audit_events(s)[0]['status']=='CONSUMED'
        return s.adapter
    constructor=Mock(side_effect=initialize);monkeypatch.setattr(embeddings,'MyEmbedder',constructor)
    result=model.execute_model_load_only(**kw)
    assert result['execution_mode']=='LIVE_MODEL_LOAD_ONLY'
    assert result['status']=='MODEL_LOAD_VERIFIED' and result['encoded_inputs']==0
    assert audit_events(s)[-1]['execution_mode']=='LIVE_MODEL_LOAD_ONLY'
    constructor.assert_called_once();s.adapter.embed_query.assert_not_called()
    with pytest.raises((FileExistsError,auth.AuthorizationError)):model.execute_model_load_only(**kw)
    constructor.assert_called_once()


@pytest.mark.parametrize('failure',['approval','request','constructor','profile','audit'])
def test_model_live_fail_closed(setup_model,monkeypatch,failure):
    s=setup_model;kw=model_args(s);constructor=Mock(return_value=s.adapter)
    monkeypatch.setattr(embeddings,'MyEmbedder',constructor)
    if failure=='approval':kw['approval']={'approved':True}
    if failure=='request':kw['request_canonical']=s.request
    if failure=='constructor':constructor.side_effect=RuntimeError('secret must not escape')
    if failure=='profile':s.adapter.profile_id='0'*64
    if failure=='audit':monkeypatch.setattr(model.lab._LabAudit,'write',Mock(side_effect=OSError('private path')))
    with pytest.raises((auth.AuthorizationError,model.ModelLoadPreparationError)) as error:
        model.execute_model_load_only(**kw)
    assert 'secret' not in str(error.value) and 'private path' not in str(error.value)
    assert constructor.call_count==(1 if failure in ('constructor','profile') else 0)


@pytest.fixture
def probe_live(db_probe,tmp_path,monkeypatch):
    d=db_probe;repo=Path(model.__file__).resolve().parents[2]
    for name in live.PROBE_CODE_FILES:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((repo/name).read_bytes())
    monkeypatch.setattr(boot,'prepare_dev',Mock(return_value=d.prepared))
    request=live.probe_request(root=tmp_path,prepared=d.prepared,run_id='probe-live',executor_id='synthetic-executor',
        selected_role='synthetic-reader',credential_channel_id='protected-channel')
    authority=SyntheticManualVerifier();authority.scope=live.SCOPE
    provider=Mock(side_effect=AssertionError('Test must not discover credentials'))
    kw=dict(root=tmp_path,run_id='probe-live',executor_id='synthetic-executor',selected_role='synthetic-reader',
        credential_channel_id='protected-channel',credential_provider=live.CredentialChannel('protected-channel',provider),request_canonical=request,
        authority=authority,approval=authority.issue(request,reviewer='reviewer'))
    def connect(**kwargs):
        auth.ConsumptionLedger(root=tmp_path).require_consumed(request)
        assert kwargs['user']=='synthetic-reader' and kwargs['connect_timeout']==5
        return d.connection
    connector=Mock(side_effect=connect);monkeypatch.setattr(live,'_connect',connector)
    return d,kw,connector,provider


def test_probe_live_wiring_consumes_before_single_connection(probe_live):
    d,kw,connector,provider=probe_live
    result=probe.execute_live_probe(**kw)
    assert result['counts']['total']==510 and result['scope']==live.SCOPE
    assert d.state.commits==1 and not d.state.active
    connector.assert_called_once();provider.assert_not_called()
    records=[json.loads(p.read_text()) for p in sorted((kw['root']/'data/local/stage5/lab_audit/probe-live').glob('*.json'))]
    assert records[-1]['status']=='PROBE_VERIFIED'
    with pytest.raises((FileExistsError,auth.AuthorizationError)):probe.execute_live_probe(**kw)
    connector.assert_called_once()


@pytest.mark.parametrize('failure',['approval','role','connection','permission','audit','scope'])
def test_probe_live_rejections_no_retry(probe_live,monkeypatch,failure):
    d,kw,connector,provider=probe_live
    if failure=='approval':kw['approval']={'approved':True}
    if failure=='role':kw['selected_role']='other-reader'
    if failure=='connection':connector.side_effect=RuntimeError('secret')
    if failure=='permission':d.state.privileges=(True,True,False)
    if failure=='audit':monkeypatch.setattr(live.lab._LabAudit,'write',Mock(side_effect=OSError('secret')))
    if failure=='scope':kw['authority'].scope=model.LIVE_SCOPE
    with pytest.raises((auth.AuthorizationError,probe.ProbeBlocked)) as error:probe.execute_live_probe(**kw)
    assert 'secret' not in str(error.value)
    assert connector.call_count==(1 if failure in ('connection','permission') else 0)
    provider.assert_not_called()


def test_no_default_authority():
    with pytest.raises(PermissionError):model.execute_model_load_only()
    with pytest.raises(PermissionError):probe.execute_live_probe()
    with pytest.raises(PermissionError):boot.execute_dev()


def test_protected_credential_injection_has_explicit_parameters_only(monkeypatch):
    driver=Mock(return_value=object())
    monkeypatch.setitem(sys.modules,'psycopg',SimpleNamespace(connect=driver))
    provider=Mock(return_value='synthetic-fixture-password-not-a-real-credential')
    parameters=dict(host='127.0.0.1',port=55433,dbname='day6_lab',user='synthetic-reader',
        connect_timeout=5,autocommit=True,options='-c default_transaction_read_only=on')
    live._connect(credential_provider=provider,**parameters)
    provider.assert_called_once_with()
    driver.assert_called_once_with(password=provider.return_value,**parameters)


def test_missing_credential_cannot_initialize_driver(monkeypatch):
    driver=Mock(side_effect=AssertionError('No connection authorized'))
    monkeypatch.setitem(sys.modules,'psycopg',SimpleNamespace(connect=driver))
    with pytest.raises(PermissionError):live._connect(credential_provider=lambda:None)
    driver.assert_not_called()


@pytest.mark.parametrize('provider_kind',['wrong-channel','bare-callable','missing'])
def test_channel_binding_rejected_before_consumption(probe_live,monkeypatch,provider_kind):
    d,kw,connector,reader=probe_live
    consume=Mock(side_effect=AssertionError('Must not consume'))
    monkeypatch.setattr(auth.ConsumptionLedger,'consume',consume)
    if provider_kind=='wrong-channel':kw['credential_provider']=live.CredentialChannel('other-channel',reader)
    elif provider_kind=='bare-callable':kw['credential_provider']=reader
    else:kw['credential_provider']=None
    with pytest.raises(auth.AuthorizationError):probe.execute_live_probe(**kw)
    consume.assert_not_called();connector.assert_not_called();reader.assert_not_called()


@pytest.mark.parametrize('field,value',[
    ('host','remote.invalid'),('port',True),('dbname','other'),('cluster','wrong'),
    ('postgresql','17.0'),('pgvector','0.9.0'),('migration_sha256','0'*64),
    ('catalog_sha256','0'*64),('read_only',False),
    ('profile_id','0'*64),('snapshot_ids',['0'*64,'1'*64]),
    ('descriptor_hashes',['0'*64,'1'*64]),('selected_role','other-reader'),
    ('credential_channel_id','other-channel'),('connect_timeout',6),
    ('statement_timeout_seconds',11),('readonly',False),('isolation','read committed'),
    ('autocommit',False),('default_transaction_read_only',False),
    ('lock_timeout_ms',6000),('idle_in_transaction_session_timeout_ms',16000),
])
def test_explicit_invariants_reject_even_if_regeneration_and_signature_match(probe_live,monkeypatch,field,value):
    d,kw,connector,reader=probe_live
    request=json.loads(kw['request_canonical'])
    if field in request['database']:request['database'][field]=value
    elif field in request['connection']:request['connection'][field]=value
    else:request[field]=value
    # Independently exercise the invariant gate, rather than rely only on hash mismatch.
    kw['request_canonical']=live.canonical_json(request)
    kw['approval']=kw['authority'].issue(kw['request_canonical'],reviewer='reviewer')
    monkeypatch.setattr(live,'probe_request',Mock(return_value=kw['request_canonical']))
    consume=Mock(side_effect=AssertionError('Must not consume'))
    monkeypatch.setattr(auth.ConsumptionLedger,'consume',consume)
    with pytest.raises(auth.AuthorizationError,match='invariants'):probe.execute_live_probe(**kw)
    consume.assert_not_called();connector.assert_not_called();reader.assert_not_called()


def test_channel_binding_is_immutable_and_does_not_read_credentials():
    from dataclasses import FrozenInstanceError
    reader=Mock(side_effect=AssertionError('No secret access'))
    channel=live.CredentialChannel('protected-channel',reader)
    with pytest.raises(FrozenInstanceError):channel.credential_channel_id='other'
    reader.assert_not_called()
