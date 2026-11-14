"""Validated namespace-scoped snapshot sync and read-only cosine retrieval."""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any

from .embeddings import validate_vector
from .models import Chunk, DocumentPage
from .schema import (
    EmbeddingProfile, Namespace, Snapshot, canonical_json, load_migrations, require_compatible,
)

MIGRATION_SHA256 = '04f891492379e9800dd023d604b61e9bd7a60d40e48a1179dd4d6840633166e6'

# Only these trusted identifiers are composed into SQL. All data uses bind values.
CHUNK_COLUMNS = (
    'dataset_id', 'profile_id', 'strategy', 'chunk_id', 'snapshot_id', 'manifest_sha256',
    'corpus_sha256', 'document_id', 'source', 'source_sha256', 'physical_page',
    'printed_page_label', 'page_id', 'section', 'text', 'text_sha256', 'page_text_sha256',
    'normalized_char_count', 'start_char', 'end_char', 'metadata', 'embedding',
)
LEDGER_COLUMNS = (
    'snapshot_id', 'manifest_sha256', 'corpus_sha256', 'chunkset_sha256', 'chunking_config',
    'selected_page_count', 'expected_count', 'actual_count', 'status', 'completed_at',
)
NAMESPACE_WHERE = 'dataset_id=%s AND profile_id=%s AND strategy=%s'
_MUTABLE = CHUNK_COLUMNS[4:]
CHUNK_UPSERT = (
    'INSERT INTO day6_ingestion.chunks AS stored (' + ','.join(CHUNK_COLUMNS) + ') VALUES ('
    + ','.join('%s::jsonb' if col == 'metadata' else '%s::public.vector' if col == 'embedding' else '%s'
               for col in CHUNK_COLUMNS)
    + ') ON CONFLICT (dataset_id,profile_id,strategy,chunk_id) DO UPDATE SET '
    + ','.join(col + '=EXCLUDED.' + col for col in _MUTABLE)
    + ' WHERE ROW(' + ','.join('stored.' + col for col in _MUTABLE)
    + ') IS DISTINCT FROM ROW(' + ','.join('EXCLUDED.' + col for col in _MUTABLE) + ')'
)


class StoreError(ValueError):
    """Invalid identity/context/data; never infer missing provenance or repair it."""


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise StoreError('Expected lowercase SHA-256')
    return value


def _text(value):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise StoreError('Expected nonempty text without NUL')
    return value


@dataclass(frozen=True)
class SnapshotContext:
    """Immutable copy of caller-supplied, loader-verified corpus evidence.

    This checks internal consistency, not permission or the PDF on disk. The
    caller must first use load_manifest_pages(); chunks alone cannot create it.
    """
    manifest_sha256: str
    corpus_canonical: str

    def __post_init__(self):
        _sha(self.manifest_sha256)
        try:
            payload = json.loads(self.corpus_canonical)
            if canonical_json(payload) != self.corpus_canonical or set(payload) != {'pages', 'sources'}:
                raise StoreError('Noncanonical corpus context')
            pages, sources = payload['pages'], payload['sources']
            if not isinstance(pages, list) or len(pages) < 30 or not isinstance(sources, list):
                raise StoreError('Context requires at least 30 independently supplied pages')
            source_map = {}
            for source in sources:
                sid = _text(source['source_id'])
                if sid in source_map:
                    raise StoreError('Duplicate source in context')
                _sha(source['sha256'])
                _text(source['source'])
                source_map[sid] = source
            seen, page_ids = set(), set()
            for item in pages:
                page = DocumentPage(**item)
                key = (page.document_id, page.page)
                if type(page.page) is not int or page.page < 1 or key in seen:
                    raise StoreError('Invalid/duplicate physical page')
                seen.add(key)
                _text(page.text)
                source = source_map[page.document_id]
                if page.source != source['source']:
                    raise StoreError('Page/source mismatch')
                m = page.metadata
                required = {'source_id', 'physical_page', 'page_id', 'printed_page_label',
                            'section', 'section_evidence', 'version', 'normalized_char_count',
                            'text_sha256', 'extraction_status'}
                if not isinstance(m, dict) or not required <= m.keys() or '_chunking' in m:
                    raise StoreError('Incomplete page metadata')
                pid = _text(m['page_id'])
                if pid in page_ids:
                    raise StoreError('Duplicate page ID')
                page_ids.add(pid)
                _text(m['section'])
                _text(m['section_evidence'])
                if (m['source_id'] != page.document_id or type(m['physical_page']) is not int
                        or m['physical_page'] != page.page or type(m['normalized_char_count']) is not int
                        or m['normalized_char_count'] != len(page.text) or m['extraction_status'] != 'ok'
                        or m['text_sha256'] != hashlib.sha256(page.text.encode()).hexdigest()):
                    raise StoreError('Page metadata/checksum mismatch')
                for field in ['printed_page_label', 'version']:
                    if m[field] is not None and (not isinstance(m[field], str) or '\x00' in m[field]):
                        raise StoreError('Invalid nullable metadata')
        except (TypeError, KeyError, ValueError) as exc:
            raise StoreError('Invalid corpus context: ' + str(exc)) from exc

    @classmethod
    def from_ingestion_result(cls, result):
        return cls(result.manifest_sha256, canonical_json(
            dict(pages=[asdict(p) for p in result.pages], sources=result.sources)))

    @property
    def pages(self):
        return [DocumentPage(**item) for item in json.loads(self.corpus_canonical)['pages']]


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int, *,
                 dataset_id: str = 'day06-postgresql', profile_id: str | None = None,
                 profile: EmbeddingProfile | None = None,
                 context: SnapshotContext | None = None) -> None:
        """No connection on construction; unconfigured instances cannot register/write."""
        _text(database_url)
        if type(dimensions) is not int or dimensions != 384:
            raise StoreError('Store requires exactly 384 dimensions')
        Namespace(dataset_id, profile_id if profile_id is not None else '0' * 64, 'A')
        if context is not None and type(context) is not SnapshotContext:
            raise StoreError('Expected explicit SnapshotContext')
        self._database_url = database_url
        self.dimensions, self.dataset_id, self.profile_id = dimensions, dataset_id, profile_id
        self.context = context
        self._profile = self._validate_profile(profile) if profile is not None else None

    def _validate_profile(self, profile):
        if self.profile_id is None or type(profile) is not EmbeddingProfile:
            raise StoreError('Explicit profile_id and EmbeddingProfile required')
        checked = EmbeddingProfile(profile.config_canonical)
        if checked.profile_id != self.profile_id:
            raise StoreError('Profile ID/canonical config mismatch')
        return checked

    def _connect(self, *, readonly=False):
        # Lazy driver import keeps pure validation tests independent of psycopg.
        import psycopg
        options = '-c default_transaction_read_only=on' if readonly else ''
        return psycopg.connect(self._database_url, connect_timeout=5, autocommit=True, options=options)

    @staticmethod
    def _verify_schema(cursor):
        migrations = load_migrations()
        if len(migrations) != 1 or migrations[0].version != 1 or migrations[0].checksum != MIGRATION_SHA256:
            raise StoreError('Local migration differs from approved 0001')
        cursor.execute("SELECT to_regclass('day6_ingestion.schema_migrations')")
        if cursor.fetchone() == (None,):
            raise StoreError('Migration 0001 has not been applied')
        cursor.execute('SELECT version,name,checksum,catalog_sha256,'
                       'day6_ingestion.catalog_fingerprint() FROM day6_ingestion.schema_migrations ORDER BY version')
        rows = cursor.fetchall()
        if (len(rows) != 1 or rows[0][:3] != (1, migrations[0].name, MIGRATION_SHA256)
                or not isinstance(rows[0][3], str) or not re.fullmatch('[0-9a-f]{64}', rows[0][3])
                or rows[0][3] != rows[0][4]):
            raise StoreError('Migration history/checksum/catalog mismatch')

    def create_schema(self) -> None:
        """Verify existing 0001 in a read-only transaction; never execute DDL."""
        with self._connect(readonly=True) as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    self._verify_schema(cursor)

    def register_profile(self, profile: EmbeddingProfile | None = None, *, connection=None) -> str:
        """Join caller's active transaction, or own exactly one transaction.

        With connection supplied: no begin/commit/rollback/close here. A caller
        must propagate any error and roll back the enclosing strategy sync.
        """
        checked = self._validate_profile(profile if profile is not None else self._profile)
        if connection is not None:
            if connection.info.transaction_status.name != 'INTRANS':
                raise StoreError('Registration requires an active caller transaction')
            with connection.cursor() as cursor:
                self._verify_schema(cursor)
                self._register_profile_cursor(cursor, checked)
        else:
            with self._connect() as owned:
                with owned.transaction():
                    with owned.cursor() as cursor:
                        self._verify_schema(cursor)
                        self._register_profile_cursor(cursor, checked)
        return checked.profile_id

    @staticmethod
    def _register_profile_cursor(cursor, profile):
        config = profile.config
        cursor.execute('INSERT INTO day6_ingestion.embedding_profiles '
                       '(profile_id,model_name,revision,dimensions,config_canonical,config) '
                       'VALUES (%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT (profile_id) DO NOTHING',
                       (profile.profile_id, config['model_name'], config['revision'], 384,
                        profile.config_canonical, profile.config_canonical))
        cursor.execute('SELECT model_name,revision,dimensions,config_canonical,config '
                       'FROM day6_ingestion.embedding_profiles WHERE profile_id=%s', (profile.profile_id,))
        expected = (config['model_name'], config['revision'], 384, profile.config_canonical, config)
        if cursor.fetchone() != expected:
            raise StoreError('Immutable profile conflict; existing profile not updated')

    def validate_batch(self, strategy, chunks, vectors, *, vector_chunk_ids, embedding_profile_id):
        """Return detached (chunk, float32 vector) pairs in supplied order; no DB.

        ID/profile receipts bind producer order/identity. Numeric vectors alone
        cannot prove which text or model produced them. Context comes separately
        from loader evidence, never inferred from this batch.
        """
        self._validate_profile(self._profile)
        Namespace(self.dataset_id, self.profile_id, strategy)
        if self.context is None:
            raise StoreError('Verified corpus context required; chunks are not completeness evidence')
        if (not isinstance(chunks, list) or not chunks or not isinstance(vectors, list)
                or len(chunks) != len(vectors) or any(type(c) is not Chunk for c in chunks)):
            raise StoreError('Expected nonempty chunks and equal vector count')
        ids = [c.chunk_id for c in chunks]
        if len(set(ids)) != len(ids) or vector_chunk_ids != ids:
            raise StoreError('Duplicate chunk IDs or vector/input order mismatch')
        if embedding_profile_id != self.profile_id:
            raise StoreError('Vector producer profile does not match store namespace')
        # Rebuild expected IDs/text/metadata/offsets from independent page context.
        # This validates full input only; it does not synchronize any database row.
        from .chunking import fixed_size, by_paragraph
        pages = self.context.pages
        expected = {c.chunk_id: c for p in pages for c in
                    (fixed_size(p, 500, 50) if strategy == 'A' else by_paragraph(p, 500))}
        if set(ids) != set(expected):
            raise StoreError('Batch does not match all context pages/chunks')
        result = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            if chunk != expected[chunk.chunk_id]:
                raise StoreError('Chunk ID/text/source/metadata/offsets differ from verified context')
            try:
                converted = validate_vector(vector)
            except (TypeError, ValueError) as exc:
                raise StoreError('Invalid vector: ' + str(exc)) from exc
            result.append((Chunk(**json.loads(canonical_json(asdict(chunk)))), converted))
        return result

    @staticmethod
    def _prepare_snapshot(namespace, context, pairs):
        payload = json.loads(context.corpus_canonical)
        sources = {s['source_id']: s['sha256'] for s in payload['sources']}
        pages = sorted(context.pages, key=lambda p: (p.document_id, p.page))
        corpus_descriptor = [dict(document_id=p.document_id, source=p.source, physical_page=p.page,
                                  source_sha256=sources[p.document_id], metadata=p.metadata)
                             for p in pages]
        chunk_descriptor = [dict(chunk_id=c.chunk_id, text_sha256=hashlib.sha256(c.text.encode()).hexdigest(),
                                 metadata=c.metadata) for c, v in sorted(pairs, key=lambda pair: pair[0].chunk_id)]
        digest = lambda data: hashlib.sha256(canonical_json(data).encode()).hexdigest()
        snapshot = Snapshot(namespace, context.manifest_sha256, digest(corpus_descriptor),
                            digest(chunk_descriptor), len(pages), len(pairs), len(pairs), 'complete')
        rows = {}
        for chunk, vector in pairs:
            m, trace = chunk.metadata, chunk.metadata['_chunking']
            rows[chunk.chunk_id] = (
                *namespace.parameters, chunk.chunk_id, snapshot.snapshot_id,
                snapshot.manifest_sha256, snapshot.corpus_sha256, chunk.document_id,
                chunk.source, sources[chunk.document_id], chunk.page, m['printed_page_label'],
                m['page_id'], m['section'], chunk.text, hashlib.sha256(chunk.text.encode()).hexdigest(),
                m['text_sha256'], m['normalized_char_count'], trace['start_char'], trace['end_char'], m, vector,
            )
        config = dict(strategy=namespace.strategy, algorithm_version=1, unit='characters',
                      parameters=dict(size=500, overlap=50) if namespace.strategy == 'A' else dict(max_size=500))
        ledger = (snapshot.snapshot_id, snapshot.manifest_sha256, snapshot.corpus_sha256,
                  snapshot.chunkset_sha256, config, snapshot.selected_page_count,
                  snapshot.expected_count, snapshot.actual_count, 'complete')
        return snapshot, rows, ledger

    @staticmethod
    def _read_sync_state(cursor, namespace):
        cursor.execute('SELECT ' + ','.join(LEDGER_COLUMNS)
                       + ' FROM day6_ingestion.strategy_snapshots WHERE ' + NAMESPACE_WHERE,
                       namespace.parameters)
        ledger = cursor.fetchone()
        selected = [col if col != 'embedding' else 'embedding::text' for col in CHUNK_COLUMNS]
        cursor.execute('SELECT ' + ','.join(selected) + ' FROM day6_ingestion.chunks WHERE '
                       + NAMESPACE_WHERE + ' ORDER BY chunk_id', namespace.parameters)
        rows = {}
        for row in cursor.fetchall():
            # pgvector text output round-trips float32; compare actual stored vectors,
            # not only the snapshot digest (which intentionally excludes vectors).
            vector = validate_vector(json.loads(row[-1]))
            if row[3] in rows:
                raise StoreError('Duplicate persisted chunk identity')
            rows[row[3]] = (*row[:-1], vector)
        return ledger, rows

    @staticmethod
    def _same_materialization(actual_ledger, actual_rows, expected_ledger, expected_rows):
        return (actual_ledger is not None and tuple(actual_ledger[:-1]) == expected_ledger
                and actual_ledger[-1] is not None and actual_rows == expected_rows)

    def sync_snapshot(self, strategy, chunks, vectors, *, vector_chunk_ids, embedding_profile_id):
        """Validate the entire input first, then atomically replace ONE namespace.

        Receipts are explicit; no inferred vector provenance. No retry or DDL.
        Return diagnostics only after the driver's transaction context commits.
        """
        if type(self.context) is not SnapshotContext:
            raise StoreError('Verified corpus context required')
        # Revalidate/capture independent context and all values before connecting.
        context = SnapshotContext(self.context.manifest_sha256, self.context.corpus_canonical)
        namespace = Namespace(self.dataset_id, self.profile_id, strategy)
        profile = self._validate_profile(self._profile)
        pairs = self.validate_batch(strategy, chunks, vectors, vector_chunk_ids=vector_chunk_ids,
                                    embedding_profile_id=embedding_profile_id)
        snapshot, wanted_rows, wanted_ledger = self._prepare_snapshot(namespace, context, pairs)
        written = deleted = 0
        replayed = False
        with self._connect() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout='5s'")
                    cursor.execute("SET LOCAL statement_timeout='30s'")
                self.register_profile(profile, connection=connection)
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_xact_lock(%s)', (namespace.lock_key,))
                    previous_ledger, previous_rows = self._read_sync_state(cursor, namespace)
                    replayed = self._same_materialization(previous_ledger, previous_rows, wanted_ledger, wanted_rows)
                    if not replayed:
                        # Reset actual_count atomically with a possibly smaller expected_count.
                        cursor.execute(
                            'INSERT INTO day6_ingestion.strategy_snapshots '
                            '(dataset_id,profile_id,strategy,snapshot_id,manifest_sha256,corpus_sha256,'
                            'chunkset_sha256,chunking_config,selected_page_count,expected_count,actual_count,status,completed_at) '
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,0,'syncing',NULL) "
                            'ON CONFLICT (dataset_id,profile_id,strategy) DO UPDATE SET '
                            'snapshot_id=EXCLUDED.snapshot_id,manifest_sha256=EXCLUDED.manifest_sha256,'
                            'corpus_sha256=EXCLUDED.corpus_sha256,chunkset_sha256=EXCLUDED.chunkset_sha256,'
                            'chunking_config=EXCLUDED.chunking_config,selected_page_count=EXCLUDED.selected_page_count,'
                            "expected_count=EXCLUDED.expected_count,actual_count=0,status='syncing',completed_at=NULL",
                            (*namespace.parameters, *wanted_ledger[:4], canonical_json(wanted_ledger[4]),
                             snapshot.selected_page_count, snapshot.expected_count))
                        for chunk_id in sorted(wanted_rows):
                            row = wanted_rows[chunk_id]
                            cursor.execute(CHUNK_UPSERT, (*row[:-2], canonical_json(row[-2]), canonical_json(row[-1])))
                            written += cursor.rowcount
                        cursor.execute('DELETE FROM day6_ingestion.chunks WHERE ' + NAMESPACE_WHERE
                                       + ' AND NOT (chunk_id=ANY(%s::text[]))',
                                       (*namespace.parameters, sorted(wanted_rows)))
                        deleted = cursor.rowcount
                        cursor.execute("UPDATE day6_ingestion.strategy_snapshots SET actual_count=%s,status='complete',"
                                       'completed_at=transaction_timestamp() WHERE ' + NAMESPACE_WHERE,
                                       (snapshot.expected_count, *namespace.parameters))
                    final_ledger, final_rows = self._read_sync_state(cursor, namespace)
                    if not self._same_materialization(final_ledger, final_rows, wanted_ledger, wanted_rows):
                        raise StoreError('Final ledger/materialization verification failed')
                    # Force the schema's deferred FK/completion checks before commit.
                    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
        return dict(dataset_id=namespace.dataset_id, profile_id=namespace.profile_id, strategy=strategy,
                    snapshot_id=snapshot.snapshot_id, expected_count=snapshot.expected_count,
                    replayed=replayed, written_rows=written, deleted_rows=deleted)

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]], *,
               vector_chunk_ids=None, embedding_profile_id=None) -> None:
        """Compatibility entry point; caller must supply the B-1 producer receipts."""
        self.sync_snapshot(strategy, chunks, vectors, vector_chunk_ids=vector_chunk_ids,
                           embedding_profile_id=embedding_profile_id)

    def require_compatible_snapshots(self, *, connection=None):
        """Guard comparisons; no retrieval. Supply the comparison's transaction
        to retain shared namespace locks until all comparison reads are finished.
        Without one, this returns only compatibility at the instant checked.
        """
        self._validate_profile(self._profile)
        namespaces = [Namespace(self.dataset_id, self.profile_id, s) for s in ('A', 'B')]

        def check(active):
            if active.info.transaction_status.name != 'INTRANS':
                raise StoreError('Compatibility check requires an active transaction')
            with active.cursor() as cursor:
                self._verify_schema(cursor)
                for ns in sorted(namespaces, key=lambda n: n.lock_key):
                    cursor.execute('SELECT pg_advisory_xact_lock_shared(%s)', (ns.lock_key,))
                snapshots = []
                for ns in namespaces:
                    cursor.execute('SELECT ' + ','.join(LEDGER_COLUMNS)
                                   + ' FROM day6_ingestion.strategy_snapshots WHERE ' + NAMESPACE_WHERE, ns.parameters)
                    row = cursor.fetchone()
                    if row is None or row[-1] is None:
                        raise StoreError('Missing completed A/B snapshot')
                    snap = Snapshot(ns, row[1], row[2], row[3], row[5], row[6], row[7], row[8])
                    if snap.snapshot_id != row[0]:
                        raise StoreError('Ledger snapshot identity mismatch')
                    snapshots.append(snap)
                require_compatible(*snapshots)
                return tuple(snapshots)

        if connection is not None:
            return check(connection)
        with self._connect(readonly=True) as owned:
            with owned.transaction():
                return check(owned)

    def retrieval_session(self, *, baseline=None, lock_timeout_ms=5000,
                          statement_timeout_ms=30000, idle_timeout_ms=60000, deadline_seconds=None):
        """Prepare vectors before entry; no connection is retained on this store."""
        from .retrieval import retrieval_session
        return retrieval_session(self, baseline=baseline, lock_timeout_ms=lock_timeout_ms,
                                 statement_timeout_ms=statement_timeout_ms, idle_timeout_ms=idle_timeout_ms,
                                 deadline_seconds=deadline_seconds)

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Standalone read-only search. Use retrieval_session for A/B/C comparisons."""
        if not isinstance(strategy, str) or strategy not in ('A', 'B', 'C'):
            raise StoreError('Expected retrieval strategy A, B or C')
        if type(top_k) is not int or top_k <= 0:
            raise StoreError('top_k must be a positive integer')
        if filters is not None and not isinstance(filters, dict):
            raise StoreError('filters must be a dictionary or None')
        filters = dict(filters or {})
        if (set(filters) - {'section'} or (filters and strategy != 'C')):
            raise StoreError('Only C supports section equality filtering')
        if 'section' in filters:
            _text(filters['section'])
        self._validate_profile(self._profile)
        try:
            vector = validate_vector(query_vector)
        except (TypeError, ValueError) as exc:
            raise StoreError('Invalid query vector: ' + str(exc)) from exc
        stored_strategy = 'B' if strategy == 'C' else strategy
        namespace = Namespace(self.dataset_id, self.profile_id, stored_strategy)
        with self.retrieval_session() as session:
            return session.search(strategy, vector, top_k, filters)

    def _search_in_session(self, connection, snapshots, strategy, query_vector, top_k, filters):
        if not isinstance(strategy, str) or strategy not in ('A', 'B', 'C'):
            raise StoreError('Expected retrieval strategy A, B or C')
        if type(top_k) is not int or top_k <= 0:
            raise StoreError('top_k must be a positive integer')
        if filters is not None and not isinstance(filters, dict):
            raise StoreError('filters must be a dictionary or None')
        filters = dict(filters or {})
        if (set(filters) - {'section'} or (filters and strategy != 'C')):
            raise StoreError('Only C supports section equality filtering')
        if 'section' in filters:
            _text(filters['section'])
        self._validate_profile(self._profile)
        try:
            vector = validate_vector(query_vector)
        except (TypeError, ValueError) as exc:
            raise StoreError('Invalid query vector: ' + str(exc)) from exc
        stored_strategy = 'B' if strategy == 'C' else strategy
        namespace = Namespace(self.dataset_id, self.profile_id, stored_strategy)
        columns = ('chunk_id', 'document_id', 'source', 'physical_page',
                   'printed_page_label', 'section', 'start_char', 'end_char',
                   'text', 'metadata', 'snapshot_id', 'manifest_sha256', 'corpus_sha256',
                   'source_sha256', 'page_text_sha256', 'text_sha256', 'page_id')
        # Typed section is constrained to equal metadata.section by Migration 0001.
        sql = ('SELECT ' + ','.join(columns)
               + ',embedding <=> %s::public.vector AS cosine_distance '
               'FROM day6_ingestion.chunks WHERE ' + NAMESPACE_WHERE
               + ' AND snapshot_id=%s'
               + (' AND section=%s' if filters else '')
               + ' ORDER BY cosine_distance ASC, chunk_id ASC LIMIT %s')
        snapshot = snapshots[0 if stored_strategy == 'A' else 1]
        with connection.cursor() as cursor:
            params = (json.dumps(vector), *namespace.parameters, snapshot.snapshot_id)
            if filters:
                params += (filters['section'],)
            cursor.execute(sql, (*params, top_k))
            results = []
            for rank, row in enumerate(cursor.fetchall(), 1):
                hit = dict(zip((*columns, 'cosine_distance'), row, strict=True))
                hit.update(rank=rank, score=1 - hit['cosine_distance'],
                           dataset_id=self.dataset_id, profile_id=self.profile_id,
                           requested_strategy=strategy, stored_strategy=stored_strategy)
                results.append(hit)
            return results
