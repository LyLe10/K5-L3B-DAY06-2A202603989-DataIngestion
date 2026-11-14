"""Explicit isolated integration cases; synthetic fixtures, never benchmark data."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import math
import time

import psycopg
import pytest

from starter.tests.postgres_store_cases import subject, sync, inputs, connect, SafeStore, DSN
from starter.src.retrieval import RetrievalBaseline
from starter.src.store import StoreError

Q = [1.0]+[0.0]*383
EVIDENCE = []


def record(name, **fields):
    EVIDENCE.append(dict(case=name, **fields))


@pytest.fixture
def ready(subject):
    store, corpus = subject
    for strategy in ('A','B'):
        chunks, vectors = inputs(store,strategy)
        vectors = [Q.copy() if c.page <= 15 else [0.6,0.8]+[0.0]*382 for c in chunks]
        store.sync_snapshot(strategy,chunks,vectors,vector_chunk_ids=[c.chunk_id for c in chunks],
                            embedding_profile_id=store.profile_id)
    return store


@pytest.mark.parametrize('strategy',['A','B','C'])
def test_cosine_tie_score_and_mapping(ready,strategy):
    hits = ready.search(strategy,Q,30)
    assert len(hits)==30
    assert [(h['cosine_distance'],h['chunk_id']) for h in hits] == sorted(
        (h['cosine_distance'],h['chunk_id']) for h in hits)
    assert all(h['cosine_distance']==pytest.approx(0) for h in hits[:15])
    assert all(h['cosine_distance']==pytest.approx(0.4,abs=1e-6) for h in hits[15:])
    assert hits[0]['score']==pytest.approx(1)
    assert all(h['stored_strategy']==('B' if strategy=='C' else strategy) for h in hits)
    assert all(h['metadata']['physical_page']==h['physical_page'] for h in hits)
    assert all(h['end_char']-h['start_char']==len(h['text']) for h in hits)
    record('ranking_'+strategy,rows=30,real_cosine=True,tie_breaking=True)


def test_filter_before_limit(ready):
    assert all(h['section']=='alpha' for h in ready.search('B',Q))
    hits=ready.search('C',Q,3,{'section':'beta'})
    assert len(hits)==3 and all(h['section']=='beta' for h in hits)
    assert ready.search('C',Q,3,{'section':"beta' OR TRUE --"})==[]
    record('filter_before_limit',filtered_rows=3,parameter_binding=True)


def test_b_equals_c_and_preflight_once(ready,monkeypatch):
    import starter.src.retrieval as module
    real=module.preflight
    calls=[]
    def wrapped(*args):
        calls.append(1)
        return real(*args)
    monkeypatch.setattr(module,'preflight',wrapped)
    with ready.retrieval_session() as session:
        b=session.search('B',Q)
        c=session.search('C',Q)
        assert [{k:v for k,v in h.items() if k!='requested_strategy'} for h in b]==[
            {k:v for k,v in h.items() if k!='requested_strategy'} for h in c]
        assert session.integrity==('STRUCTURAL_INTEGRITY_VERIFIED','VECTOR_INTEGRITY_NOT_REVERIFIED')
        assert session._connection.execute('SHOW transaction_isolation').fetchone()==('repeatable read',)
        assert session._connection.execute('SHOW transaction_read_only').fetchone()==('on',)
    assert len(calls)==1
    with pytest.raises(StoreError): session.search('B',Q)
    record('session_once',preflight_calls=1,isolation='repeatable read',read_only=True)


def test_namespace_isolation(ready):
    other=SafeStore(DSN,384,dataset_id=ready.dataset_id+'-other',profile_id=ready.profile_id,
                    profile=ready._profile,context=ready.context)
    sync(other,'A');sync(other,'B')
    assert all(h['dataset_id']==ready.dataset_id for h in ready.search('A',Q,100))
    assert all(h['dataset_id']==other.dataset_id for h in other.search('B',Q,100))
    record('namespace_isolation',other_dataset=True)


def test_missing_ledger(subject):
    store,_=subject
    sync(store,'A')
    with pytest.raises(StoreError,match='Missing'): store.search('A',Q)


@pytest.mark.parametrize('mutation,sqlstate',[
    ("UPDATE day6_ingestion.strategy_snapshots SET status='syncing',actual_count=0,completed_at=NULL WHERE dataset_id=%s",'P0001'),
    ("DELETE FROM day6_ingestion.chunks WHERE dataset_id=%s AND strategy='A'",'P0001'),
    ("UPDATE day6_ingestion.chunks SET snapshot_id=repeat('f',64) WHERE dataset_id=%s AND strategy='A'",'23503'),
])
def test_invalid_committed_states_rejected(ready,mutation,sqlstate):
    # No triggers/constraints disabled. These states cannot be committed under
    # 0001. Guard detection of impossible committed corruption is unit-tested.
    with connect() as conn:
        with pytest.raises(psycopg.Error) as exc:
            with conn.transaction(): conn.execute(mutation,(ready.dataset_id,))
        assert exc.value.sqlstate==sqlstate
    assert len(ready.search('B',Q))==3
    record('mutation_rejected',sqlstate=sqlstate,rollback_verified=True)


def test_approved_identity_mismatch(ready):
    baseline=RetrievalBaseline.from_context(ready.dataset_id,ready.profile_id,ready.context)
    bad=replace(baseline,snapshots=(replace(baseline.snapshots[0],chunkset_sha256='e'*64),baseline.snapshots[1]))
    with pytest.raises(StoreError,match='identities'):
        with ready.retrieval_session(baseline=bad): pass


def test_readonly_enforced_and_cleanup(ready,monkeypatch):
    def illegal(connection,*args):
        connection.execute('DELETE FROM day6_ingestion.chunks WHERE dataset_id=%s',(ready.dataset_id,))
    monkeypatch.setattr(ready,'_search_in_session',illegal)
    with pytest.raises(psycopg.Error) as exc:
        with ready.retrieval_session() as session: session.search('B',Q)
    assert exc.value.sqlstate=='25006'
    assert not session._active and session._connection.closed
    record('readonly_enforcement',sqlstate=exc.value.sqlstate,connection_closed=True)


def test_query_error_rollback_and_no_retry(ready,monkeypatch):
    connections=[]
    real=ready._connect
    def capture(**kwargs):
        conn=real(**kwargs);connections.append(conn);return conn
    monkeypatch.setattr(ready,'_connect',capture)
    monkeypatch.setattr(ready,'_search_in_session',lambda conn,*args:conn.execute('SELECT 1/0'))
    with pytest.raises(psycopg.Error) as exc:
        with ready.retrieval_session() as session: session.search('B',Q)
    assert exc.value.sqlstate=='22012'
    assert len(connections)==1 and connections[0].closed
    record('query_error_cleanup',sqlstate='22012',connections=1)


def test_statement_timeout_cleanup(ready,monkeypatch):
    monkeypatch.setattr(ready,'_search_in_session',lambda conn,*args:conn.execute('SELECT pg_sleep(1)'))
    # Preflight uses normal timeout; tighten only the query under test.
    with pytest.raises(psycopg.Error) as exc:
        with ready.retrieval_session() as session:
            session._connection.execute("SELECT set_config('statement_timeout','50ms',true)")
            session.search('B',Q)
    assert exc.value.sqlstate=='57014' and session._connection.closed
    record('statement_timeout',sqlstate='57014',connection_closed=True)


def test_shared_locks_block_sync_and_cleanup(ready):
    chunks,vectors=inputs(ready,'B')
    changed=[[-1.0]+[0.0]*383 for c in chunks]
    with ThreadPoolExecutor(max_workers=1) as pool:
        with ready.retrieval_session() as session:
            before=session.search('B',Q)
            future=pool.submit(ready.sync_snapshot,'B',chunks,changed,
                               vector_chunk_ids=[c.chunk_id for c in chunks],embedding_profile_id=ready.profile_id)
            deadline=time.monotonic()+4
            with connect() as observer:
                while time.monotonic()<deadline:
                    waiting=observer.execute("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND NOT granted").fetchone()[0]
                    if waiting: break
                    time.sleep(0.03)
            assert waiting and not future.done()
            assert session.search('B',Q)==before
        result=future.result(timeout=8)
    assert result['written_rows']==30
    assert ready.search('B',Q)[0]['cosine_distance']==pytest.approx(2)
    record('concurrent_sync',writer_wait_observed=True,session_stable=True,writer_completed_after_exit=True)


def test_repeatable_read_other_namespace_commits(ready):
    other=SafeStore(DSN,384,dataset_id=ready.dataset_id+'-other',profile_id=ready.profile_id,
                    profile=ready._profile,context=ready.context)
    with ready.retrieval_session() as session:
        query='SELECT count(*) FROM day6_ingestion.chunks WHERE dataset_id=%s'
        assert session._connection.execute(query,(other.dataset_id,)).fetchone()==(0,)
        with ThreadPoolExecutor(max_workers=1) as pool: pool.submit(sync,other,'A').result(timeout=8)
        assert session._connection.execute(query,(other.dataset_id,)).fetchone()==(0,)
    with connect() as conn: assert conn.execute(query,(other.dataset_id,)).fetchone()==(30,)
    record('mvcc',other_namespace_writer_committed=True,repeatable_read_stable=True)


def test_lock_timeout_cleanup(ready):
    from starter.src.schema import Namespace
    with connect() as blocker:
        with blocker.transaction():
            blocker.execute('SELECT pg_advisory_xact_lock(%s)',
                            (Namespace(ready.dataset_id,ready.profile_id,'B').lock_key,))
            with ThreadPoolExecutor(max_workers=1) as pool:
                def attempt():
                    with ready.retrieval_session(lock_timeout_ms=100): pass
                with pytest.raises(psycopg.Error) as exc: pool.submit(attempt).result(timeout=5)
            assert exc.value.sqlstate=='55P03'
    assert len(ready.search('B',Q))==3
    record('lock_timeout',sqlstate='55P03',subsequent_session_succeeds=True)


def test_catalog_unchanged(ready):
    with connect() as conn:
        row=conn.execute('SELECT checksum,catalog_sha256,day6_ingestion.catalog_fingerprint() '
                         'FROM day6_ingestion.schema_migrations').fetchone()
        assert row[0]=='04f891492379e9800dd023d604b61e9bd7a60d40e48a1179dd4d6840633166e6'
        assert row[1]==row[2]
    record('catalog',checksum=row[0],fingerprint=row[1])
