"""Explicit-only PostgreSQL integration cases; excluded from normal test discovery.

Run via check_store_postgres.py. All content/vectors/profiles are SYNTHETIC.
No model calls, production URL fallback, schema repair or database cleanup.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
import os
import re
import threading
import time
from types import SimpleNamespace
import uuid

import psycopg
import pytest

from starter.src.chunking import fixed_size, by_paragraph
from starter.src.embeddings import validate_vector
from starter.src.models import DocumentPage
from starter.src.schema import EmbeddingProfile, Namespace, canonical_json
from starter.src.store import PgVectorStore, SnapshotContext, StoreError, MIGRATION_SHA256

from starter.scripts.store_test_target import integration_target, validate_identity, TEST_DATABASE

_TARGET = integration_target()
DSN = psycopg.conninfo.make_conninfo(host='127.0.0.1', port=55434, dbname=TEST_DATABASE,
    user='tester', password=_TARGET['password'], application_name='day6_store_integration')
TEST_CLUSTER = _TARGET['cluster']
RUN = uuid.uuid4().hex[:10]
EVIDENCE = []


def target(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(),current_user,current_setting('server_version_num'),"
                       '(SELECT system_identifier::text FROM pg_control_system()),'
                       "(SELECT extversion FROM pg_extension WHERE extname='vector')")
        validate_identity(cursor.fetchone(), TEST_CLUSTER)


def connect():
    connection = psycopg.connect(DSN,autocommit=True,connect_timeout=5,
                                options='-c statement_timeout=10000 -c lock_timeout=5000')
    target(connection)
    return connection


class SafeStore(PgVectorStore):
    def _connect(self,**kwargs):
        connection=super()._connect(**kwargs)
        try: target(connection)
        except Exception:
            connection.close()
            raise
        return connection


def corpus(count=30):
    pages=[]
    for n in range(1,count+1):
        text=f'Synthetic PostgreSQL fixture trang {n}: Tiếng Việt; no real corpus.'
        metadata=dict(source_id='synthetic-document',physical_page=n,page_id=f'synthetic:{n}',
                      printed_page_label=None,section='alpha' if n<=15 else 'beta',
                      section_evidence='Synthetic heading',version=None,normalized_char_count=len(text),
                      text_sha256=hashlib.sha256(text.encode()).hexdigest(),extraction_status='ok')
        pages.append(DocumentPage('synthetic-document','synthetic://postgres-tests',n,text,metadata))
    return SimpleNamespace(pages=pages,sources=[dict(source_id='synthetic-document',source='synthetic://postgres-tests',sha256='d'*64)],
                           manifest_sha256='c'*64)


def profile(tag):
    name='synthetic/'+tag
    return EmbeddingProfile.from_config(dict(profile_schema_version=1,model_name=name,revision='a'*40,dimensions=384,
        dtype='float32',pooling='mean',normalize_embeddings=True,document_prefix='passage: ',query_prefix='query: ',
        max_seq_length=512,device='cpu',backend='torch',trust_remote_code=False,pooling_include_prompt=True,
        tokenizer={'name':name,'revision':'a'*40,'class':'SyntheticFast','use_fast':True,'model_max_length':512},
        artifact_sha256={'synthetic.fixture':'b'*64},library_versions={'synthetic.fixture':'1'}))


@pytest.fixture
def subject(request):
    tag='pg43b3-'+RUN+'-'+re.sub('[^a-z0-9_-]','-',request.node.name.lower())[:70]
    evidence=corpus()
    p=profile(tag)
    store=SafeStore(DSN,384,dataset_id=tag,profile_id=p.profile_id,profile=p,
                    context=SnapshotContext.from_ingestion_result(evidence))
    return store,evidence


def inputs(store,strategy='A'):
    chunks=[c for page in store.context.pages for c in
            (fixed_size(page,500,50) if strategy=='A' else by_paragraph(page,500))]
    vector=validate_vector([1/math.sqrt(384)]*384)
    return chunks,[vector.copy() for c in chunks]


def sync(store,strategy='A',vectors=None):
    chunks,default=inputs(store,strategy)
    return store.sync_snapshot(strategy,chunks,default if vectors is None else vectors,
                               vector_chunk_ids=[c.chunk_id for c in chunks],embedding_profile_id=store.profile_id)


def ns(store,strategy='A'):
    return (store.dataset_id,store.profile_id,strategy)


def state(store,strategy='A'):
    with connect() as connection:
        with connection.cursor() as cursor:
            return store._read_sync_state(cursor,Namespace(*ns(store,strategy)))


def profile_row(store):
    with connect() as connection:
        return connection.execute('SELECT profile_id,config_canonical,xmin::text FROM day6_ingestion.embedding_profiles WHERE profile_id=%s',
                                  (store.profile_id,)).fetchone()


def row_versions(store,strategy='A'):
    with connect() as connection:
        return dict(connection.execute('SELECT chunk_id,xmin::text FROM day6_ingestion.chunks WHERE dataset_id=%s AND profile_id=%s AND strategy=%s',ns(store,strategy)).fetchall())


def record(name,**data):
    EVIDENCE.append(dict(name=name,**data))


def test_first_sync_profile_and_vector_round_trip(subject):
    store,_=subject
    result=sync(store)
    ledger,rows=state(store)
    assert result['written_rows']==30 and result['deleted_rows']==0 and not result['replayed']
    assert ledger[6:9]==(30,30,'complete') and len(rows)==30 and profile_row(store)
    chunks,vectors=inputs(store)
    for c,v in zip(chunks,vectors,strict=True):
        assert rows[c.chunk_id][-1]==v and rows[c.chunk_id][-2]==c.metadata
    record('first_sync',**result,completed_at=ledger[-1],vector_dimension=384,vector_round_trip_exact=True)


def test_registration_replay_and_immutability(subject):
    store,_=subject
    store.register_profile();before=profile_row(store)
    store.register_profile()
    assert profile_row(store)==before
    for command in ['UPDATE day6_ingestion.embedding_profiles SET model_name=model_name WHERE profile_id=%s',
                    'DELETE FROM day6_ingestion.embedding_profiles WHERE profile_id=%s']:
        with connect() as connection:
            with pytest.raises(psycopg.Error) as error:
                with connection.transaction(): connection.execute(command,(store.profile_id,))
            assert error.value.sqlstate=='P0001'
            record('immutable_profile',sqlstate=error.value.sqlstate,operation=command.split()[0])
    assert profile_row(store)==before


def test_replay_preserves_rows_vectors_xmin_and_completed_at(subject):
    store,_=subject
    sync(store);before=state(store);versions=row_versions(store);p=profile_row(store)
    result=sync(store)
    assert result['replayed'] and result['written_rows']==result['deleted_rows']==0
    assert state(store)==before and row_versions(store)==versions and profile_row(store)==p
    record('replay',completed_at_unchanged=True,chunk_xmin_unchanged=True,profile_xmin_unchanged=True,**result)


def test_changed_vector_with_same_snapshot_id(subject):
    store,_=subject
    first=sync(store);before=state(store);versions=row_versions(store)
    chunks,vectors=inputs(store);vectors[0]=[1.0]+[0.0]*383
    changed=sync(store,vectors=vectors);after=state(store)
    assert changed['snapshot_id']==first['snapshot_id'] and not changed['replayed'] and changed['written_rows']==1
    assert after[0][-1]!=before[0][-1] and after[1][chunks[0].chunk_id][-1]==vectors[0]
    assert sum(row_versions(store)[cid]!=stamp for cid,stamp in versions.items())==1
    assert sync(store,vectors=vectors)['replayed']
    record('changed_vector',same_snapshot_id=True,changed_rows=1,stored_vector_verified=True)


@pytest.mark.parametrize('kind',['metadata','text','provenance'])
def test_changed_context_updates_retained_provenance(subject,kind):
    store,evidence=subject
    first=sync(store);old=state(store)[1]
    if kind=='metadata': evidence.pages[0].metadata['section']='changed synthetic section'
    elif kind=='text':
        page=evidence.pages[0];page.text+=' changed'
        page.metadata.update(normalized_char_count=len(page.text),text_sha256=hashlib.sha256(page.text.encode()).hexdigest())
    else: evidence.sources[0]['sha256']='f'*64
    store.context=SnapshotContext.from_ingestion_result(evidence)
    result=sync(store);after=state(store)[1]
    assert result['snapshot_id']!=first['snapshot_id'] and result['written_rows']==30
    assert result['deleted_rows']==(1 if kind=='text' else 0)
    assert all(row[4]==result['snapshot_id'] for row in after.values())
    assert set(old)&set(after)
    chunks,_=inputs(store)
    for chunk in chunks:
        row=after[chunk.chunk_id]
        assert row[14]==chunk.text and row[20]==chunk.metadata
        assert row[9]==evidence.sources[0]['sha256']
    record('changed_'+kind,retained_ids=len(set(old)&set(after)),**result)


def test_expected_count_reduction_and_stale_deletion(subject):
    store,_=subject
    store.context=SnapshotContext.from_ingestion_result(corpus(31));sync(store)
    assert state(store)[0][6:8]==(31,31)
    store.context=SnapshotContext.from_ingestion_result(corpus(30))
    result=sync(store);ledger,rows=state(store)
    assert result['deleted_rows']==1 and len(rows)==30 and ledger[6:9]==(30,30,'complete')
    record('count_reduction',from_expected=31,to_expected=30,actual_count=30,**result)


def test_namespace_isolation(subject):
    store,evidence=subject
    p2=profile(store.dataset_id+'-other-profile')
    others=[SafeStore(DSN,384,dataset_id=store.dataset_id+'-other',profile_id=store.profile_id,profile=store._profile,context=store.context),
            SafeStore(DSN,384,dataset_id=store.dataset_id,profile_id=p2.profile_id,profile=p2,context=store.context)]
    for peer in others: sync(peer)
    sync(store,'B');sync(store,'A')
    before=[state(peer) for peer in others]+[state(store,'B')]
    evidence.sources[0]['sha256']='f'*64
    store.context=SnapshotContext.from_ingestion_result(evidence)
    sync(store)
    assert [state(peer) for peer in others]+[state(store,'B')]==before
    record('namespace_isolation',other_dataset_other_profile_other_strategy_unchanged=True)


def test_sql_parameter_binding_and_on_conflict(subject):
    store,evidence=subject
    hostile="synthetic://'; DROP SCHEMA public CASCADE; --"
    evidence.sources[0]['source']=hostile
    for page in evidence.pages: page.source=hostile
    store.context=SnapshotContext.from_ingestion_result(evidence)
    sync(store);assert sync(store)['replayed']
    assert all(row[8]==hostile for row in state(store)[1].values())
    with connect() as connection:
        assert connection.execute("SELECT to_regnamespace('public') IS NOT NULL").fetchone()==(True,)
    record('binding',hostile_source_stored_as_data=True,public_schema_unchanged=True)


class CursorProxy:
    """Fault/coordination wrapper around a REAL psycopg cursor, never fake rows."""
    def __init__(self,cursor,owner): self.cursor,self.owner=cursor,owner
    def __enter__(self): self.cursor.__enter__();return self
    def __exit__(self,*args): return self.cursor.__exit__(*args)
    def __getattr__(self,name): return getattr(self.cursor,name)
    def execute(self,query,params=None):
        owner=self.owner
        self.cursor.execute(query,params)
        owner.pid=self.cursor.connection.info.backend_pid
        if query=='SELECT pg_advisory_xact_lock(%s)' and owner.entered is not None:
            owner.entered.set()
            if not owner.release.wait(4): raise TimeoutError('Fixture lock hold exceeded four seconds')
        marker=None
        if query.startswith('INSERT INTO day6_ingestion.embedding_profiles'): marker='profile'
        elif query.startswith('INSERT INTO day6_ingestion.strategy_snapshots'): marker='ledger'
        elif query.startswith('INSERT INTO day6_ingestion.chunks'):
            owner.chunk_calls+=1
            if owner.chunk_calls==2: marker='chunk'
        elif query.startswith('DELETE FROM day6_ingestion.chunks'): marker='delete'
        elif query.startswith('UPDATE day6_ingestion.strategy_snapshots'): marker='complete'
        elif query=='SET CONSTRAINTS ALL IMMEDIATE': marker='constraints'
        if owner.fault is not None and marker==owner.fault:
            self.cursor.execute('SELECT 1/0')  # Actual server error aborts the real transaction.
        if query=='SET CONSTRAINTS ALL IMMEDIATE' and owner.fault=='commit':
            self.cursor.execute('SET CONSTRAINTS ALL DEFERRED')
            self.cursor.execute("UPDATE day6_ingestion.strategy_snapshots SET status='syncing',actual_count=0,completed_at=NULL "
                                'WHERE dataset_id=%s AND profile_id=%s AND strategy=%s',ns(owner))
        return self


class ConnectionProxy:
    def __init__(self,connection,owner): self.connection,self.owner=connection,owner
    def __enter__(self): self.connection.__enter__();return self
    def __exit__(self,*args): return self.connection.__exit__(*args)
    def __getattr__(self,name): return getattr(self.connection,name)
    def cursor(self,*args,**kwargs): return CursorProxy(self.connection.cursor(*args,**kwargs),self.owner)


class InstrumentedStore(SafeStore):
    fault=None
    entered=release=None
    pid=None
    chunk_calls=0
    def _connect(self,**kwargs): return ConnectionProxy(super()._connect(**kwargs),self)


def instrument(store,**options):
    result=InstrumentedStore(DSN,384,dataset_id=store.dataset_id,profile_id=store.profile_id,
                             profile=store._profile,context=store.context)
    for key,value in options.items(): setattr(result,key,value)
    return result


@pytest.mark.parametrize('stage',['profile','ledger','chunk','delete','complete','constraints','commit'])
def test_real_transaction_rollback_at_each_stage(subject,stage):
    store,_=subject
    broken=instrument(store,fault=stage)
    with pytest.raises(psycopg.Error) as error: sync(broken)
    expected='P0001' if stage=='commit' else '22012'
    assert error.value.sqlstate==expected
    assert profile_row(store) is None and state(store)==(None,{})
    record('rollback_'+stage,sqlstate=error.value.sqlstate,profile_absent=True,ledger_absent=True,chunks_absent=True)


def test_rollback_restores_existing_snapshot(subject):
    store,evidence=subject
    sync(store);before=state(store);versions=row_versions(store)
    evidence.sources[0]['sha256']='f'*64
    store.context=SnapshotContext.from_ingestion_result(evidence)
    with pytest.raises(psycopg.Error) as error: sync(instrument(store,fault='delete'))
    assert error.value.sqlstate=='22012' and state(store)==before and row_versions(store)==versions
    record('rollback_existing',sqlstate='22012',completed_at_rows_vectors_xmin_restored=True)


@pytest.mark.parametrize('kind',['fk','completion'])
def test_deferred_constraints_reject_commit_and_restore_data(subject,kind):
    store,_=subject
    sync(store);before=state(store)
    with connect() as connection:
        with pytest.raises(psycopg.Error) as error:
            with connection.transaction():
                if kind=='fk':
                    connection.execute('UPDATE day6_ingestion.chunks SET snapshot_id=%s WHERE dataset_id=%s AND profile_id=%s AND strategy=%s',
                                       ('0'*64,*ns(store)))
                else:
                    connection.execute('DELETE FROM day6_ingestion.chunks WHERE dataset_id=%s AND profile_id=%s AND strategy=%s AND physical_page=1',ns(store))
                # The mutation statement completed; failure occurs leaving transaction (COMMIT).
                assert connection.execute('SELECT 1').fetchone()==(1,)
        assert error.value.sqlstate==('23503' if kind=='fk' else 'P0001')
    assert state(store)==before
    record('deferred_'+kind,sqlstate=error.value.sqlstate,failure_at_commit=True,data_restored=True)


def test_ab_compatibility_and_c_refusal(subject):
    store,evidence=subject
    sync(store,'A')
    with pytest.raises(StoreError): store.require_compatible_snapshots()
    sync(store,'B');a,b=store.require_compatible_snapshots()
    assert a.corpus_sha256==b.corpus_sha256
    evidence.sources[0]['sha256']='f'*64
    store.context=SnapshotContext.from_ingestion_result(evidence);sync(store,'A')
    with pytest.raises(ValueError,match='Incompatible'): store.require_compatible_snapshots()
    sync(store,'B');assert len(store.require_compatible_snapshots())==2
    chunks,vectors=inputs(store,'B')
    with pytest.raises(ValueError):
        store.sync_snapshot('C',chunks,vectors,vector_chunk_ids=[c.chunk_id for c in chunks],embedding_profile_id=store.profile_id)
    with connect() as connection:
        assert connection.execute('SELECT count(*) FROM day6_ingestion.strategy_snapshots WHERE strategy=%s',('C',)).fetchone()==(0,)
    record('compatibility',mismatch_blocked=True,C_rows=0)


def wait_for_advisory_wait(worker,seconds=2):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if worker.pid:
            with connect() as connection:
                row=connection.execute('SELECT wait_event FROM pg_stat_activity WHERE pid=%s',(worker.pid,)).fetchone()
                if row and row[0]=='advisory': return
        time.sleep(.02)
    raise AssertionError('Second writer did not demonstrably wait on advisory lock')


class WaitingStore(SafeStore):
    pid=None
    def _connect(self,**kwargs):
        connection=super()._connect(**kwargs)
        self.pid=connection.info.backend_pid
        return connection


def waiting(store):
    return WaitingStore(DSN,384,dataset_id=store.dataset_id,profile_id=store.profile_id,
                        profile=store._profile,context=store.context)


def test_same_namespace_concurrent_writers_serialize(subject):
    store,_=subject
    sync(store)
    entered,release=threading.Event(),threading.Event()
    first=instrument(store,entered=entered,release=release)
    second=waiting(store)
    _,v1=inputs(store);_,v2=inputs(store)
    v1[0]=[1.0]+[0.0]*383;v2[0]=[0.0,1.0]+[0.0]*382
    with ThreadPoolExecutor(max_workers=2) as pool:
        future1=pool.submit(sync,first,'A',v1)
        try:
            assert entered.wait(2)
            future2=pool.submit(sync,second,'A',v2)
            wait_for_advisory_wait(second)
            assert not future2.done()
        finally: release.set()
        assert future1.result(timeout=8)['written_rows']==1
        assert future2.result(timeout=8)['written_rows']==1
    chunk=inputs(store)[0][0]
    assert state(store)[1][chunk.chunk_id][-1]==v2[0]
    record('concurrency_same_namespace',observed_pg_advisory_wait=True,serialized=True,last_writer_vector_verified=True)


def test_different_namespace_writers_do_not_block(subject):
    store,_=subject
    store.register_profile()
    entered,release=threading.Event(),threading.Event()
    held=instrument(store,entered=entered,release=release)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future1=pool.submit(sync,held,'A')
        try:
            assert entered.wait(2)
            started=time.perf_counter()
            result=pool.submit(sync,store,'B').result(timeout=3)
            elapsed=time.perf_counter()-started
            assert result['written_rows']==30 and not future1.done()
        finally: release.set()
        assert future1.result(timeout=8)['written_rows']==30
    record('concurrency_different_namespace',other_writer_completed_while_A_locked=True,seconds=elapsed)


def test_lock_timeout_rolls_back_without_retry(subject):
    store,_=subject
    sync(store);before=state(store)
    with connect() as blocker:
        with blocker.transaction():
            blocker.execute('SELECT pg_advisory_xact_lock(%s)',(Namespace(*ns(store)).lock_key,))
            started=time.perf_counter()
            with ThreadPoolExecutor(max_workers=1) as pool:
                with pytest.raises(psycopg.Error) as error: pool.submit(sync,store).result(timeout=8)
            elapsed=time.perf_counter()-started
            assert error.value.sqlstate=='55P03'
    assert state(store)==before
    record('concurrency_timeout',sqlstate='55P03',seconds=elapsed,data_unchanged=True)


def test_catalog_ledger_checksum_and_row_counts():
    with connect() as connection:
        ledger=connection.execute('SELECT version,checksum,catalog_sha256,day6_ingestion.catalog_fingerprint() FROM day6_ingestion.schema_migrations').fetchall()
        assert len(ledger)==1 and ledger[0][0:2]==(1,MIGRATION_SHA256) and ledger[0][2]==ledger[0][3]
        assert connection.execute("SELECT count(*) FROM day6_ingestion.strategy_snapshots WHERE status<>'complete' OR expected_count<>actual_count").fetchone()==(0,)
        assert connection.execute('SELECT count(*) FROM day6_ingestion.strategy_snapshots s WHERE actual_count<>(SELECT count(*) FROM day6_ingestion.chunks c WHERE (c.dataset_id,c.profile_id,c.strategy)=(s.dataset_id,s.profile_id,s.strategy))').fetchone()==(0,)
        counts=connection.execute('SELECT (SELECT count(*) FROM day6_ingestion.embedding_profiles),(SELECT count(*) FROM day6_ingestion.strategy_snapshots),(SELECT count(*) FROM day6_ingestion.chunks)').fetchone()
    record('final_catalog',checksum=ledger[0][1],catalog_fingerprint=ledger[0][3],counts=counts,all_snapshots_complete=True)
