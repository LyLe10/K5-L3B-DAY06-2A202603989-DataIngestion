# Stage 5.7B-A1: lab-controlled dev runtime preparation

This checkpoint is offline implementation and synthetic tests only. It does not
authorize live model loading, query encoding, PostgreSQL access or real benchmark
execution. No production broker is required or implemented. The existing
`dev_bootstrap.execute_dev()` is still disabled; both existing CLIs remain plan-only.
Test split execution is always blocked. No credentials, real approvals or keys are
created by the execution modules.

## Lab trust assumptions and manual decision

The lab operator controls the workspace, clock and local ledger. These are trusted
lab resources, not a production isolation boundary. The reviewer makes an explicit
human decision outside the executor and selects the approval verifier separately.
The executor cannot establish authority by setting `approved=True`, adding a CLI
flag, setting an environment variable or supplying an untrusted verifier.

`lab_authorization_request(prepared, *, root, run_id, output, executor_id)` reuses
the Stage 5.7A request builder with schema version 2, scope `LAB_CONTROLLED_DEV`,
an executor ID and explicit local-custody policy. It binds the exact canonical
request: 15 ordered dev IDs; frozen benchmark/file/source hashes; evaluator,
bootstrap and both orchestration code hashes; canonical profile/model/revision/
artifact/cache identities; database endpoint/cluster/version/migration/catalog;
A/B snapshots/descriptors; A/B/C, K=3, 120 seconds; unique run and new output.

`verify_lab_approval(request_canonical, approval, *, authority)` is independently
testable and has no issuance function or caller-controlled time argument. The
explicitly trusted `ManualApprovalVerifier.verify()` must authenticate the external
manual decision and return `LabDecision(grant, reviewer_id, executor_id, decision_id)`.
Its `VerifiedGrant` binds authority/approval/request IDs and validity interval.
The wrapper rejects missing/invalid decisions, wrong scope/request/executor,
reviewer equal to executor, and expired/not-yet-valid grants. Local wall-clock
UTC epoch time is used; clock custody is an operator responsibility in this lab.

Different reviewer/executor strings do not prove different people. Authenticating
the human decision and preventing executor-issued approval remain verifier/custody
responsibilities. There is no default verifier or real signing implementation in
this checkpoint. Only tests contain an issuer, with random ephemeral synthetic keys.
Before real use the user must approve a concrete manual authentication/verification
procedure, its custody and exact request. A plain JSON file or chat text is not
silently accepted as machine-verifiable authorization.

Manual lifecycle:

1. Prepare locally and present exact canonical request/hash to the reviewer.
2. Obtain an external, authenticated manual decision for that request/run only.
3. Rebuild preparation and require byte-identical canonical request.
4. Verify the decision, then consume the approval atomically before any runtime.
5. Keep it consumed after success, failure, timeout, crash or missing result.
6. Any later attempt requires a new explicit decision/run; no automated retry/reset.

## Local consumption and limitations

The accepted `ConsumptionLedger` is reused unchanged at
`data/local/stage5/authorization/consumption.sqlite3`: SQLite `BEGIN IMMEDIATE`,
`synchronous=FULL`, DELETE journaling, unique approval/run/request identities and
no application retry. A claim must COMMIT before model verification/loading,
database probe or retrieval. Concurrent/replayed claims fail closed.

The existing path checks reject traversal, symlinks/junctions and unsafe sidecar
paths. Claims survive the process-crash case covered by synthetic tests. This does
not establish power-loss durability or production anti-rollback. Deleting,
restoring or cloning local state can defeat single-use custody. The operator must
protect the ledger and its parent directories, forbid rollback/deletion during
the approved run, and stop if custody is uncertain. Do not reinitialize/reset a
ledger after an uncertain claim.

WSL modes 0700/0600 are requested, but effective NTFS/Windows ACLs and filesystem
fsync behavior require review. Check-then-open paths still have TOCTOU limitations
against concurrent malicious filesystem changes. These helpers are not a security
sandbox against the workspace owner or local administrator.

## Disabled factory boundaries

The module defines `ModelAdapterFactory`, `QueryCacheFactory`,
`ReadOnlyConnectionFactory`, and `NamespaceStoreFactory` protocols.
`DisabledLabFactories` supplies inspectable signatures, and every method raises
`LAB_LIVE_RUNTIME_DISABLED` without importing the heavy runtime or reading secrets:

- Model adapter: `model_name`, keyword-only revision/snapshot/cache paths, matching
  the approved `MyEmbedder` constructor.
- Query cache: explicit root/profile identity. The current simulation passes the
  prepared Stage 5 cache path to the model/producer; it does not create a cache via
  this disabled factory.
- Read-only connection: explicit `target` and `readonly`; no DSN discovery.
- Probe: explicit endpoint; a future reviewed factory would call the existing
  `probe_database(target, connection_factory)` and enforce its read-only contract.
- Namespace store: dimensions/dataset/profile/context. A future reviewed closure
  would hold a separately supplied private DSN and construct `PgVectorStore`.

No `.env` scanning, default DSN, model download or implicit constructor is provided.
The current orchestration accepts only `OfflineWiring` mocks. Arbitrary injected
Python side effects remain trusted test code, not independently sandboxed code.

## Shared execution sequence and ownership

`simulate_lab_dev()` is an offline seam, not a working live execution entry point:

```text
prepare_dev -> exact lab approval verification -> ConsumptionLedger
 -> durable CONSUMED audit -> model artifact checks -> model-factory mock
 -> runtime canonical profile/cache check -> QueryProducer factory mock
 -> database probe mock -> SELECT-only role/identity check
 -> namespace store mock -> existing runner mock
 -> save_dev_artifacts mock -> verify_dev_artifacts mock -> terminal audit
```

The Stage 5.7A orchestration tail is shared, with stage notifications added for
audit. Retrieval/evaluation logic is not duplicated. The existing runner alone
calls `QueryProducer.prepare()` once for 15 queries, then owns exactly one
retrieval session and 45 simulated A/B/C searches. The orchestrator does not open
another session or run inference inside a transaction. C reuses B's namespace.
The 120-second retrieval deadline is unchanged.

Wrong endpoint/request identity, cluster, migration, catalog, privileged role or
`role_review_required=True` blocks progress. Model artifacts, canonical runtime
profile and Stage 5 cache path must match the prepared request. There is no repair,
fallback, retry or deadline increase.

## Failure audit

Audit files are separate from benchmark results, under a new directory
`data/local/stage5/lab_audit/<run_id>/`. Exclusive numbered JSON files request
private modes and are flushed/fsynced, including the directory on POSIX. Records
contain fixed fields: audit version/scope, run/request/approval/authority/decision
IDs, consumed flag, sequence, timestamp, stage, status, sanitized error code,
optional validated SQLSTATE and artifact-manifest digest. They contain no raw
exception message, traceback, DSN, token, vectors or fabricated quality metrics.

| Outcome | Audit policy |
|---|---|
| Successful consumption | `CONSUMED`, before any model/database factory |
| Runtime stages | `STAGE_STARTED` with fixed stage name |
| Runner returns COMPLETE and save/verify succeed | `COMPLETED_VERIFIED` |
| Runner returns INCOMPLETE | Preserve validated partial artifacts with summary null; `RUN_INCOMPLETE` |
| Runner raises before returning | `FAILED_NO_RESULT`; no invented benchmark result/metrics |
| Artifact save fails | `ARTIFACT_WRITE_FAILED`; keep unfinalized files, no overwrite |
| Artifact verification fails | `ARTIFACT_VERIFY_FAILED`; no verified-success claim |
| Initial audit creation/write fails | Stop before runtime, claim remains consumed |
| Later audit write fails | Stop without automatic write retry; audit may remain nonterminal |
| Crash between claim and first audit | Ledger proves consumption; no result/audit is assumed |

The wrapper raises sanitized `LabAuditError` after post-claim failures, even when
recording the failure itself fails. Audit failure must be reconciled manually with
the ledger and any artifact files; it never makes the approval reusable. A claim
whose commit outcome is uncertain does not reach runtime. There is no claim that
ledger and audit files are one atomic multi-file transaction.

## Remaining steps before any real execution

1. Review this offline code and synthetic tests.
2. Approve the actual manual verifier/authentication procedure, local ledger/ACL/
   clock custody, and output storage permissions.
3. Separately review live factory implementations, credential delivery and a
   SELECT-only role able to perform the existing cluster/schema checks.
4. Review the future guarded entry point; keep existing disabled gates unchanged
   until explicitly authorized. Bind its exact code hashes in a fresh request.
5. Obtain a real manual approval for one exact dev request, then separately approve
   the real runtime operation. No approval is issued at this checkpoint.

Offline tests cover synthetic human-decision authentication, identity/expiry gates,
replay/concurrency/process crash, claim ordering, runtime errors, session ownership,
partial results, artifact/audit failures, and disabled factories. They do not
verify the live database, model/tokenizer behavior, real dev quality, actual ACLs
or power-loss durability.
