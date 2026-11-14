"""Read-only retrieval sessions. No inference, ingestion, downloads or repair."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import threading
import time

from .schema import Namespace, Snapshot, canonical_json
from .store import CHUNK_COLUMNS, NAMESPACE_WHERE, SnapshotContext, StoreError

# No vectors or full text are selected by structural preflight.
DESCRIPTOR_COLUMNS = tuple(c for c in CHUNK_COLUMNS if c not in ('text', 'embedding'))
STAGE4_PROFILE = '528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651'
STAGE4_SNAPSHOTS = ('d06b89acda8d08a5c423bfb5d4cd82662a962481cd7a2f81b2ab324e08b3e860',
                    'c7d9d92e6695709595d044e5a5a09bb8f91826fb692474c7b1806751015ec1e0')


@dataclass(frozen=True)
class RetrievalBaseline:
    """Expected identities from independent loader-verified context, never DB rows.

    Callers must verify the source/manifest and approval before supplying context.
    This factory checks consistency; it does not certify approval or vector origin.
    For Stage 4, compare generated snapshot IDs to the approved apply evidence.
    """
    dataset_id: str
    profile_id: str
    snapshots: tuple
    descriptor_hashes: tuple

    @classmethod
    def from_context(cls, dataset_id, profile_id, context):
        from .chunking import fixed_size, by_paragraph
        if type(context) is not SnapshotContext:
            raise StoreError('Independent verified SnapshotContext required')
        context = SnapshotContext(context.manifest_sha256, context.corpus_canonical)
        payload = json.loads(context.corpus_canonical)
        sources = {s['source_id']: s['sha256'] for s in payload['sources']}
        pages = sorted(context.pages, key=lambda p: (p.document_id, p.page))
        digest = lambda value: hashlib.sha256(canonical_json(value).encode()).hexdigest()
        corpus = [dict(document_id=p.document_id, source=p.source, physical_page=p.page,
                       source_sha256=sources[p.document_id], metadata=p.metadata) for p in pages]
        snapshots, hashes = [], []
        for strategy in ('A', 'B'):
            ns = Namespace(dataset_id, profile_id, strategy)
            chunks = sorted([c for p in pages for c in
                             (fixed_size(p, 500, 50) if strategy == 'A' else by_paragraph(p, 500))],
                            key=lambda c: c.chunk_id)
            chunkset = [dict(chunk_id=c.chunk_id, text_sha256=hashlib.sha256(c.text.encode()).hexdigest(),
                             metadata=c.metadata) for c in chunks]
            snap = Snapshot(ns, context.manifest_sha256, digest(corpus), digest(chunkset),
                            len(pages), len(chunks), len(chunks), 'complete')
            rows = []
            for c in chunks:
                m, trace = c.metadata, c.metadata['_chunking']
                values = dict(dataset_id=dataset_id, profile_id=profile_id, strategy=strategy,
                              chunk_id=c.chunk_id, snapshot_id=snap.snapshot_id,
                              manifest_sha256=snap.manifest_sha256, corpus_sha256=snap.corpus_sha256,
                              document_id=c.document_id, source=c.source, source_sha256=sources[c.document_id],
                              physical_page=c.page, printed_page_label=m['printed_page_label'],
                              page_id=m['page_id'], section=m['section'],
                              text_sha256=hashlib.sha256(c.text.encode()).hexdigest(),
                              page_text_sha256=m['text_sha256'], normalized_char_count=m['normalized_char_count'],
                              start_char=trace['start_char'], end_char=trace['end_char'], metadata=m)
                rows.append([values[col] for col in DESCRIPTOR_COLUMNS])
            snapshots.append(snap)
            hashes.append(digest(rows))
        baseline = cls(dataset_id, profile_id, tuple(snapshots), tuple(hashes))
        baseline.validate_approved_identity()
        return baseline

    def validate_approved_identity(self):
        # Pins from approved Stage 4 apply evidence; synthetic namespaces remain
        # usable in isolated tests without pretending to be the real corpus.
        if self.dataset_id == 'day06-postgresql':
            if (self.profile_id != STAGE4_PROFILE
                    or tuple(s.snapshot_id for s in self.snapshots) != STAGE4_SNAPSHOTS):
                raise StoreError('Baseline differs from approved Stage 4 identities')


def preflight(store, connection, baseline):
    if (type(baseline) is not RetrievalBaseline or baseline.dataset_id != store.dataset_id
            or baseline.profile_id != store.profile_id or len(baseline.snapshots) != 2
            or len(baseline.descriptor_hashes) != 2):
        raise StoreError('Explicit matching retrieval baseline required')
    profile = store._validate_profile(store._profile)
    baseline.validate_approved_identity()
    snapshots = store.require_compatible_snapshots(connection=connection)
    if tuple(snapshots) != baseline.snapshots:
        raise StoreError('Snapshot identities differ from approved baseline')
    with connection.cursor() as cursor:
        cursor.execute('SELECT model_name,revision,dimensions,config_canonical,config '
                       'FROM day6_ingestion.embedding_profiles WHERE profile_id=%s', (store.profile_id,))
        config = profile.config
        if cursor.fetchone() != (config['model_name'], config['revision'], 384,
                                 profile.config_canonical, config):
            raise StoreError('Stored profile/canonical config mismatch')
        for snap, expected_hash in zip(snapshots, baseline.descriptor_hashes, strict=True):
            cursor.execute('SELECT count(*),count(DISTINCT (document_id,physical_page)),'
                           'count(*) FILTER (WHERE snapshot_id IS DISTINCT FROM %s '
                           'OR manifest_sha256 IS DISTINCT FROM %s OR corpus_sha256 IS DISTINCT FROM %s) '
                           'FROM day6_ingestion.chunks WHERE ' + NAMESPACE_WHERE,
                           (snap.snapshot_id, snap.manifest_sha256, snap.corpus_sha256, *snap.namespace.parameters))
            if cursor.fetchone() != (snap.expected_count, snap.selected_page_count, 0):
                raise StoreError('Row count/pages/snapshot provenance mismatch')
            cursor.execute('SELECT ' + ','.join(DESCRIPTOR_COLUMNS)
                           + ' FROM day6_ingestion.chunks WHERE ' + NAMESPACE_WHERE + ' ORDER BY chunk_id',
                           snap.namespace.parameters)
            actual_hash = hashlib.sha256(canonical_json(cursor.fetchall()).encode()).hexdigest()
            if actual_hash != expected_hash:
                raise StoreError('Chunk IDs/provenance differ from approved descriptor')
    return snapshots


class RetrievalDeadline:
    """One watchdog for one owned connection; never reconnects on cancellation."""
    def __init__(self, seconds):
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
            raise StoreError('Deadline must be finite and positive')
        self.ends = time.monotonic() + seconds
        self.connection = None
        self._lock = threading.Lock()
        self._closed = False
        self.expired = threading.Event()
        self.timer = threading.Timer(seconds, self._cancel)
        self.timer.daemon = True

    def _cancel(self):
        # Serialize cancellation with detachment, transaction exit and close.
        with self._lock:
            if self._closed:
                return
            self.expired.set()
            if self.connection is not None and not self.connection.closed:
                try:
                    self.connection.cancel_safe(timeout=1.0)
                except Exception:
                    # No retry. Deadline checks still force transaction exit/close.
                    pass

    def bind(self,connection):
        with self._lock:
            if self._closed:
                raise TimeoutError('Deadline already disarmed')
            self.connection=connection
        self.check()

    def check(self):
        if self.expired.is_set() or time.monotonic() >= self.ends:
            raise TimeoutError('Total retrieval deadline exceeded; no retry')

    def milliseconds(self, maximum):
        self.check()
        return max(1, min(maximum, int((self.ends-time.monotonic())*1000)))

    def close(self):
        self.timer.cancel()
        with self._lock:
            self._closed=True
            self.connection=None
        if self.timer.ident is not None and threading.current_thread() is not self.timer:
            self.timer.join()  # Finish cancellation before driver transaction/connection exit.


class RetrievalSession:
    """Transaction-bound handle, never stored on PgVectorStore or reusable on exit."""
    def __init__(self, store, connection, snapshots, deadline=None):
        self._store, self._connection, self._snapshots = store, connection, snapshots
        self._active, self._failed = True, False
        self._deadline = deadline
        self.integrity = ('STRUCTURAL_INTEGRITY_VERIFIED', 'VECTOR_INTEGRITY_NOT_REVERIFIED')

    @property
    def snapshots(self):
        return self._snapshots

    def search(self, strategy, query_vector, top_k=3, filters=None):
        if not self._active or self._failed:
            raise StoreError('Retrieval session is closed or failed; no retry')
        try:
            if self._deadline:
                self._deadline.check()
                with self._connection.cursor() as cursor:
                    cursor.execute('SELECT set_config(%s,%s,true)',
                                   ('statement_timeout', str(self._deadline.milliseconds(30000))+'ms'))
            result = self._store._search_in_session(self._connection, self._snapshots,
                                                    strategy, query_vector, top_k, filters)
            if self._deadline:
                self._deadline.check()
            return result
        except Exception:
            self._failed = True
            raise


@contextmanager
def retrieval_session(store, *, baseline=None, lock_timeout_ms=5000,
                      statement_timeout_ms=30000, idle_timeout_ms=60000, deadline_seconds=None):
    """One bounded read-only transaction. Prepare query vectors BEFORE entry."""
    for value in (lock_timeout_ms, statement_timeout_ms, idle_timeout_ms):
        if type(value) is not int or not 1 <= value <= 300000:
            raise StoreError('Timeout must be an integer in [1,300000] milliseconds')
    store._validate_profile(store._profile)
    if baseline is None:
        baseline = RetrievalBaseline.from_context(store.dataset_id, store.profile_id, store.context)
    session = None
    deadline = RetrievalDeadline(deadline_seconds) if deadline_seconds is not None else None
    try:
        if deadline:
            deadline.timer.start()
        with store._connect(readonly=True) as connection:
            try:
                if deadline:
                    deadline.bind(connection)
                with connection.transaction():
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                            for key, value in (('lock_timeout', lock_timeout_ms),
                                               ('statement_timeout', statement_timeout_ms),
                                               ('idle_in_transaction_session_timeout', idle_timeout_ms)):
                                timeout = deadline.milliseconds(value) if deadline else value
                                cursor.execute('SELECT set_config(%s,%s,true)', (key, str(timeout)+'ms'))
                        snapshots = preflight(store, connection, baseline)
                        if deadline:
                            deadline.check()
                        session = RetrievalSession(store, connection, snapshots, deadline)
                        yield session
                        if deadline:
                            deadline.check()
                        if session._failed:
                            raise StoreError('Retrieval failed; rolling back session, no retry')
                    finally:
                        if deadline:
                            deadline.close()
            finally:
                if deadline:
                    deadline.close()
    finally:
        if deadline:
            deadline.close()
        if session is not None:
            session._active = False
