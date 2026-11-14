# Stage 5.4: retrieval session and integrity

`PgVectorStore.search(strategy, query_vector, top_k=3, filters=None)` retains its
signature. Standalone calls each own one transaction. For comparisons, prepare
query vectors before entry and use a transaction-bound session:

```python
from starter.src.retrieval import RetrievalBaseline

# context comes from load_manifest_pages() + SnapshotContext.from_ingestion_result().
# Verify source/manifest checksums and approved identities before entering.
baseline = RetrievalBaseline.from_context(store.dataset_id, store.profile_id, context)
with store.retrieval_session(baseline=baseline) as session:
    a = session.search('A', query_vector)
    b = session.search('B', query_vector)
    c = session.search('C', query_vector, filters=user_supplied_filters)
    snapshots = session.snapshots
    integrity = session.integrity
```

This is API usage, not an implemented benchmark runner. Never derive filters from
gold. Do not perform model inference or embedding within the session. No benchmark
questions or metrics were run in Stage 5.4.

## Identity and transaction

- The store retains no connection. Each session owns its connection and one
  `REPEATABLE READ READ ONLY` transaction. Do not share a session across threads.
- Shared transaction advisory locks for A and B are taken in sorted lock-key
  order by the existing compatibility helper and retained until transaction exit.
- Preflight executes once. Every A/B/C call uses the same connection, snapshots
  and read view. C reads B and never creates a separate namespace.
- Defaults: lock timeout 5 seconds, statement timeout 30 seconds and idle-in-
  transaction timeout 60 seconds. Session timeout arguments accept 1..300000 ms.
  These bound waits/statements/idle periods, not the total duration of a run.
  Keep runs bounded; otherwise readers can delay ingestion and retain old tuples.
- No automatic retry. A failed search poisons the handle, including when the
  caller catches its exception; context exit then forces rollback. Exit closes
  the connection and invalidates the handle. A server-side idle timeout may close
  the connection first; this remains an explicit failure, never a reconnect.
- A snapshot can predate a writer that committed while locks were being acquired.
  It remains internally consistent. Exact approved identity checks prevent silently
  accepting another materialization; locks do not promise the latest wall-clock view.

## Structural preflight

The independent baseline is constructed before connection/transaction from verified
`SnapshotContext`, reproducing the unchanged A/B chunk descriptors. It is not built
from rows being audited. The real `day06-postgresql` namespace additionally pins the
profile and both snapshot IDs from [Stage 4 apply evidence](../results/full_corpus_apply.json).
Synthetic namespaces use independent synthetic context for isolated tests.

The preflight checks:

1. Migration checksum/catalog fingerprint; canonical profile; complete A/B ledger,
   expected/actual counts, recomputed snapshot IDs and compatible corpus/manifest.
2. Equality to the supplied approved baseline, including snapshot counts and IDs.
3. Per namespace, `COUNT(*)`, distinct `(document_id, physical_page)` and count of
   rows whose snapshot/manifest/corpus identity differs from the ledger.
4. Ordered chunk IDs/provenance: SHA-256 of canonical descriptor rows equals the
   independently generated descriptor. This includes metadata, offsets and source,
   page and text checksum fields. The query selects neither full text nor vectors.

The aggregate SQL is parameterized:

```sql
SELECT count(*), count(DISTINCT (document_id,physical_page)),
       count(*) FILTER (WHERE snapshot_id IS DISTINCT FROM %s
                         OR manifest_sha256 IS DISTINCT FROM %s
                         OR corpus_sha256 IS DISTINCT FROM %s)
FROM day6_ingestion.chunks
WHERE dataset_id=%s AND profile_id=%s AND strategy=%s;
```

Descriptor columns and SQL identifiers are fixed in code. Exact cosine search
necessarily reads embeddings inside PostgreSQL, but preflight does not select,
hash or re-encode vectors. The resulting labels explicitly distinguish:

- `STRUCTURAL_INTEGRITY_VERIFIED`
- `VECTOR_INTEGRITY_NOT_REVERIFIED`

A valid unit vector can change without changing the snapshot ID. No lightweight
guard proves cache equality, producer model identity or vector/text correspondence.
Those remain separate vector round-trip/receipt audits. Query producer identity
must also be verified by the later orchestrator.

## Isolated integration

Run explicitly with the existing Stage 4 Python environment, Docker and the local
PostgreSQL 16.16 / pgvector 0.8.7 image:

```bash
PYTHONDONTWRITEBYTECODE=1 data/local/stage4/venv/bin/python -B \
  starter/scripts/check_retrieval_postgres.py \
  --report results/retrieval_postgres_new_run.json
```

The report path must be new. The runner creates a newly named tmpfs-only container
bound exclusively to `127.0.0.1:55434`, with random disposable credentials. It checks
the existing container/endpoint/cluster guard before connecting and rejects the
production cluster. Database name `day6_lab` is required by Migration 0001 even in
the isolated cluster; name alone is never evidence of isolation.

This runner **writes only synthetic fixtures and the unchanged migration to that
isolated cluster**. It never reads `.env` or connects to port 55433. It does not call
the historical runner that snapshots the main database. Successful containers are
stopped; failed containers are retained for manual review. No repair or test retry
is performed. Readiness polling occurs only before migration/test execution.

Migration 0001 prevents several corrupted states from being committed. Integration
tests assert those mutations fail and rollback; unit tests separately exercise the
preflight's detection of count/provenance/descriptor mismatches. No triggers or
constraints are disabled and those tests do not claim end-to-end reads of impossible
committed states.

See [integration evidence](../results/retrieval_postgres_integration.json).
