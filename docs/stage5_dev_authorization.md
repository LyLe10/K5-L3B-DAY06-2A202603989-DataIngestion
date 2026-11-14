# Stage 5.7A: offline dev authorization and runtime wiring

This checkpoint implements a synthetic test seam, not permission to execute the
real dev benchmark. `dev_bootstrap.execute_dev()` remains disabled and the existing
CLI remains plan-only. Test execution remains blocked. No production authority,
signing key, DSN, model factory or database connector is supplied by this module.

## Canonical request

`authorization_request(prepared, *, root, run_id, output)` accepts a fresh
`prepare_dev()` result. It returns canonical JSON (the existing sorted-key,
compact JSON contract), not a caller-supplied `approved` boolean. Its version-1
fields bind:

| Fields | Binding |
|---|---|
| `authorization_version`, `scope`, `split`, `single_execution` | Version 1, SYNTHETIC_ONLY, dev, one execution |
| `run_id`, `output`, `plan_sha256` | Unique run, new Stage 5 runs directory, prepared plan |
| `question_ids`, `question_count`, `retrieval_calls` | Ordered 15 frozen dev IDs, 15 questions, 45 searches |
| `freeze_sha256`, `benchmark_manifest_sha256`, `frozen_files` | Frozen benchmark identity and dev/test file hashes |
| `manifest_sha256`, `source_checksums` | Verified corpus sources |
| `code`, `bootstrap_source_hashes`, `execution_source_hashes` | Evaluator, bootstrap and this execution module from the same root |
| `model`, `profile_id` | Canonical profile, pinned revision/artifact hashes, local snapshot/cache configuration |
| `database` | Endpoint, cluster, PostgreSQL/pgvector versions, migration/catalog, read-only plan |
| `snapshot_ids`, `descriptor_hashes` | Approved A/B snapshots and descriptors |
| `configuration`, `configuration_sha256` | A/B/C, K=3, 120 seconds and exact approved configuration |

The request digest is `evaluation.digest(json.loads(request_canonical))`, using
the existing canonical hashing contract. Rebuilding from fresh local preparation
must produce exactly the same canonical request before approval consumption.

## Trust boundary

`verify_authorization(request_canonical, approval, *, authority, now=None)` requires
an explicitly injected authority with `scope=SYNTHETIC_ONLY`. Its
`verify(request_canonical, approval)` authenticates the approval and returns a
`VerifiedGrant(approval_id, authority_id, request_sha256, not_before, expires_at)`.
The wrapper checks authority identity, request identity and validity interval
`not_before <= now < expires_at`. Missing, forged and mismatched approvals fail.
The optional clock is for deterministic synthetic tests.

Only the test module defines a synthetic HMAC authority. Its ephemeral random key
exists solely in fixture memory; it is not a production trust root. Production
approval cannot be minted by this package. An arbitrary caller-selected verifier
is not independent authorization: trusted orchestration must select the authority,
not an approval file or untrusted caller.

A future real integration requires a separately reviewed authority implementation,
operator-controlled trust root, authenticated reviewer decision, trustworthy clock,
revocation/expiry policy and durable ledger custody. It must bind this full request,
including code changes introduced by that integration. Adding this requires a new
review; neither metadata nor environment variables nor CLI flags unlock runtime.

## Atomic single-use ledger

`ConsumptionLedger(root=..., path=...).consume(request_canonical, grant)` stores
claims under `data/local/stage5/authorization/consumption.sqlite3`. Traversal,
symlinks/junctions and unsafe SQLite sidecar paths are rejected. New files request
0600 and the directory 0700. Effective Windows/WSL ACLs require operator review.

SQLite uses `BEGIN IMMEDIATE`, `synchronous=FULL`, DELETE journaling and unique
constraints on `(authority, approval_id)`, `run_id`, and request digest. A successful
claim COMMIT happens before model loading, probing or retrieval. A concurrent
claim fails on locking/uniqueness, with no application retry. A process crash
after the claim remains consumed; failures do not delete/reset claims. Expiry
is evaluated at authorization entry, not used to revive an existing claim.

The ledger is durable local state, not a secret approval file. Protect it from
deletion/restoration and concurrent malicious filesystem edits. Path checks are
not a sandbox against an attacker who controls the operator's filesystem; SQLite
durability depends on filesystem/fsync guarantees. A restored/deleted ledger can
invalidate replay protection, so real operation needs protected custody and recovery
policy. Database credentials are never stored in it.

## Offline runtime wiring and ownership

`simulate_authorized_dev(..., wiring=OfflineWiring(...))` accepts **Mock dependencies
only**, checks dev-only configuration, prepares locally, verifies authorization,
then atomically consumes it. This is an integration-test seam, not a production
entry point or a security sandbox for arbitrary injected Python side effects.

After consumption it verifies model file checksums without imports/inference, then:

1. Calls the model-factory mock with the actual `MyEmbedder` argument contract.
2. Checks canonical runtime profile/cache, then creates `QueryProducer` via its mock.
3. Calls a probe mock for the approved endpoint and rejects identity mismatch,
   privileged role or `role_review_required=True`.
4. Calls a private-DSN store-factory mock with dimensions, dataset/profile/context.
   A future reviewed factory would construct `PgVectorStore(database_url, 384, ...)`.
   Credentials must never enter request, result or artifacts.
5. Calls the runner mock once with the prepared bundle/baseline and no output path.
6. Saves and verifies through Stage 5.6 artifact mocks, with the approved outer run ID.

The orchestrator never calls `producer.prepare()` or opens a retrieval session.
The existing runner alone prepares the 15 query vectors, then owns one read-only
session and 45 A/B/C calls, sharing each query vector. No model inference occurs
inside that transaction. The runner currently generates an internal random run ID;
the orchestrator binds the approved outer run ID before artifact serialization.
Trace identities do not include that manifest field.

Synthetic end-to-end tests wrap the existing QueryProducer, runner and artifact
functions with mocks and supply fake adapters/store sessions and temporary synthetic
questions. They do not run the real frozen benchmark or connect to PostgreSQL.

## Failures and remaining gates

Any exception propagates without retry or deadline increase. A consumed grant stays
consumed after artifact/model/profile/probe/role/store/runner/timeout/write failure.
The runner can return INCOMPLETE with partial traces; its summary must remain null.
Artifact write/verification failure must not be reported as successful completion.
Unfinalized output is retained for inspection and never overwritten automatically.

Before real runtime: approve a genuine authority/consumption integration, filesystem
ACL/custody policy, live model factory, SELECT-only connection factory and cluster
identity privileges, exact code identities, and a single controlled dev execution.
The retrieval deadline remains 120 seconds, not a hard real-time guarantee.
No production database identity, runtime model behavior or live evaluation latency
is verified by these offline tests.
