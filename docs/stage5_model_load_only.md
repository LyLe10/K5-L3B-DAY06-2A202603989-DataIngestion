# Stage 5.7B-A5: guarded model-load-only preparation

> **Historical status - checkpoint A5.** Statements below that the real entry point is absent or always disabled describe that earlier offline checkpoint. See [current model/probe wiring](stage5_minimal_live_wiring.md) and [current guarded DEV runtime](stage5_live_dev_runtime.md). Regenerate current canonical requests and code identities from the actual executing workspace; historical identities do not authorize current code. Guarded runtime availability does not constitute live execution approval. Model-only and DEV operations require their own explicit approvals; TEST remains blocked.

Offline implementation and synthetic tests only. No real model/tokenizer is loaded
or imported by this checkpoint, and no approval is issued. `execute_model_load_only()`
always raises. `execute_dev()` and `execute_live_probe()` remain disabled; test
holdout stays blocked. There is no CLI or environment/flag bypass.

## Small scope and request

`model_load_request(*, root, run_id, executor_id)` reads local code and accepted
profile evidence, without constructing an adapter or reading benchmark questions.
It creates a canonical request for `LAB_MODEL_LOAD_ONLY`, purpose `MODEL_LOAD_ONLY`,
and `execution_mode=OFFLINE_SYNTHETIC`. It binds the approved model name, exact
revision, all ten artifact SHA-256 values, immutable profile, evidence hash, code
hashes, CPU/float32/eval configuration, Stage 5 cache and new audit run destination.

The model is intfloat/multilingual-e5-small at revision
fd1525a9fd15316a2d503bf26ab031a61d056e98. The expected profile is
528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651.
Expected artifact identities come from the unchanged Stage 4 adapter and must
equal accepted profile evidence. Snapshot/cache paths are explicit and local.
The query cache is `data/local/stage5/embedding_cache`, not the adapter's default
Stage 4 cache. This checkpoint does not create or write the real cache.

The request explicitly prohibits query/document encoding, PostgreSQL, retrieval
and evaluation. It does not contain a benchmark split, questions or dev evaluation
configuration. An approval for the 45-search dev run cannot authorize a model-only
attempt or vice versa. No token from the current synthetic mode authorizes live use.

## Authorization and consumption reuse

`verify_model_load_approval()` validates the purpose/model contract and reuses the
accepted `LabDecision`/`VerifiedGrant` and manual-decision verifier. Shared human
verification was extracted into `lab_dev_runtime.verify_manual_decision()`; the
existing dev verifier still validates its original full request first. There is
no new production security framework, issuer or default authority.

`verify_model_load_approval()` is not a standalone complete request-schema
validator. The current simulation first regenerates the request from local
identities and compares the exact canonical request before approval verification.
A future live entry point must preserve that invariant or implement complete
independent request validation; calling this verifier alone is insufficient.

An authority selected outside the executor must authenticate a real external human
decision before any future real load. Reviewer and executor identities must differ;
different strings alone are not proof of independent humans. Current tests use
only an ephemeral synthetic authority. Missing/forged/expired/wrong-scope or wrong
request decisions fail before consumption/model factory. There is no caller clock
override. Operator clock and local filesystem custody remain lab assumptions.

The existing durable local ConsumptionLedger is reused unchanged. Its unique
approval/run/request claim COMMIT happens before any model/tokenizer factory.
Failure, timeout, process crash or absent output never resets that claim. No retry
or automatic audit/output overwrite is implemented. Local deletion/restoration or
cloning can defeat custody; no production anti-rollback guarantee is claimed.

## Disabled factory and runtime contract

`simulate_model_load_only(..., model_factory=...)` accepts Mock factories only,
rebuilds exact request identities and consumes approval. It reuses
`verify_model_artifacts()` before invoking the mock with the existing MyEmbedder
signature: model_name, revision, snapshot_path and cache_dir. No implicit constructor
or download is provided. A future reviewed real factory must use the pinned
MyEmbedder constructor, whose code initializes CPU float32/eval, local files only,
mean pooling and normalization. It must not invoke encode methods or auto-smoke-test.

The `isinstance(model_factory, Mock)` check is a synthetic-test convention, not
a security sandbox. A Mock's `side_effect` can execute arbitrary Python code.
Injected factories and their side effects remain trusted test dependencies.

After initialization, the seam checks canonical profile identity, dimension 384,
explicit cache path, CPU/float32/eval runtime flags and both 512-token limits.
Adapter counters must show zero calls/inputs/encoded inputs/batches and no query
token lengths. No QueryProducer, store, database probe, session or evaluator is
called. No model handle is returned. A finally block releases this owner's adapter
reference; there is no invented close API or promise of immediate OS memory reclaim.
Initialization failures before an adapter is returned remain factory responsibilities.

Runtime counters verify the adapter contract; they cannot independently prove
the absence of arbitrary factory side effects. A future live factory must be
code-reviewed to exclude automatic inference, encoding, downloads and database
access, including operations outside the adapter's counters.

## Minimal sanitized audit

Audit reuses the existing private, exclusive-file/fsync writer under
`data/local/stage5/lab_audit/<run_id>/`. Its scope and model/profile fields are now
recorded explicitly, alongside run ID, request hash, approval/authority/decision
IDs, consumption identity, sequence, timestamp, stage and status. Every write in
the model-only path is read back and checked against its canonical content digest
before continuing. Success is not returned unless the terminal audit verifies.

| Status | Meaning |
|---|---|
| CONSUMED / STAGE_STARTED | Durable claim and staged preparation |
| MODEL_LOAD_VERIFIED | Factory returned and runtime checks passed; terminal audit verified |
| ARTIFACT_MISMATCH | Missing/changed/unsafe artifact after consumption, before factory |
| MODEL_PROFILE_MISMATCH | Runtime profile/cache/device/dtype/eval/dimension/no-encoding mismatch |
| MODEL_LOAD_FAILED | Factory initialization failure or timeout |
| AUDIT_WRITE_FAILED | Exception outcome when audit creation/write/readback fails; never success |

All current records/results explicitly state `OFFLINE_SYNTHETIC`; successful fake
adapter tests are not real model-load evidence. No load-time or memory measurements
are fabricated. Audit records contain no raw exception/traceback, credentials,
tokens, weights, vectors, private absolute paths or environment variables.

If audit storage fails, persisting another failure record may be impossible. The
sanitized exception status is AUDIT_WRITE_FAILED, the claim remains consumed and
no second write attempt is made automatically. Process death after claim but before
first audit may leave only the ledger record. Reconcile manually; never reload
just because a terminal record is absent. Audit hashes are integrity checks, not
proof against a workspace owner replacing storage. Effective ACLs and WSL/NTFS
durability/TOCTOU limitations from the lab custody design remain applicable.

## Exact approval still needed before a real load

Review a real, currently absent guarded load-only entry point/factory and its code
hashes first. Then obtain a separate authenticated manual approval for one
MODEL_LOAD_ONLY attempt, naming the exact profile/model/revision/artifact and code
identities, CPU float32/eval, explicit local snapshot/cache, run/audit destination,
reviewer/executor, expiry window and durable consumption procedure. Its execution
mode must describe real loading; an OFFLINE_SYNTHETIC request cannot be reused.

The approval must explicitly permit model **and tokenizer initialization only**,
with no encoding, inference, PostgreSQL connection, retrieval or benchmark. It must
cover local read access and audit writes; any cache write or separate smoke query
requires its own explicit scope. Do not silently spend a dev-evaluation approval
on this checkpoint. Keep all live entry points blocked until that separate review
and explicit user authorization have occurred.
