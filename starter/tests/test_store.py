"""Targeted store foundation tests: synthetic in-memory fixtures, no PostgreSQL."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from types import SimpleNamespace

import pytest

from starter.src.chunking import fixed_size
from starter.src.models import Chunk, DocumentPage
from starter.src.schema import EmbeddingProfile
from starter.src.store import MIGRATION_SHA256, PgVectorStore, SnapshotContext, StoreError


@pytest.fixture
def profile():
    return EmbeddingProfile.from_config(dict(
        profile_schema_version=1, model_name='unit/model', revision='a'*40, dimensions=384,
        dtype='float32', pooling='mean', normalize_embeddings=True, document_prefix='passage: ',
        query_prefix='query: ', max_seq_length=512, device='cpu', backend='torch',
        trust_remote_code=False, pooling_include_prompt=True,
        tokenizer={'name':'unit/model','revision':'a'*40,'class':'UnitFast','use_fast':True,'model_max_length':512},
        artifact_sha256={'fixture':'b'*64}, library_versions={'fixture':'1'}))


@pytest.fixture
def ingestion():
    pages=[]
    for n in range(1,31):
        text=f'Synthetic unit fixture page {n}.'
        m=dict(source_id='unit-doc', physical_page=n, page_id=f'unit:{n}',
               printed_page_label=None, section='first' if n<=15 else 'second',
               section_evidence='unit heading', version=None, normalized_char_count=len(text),
               text_sha256=hashlib.sha256(text.encode()).hexdigest(), extraction_status='ok')
        pages.append(DocumentPage('unit-doc','synthetic://unit',n,text,m))
    return SimpleNamespace(manifest_sha256='c'*64,pages=pages,
                           sources=[dict(source_id='unit-doc',source='synthetic://unit',sha256='d'*64)])


@pytest.fixture
def store(profile,ingestion):
    return PgVectorStore('postgresql://not-connected/unit',384,dataset_id='unit-dataset',
                         profile_id=profile.profile_id,profile=profile,
                         context=SnapshotContext.from_ingestion_result(ingestion))


def batch(store):
    chunks=[c for p in store.context.pages for c in fixed_size(p,500,50)]
    vectors=[[1.0]+[0.0]*383 for c in chunks]
    return chunks,vectors


def validate(store,chunks,vectors,**overrides):
    kwargs=dict(vector_chunk_ids=[c.chunk_id for c in chunks],embedding_profile_id=store.profile_id)
    kwargs.update(overrides)
    return store.validate_batch('A',chunks,vectors,**kwargs)


class CursorDouble:
    def __init__(self,connection):
        self.connection=connection
        self.last=''

    def __enter__(self): return self
    def __exit__(self,*args): return False

    def execute(self,query,params=None):
        self.last=query
        c=self.connection
        c.calls.append((query,params))
        if query.startswith('INSERT'):
            if c.insert_error: raise RuntimeError('unit injected INSERT failure')
            pid,model,revision,dimension,canonical,config=params
            c.profiles.setdefault(pid,(model,revision,dimension,canonical,json.loads(config)))
            c.selected=pid
        elif 'WHERE profile_id=%s' in query:
            c.selected=params[0]

    def fetchone(self):
        c=self.connection
        if 'to_regclass' in self.last:
            return ('day6_ingestion.schema_migrations',) if c.schema_present else (None,)
        return c.conflict_row if c.conflict_row is not None else c.profiles.get(c.selected)

    def fetchall(self):
        return self.connection.history


class ConnectionDouble:
    def __init__(self,active=False):
        self.info=SimpleNamespace(transaction_status=SimpleNamespace(name='INTRANS' if active else 'IDLE'))
        self.calls=[]
        self.profiles={}
        self.schema_present=True
        self.history=[(1,'0001_day6_ingestion.sql',MIGRATION_SHA256,'e'*64,'e'*64)]
        self.conflict_row=None
        self.insert_error=False
        self.begins=self.commits=self.rollbacks=self.closes=0

    def __enter__(self): return self
    def __exit__(self,*args):
        self.closes+=1
        return False

    def cursor(self): return CursorDouble(self)

    @contextmanager
    def transaction(self):
        self.begins+=1
        old=deepcopy(self.profiles)
        self.info.transaction_status.name='INTRANS'
        try:
            yield
        except Exception:
            self.profiles=old
            self.rollbacks+=1
            raise
        else:
            self.commits+=1
        finally:
            self.info.transaction_status.name='IDLE'


def test_constructor_keeps_two_arguments_and_does_not_connect(monkeypatch):
    monkeypatch.setattr(PgVectorStore,'_connect',lambda *a,**k: pytest.fail('Unexpected connection'))
    unconfigured=PgVectorStore('unit-url',384)
    assert unconfigured.profile_id is None and unconfigured.context is None
    with pytest.raises(StoreError): unconfigured.register_profile()
    with pytest.raises(TypeError): PgVectorStore('unit-url',384,'positional-dataset')


@pytest.mark.parametrize('dimensions',[383,385,True,384.0])
def test_wrong_dimensions(dimensions):
    with pytest.raises(StoreError): PgVectorStore('unit-url',dimensions)


@pytest.mark.parametrize('changes',[{'database_url':''},{'dataset_id':'../bad'},{'profile_id':'main'},
                                    {'context':{}},{'profile_id':'f'*64}])
def test_invalid_constructor_identity(profile,changes):
    kwargs=dict(database_url='unit-url',dimensions=384,dataset_id='unit',profile_id=profile.profile_id,profile=profile)
    kwargs.update(changes)
    with pytest.raises(ValueError): PgVectorStore(**kwargs)


def test_canonical_profile_tampering_rejected(profile):
    object.__setattr__(profile,'config_canonical','{}')
    with pytest.raises(ValueError): PgVectorStore('unit-url',384,profile_id='f'*64,profile=profile)


def test_context_is_explicit_frozen_and_detached(ingestion,store):
    original=store.context.pages[0].text
    ingestion.pages[0].text='modified caller page'
    detached=store.context.pages
    detached[0].metadata['section']='modified returned dict'
    assert store.context.pages[0].text==original
    assert store.context.pages[0].metadata['section']=='first'
    with pytest.raises(FrozenInstanceError): store.context.manifest_sha256='f'*64


@pytest.mark.parametrize('change',['pages','checksum','offset-count','metadata','source','duplicate','manifest'])
def test_bad_context(ingestion,change):
    if change=='pages': ingestion.pages=ingestion.pages[:29]
    elif change=='checksum': ingestion.pages[0].metadata['text_sha256']='0'*64
    elif change=='offset-count': ingestion.pages[0].metadata['normalized_char_count']+=1
    elif change=='metadata': del ingestion.pages[0].metadata['printed_page_label']
    elif change=='source': ingestion.sources[0]['source']='different'
    elif change=='duplicate': ingestion.pages[-1]=deepcopy(ingestion.pages[0])
    else: ingestion.manifest_sha256='invalid'
    with pytest.raises(StoreError): SnapshotContext.from_ingestion_result(ingestion)


def test_valid_batch_order_and_detachment(store):
    chunks,vectors=batch(store)
    chunks.reverse();vectors.reverse()
    result=validate(store,chunks,vectors)
    assert [c.chunk_id for c,v in result]==[c.chunk_id for c in chunks]
    result[0][0].metadata['section']='changed'
    result[0][1][0]=0
    assert chunks[0].metadata['section']!='changed' and vectors[0][0]==1


def test_no_completeness_inference_from_chunks(store):
    chunks,vectors=batch(store)
    store.context=None
    with pytest.raises(StoreError,match='context required'): validate(store,chunks,vectors)


@pytest.mark.parametrize('change',['empty','count','missing-page','duplicate','order','profile','metadata','offset','text','source','id'])
def test_bad_batch(store,change):
    chunks,vectors=batch(store)
    overrides={}
    if change=='empty': chunks=[];vectors=[]
    elif change=='count': vectors.pop()
    elif change=='missing-page': chunks.pop();vectors.pop()
    elif change=='duplicate': chunks[-1]=deepcopy(chunks[0])
    elif change=='order': overrides['vector_chunk_ids']=list(reversed([c.chunk_id for c in chunks]))
    elif change=='profile': overrides['embedding_profile_id']='f'*64
    elif change=='metadata': chunks[0].metadata.pop('section')
    elif change=='offset': chunks[0].metadata['_chunking']['end_char']-=1
    elif change=='text': chunks[0].text+='x'
    elif change=='source': chunks[0].source='other'
    else: chunks[0].chunk_id='A:'+'f'*64
    with pytest.raises(StoreError): validate(store,chunks,vectors,**overrides)


@pytest.mark.parametrize('vector',[[1.0]+[0.0]*382,[0.0]*384,[2.0]+[0.0]*383,
                                   [float('nan')]+[0.0]*383,[float('inf')]+[0.0]*383,None])
def test_bad_vectors(store,vector):
    chunks,vectors=batch(store)
    vectors[0]=vector
    with pytest.raises(StoreError): validate(store,chunks,vectors)


def test_c_is_not_a_storage_strategy(store):
    chunks,vectors=batch(store)
    with pytest.raises(ValueError):
        store.validate_batch('C',chunks,vectors,vector_chunk_ids=[c.chunk_id for c in chunks],embedding_profile_id=store.profile_id)


def test_registration_first_and_replay_in_callers_transaction(store):
    conn=ConnectionDouble(active=True)
    for i in range(2): assert store.register_profile(connection=conn)==store.profile_id
    assert len(conn.profiles)==1
    assert conn.begins==conn.commits==conn.rollbacks==conn.closes==0
    assert all(not sql.startswith(('UPDATE','DELETE','CREATE','ALTER','DROP')) for sql,p in conn.calls)
    inserts=[(sql,p) for sql,p in conn.calls if sql.startswith('INSERT')]
    assert len(inserts)==2 and all('ON CONFLICT (profile_id) DO NOTHING' in sql for sql,p in inserts)
    assert all(p[0]==store.profile_id for sql,p in inserts)


def test_registration_owns_one_transaction_when_no_connection(store,monkeypatch):
    conn=ConnectionDouble()
    monkeypatch.setattr(store,'_connect',lambda **kw:conn)
    assert store.register_profile()==store.profile_id
    assert (conn.begins,conn.commits,conn.rollbacks,conn.closes)==(1,1,0,1)


@pytest.mark.parametrize('owned',[False,True])
def test_profile_conflict_propagates_and_respects_transaction_owner(store,monkeypatch,owned):
    conn=ConnectionDouble(active=not owned)
    conn.conflict_row=('wrong','a'*40,384,'{}',{})
    monkeypatch.setattr(store,'_connect',lambda **kw:conn)
    with pytest.raises(StoreError,match='Immutable profile conflict'):
        store.register_profile(**({} if owned else {'connection':conn}))
    assert conn.commits==0
    if owned:
        assert conn.rollbacks==1 and conn.profiles=={}
    else:
        assert conn.rollbacks==conn.closes==0


def test_registration_insert_error_is_rolled_back_by_owned_transaction(store,monkeypatch):
    conn=ConnectionDouble();conn.insert_error=True
    monkeypatch.setattr(store,'_connect',lambda **kw:conn)
    with pytest.raises(RuntimeError,match='injected INSERT'): store.register_profile()
    assert conn.rollbacks==1 and conn.commits==0


def test_registration_rejects_idle_caller_connection(store):
    conn=ConnectionDouble()
    with pytest.raises(StoreError,match='active caller transaction'): store.register_profile(connection=conn)
    assert not conn.calls


def test_create_schema_is_readonly_verification(store,monkeypatch):
    conn=ConnectionDouble();options=[]
    def connect(**kw):
        options.append(kw)
        return conn
    monkeypatch.setattr(store,'_connect',connect)
    store.create_schema()
    assert options==[{'readonly':True}]
    assert all(sql.startswith('SELECT') for sql,p in conn.calls)
    assert not conn.profiles


@pytest.mark.parametrize('problem',['absent','empty-history','checksum','fingerprint','extra-version'])
def test_schema_verification_rejects_drift_without_writing(store,monkeypatch,problem):
    conn=ConnectionDouble()
    if problem=='absent': conn.schema_present=False
    elif problem=='empty-history': conn.history=[]
    elif problem=='checksum': conn.history=[(1,'0001_day6_ingestion.sql','f'*64,'e'*64,'e'*64)]
    elif problem=='fingerprint': conn.history=[(1,'0001_day6_ingestion.sql',MIGRATION_SHA256,'e'*64,'f'*64)]
    else: conn.history+=conn.history
    monkeypatch.setattr(store,'_connect',lambda **kw:conn)
    with pytest.raises(StoreError): store.create_schema()
    assert all(sql.startswith('SELECT') for sql,p in conn.calls)


def test_empty_upsert_rejected(store):
    with pytest.raises(StoreError): store.upsert('A',[],[])


# This stateful double tests Python orchestration and bound SQL values only.
# It is NOT a PostgreSQL parser, MVCC, locking or deferred-trigger proof.
class SyncCursorDouble(CursorDouble):
    def __init__(self,connection):
        super().__init__(connection)
        self.kind=None
        self.answer=None
        self.rowcount=0

    def execute(self,query,params=None):
        from starter.src.store import CHUNK_COLUMNS, CHUNK_UPSERT
        c=self.connection
        self.rowcount=0
        if query.startswith('SELECT ') and ('FROM day6_ingestion.strategy_snapshots WHERE' in query
                or 'FROM day6_ingestion.chunks WHERE' in query):
            c.calls.append((query,params))
            self.kind='sync-read'
            key=tuple(params)
            if 'strategy_snapshots WHERE' in query:
                self.answer=deepcopy(c.ledgers.get(key))
            else:
                rows=c.chunks.get(key,{})
                self.answer=[(*row[:-1],json.dumps(row[-1])) for cid,row in sorted(rows.items())]
                if c.fail_at=='final-data' and c.completed_in_transaction and self.answer:
                    self.answer=self.answer[:-1]
            return
        self.kind=None
        if query.startswith('INSERT INTO day6_ingestion.strategy_snapshots'):
            c.calls.append((query,params))
            ns=tuple(params[:3])
            c.ledgers[ns]=(*params[3:7],json.loads(params[7]),params[8],params[9],0,'syncing',None)
            # Model only the immediate count CHECK relevant to expected_count reduction.
            assert 0<=c.ledgers[ns][7]<=c.ledgers[ns][6]
            if c.fail_at=='ledger': raise RuntimeError('unit ledger failure')
        elif query==CHUNK_UPSERT:
            c.calls.append((query,params))
            ns=tuple(params[:3])
            row=(*params[:-2],json.loads(params[-2]),json.loads(params[-1]))
            assert len(row)==len(CHUNK_COLUMNS)
            rows=c.chunks.setdefault(ns,{})
            if rows.get(params[3])!=row:
                rows[params[3]]=row
                self.rowcount=1
            c.chunk_attempts+=1
            if c.fail_at=='chunk' and c.chunk_attempts==2: raise RuntimeError('unit chunk failure')
        elif query.startswith('DELETE FROM day6_ingestion.chunks'):
            c.calls.append((query,params))
            ns=tuple(params[:3]);wanted=set(params[3])
            rows=c.chunks.setdefault(ns,{})
            stale=set(rows)-wanted
            for cid in stale: del rows[cid]
            self.rowcount=len(stale)
            if c.fail_at=='delete': raise RuntimeError('unit stale-delete failure')
        elif query.startswith('UPDATE day6_ingestion.strategy_snapshots'):
            c.calls.append((query,params))
            count,*ns=params
            old=c.ledgers[tuple(ns)]
            c.ledgers[tuple(ns)]=(*old[:7],count,'complete',c.clock)
            c.completed_in_transaction=True
            self.rowcount=1
            if c.fail_at=='complete': raise RuntimeError('unit complete failure')
        elif query=='SET CONSTRAINTS ALL IMMEDIATE':
            c.calls.append((query,params))
            if c.fail_at=='constraint': raise RuntimeError('unit deferred constraint failure')
        elif query.startswith(('SET LOCAL','SELECT pg_advisory')):
            c.calls.append((query,params))
        else:
            super().execute(query,params)

    def fetchone(self):
        return self.answer if self.kind=='sync-read' else super().fetchone()

    def fetchall(self):
        return self.answer if self.kind=='sync-read' else super().fetchall()


class SyncConnectionDouble(ConnectionDouble):
    def __init__(self,active=False):
        super().__init__(active)
        self.ledgers={}
        self.chunks={}
        self.clock=0
        self.chunk_attempts=0
        self.completed_in_transaction=False
        self.fail_at=None

    def cursor(self): return SyncCursorDouble(self)

    @contextmanager
    def transaction(self):
        self.begins+=1
        self.clock+=1
        self.chunk_attempts=0
        self.completed_in_transaction=False
        old=deepcopy((self.profiles,self.ledgers,self.chunks))
        self.info.transaction_status.name='INTRANS'
        try:
            yield
            if self.fail_at=='commit': raise RuntimeError('unit commit failure')
        except Exception:
            self.profiles,self.ledgers,self.chunks=old
            self.rollbacks+=1
            raise
        else:
            self.commits+=1
        finally:
            self.info.transaction_status.name='IDLE'


@pytest.fixture
def sync_connection(store,monkeypatch):
    connection=SyncConnectionDouble()
    monkeypatch.setattr(store,'_connect',lambda **kw:connection)
    return connection


def sync(store,strategy='A',vectors=None):
    from starter.src.chunking import by_paragraph
    chunks=[c for p in store.context.pages for c in
            (fixed_size(p,500,50) if strategy=='A' else by_paragraph(p,500))]
    if vectors is None: vectors=[[1.0]+[0.0]*383 for c in chunks]
    return store.sync_snapshot(strategy,chunks,vectors,vector_chunk_ids=[c.chunk_id for c in chunks],
                               embedding_profile_id=store.profile_id)


def test_first_sync_and_sql_transaction_order(store,sync_connection):
    conn=sync_connection
    result=sync(store)
    ns=(store.dataset_id,store.profile_id,'A')
    assert result['written_rows']==30 and result['deleted_rows']==0 and not result['replayed']
    assert len(conn.profiles)==1 and len(conn.chunks[ns])==30
    assert conn.ledgers[ns][6:9]==(30,30,'complete')
    assert (conn.begins,conn.commits,conn.rollbacks,conn.closes)==(1,1,0,1)
    statements=[q for q,p in conn.calls]
    profile_pos=next(i for i,q in enumerate(statements) if q.startswith('INSERT INTO day6_ingestion.embedding_profiles'))
    lock_pos=next(i for i,q in enumerate(statements) if q.startswith('SELECT pg_advisory_xact_lock('))
    ledger_pos=next(i for i,q in enumerate(statements) if q.startswith('INSERT INTO day6_ingestion.strategy_snapshots'))
    chunk_pos=next(i for i,q in enumerate(statements) if q.startswith('INSERT INTO day6_ingestion.chunks'))
    delete_pos=next(i for i,q in enumerate(statements) if q.startswith('DELETE'))
    complete_pos=next(i for i,q in enumerate(statements) if q.startswith('UPDATE'))
    assert profile_pos<lock_pos<ledger_pos<chunk_pos<delete_pos<complete_pos
    assert statements[-1]=='SET CONSTRAINTS ALL IMMEDIATE'
    assert all(not q.startswith(('CREATE','DROP','ALTER')) for q in statements)


def test_replay_checks_actual_rows_and_preserves_timestamp(store,sync_connection):
    first=sync(store)
    before=deepcopy((sync_connection.ledgers,sync_connection.chunks))
    sync_connection.calls.clear()
    chunks,vectors=batch(store)
    chunks.reverse();vectors.reverse()
    second=store.sync_snapshot('A',chunks,vectors,vector_chunk_ids=[c.chunk_id for c in chunks],embedding_profile_id=store.profile_id)
    assert second['snapshot_id']==first['snapshot_id'] and second['replayed']
    assert second['written_rows']==second['deleted_rows']==0
    assert (sync_connection.ledgers,sync_connection.chunks)==before
    assert sum('FROM day6_ingestion.chunks WHERE' in q for q,p in sync_connection.calls)==2
    assert not any(q.startswith(('UPDATE','DELETE','INSERT INTO day6_ingestion.chunks','INSERT INTO day6_ingestion.strategy_snapshots'))
                   for q,p in sync_connection.calls)


def test_changed_vector_updates_without_new_snapshot_identity(store,sync_connection):
    first=sync(store)
    ns=(store.dataset_id,store.profile_id,'A')
    old_timestamp=sync_connection.ledgers[ns][-1]
    chunks,vectors=batch(store)
    vectors[0]=[0.0,1.0]+[0.0]*382
    second=sync(store,vectors=vectors)
    assert second['snapshot_id']==first['snapshot_id'] and not second['replayed']
    assert second['written_rows']==1 and second['deleted_rows']==0
    assert sync_connection.chunks[ns][chunks[0].chunk_id][-1]==vectors[0]
    assert sync_connection.ledgers[ns][-1]!=old_timestamp
    third=sync(store,vectors=vectors)
    assert third['replayed']


def test_changed_provenance_updates_every_retained_chunk(store,sync_connection,ingestion):
    first=sync(store)
    ns=(store.dataset_id,store.profile_id,'A')
    old_ids=set(sync_connection.chunks[ns])
    ingestion.sources[0]['sha256']='f'*64
    store.context=SnapshotContext.from_ingestion_result(ingestion)
    second=sync(store)
    assert second['snapshot_id']!=first['snapshot_id'] and second['written_rows']==30
    assert second['deleted_rows']==0 and set(sync_connection.chunks[ns])==old_ids
    for row in sync_connection.chunks[ns].values():
        assert row[4]==second['snapshot_id'] and row[9]=='f'*64


def test_metadata_change_updates_materialization(store,sync_connection,ingestion):
    first=sync(store)
    ingestion.pages[0].metadata['section']='new verified unit section'
    store.context=SnapshotContext.from_ingestion_result(ingestion)
    second=sync(store)
    assert second['snapshot_id']!=first['snapshot_id'] and second['written_rows']==30
    ns=(store.dataset_id,store.profile_id,'A')
    changed=[row for row in sync_connection.chunks[ns].values() if row[10]==1]
    assert changed[0][13]==changed[0][-2]['section']=='new verified unit section'


def test_expected_count_reduction_and_namespace_stale_delete(store,sync_connection,ingestion):
    expanded=deepcopy(ingestion)
    extra=deepcopy(expanded.pages[-1]);extra.page=31
    extra.metadata.update(physical_page=31,page_id='unit:31')
    expanded.pages.append(extra)
    store.context=SnapshotContext.from_ingestion_result(expanded)
    sync(store)
    ns=(store.dataset_id,store.profile_id,'A')
    assert sync_connection.ledgers[ns][6:8]==(31,31)
    store.context=SnapshotContext.from_ingestion_result(ingestion)
    result=sync(store)
    assert result['deleted_rows']==1 and result['written_rows']==30
    assert sync_connection.ledgers[ns][6:8]==(30,30)
    assert len(sync_connection.chunks[ns])==30
    sql,params=next((q,p) for q,p in reversed(sync_connection.calls) if q.startswith('DELETE'))
    assert 'dataset_id=%s AND profile_id=%s AND strategy=%s' in sql
    assert params[:3]==ns and len(params[3])==30
    syncing=[(q,p) for q,p in sync_connection.calls if q.startswith('INSERT INTO day6_ingestion.strategy_snapshots')][-1]
    assert 'actual_count=0' in syncing[0] and syncing[1][-1]==30


@pytest.mark.parametrize('stage',['ledger','chunk','delete','complete','constraint','commit','final-data'])
def test_first_sync_failure_rolls_back_all_state(store,sync_connection,stage):
    sync_connection.fail_at=stage
    with pytest.raises((RuntimeError,StoreError)): sync(store)
    assert not sync_connection.profiles and not sync_connection.ledgers and not sync_connection.chunks
    assert sync_connection.rollbacks==1 and sync_connection.commits==0


def test_failed_changed_sync_restores_previous_snapshot(store,sync_connection,ingestion):
    sync(store)
    before=deepcopy((sync_connection.profiles,sync_connection.ledgers,sync_connection.chunks))
    ingestion.sources[0]['sha256']='f'*64
    store.context=SnapshotContext.from_ingestion_result(ingestion)
    sync_connection.fail_at='complete'
    with pytest.raises(RuntimeError): sync(store)
    assert (sync_connection.profiles,sync_connection.ledgers,sync_connection.chunks)==before


def test_sync_namespace_isolation_across_dataset_profile_and_strategy(store,sync_connection,profile,monkeypatch,ingestion):
    from starter.src.schema import canonical_json
    config=profile.config;config['library_versions']['fixture']='other'
    other_profile=EmbeddingProfile(canonical_json(config))
    peers=[PgVectorStore('unit-url',384,dataset_id='other-dataset',profile_id=profile.profile_id,profile=profile,context=store.context),
           PgVectorStore('unit-url',384,dataset_id=store.dataset_id,profile_id=other_profile.profile_id,profile=other_profile,context=store.context)]
    for peer in peers:
        monkeypatch.setattr(peer,'_connect',lambda **kw:sync_connection)
        sync(peer)
    sync(store,'B');sync(store,'A')
    ns=(store.dataset_id,store.profile_id,'A')
    before_ledgers={k:deepcopy(v) for k,v in sync_connection.ledgers.items() if k!=ns}
    before_chunks={k:deepcopy(v) for k,v in sync_connection.chunks.items() if k!=ns}
    ingestion.sources[0]['sha256']='f'*64
    store.context=SnapshotContext.from_ingestion_result(ingestion)
    sync(store)
    assert {k:v for k,v in sync_connection.ledgers.items() if k!=ns}==before_ledgers
    assert {k:v for k,v in sync_connection.chunks.items() if k!=ns}==before_chunks
    assert all(k[2]!='C' for k in sync_connection.ledgers)


@pytest.mark.parametrize('problem',['empty','vector','receipt','profile','missing-page','C','context'])
def test_invalid_sync_fails_before_connect(store,monkeypatch,problem):
    chunks,vectors=batch(store)
    receipt=[c.chunk_id for c in chunks]
    pid=store.profile_id;strategy='A'
    if problem=='empty': chunks=[];vectors=[];receipt=[]
    elif problem=='vector': vectors[0]=[0.0]*384
    elif problem=='receipt': receipt.reverse()
    elif problem=='profile': pid='f'*64
    elif problem=='missing-page': chunks.pop();vectors.pop();receipt.pop()
    elif problem=='C': strategy='C'
    else: object.__setattr__(store.context,'manifest_sha256','invalid')
    monkeypatch.setattr(store,'_connect',lambda **kw:pytest.fail('Invalid batch opened a connection'))
    with pytest.raises(ValueError):
        store.sync_snapshot(strategy,chunks,vectors,vector_chunk_ids=receipt,embedding_profile_id=pid)


def test_legacy_upsert_requires_receipts_and_returns_none(store,sync_connection):
    chunks,vectors=batch(store)
    with pytest.raises(StoreError): store.upsert('A',chunks,vectors)
    assert sync_connection.begins==0
    assert store.upsert('A',chunks,vectors,vector_chunk_ids=[c.chunk_id for c in chunks],embedding_profile_id=store.profile_id) is None


def test_upsert_sql_conditional_update_includes_all_data_and_provenance():
    from starter.src.store import CHUNK_COLUMNS, CHUNK_UPSERT
    assert 'ON CONFLICT (dataset_id,profile_id,strategy,chunk_id) DO UPDATE' in CHUNK_UPSERT
    assert 'IS DISTINCT FROM ROW(' in CHUNK_UPSERT
    for column in CHUNK_COLUMNS[4:]:
        assert 'stored.'+column in CHUNK_UPSERT and 'EXCLUDED.'+column in CHUNK_UPSERT


def test_input_data_never_interpolated_into_sql(store,sync_connection,ingestion):
    dangerous="synthetic://unit'); DROP SCHEMA public; --"
    ingestion.sources[0]['source']=dangerous
    for page in ingestion.pages: page.source=dangerous
    store.context=SnapshotContext.from_ingestion_result(ingestion)
    sync(store)
    assert all(dangerous not in query for query,params in sync_connection.calls)
    assert any(params is not None and dangerous in params for query,params in sync_connection.calls)


def test_compatibility_guard_checks_ledgers_and_holds_caller_locks(store,sync_connection):
    sync(store,'A');sync(store,'B')
    begins,commits,closes=sync_connection.begins,sync_connection.commits,sync_connection.closes
    sync_connection.info.transaction_status.name='INTRANS'
    sync_connection.calls.clear()
    a,b=store.require_compatible_snapshots(connection=sync_connection)
    assert a.corpus_sha256==b.corpus_sha256 and a.namespace.strategy=='A' and b.namespace.strategy=='B'
    assert (sync_connection.begins,sync_connection.commits,sync_connection.closes)==(begins,commits,closes)
    locks=[p[0] for q,p in sync_connection.calls if q.startswith('SELECT pg_advisory_xact_lock_shared')]
    assert len(locks)==2 and locks==sorted(locks)
    assert all(q.startswith('SELECT') for q,p in sync_connection.calls)


def test_compatibility_mismatch_does_not_modify_or_create_other_strategy(store,sync_connection,ingestion):
    sync(store,'A')
    with pytest.raises(StoreError): store.require_compatible_snapshots()
    assert len(sync_connection.ledgers)==1
    sync(store,'B')
    ingestion.sources[0]['sha256']='f'*64
    store.context=SnapshotContext.from_ingestion_result(ingestion)
    sync(store,'A')
    before=deepcopy((sync_connection.ledgers,sync_connection.chunks))
    with pytest.raises(ValueError,match='Incompatible'): store.require_compatible_snapshots()
    assert (sync_connection.ledgers,sync_connection.chunks)==before
    sync(store,'B')
    assert len(store.require_compatible_snapshots())==2
