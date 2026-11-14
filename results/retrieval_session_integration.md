# Stage 5.4 retrieval session verification

Result: **STAGE5_4_READY_FOR_REVIEW**.

## Executed tests

- Targeted offline store/search/session/guard tests: **155 PASS, 0 FAIL** (3.65 s).
- Explicit PostgreSQL integration: **18 PASS, 0 FAIL, 0 BLOCKED** (24.04 s test
  execution; 43.60 s including disposable bootstrap and shutdown).
- Full offline regression after integration passed: **414 PASS, 12 subtests PASS,
  0 FAIL, 0 SKIP** (53.74 s).
- No retrieval over dev/test, model inference or evaluation metrics were executed.

Machine-readable outcomes and transaction evidence are in
[retrieval_postgres_integration.json](retrieval_postgres_integration.json).

## Database isolation

- New container: `day6-store-test-retrieval-a1d26a267c`.
- Loopback endpoint: `127.0.0.1:55434`, tmpfs-only PGDATA, no bind mounts/volumes.
- PostgreSQL **16.16**, extension **pgvector 0.8.7**, user `tester`.
- Cluster ID: `7707974844387852327`, distinct from the rejected main cluster.
- The isolated database is named `day6_lab` solely because Migration 0001 requires
  that name. It is not the main cluster at port 55433.
- Guard verified container configuration and independently discovered cluster ID
  before client connections. No `.env`, main database connection or main snapshot
  function was used. Credentials were random disposable fixtures, omitted here.
- The successful disposable container was stopped. No main volume was accessed.

Migration checksum remained:
`04f891492379e9800dd023d604b61e9bd7a60d40e48a1179dd4d6840633166e6`.
The catalog fingerprint matched its migration ledger after the integration cases.

## What the evidence establishes

- Real pgvector cosine ranking, deterministic ties, scores, A/B/C mapping and
  metadata/provenance preservation; filters execute before LIMIT and are bound.
- B and unfiltered C return the same materialization and scores.
- One preflight and one repeatable-read/read-only transaction for repeated calls.
- Shared locks demonstrably block a concurrent sync until session exit. Results
  remain stable; after exit the writer completes and a new session sees its vector
  change. Snapshot IDs alone deliberately do not attest to vector equality.
- A different namespace can commit while the session's MVCC read view stays fixed.
- Query failures close the connection with no reconnect/retry. Read-only mutation
  rejection: SQLSTATE `25006`; division error cleanup: `22012`; statement timeout:
  `57014`; advisory-lock timeout: `55P03`.
- Invalid incomplete/count states cannot commit (`P0001`); row snapshot/FK mismatch
  cannot commit (`23503`). Subsequent valid reads succeed. No triggers/constraints
  were disabled. Separate unit tests cover guard detection of synthetic mismatches;
  this is not a claim to have read impossible committed corrupted states.

## Contract and limits

See [session API/preflight SQL](../docs/stage5_retrieval_session.md).

Structural guards compare the independent descriptor, counts, pages, source/text
checksum fields, profile and approved snapshot identities without selecting full
text or vectors during preflight. Session labels are:

- `STRUCTURAL_INTEGRITY_VERIFIED`
- `VECTOR_INTEGRITY_NOT_REVERIFIED`

This review does not re-audit the 510 real stored vectors or their cache receipts.
It does not prove model provenance from numeric vectors. Query producer identity
remains an orchestrator responsibility. No main-database state is claimed to have
been queried in this checkpoint.

Idle timeout configuration is covered by unit tests; forced server disconnect after
idle expiry was not separately exercised. Lock/statement timeout cleanup was tested
on PostgreSQL. Session use is single-threaded; total run duration is not automatically
bounded by the per-statement/idle timeout settings. Keep runs short to avoid delaying
ingestion. Main-database retrieval and benchmark execution still require approval.

## Preserved artifacts

Frozen benchmark SHA-256:
`f1aafb9c62ccf63a8f98d47283a8286abe0c46087f8546cec82121d9b9586f5d`.

Stage 4 ingestion/upsert methods, Migration 0001, registry, corpus/manifest,
benchmark/gold and protected local files were not modified. No Git staging,
commit or push was performed.
