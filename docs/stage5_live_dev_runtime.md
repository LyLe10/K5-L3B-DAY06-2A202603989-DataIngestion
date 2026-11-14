# Guarded live DEV runtime

This module is wiring, not authorization. Implementation tests use only temporary
synthetic corpus/questions, fake model/database boundaries and synthetic authorities.
No live benchmark, model initialization or primary database connection has been run.
Existing `execute_dev`, disabled lab factories, CLIs and TEST gates are unchanged.

## Operator preparation and approval

1. Select and independently review a real `ManualApprovalVerifier`, reviewer
   authentication, clock/ledger custody and private output permissions. There is
   no default verifier, issuer, environment approval switch or CLI bypass.
2. Supply the actual SELECT-only login role and a reviewed
   `CredentialChannel(credential_channel_id, reader)` using the existing contract.
   No credential discovery or default role is provided. The channel label binds
   the approval metadata; arbitrary callable code still requires operator review.
3. Run metadata-only `prepare_dev(root=..., output=...)`, then
   `live_dev_request(root=..., prepared=..., run_id=..., output=..., executor_id=...,
   selected_role=..., credential_channel_id=...)`. Review the exact canonical
   request, code hash map, new run and output destinations.
4. Obtain a separate authenticated approval for scope `LAB_LIVE_DEV_EVALUATION`,
   schema version 3, exact request/hash, reviewer/executor and validity interval.
   Model-load-only, probe-only and old mock DEV approvals cannot authorize it.
5. Separately approve one real execution through `execute_live_dev` with that
   exact request/approval/authority and credential channel. No operation in this
   document issues or implies that approval.

The request reuses existing lab invariants and binds the 15 ordered frozen dev IDs,
source/freeze identities, canonical profile, pinned local model/revision/artifacts,
Stage 5 cache, A/B snapshots/descriptors, database identities and current dirty-code
hashes. Additional binding covers the live executor and supporting source files,
selected role/channel, read-only connection settings and retrieval timeouts.
The approved root must be the actual executing workspace. Loaded module `__file__`
and `__spec__.origin` must agree and resolve to the expected workspace source paths.
The request binds their relative origins, source hashes, a workspace-path digest,
interpreter/environment-path digests, Python version, implementation and cache tag.
Checks repeat after independent approval verification before consumption, at runtime
stage boundaries and before entering/yielding the retrieval session. Paths remain
private; request digests do not provide an OS security boundary.
Configuration remains A/B/C, K=3, 120-second retrieval deadline. No stale code hash
or prior checkpoint request should be reused after code changes.

## Execution and ownership

`execute_live_dev` accepts only dev, checks credential binding, independently runs
`prepare_dev` again and compares the entire canonical request. Existing pure lab
invariants and explicit probe invariants run before independent manual verification.
The existing ledger commits consumption before any model or credential access.
The initial sanitized audit must be read back and verified before runtime begins.

After artifact verification, the existing MyEmbedder initializes from the approved
local snapshot on CPU float32/eval with an explicit Stage 5 cache. Profile, limits,
dimensions and initial zero-encoding counters are checked. QueryProducer delegates
the query prefix to the adapter; no duplicate prefix is added.
Snapshot/path/hash/inventory validation is shared with `pinned_model_factory` through
an authorization-independent helper. Extra files/configuration, unknown directories,
symlinks and junctions are rejected before initialization. The helper grants no
model-only or DEV authorization; both entry points retain their own approval gates.

The existing metadata probe performs identity, effective-role and structural checks
through the approved protected connector, without retrieval. Privileged roles and
warnings fail closed. The probe connection is distinct from the retrieval connection;
it does not substitute for the retrieval session's own structural preflight.
On the actual retrieval connection, inside the existing read-only transaction and
before yielding any searches, the DEV wrapper rechecks database, cluster, PostgreSQL
and pgvector versions, migration checksum/catalog fingerprint, session/current role,
effective privilege policy, required SELECT grants, read-only state and isolation.
It rejects TEMP privileges consistently with the earlier probe's warning policy.
A mismatch propagates through the existing transaction context, causing cleanup
and rollback without retry or a new connection. This adds metadata SELECTs only;
vector search SQL, metrics, namespace locks and snapshot semantics are unchanged.

A private PgVectorStore subclass preserves constructor/API and retrieval SQL,
overriding only its connection hook. It rejects writable connections and supplies
explicit endpoint/login/password, connect timeout 5s, autocommit and default read-only
mode. Actual connection endpoint/login mismatches close the connection immediately.
It never calls register, sync, upsert or migration methods. No DSN is exported.

The unchanged runner calls QueryProducer.prepare once for 15 questions, before its
single retrieval session. That session owns the repeatable-read/read-only transaction,
locks, structural preflight, watchdog and 45 A/B/C searches using shared query vectors.
C uses B rows. Retrieval defaults remain lock timeout 5s, statement timeout 30s,
idle timeout 60s, deadline 120s. Model load and query encoding are outside that
retrieval deadline. Scoring happens after the transaction. No TEST execution is enabled.

## Artifacts, failures and limitations

The outer approved run ID replaces the runner-generated run ID before artifact
hashing. Existing save/verify functions preserve private raw and redacted export
files in the new Stage 5 output directory, enforce COMPLETE coverage and reject
secret/vector payloads. The terminal read-back-verified audit binds the verified
artifact manifest hash. No automatic publication occurs.

INCOMPLETE preserves validated partial traces and summary=null. A raised runner
error does not fabricate a result. Model, probe, output-save or verification failure
records a sanitized failure when possible and burns consumption. Initial or terminal
audit failure cannot report verified success. No retry, claim reset, overwrite,
fallback role, repair or deadline increase is performed. Model references are released;
there is no invented close API. Connection/session cleanup belongs to the existing
probe and runner, except immediate rejection of a wrong connector identity.

This is a trusted local lab boundary, not an OS sandbox or anti-rollback service.
Operator custody must protect ledger, clock, artifacts and code against mutation.
Start real execution in a fresh controlled Python process, with source files and
the import environment fixed before approval preparation and unchanged until exit.
Module origins and disk hashes cannot prove that already-loaded Python bytecode is
immutable or matches disk, cannot authenticate monkeypatched callables, and cannot
eliminate filesystem TOCTOU races. Do not treat a successful metadata check as a
fresh-process attestation. Tests override process-origin metadata only for explicitly
temporary synthetic workspaces; no live argument or flag permits that override.
Dependency logging/native initialization and credential-reader side effects require
live environment review. Probe and retrieval use separate connections; structural
identity is checked again in the retrieval transaction, but vectors are not rehashed
or re-encoded. Existing isolated evidence does not certify current primary DB state.
Effective-role checks are transaction-time observations, not a freeze of future
administrative GRANT/REVOKE changes; database administration must also remain stable
during the controlled run.

Before live approval, review synthetic regression results and the new exact code
identities, supply real authority/credential inputs, verify permissions (including
cluster/catalog introspection) and approve one execution. TEST remains blocked.
