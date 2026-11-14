"""Offline session/preflight tests; synthetic context only."""
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
import json

import pytest

from starter.src.chunking import fixed_size, by_paragraph
from starter.src.retrieval import RetrievalBaseline, DESCRIPTOR_COLUMNS, preflight
from starter.src.store import CHUNK_COLUMNS, StoreError
from starter.tests.test_store import profile, ingestion, store


@pytest.fixture
def backend(store, monkeypatch):
    baseline = RetrievalBaseline.from_context(store.dataset_id, store.profile_id, store.context)
    conn, cursor = Mock(), Mock()
    conn.__enter__ = Mock(return_value=conn)
    conn.__exit__ = Mock(return_value=False)
    conn.transaction.side_effect = lambda: nullcontext()
    conn.cursor.return_value = cursor
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    connect = Mock(return_value=conn)
    monkeypatch.setattr(store, '_connect', connect)
    compat = Mock(return_value=baseline.snapshots)
    monkeypatch.setattr(store, 'require_compatible_snapshots', compat)
    rows = {}
    for strategy in ('A','B'):
        chunks = [c for p in store.context.pages for c in
                  (fixed_size(p,500,50) if strategy=='A' else by_paragraph(p,500))]
        _, materialized, _ = store._prepare_snapshot(baseline.snapshots[0 if strategy=='A' else 1].namespace,
                                                    store.context, [(c,[]) for c in chunks])
        rows[strategy] = [tuple(dict(zip(CHUNK_COLUMNS,materialized[cid]))[k]
                                for k in DESCRIPTOR_COLUMNS) for cid in sorted(materialized)]
    def one():
        sql, params = cursor.execute.call_args.args
        if 'embedding_profiles' in sql:
            p = store._profile
            return (p.config['model_name'],p.config['revision'],384,p.config_canonical,p.config)
        return (30,30,0)
    cursor.fetchone.side_effect = one
    cursor.fetchall.side_effect = lambda: rows[cursor.execute.call_args.args[1][-1]]
    return SimpleNamespace(baseline=baseline,conn=conn,cursor=cursor,connect=connect,compat=compat,rows=rows)


def test_preflight_structural_and_no_vectors(store, backend):
    assert preflight(store,backend.conn,backend.baseline) == backend.baseline.snapshots
    sql = [call.args[0] for call in backend.cursor.execute.call_args_list]
    assert len([q for q in sql if 'count(*)' in q]) == 2
    assert all('embedding <=>' not in q and 'SELECT embedding' not in q for q in sql)
    assert all('text,' not in q for q in sql)


@pytest.mark.parametrize('bad', [(29,30,0),(30,29,0),(30,30,1),(31,30,0)])
def test_count_pages_provenance_mismatch(store, backend, bad):
    original = backend.cursor.fetchone.side_effect
    backend.cursor.fetchone.side_effect = lambda: (bad if 'count(*)' in backend.cursor.execute.call_args.args[0] else original())
    with pytest.raises(StoreError,match='count/pages/snapshot'):
        preflight(store,backend.conn,backend.baseline)


def test_descriptor_mismatch(store, backend):
    backend.rows['A'][0] = (*backend.rows['A'][0][:-1], {'corrupted':'fixture'})
    with pytest.raises(StoreError,match='descriptor'):
        preflight(store,backend.conn,backend.baseline)


def test_snapshot_identity_mismatch(store, backend):
    changed = replace(backend.baseline.snapshots[0], chunkset_sha256='e'*64)
    backend.compat.return_value = (changed,backend.baseline.snapshots[1])
    with pytest.raises(StoreError,match='identities'):
        preflight(store,backend.conn,backend.baseline)


def test_profile_mismatch(store, backend):
    backend.cursor.fetchone.side_effect = lambda: None
    with pytest.raises(StoreError,match='profile'):
        preflight(store,backend.conn,backend.baseline)


def test_stage4_pinning(store, backend):
    fake = replace(backend.baseline,dataset_id='day06-postgresql')
    with pytest.raises(StoreError,match='Stage 4'):
        fake.validate_approved_identity()


def test_session_once_and_cleanup(store, backend, monkeypatch):
    guard = Mock(return_value=backend.baseline.snapshots)
    monkeypatch.setattr('starter.src.retrieval.preflight',guard)
    search = Mock(return_value=[])
    monkeypatch.setattr(store,'_search_in_session',search)
    with store.retrieval_session(baseline=backend.baseline) as session:
        for s in ('A','B','C'): assert session.search(s,[1.0]+[0.0]*383) == []
        assert session.integrity == ('STRUCTURAL_INTEGRITY_VERIFIED','VECTOR_INTEGRITY_NOT_REVERIFIED')
    guard.assert_called_once()
    backend.connect.assert_called_once_with(readonly=True)
    assert search.call_count == 3
    assert all(c.args[0] is backend.conn for c in search.call_args_list)
    assert '_connection' not in vars(store)
    with pytest.raises(StoreError,match='closed'):
        session.search('B',[1.0]+[0.0]*383)
    settings = [c.args[1] for c in backend.cursor.execute.call_args_list if 'set_config' in c.args[0]]
    assert settings == [('lock_timeout','5000ms'),('statement_timeout','30000ms'),
                        ('idle_in_transaction_session_timeout','60000ms')]


def test_caught_query_error_poison_session(store, backend, monkeypatch):
    monkeypatch.setattr('starter.src.retrieval.preflight',lambda *a:backend.baseline.snapshots)
    monkeypatch.setattr(store,'_search_in_session',Mock(side_effect=RuntimeError('fixture')))
    with pytest.raises(StoreError,match='rolling back'):
        with store.retrieval_session(baseline=backend.baseline) as session:
            with pytest.raises(RuntimeError): session.search('B',[])
            with pytest.raises(StoreError,match='failed'): session.search('B',[])
    assert not session._active


@pytest.mark.parametrize('timeout',[0,-1,True,'5',300001])
def test_invalid_timeouts_before_connection(store,backend,timeout):
    with pytest.raises(StoreError):
        with store.retrieval_session(lock_timeout_ms=timeout): pass
    backend.connect.assert_not_called()


@pytest.mark.parametrize('seconds',[0,-1,True,float('inf'),float('nan'),'120'])
def test_invalid_total_deadline(store,backend,seconds):
    with pytest.raises(StoreError):
        with store.retrieval_session(deadline_seconds=seconds): pass
    backend.connect.assert_not_called()


def test_watchdog_cancels_owned_connection_and_session_fails(store,backend,monkeypatch):
    import threading
    cancelled=threading.Event()
    backend.conn.closed=False
    backend.conn.cancel_safe.side_effect=lambda **kwargs:cancelled.set()
    monkeypatch.setattr('starter.src.retrieval.preflight',lambda *args:backend.baseline.snapshots)
    def slow(*args):
        assert cancelled.wait(1)
        return []
    monkeypatch.setattr(store,'_search_in_session',slow)
    with pytest.raises(TimeoutError):
        with store.retrieval_session(baseline=backend.baseline,deadline_seconds=.05) as session:
            session.search('B',[1.0]+[0.0]*383)
    assert not session._active
    backend.conn.cancel_safe.assert_called_once_with(timeout=1.0)
    backend.conn.__exit__.assert_called_once()
    backend.connect.assert_called_once()


def test_deadline_includes_preflight(store,backend,monkeypatch):
    import threading
    cancelled=threading.Event()
    backend.conn.closed=False
    backend.conn.cancel_safe.side_effect=lambda **kwargs:cancelled.set()
    def slow(*args):
        assert cancelled.wait(1)
        return backend.baseline.snapshots
    monkeypatch.setattr('starter.src.retrieval.preflight',slow)
    with pytest.raises(TimeoutError):
        with store.retrieval_session(baseline=backend.baseline,deadline_seconds=.05): pass
    backend.conn.__exit__.assert_called_once()


def test_deadline_timer_disarmed_on_normal_exit(store,backend,monkeypatch):
    monkeypatch.setattr('starter.src.retrieval.preflight',lambda *args:backend.baseline.snapshots)
    with store.retrieval_session(baseline=backend.baseline,deadline_seconds=10) as session:
        deadline=session._deadline
    assert not deadline.timer.is_alive()
    backend.conn.cancel_safe.assert_not_called()


def test_watchdog_disarmed_before_transaction_and_connection_exit(store,backend,monkeypatch):
    from contextlib import contextmanager
    monkeypatch.setattr('starter.src.retrieval.preflight',lambda *a:backend.baseline.snapshots)
    deadline_box=[]
    @contextmanager
    def transaction():
        try: yield
        finally:
            d=deadline_box[0]
            assert d._closed and not d.timer.is_alive() and d.connection is None
    backend.conn.transaction.side_effect=transaction
    with store.retrieval_session(baseline=backend.baseline,deadline_seconds=10) as session:
        deadline_box.append(session._deadline)
    backend.conn.cancel_safe.assert_not_called()


def test_disarm_waits_for_inflight_cancellation():
    import threading
    from starter.src.retrieval import RetrievalDeadline
    entered,release,closed=threading.Event(),threading.Event(),threading.Event()
    conn=Mock(closed=False)
    def cancel(**kwargs):
        entered.set()
        assert release.wait(1)
    conn.cancel_safe.side_effect=cancel
    deadline=RetrievalDeadline(.01);deadline.bind(conn);deadline.timer.start()
    assert entered.wait(1)
    worker=threading.Thread(target=lambda:(deadline.close(),closed.set()))
    worker.start()
    assert not closed.wait(.03)
    release.set();worker.join(1)
    assert closed.is_set() and deadline.connection is None
    assert not deadline.timer.is_alive()
    deadline._cancel()  # stale callback cannot cancel after disarm
    conn.cancel_safe.assert_called_once()
