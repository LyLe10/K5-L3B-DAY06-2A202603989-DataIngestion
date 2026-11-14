"""Explicit real-cancellation tests on guarded disposable PostgreSQL only."""
from concurrent.futures import ThreadPoolExecutor
import time

import psycopg
import pytest

from starter.tests.postgres_store_cases import subject, sync
from starter.tests.postgres_retrieval_cases import ready

EVIDENCE=[]


def test_watchdog_cancels_real_query_and_releases_locks(ready,monkeypatch):
    def slow(connection,*args):
        # Disable the statement timeout for this synthetic probe only, so the
        # watchdog (not PostgreSQL's timeout) must issue the CancelRequest.
        connection.execute('SET LOCAL statement_timeout=0')
        connection.execute('SELECT pg_sleep(20)')
    monkeypatch.setattr(ready,'_search_in_session',slow)
    start=time.monotonic()
    with pytest.raises(psycopg.Error) as error:
        with ready.retrieval_session(deadline_seconds=2) as session:
            session.search('B',[1.0]+[0.0]*383)
    elapsed=time.monotonic()-start
    assert error.value.sqlstate=='57014'
    assert 'user request' in error.value.diag.message_primary
    assert session._connection.closed and not session._active
    assert session._deadline._closed and not session._deadline.timer.is_alive()
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(sync,ready,'A').result(timeout=8)['expected_count']==30
    EVIDENCE.append(dict(case='watchdog_query',sqlstate='57014',seconds=elapsed,
        source='user request',connection_closed=True,watchdog_quiescent=True,writer_after_error=True))


def test_watchdog_cancels_real_preflight(ready,monkeypatch):
    import starter.src.retrieval as module
    original=module.preflight
    connections=[]
    def slow(store,connection,baseline):
        connections.append(connection)
        snapshots=original(store,connection,baseline)
        connection.execute('SET LOCAL statement_timeout=0')
        connection.execute('SELECT pg_sleep(20)')
        return snapshots
    monkeypatch.setattr(module,'preflight',slow)
    with pytest.raises(psycopg.Error) as error:
        with ready.retrieval_session(deadline_seconds=2):
            pytest.fail('Cancelled preflight must never yield a session')
    assert error.value.sqlstate=='57014' and 'user request' in error.value.diag.message_primary
    assert len(connections)==1 and connections[0].closed
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(sync,ready,'B').result(timeout=8)['expected_count']==30
    EVIDENCE.append(dict(case='watchdog_preflight',sqlstate='57014',connections=1,
        connection_closed=True,writer_after_error=True))


def test_normal_exit_disarms_before_driver_exit(ready):
    with ready.retrieval_session(deadline_seconds=2) as session:
        assert len(session.search('B',[1.0]+[0.0]*383))==3
        deadline=session._deadline
    assert deadline._closed and deadline.connection is None
    assert not deadline.timer.is_alive() and session._connection.closed
    deadline._cancel()  # A stale callback must be inert after detachment.
    assert not deadline.expired.is_set()
    with ready.retrieval_session() as fresh:
        assert len(fresh.search('B',[1.0]+[0.0]*383))==3
    EVIDENCE.append(dict(case='normal_exit',watchdog_quiescent=True,
        stale_callback_inert=True,new_explicit_session_ok=True))
