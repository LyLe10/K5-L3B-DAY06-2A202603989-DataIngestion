"""Synthetic permission/identity responses only; no PostgreSQL or credential access."""
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from starter.src import database_probe as probe, dev_bootstrap as boot
from starter.src.retrieval import RetrievalBaseline
from starter.tests.test_store import profile, ingestion, store


@pytest.fixture
def db_probe(store,monkeypatch):
    original=RetrievalBaseline.from_context(store.dataset_id,store.profile_id,store.context)
    snapshots=tuple(replace(s,selected_page_count=40,expected_count=n,actual_count=n)
                    for s,n in zip(original.snapshots,(246,264)))
    baseline=replace(original,snapshots=snapshots)
    # Explicit synthetic identity pins; these do not modify baseline files or data.
    monkeypatch.setattr(boot,'DATASET',store.dataset_id)
    monkeypatch.setattr(boot,'STAGE4_PROFILE',store.profile_id)
    monkeypatch.setattr(boot,'STAGE4_SNAPSHOTS',tuple(s.snapshot_id for s in snapshots))
    plan=dict(split='dev',profile_id=store.profile_id,descriptor_hashes=list(baseline.descriptor_hashes),
        database=dict(probe.TARGET,cluster=boot.CLUSTER,postgresql='16.16',pgvector='0.8.7',
            migration_sha256=boot.MIGRATION_SHA256,catalog_sha256=boot.APPROVED_CATALOG,read_only=True))
    prepared=SimpleNamespace(plan=plan,profile=store._profile,baseline=baseline,context=store.context)
    state=SimpleNamespace(active=False,commits=0,rollbacks=0,identity=('day6_lab','160016','on',boot.CLUSTER,'0.8.7'),
        permissions=('synthetic-reader','synthetic-reader',True,True,True,True,True,
                     False,False,False,False,False,False,False,'on','repeatable read','10s'),
        tables=[(name,True) for name in sorted(probe.TABLES)],counts=(1,2,510),privileges=(True,False,False),
        migration=(1,boot.MIGRATION_SHA256,boot.APPROVED_CATALOG,boot.APPROVED_CATALOG))
    connection,cursor=Mock(),Mock()
    connection.info=SimpleNamespace(**probe.TARGET)
    connection.__enter__=Mock(return_value=connection);connection.__exit__=Mock(return_value=False)
    cursor.__enter__=Mock(return_value=cursor);cursor.__exit__=Mock(return_value=False)
    connection.cursor.return_value=cursor
    @contextmanager
    def transaction():
        state.active=True
        try:yield
        except BaseException:state.rollbacks+=1;raise
        else:state.commits+=1
        finally:state.active=False
    connection.transaction.side_effect=transaction
    def one():
        sql=cursor.execute.call_args.args[0]
        if 'to_regclass' in sql:return ('day6_ingestion.schema_migrations',)
        if sql==probe.PERMISSIONS_SQL:return state.permissions
        if sql.startswith('SELECT (SELECT count'):return state.counts
        if 'SELECT current_database()' in sql:return state.identity
        if 'SELECT bool_and' in sql:return state.privileges
        raise AssertionError('Unexpected synthetic fetchone SQL')
    def many():
        sql=cursor.execute.call_args.args[0]
        if sql.startswith('SELECT version,name,checksum'):
            return [(1,'0001_day6_ingestion.sql',*state.migration[1:])]
        if sql.startswith('SELECT version,checksum'):return [state.migration]
        if sql.startswith('SELECT c.relname'):return state.tables
        raise AssertionError('Unexpected synthetic fetchall SQL')
    cursor.fetchone.side_effect=one;cursor.fetchall.side_effect=many
    guard=Mock(side_effect=lambda actual_store,conn,base: (
        snapshots if state.active and conn is connection and base is baseline
        and actual_store.profile_id==store.profile_id else None))
    monkeypatch.setattr(probe,'preflight',guard)
    never_connect=Mock(side_effect=AssertionError('Store must not connect separately'))
    monkeypatch.setattr(probe.PgVectorStore,'_connect',never_connect)
    factory=Mock(return_value=connection)
    return SimpleNamespace(prepared=prepared,state=state,connection=connection,cursor=cursor,
        factory=factory,guard=guard,never_connect=never_connect)


def run(db,one_shot=None):
    return (one_shot or probe.OneShotOfflineProbe()).inspect(db.prepared,selected_role='synthetic-reader',
                                                          connection_factory=db.factory)


def test_valid_mock_probe_uses_one_connection_and_same_transaction(db_probe):
    d=db_probe;result=run(d)
    assert result['status']=='PASS' and result['scope']=='OFFLINE_SYNTHETIC_PROBE'
    assert result['counts']==dict(profiles=1,snapshots=2,A=246,B=264,total=510)
    assert result['structural']=='STRUCTURAL_INTEGRITY_VERIFIED'
    assert result['vector_integrity']=='VECTOR_INTEGRITY_NOT_REVERIFIED'
    d.factory.assert_called_once_with(target=probe.TARGET,selected_role='synthetic-reader',readonly=True,
        connect_timeout=5,autocommit=True,options='-c default_transaction_read_only=on')
    d.connection.transaction.assert_called_once();d.guard.assert_called_once();d.never_connect.assert_not_called()
    d.connection.__exit__.assert_called_once()
    assert not d.state.active and d.state.commits==1 and d.state.rollbacks==0
    sql=[call.args[0].strip() for call in d.cursor.execute.call_args_list]
    assert sql[0]=='SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'
    assert all(s.startswith(('SELECT ','SET TRANSACTION ')) for s in sql)
    assert not any('<=>' in s or 'SELECT embedding' in s for s in sql)
    assert any("'10000ms'" in s for s in sql)


@pytest.mark.parametrize('index',range(2,7))
def test_missing_minimum_permission_rejected(db_probe,index):
    row=list(db_probe.state.permissions);row[index]=False;db_probe.state.permissions=tuple(row)
    with pytest.raises(probe.ProbeBlocked,match='INSUFFICIENT'):run(db_probe)
    assert db_probe.state.rollbacks==1;db_probe.guard.assert_not_called()


@pytest.mark.parametrize('index',range(7,13))
def test_elevation_membership_create_write_ownership_rejected(db_probe,index):
    row=list(db_probe.state.permissions);row[index]=True;db_probe.state.permissions=tuple(row)
    with pytest.raises(probe.ProbeBlocked,match='INSUFFICIENT'):run(db_probe)
    db_probe.guard.assert_not_called()


@pytest.mark.parametrize('index,value',[(0,'other-login'),(1,'set-role'),(2,None),(14,'off'),
                                     (15,'read committed'),(16,'30s')])
def test_role_session_or_unknown_permissions_blocked(db_probe,index,value):
    row=list(db_probe.state.permissions);row[index]=value;db_probe.state.permissions=tuple(row)
    with pytest.raises(probe.ProbeBlocked):run(db_probe)
    assert not db_probe.state.active


def test_temp_privilege_reported_without_claiming_cluster_wide_select_only(db_probe):
    row=list(db_probe.state.permissions);row[13]=True;db_probe.state.permissions=tuple(row)
    assert run(db_probe)['warnings']==['TEMP_PRIVILEGE_PRESENT_QUERY_LIST_ONLY']


@pytest.mark.parametrize('index,value',[(0,'wrong-db'),(1,'160015'),(2,'off'),(3,'wrong-cluster'),(4,'0.8.6')])
def test_wrong_server_identity_blocks_and_closes(db_probe,index,value):
    row=list(db_probe.state.identity);row[index]=value;db_probe.state.identity=tuple(row)
    with pytest.raises(probe.ProbeBlocked):run(db_probe)
    db_probe.connection.__exit__.assert_called_once();db_probe.factory.assert_called_once()


@pytest.mark.parametrize('field,value',[('host','localhost'),('port',55434),('dbname','other'),
    ('cluster','unknown'),('migration_sha256','0'*64),('catalog_sha256','0'*64)])
def test_unapproved_target_never_calls_factory(db_probe,field,value):
    db_probe.prepared.plan['database'][field]=value
    with pytest.raises(probe.ProbeBlocked):run(db_probe)
    db_probe.factory.assert_not_called()


@pytest.mark.parametrize('kind',['client_endpoint','migration','catalog','tables','counts','extra_profile',
                                'incomplete_snapshot','descriptor','unknown_preflight','privileged'])
def test_metadata_schema_and_structural_failures(db_probe,kind):
    d=db_probe
    if kind=='client_endpoint':d.connection.info.port=55434
    elif kind=='migration':d.state.migration=(1,'0'*64,*d.state.migration[2:])
    elif kind=='catalog':d.state.migration=(1,d.state.migration[1],'0'*64,'0'*64)
    elif kind=='tables':d.state.tables.pop()
    elif kind=='counts':d.state.counts=(1,2,509)
    elif kind=='extra_profile':d.state.counts=(2,2,510)
    elif kind=='incomplete_snapshot':d.guard.side_effect=ValueError('synthetic incomplete ledger')
    elif kind=='descriptor':d.guard.side_effect=ValueError('synthetic descriptor mismatch')
    elif kind=='unknown_preflight':d.guard.side_effect=None;d.guard.return_value=None
    else:d.state.privileges=(True,True,False)
    with pytest.raises(probe.ProbeBlocked):run(d)
    d.connection.__exit__.assert_called_once();d.factory.assert_called_once()


@pytest.mark.parametrize('kind',['connection','permission','timeout','unknown'])
def test_backend_errors_sanitized_no_retry(db_probe,kind):
    d=db_probe
    error=RuntimeError('postgresql://fixture:DO_NOT_EXPORT@private/secret')
    if kind=='permission':error.sqlstate='42501';d.cursor.execute.side_effect=error
    elif kind=='timeout':d.cursor.execute.side_effect=TimeoutError('DO_NOT_EXPORT')
    elif kind=='unknown':d.connection.__exit__.side_effect=error
    else:d.factory.side_effect=error
    one_shot=probe.OneShotOfflineProbe()
    with pytest.raises(probe.ProbeBlocked) as result:run(d,one_shot)
    assert 'DO_NOT_EXPORT' not in str(result.value)
    with pytest.raises(probe.ProbeBlocked,match='already attempted'):run(d,one_shot)
    d.factory.assert_called_once()


def test_concurrent_instance_attempts_only_one_factory_call(db_probe):
    one_shot=probe.OneShotOfflineProbe();barrier=threading.Barrier(2)
    def attempt(_):
        barrier.wait()
        try:run(db_probe,one_shot);return True
        except probe.ProbeBlocked:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(attempt,range(2)))==[False,True]
    db_probe.factory.assert_called_once()


def test_live_entry_and_real_factory_remain_disabled(db_probe):
    with pytest.raises(PermissionError,match='DISABLED'):probe.execute_live_probe(approved=True,force=True)
    with pytest.raises(PermissionError):boot.execute_dev()
    with pytest.raises(probe.ProbeBlocked):
        probe.OneShotOfflineProbe().inspect(db_probe.prepared,selected_role='reader',connection_factory=lambda:None)
    db_probe.factory.assert_not_called()


@pytest.mark.parametrize('kind',['profile','snapshot','descriptor','split','count_type','grant_type'])
def test_additional_approved_identity_and_unknown_type_rejections(db_probe,kind):
    d=db_probe
    if kind=='profile':d.prepared.plan['profile_id']='0'*64
    elif kind=='snapshot':
        d.prepared.baseline=replace(d.prepared.baseline,snapshots=tuple(reversed(d.prepared.baseline.snapshots)))
    elif kind=='descriptor':d.prepared.plan['descriptor_hashes']=['0'*64,'0'*64]
    elif kind=='split':d.prepared.plan['split']='test'
    elif kind=='count_type':d.state.counts=(True,2,510)
    else:d.state.tables=[(name,1) for name in sorted(probe.TABLES)]
    with pytest.raises(probe.ProbeBlocked):run(d)
    if kind in ('profile','snapshot','descriptor','split'):d.factory.assert_not_called()
