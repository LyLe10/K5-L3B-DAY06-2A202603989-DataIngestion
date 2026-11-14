"""Synthetic retrieval contract tests; no driver, database or benchmark access."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import json

import pytest

from starter.src.store import StoreError
from starter.tests.test_store import profile, ingestion, store


VECTOR = [1.0] + [0.0] * 383


@pytest.fixture
def backend(store, monkeypatch):
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    connection = Mock()
    connection.cursor.return_value = cursor
    connection.transaction.side_effect = lambda: nullcontext()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connect = Mock(return_value=connection)
    monkeypatch.setattr(store, '_connect', connect)
    compatibility = Mock(return_value=(SimpleNamespace(snapshot_id='a'*64),
                                       SimpleNamespace(snapshot_id='b'*64)))
    monkeypatch.setattr(store, 'require_compatible_snapshots', compatibility)
    def lightweight_preflight(active_store, active_connection, baseline):
        snapshots = active_store.require_compatible_snapshots(connection=active_connection)
        p = active_store._profile
        with active_connection.cursor() as cur:
            cur.execute('SELECT model_name,revision,dimensions,config_canonical,config '
                        'FROM day6_ingestion.embedding_profiles WHERE profile_id=%s', (active_store.profile_id,))
            if cur.fetchone() != (p.config['model_name'], p.config['revision'], 384, p.config_canonical, p.config):
                raise StoreError('Stored profile mismatch')
        return snapshots
    # SQL search tests isolate preflight; its real implementation is tested in
    # test_retrieval_session.py and the explicit PostgreSQL integration suite.
    monkeypatch.setattr('starter.src.retrieval.preflight', lightweight_preflight)
    p = store._profile
    cursor.fetchone.return_value = (p.config['model_name'], p.config['revision'],
                                   384, p.config_canonical, p.config)
    cursor.fetchall.return_value = []
    return SimpleNamespace(cursor=cursor, connect=connect, compatibility=compatibility,
                           connection=connection)


def row(cid='B:one', distance=0.2):
    return (cid, 'doc', 'synthetic://source', 7, 'iii', 'scope', 4, 8,
            'text', {'section': 'scope', '_chunking': {'strategy': 'B'}},
            'b'*64, 'c'*64, 'd'*64, 'e'*64, 'f'*64, '0'*64, 'page:7', distance)


@pytest.mark.parametrize('strategy,stored', [('A','A'), ('B','B'), ('C','B')])
def test_namespace_mapping_binding_and_readonly(store, backend, strategy, stored):
    assert store.search(strategy, VECTOR) == []
    backend.connect.assert_called_once_with(readonly=True)
    backend.compatibility.assert_called_once_with(connection=backend.connection)
    sql, params = backend.cursor.execute.call_args.args
    assert 'embedding <=> %s::public.vector' in sql
    assert 'dataset_id=%s AND profile_id=%s AND strategy=%s' in sql
    assert params[1:4] == (store.dataset_id, store.profile_id, stored)
    assert json.loads(params[0]) == VECTOR
    assert params[4] == ('a' if stored == 'A' else 'b')*64
    assert params[-1] == 3
    assert 'ORDER BY cosine_distance ASC, chunk_id ASC LIMIT %s' in sql
    assert all(call.args[0].startswith(('SELECT ', 'SET '))
               for call in backend.cursor.execute.call_args_list)


def test_filter_before_limit_and_injection_is_bound(store, backend):
    section = "scope' OR TRUE --"
    store.search('C', VECTOR, 2, {'section': section})
    sql, params = backend.cursor.execute.call_args.args
    assert sql.index('section=%s') < sql.index('LIMIT %s')
    assert section not in sql
    assert params[-2:] == (section, 2)


def test_order_score_and_provenance(store, backend):
    # Double supplies database order; real cosine sorting remains for Stage 5.4.
    backend.cursor.fetchall.return_value = [row('B:a', 0.1), row('B:b', 0.1), row('B:c', 0.4)]
    hits = store.search('C', VECTOR)
    assert [h['chunk_id'] for h in hits] == ['B:a','B:b','B:c']
    assert [h['rank'] for h in hits] == [1,2,3]
    assert hits[0]['score'] == pytest.approx(0.9)
    assert hits[0]['cosine_distance'] == 0.1
    for key, value in dict(document_id='doc', source='synthetic://source', physical_page=7,
                           printed_page_label='iii', section='scope', start_char=4,
                           end_char=8, text='text', snapshot_id='b'*64,
                           stored_strategy='B', requested_strategy='C').items():
        assert hits[0][key] == value
    assert hits[0]['metadata']['_chunking']['strategy'] == 'B'
    assert 'embedding' not in hits[0]


def test_c_without_filter_equals_b_materialization(store, backend):
    backend.cursor.fetchall.return_value = [row()]
    b = store.search('B', VECTOR)
    bsql = backend.cursor.execute.call_args
    c = store.search('C', VECTOR, filters={})
    assert backend.cursor.execute.call_args == bsql
    assert [{k:v for k,v in h.items() if k != 'requested_strategy'} for h in b] == [
        {k:v for k,v in h.items() if k != 'requested_strategy'} for h in c]


def test_fewer_than_k_and_valid_unknown_filter(store, backend):
    backend.cursor.fetchall.return_value = [row()]
    assert len(store.search('B', VECTOR, 10)) == 1
    backend.cursor.fetchall.return_value = []
    assert store.search('C', VECTOR, filters={'section':'absent'}) == []


@pytest.mark.parametrize('overrides', [
    {'strategy':'D'}, {'strategy':None}, {'strategy':[]},
    {'top_k':0}, {'top_k':-1}, {'top_k':True}, {'top_k':1.5}, {'top_k':'3'},
    {'filters':[]}, {'filters':'section'}, {'filters':{'unknown':'x'}},
    {'filters':{'section':None}}, {'filters':{'section':''}},
    {'filters':{'section':'  '}}, {'filters':{'section':7}},
    {'filters':{'section':'a\x00b'}},
    {'query_vector':None}, {'query_vector':[]}, {'query_vector':[0.0]*384},
    {'query_vector':[float('nan')]+[0.0]*383},
    {'query_vector':[float('inf')]+[0.0]*383},
    {'query_vector':[True]+[0.0]*383}, {'query_vector':[2.0]+[0.0]*383},
])
def test_invalid_before_connection(store, backend, overrides):
    args=dict(strategy='C', query_vector=VECTOR)
    args.update(overrides)
    with pytest.raises(StoreError):
        store.search(**args)
    backend.connect.assert_not_called()


@pytest.mark.parametrize('strategy', ['A','B'])
def test_ab_reject_filters(store, backend, strategy):
    with pytest.raises(StoreError):
        store.search(strategy, VECTOR, filters={'section':'scope'})
    backend.connect.assert_not_called()


def test_profile_mismatch(store, backend):
    backend.cursor.fetchone.return_value = None
    with pytest.raises(StoreError, match='profile'):
        store.search('B', VECTOR)


def test_missing_local_profile(store, backend):
    store._profile = None
    with pytest.raises(StoreError):
        store.search('B', VECTOR)
    backend.connect.assert_not_called()


@pytest.mark.parametrize('failure_at', ['connect', 'compatibility', 'fetch'])
def test_backend_and_compatibility_errors_propagate(store, backend, failure_at):
    error = RuntimeError('synthetic backend failure')
    target = {'connect':backend.connect, 'compatibility':backend.compatibility,
              'fetch':backend.cursor.fetchall}[failure_at]
    target.side_effect = error
    with pytest.raises(RuntimeError) as caught:
        store.search('B', VECTOR)
    assert caught.value is error


def test_does_not_mutate_inputs(store, backend):
    vector, filters = deepcopy(VECTOR), {'section':'scope'}
    store.search('C', vector, filters=filters)
    assert vector == VECTOR and filters == {'section':'scope'}
