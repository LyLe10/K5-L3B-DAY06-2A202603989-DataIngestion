"""Offline local-lab wiring: temporary synthetic model/benchmark and fake DB only."""
import ast
from contextlib import contextmanager
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest
from starter.scripts import run_local_lab_dev as lab
from starter.src import evaluation_runner as runner
from starter.tests.test_evaluation_runner import setup, IDENTITY
from starter.tests.test_benchmark import sample, bundle, frozen_bundle
from starter.tests.test_store import profile, ingestion, store
from starter.tests.test_retrieval_session import backend


def args():
    return SimpleNamespace(split='dev', top_k=3, deadline_seconds=120, role='lab_reader',
        output='data/local/lab_benchmark/dev/synthetic',
        query_cache='data/local/lab_benchmark/query_cache/synthetic')


@pytest.fixture
def wired(setup, monkeypatch):
    s = setup
    snapshot = s.root / 'synthetic-model'
    snapshot.mkdir()
    (snapshot / 'config.json').write_text('synthetic only')
    prepared = SimpleNamespace(bundle=s.loaded, baseline=s.baseline, profile=s.adapter.profile, context=None,
        plan=dict(code=deepcopy(IDENTITY),
            model=dict(snapshot='synthetic-model', model_name='synthetic', revision='fixture',
                profile=dict(artifact_sha256={'config.json':'synthetic'}))))
    prepare = Mock(return_value=prepared)
    def model(*a, **kw):
        s.adapter._cache_dir = kw['cache_dir']
        return s.adapter
    factory = Mock(side_effect=model)
    def producer(*a, **kw):
        value=runner.QueryProducer(*a, **kw)
        original=value.prepare
        def prepare_inputs(questions):
            assert len(questions)==15
            assert all(set(q)=={'id','question','filter'} for q in questions)
            return original(questions)
        value.prepare=prepare_inputs
        return value
    runner_binding=SimpleNamespace(QueryProducer=producer,DEFAULT_CONFIG=runner.DEFAULT_CONFIG,
        run_evaluation=runner.run_evaluation,file_sha=runner.file_sha,write_artifacts=runner.write_artifacts)
    monkeypatch.setattr(lab, 'dependencies', lambda: (SimpleNamespace(prepare_dev=prepare),
        SimpleNamespace(MyEmbedder=factory), runner_binding, None))
    monkeypatch.setattr(lab, 'make_store', Mock(return_value=s.store))
    return s, prepare, factory


def test_real_runner_dev_wiring_and_private_trace(wired):
    s, prepare, factory = wired
    assert lab.execute(args(), root=s.root, password_reader=Mock()) == 0
    raw = json.loads((s.root/args().output/'raw_run.json').read_text())
    assert raw['manifest']['provenance'] == 'local_lab_dev'
    assert raw['manifest']['protected_stage5_authorization'] is False
    assert len(raw['traces']) == 45 and len(s.adapter.calls) == 15
    assert [x[0] for x in s.state.searches] == ['A','B','C']*15
    assert {x['split'] for x in raw['traces']} == {'dev'}
    assert raw['manifest']['configuration']['top_k'] == 3
    assert not (s.root/'data/local/stage5').exists()
    before = (s.root/args().output/'raw_run.json').read_bytes()
    with pytest.raises(FileExistsError):lab.execute(args(), root=s.root)
    assert (s.root/args().output/'raw_run.json').read_bytes() == before
    assert factory.call_count == 1


def test_failure_nonzero_and_no_backend_secret(wired):
    s, _, _ = wired
    s.state.fail_at = 2
    assert lab.execute(args(), root=s.root) == 1
    raw = (s.root/args().output/'raw_run.json').read_text()
    assert 'DO_NOT_EXPORT' not in raw
    assert json.loads(raw)['summary'] is None


@pytest.mark.parametrize('field,value', [('split','test'),('split','all'),('top_k',5),('deadline_seconds',121)])
def test_invalid_plan_rejected_before_dependencies(tmp_path, monkeypatch, field, value):
    dependency = Mock(side_effect=AssertionError('no access'))
    monkeypatch.setattr(lab, 'dependencies', dependency)
    a=args();setattr(a,field,value)
    with pytest.raises(ValueError):lab.execute(a,root=tmp_path)
    dependency.assert_not_called()


@pytest.mark.parametrize('value', ['data/local/stage5/runs/x','data/local/lab_benchmark/dev/../x','/tmp/out'])
def test_destinations_reject_escape(tmp_path,value):
    with pytest.raises(ValueError):lab.lab_path(tmp_path,value,'dev')


def test_existing_cache_rejected_before_loading(wired):
    s, prepare, factory=wired
    (s.root/args().query_cache).mkdir(parents=True)
    with pytest.raises(FileExistsError):lab.execute(args(),root=s.root)
    prepare.assert_not_called();factory.assert_not_called()


def test_cli_test_rejected(monkeypatch):
    execution=Mock();monkeypatch.setattr(lab,'execute',execution)
    with pytest.raises(SystemExit) as error:
        lab.main(['--split','test','--role','reader','--output','x','--query-cache','y'])
    assert error.value.code != 0
    execution.assert_not_called()


def test_symlink_destination_rejected(tmp_path):
    base=tmp_path/'data/local/lab_benchmark';base.mkdir(parents=True)
    other=tmp_path/'other';other.mkdir()
    (base/'dev').symlink_to(other,target_is_directory=True)
    with pytest.raises(ValueError):lab.lab_path(tmp_path,'data/local/lab_benchmark/dev/run','dev')


def test_main_sanitizes_all_failure_text(monkeypatch,capsys):
    monkeypatch.setattr(lab,'execute',Mock(side_effect=RuntimeError('password=DO_NOT_EXPORT')))
    assert lab.main(['--role','reader','--output','unused','--query-cache','unused']) == 1
    assert capsys.readouterr().err == 'LOCAL_LAB_DEV_FAILED_NO_RETRY\n'


def test_connector_explicit_identity_readonly_no_write(monkeypatch):
    class Base:
        def __init__(self,*a,**kw):pass
    connection=SimpleNamespace(info=SimpleNamespace(host='127.0.0.1',port=55433,dbname='day6_lab',user='reader'),close=Mock())
    connect=Mock(return_value=connection)
    monkeypatch.setitem(sys.modules,'psycopg',SimpleNamespace(connect=connect))
    reader=Mock(return_value='DO_NOT_EXPORT')
    p=SimpleNamespace(baseline=SimpleNamespace(dataset_id='fixture'),profile=SimpleNamespace(profile_id='a'*64),context=None)
    store=lab.make_store(p,'reader',reader,SimpleNamespace(PgVectorStore=Base),SimpleNamespace(CLUSTER='fixture'))
    with pytest.raises(PermissionError):store._connect()
    reader.assert_not_called()
    assert store._connect(readonly=True) is connection
    kw=connect.call_args.kwargs
    assert kw['password']=='DO_NOT_EXPORT' and kw['user']=='reader'
    assert kw['options']=='-c default_transaction_read_only=on' and kw['autocommit'] is True
    connection.info.user='wrong'
    with pytest.raises(PermissionError):store._connect(readonly=True)
    connection.close.assert_called_once()


@pytest.mark.parametrize('accepted',[True,False])
def test_database_identity_checked_before_yield(accepted):
    cursor=Mock()
    cursor.fetchone.return_value=('day6_lab','160016','fixture','0.8.7','reader','reader','on') if accepted else ('wrong',)
    cursor.fetchall.return_value=[('a'*64, 'a'*64)]
    cursor_context=Mock()
    cursor_context.__enter__=Mock(return_value=cursor)
    cursor_context.__exit__=Mock(return_value=False)
    session=SimpleNamespace(_connection=SimpleNamespace(cursor=Mock(return_value=cursor_context)))
    events=[]
    class Base:
        def __init__(self,*a,**kw):pass
        @contextmanager
        def retrieval_session(self,**kw):
            events.append('transaction')
            try:yield session
            finally:events.append('cleanup')
    p=SimpleNamespace(baseline=SimpleNamespace(dataset_id='fixture'),profile=SimpleNamespace(profile_id='a'*64),context=None)
    store=lab.make_store(p,'reader',Mock(),SimpleNamespace(PgVectorStore=Base),
        SimpleNamespace(CLUSTER='fixture',APPROVED_CATALOG='a'*64))
    if accepted:
        with store.retrieval_session() as result:
            assert result is session
            cursor.fetchone.assert_called_once()
            events.append('search_allowed')
    else:
        with pytest.raises(PermissionError):
            with store.retrieval_session():pytest.fail('must not yield searches')
    assert events == (['transaction','search_allowed','cleanup'] if accepted else ['transaction','cleanup'])
    assert cursor.execute.call_args.args[0].startswith('SELECT ')


@pytest.mark.parametrize('case', [
    'match', 'self_consistent_unapproved', 'stored_mismatch', 'missing_pin',
    'null_pin', 'invalid_pin', 'no_rows', 'null_actual', 'extra_rows',
    'execute_error', 'fetch_error',
])
def test_catalog_pin_in_real_retrieval_transaction(store, backend, monkeypatch, case):
    from starter.src import store as store_module

    approved='a'*64
    rows=[(approved,approved)]
    if case=='self_consistent_unapproved': rows=[('b'*64,'b'*64)]
    elif case=='stored_mismatch': rows=[('b'*64,approved)]
    elif case=='no_rows': rows=[]
    elif case=='null_actual': rows=[(approved,None)]
    elif case=='extra_rows': rows=rows*2
    boot=SimpleNamespace(CLUSTER='fixture',APPROVED_CATALOG=approved)
    if case=='missing_pin': del boot.APPROVED_CATALOG
    elif case=='null_pin': boot.APPROVED_CATALOG=None
    elif case=='invalid_pin': boot.APPROVED_CATALOG='not-a-sha256'

    prepared=SimpleNamespace(baseline=backend.baseline,profile=store._profile,context=store.context)
    local=lab.make_store(prepared,'reader',Mock(),store_module,boot)
    monkeypatch.setattr(local,'_connect',backend.connect)
    monkeypatch.setattr(local,'require_compatible_snapshots',backend.compat)
    events=[]
    active=False
    @contextmanager
    def transaction():
        nonlocal active
        assert not active
        active=True
        events.append('transaction')
        try: yield
        finally:
            active=False
            events.append('cleanup')
    backend.conn.transaction.side_effect=transaction
    original_one=backend.cursor.fetchone.side_effect
    original_all=backend.cursor.fetchall.side_effect
    def execute(sql,*params):
        assert active
        if 'catalog_fingerprint()' in sql:
            events.append('catalog')
            if case=='execute_error': raise RuntimeError('password=DO_NOT_EXPORT')
    def one():
        if 'current_database()' in backend.cursor.execute.call_args.args[0]:
            return ('day6_lab','160016','fixture','0.8.7','reader','reader','on')
        return original_one()
    def all_rows():
        if 'catalog_fingerprint()' in backend.cursor.execute.call_args.args[0]:
            if case=='fetch_error': raise RuntimeError('password=DO_NOT_EXPORT')
            return rows
        return original_all()
    backend.cursor.execute.side_effect=execute
    backend.cursor.fetchone.side_effect=one
    backend.cursor.fetchall.side_effect=all_rows
    def search(connection,*args):
        assert active and connection is backend.conn
        assert events==['transaction','catalog']
        return []
    searches=Mock(side_effect=search)
    monkeypatch.setattr(local,'_search_in_session',searches)

    if case=='match':
        with local.retrieval_session(baseline=backend.baseline) as session:
            assert session._connection is backend.conn
            for strategy in ('A','B','C'):
                assert session.search(strategy,[1.0]+[0.0]*383)==[]
        assert searches.call_count==3
    else:
        with pytest.raises(PermissionError) as error:
            with local.retrieval_session(baseline=backend.baseline) as session:
                session.search('A',[1.0]+[0.0]*383)
        assert 'DO_NOT_EXPORT' not in str(error.value)
        searches.assert_not_called()
    assert not active
    if case in ('missing_pin','null_pin','invalid_pin'):
        backend.connect.assert_not_called()
        assert events==[]
    else:
        assert events==['transaction','catalog','cleanup']
        backend.connect.assert_called_once_with(readonly=True)
        backend.conn.transaction.assert_called_once()
        backend.conn.__exit__.assert_called_once()
        sql=[call.args[0] for call in backend.cursor.execute.call_args_list]
        assert sql[0]=='SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'
        assert sum('catalog_fingerprint()' in query for query in sql)==1


def test_password_requires_interactive_terminal(monkeypatch):
    monkeypatch.setattr(sys.stdin,'isatty',lambda:False)
    reader=Mock();monkeypatch.setattr(lab.getpass,'getpass',reader)
    with pytest.raises(PermissionError):lab.terminal_password()
    reader.assert_not_called()


def test_import_has_no_runtime_or_heavy_imports(monkeypatch):
    monkeypatch.setattr(lab.getpass,'getpass',Mock(side_effect=AssertionError('secret access')))
    spec=importlib.util.spec_from_file_location('isolated_local_lab',lab.__file__)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    tree=ast.parse(Path(lab.__file__).read_text())
    forbidden={'live_dev_runtime','live_probe','dev_authorization','lab_dev_runtime','model_load_only','database_probe'}
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom):assert not forbidden.intersection((node.module or '').split('.'))
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
            assert node.func.attr not in {'sync_snapshot','upsert','register','consume','execute_live_dev','execute_live_probe','embed_documents'}
