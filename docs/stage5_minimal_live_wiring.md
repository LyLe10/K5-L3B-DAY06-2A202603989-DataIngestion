# Minimal live wiring: separate approvals required

Implementation is not authorization to execute. No live run was performed.
`execute_dev` and test holdout remain blocked; CLI remains plan-only.

## Model-only

Generate `model_load_request(root=..., run_id=..., executor_id=..., live=True)`.
The fresh canonical request has scope `LAB_MODEL_LOAD_ONLY_LIVE`, exact current
code hashes (including factory), ten artifact hashes, canonical profile, CPU
float32/eval, snapshot/cache and a new private audit path. Historical A6 code
hashes are no longer approval identities after this patch: regenerate all hashes.

Supply the exact request, independently authenticated approval and an explicitly
selected `ManualApprovalVerifier` to `execute_model_load_only`. It regenerates
and compares the request, verifies the decision, constructs the metadata-only
factory binding, consumes the durable claim and verifies the consumption audit
before invoking the real constructor bridge. No caller-supplied constructor is
accepted on this path. It returns verified metadata only, never the model handle.
The pinned factory's direct public call remains disabled; only the approved outer
orchestrator owns its private live binding. Python private methods are conventions,
not a sandbox against arbitrary code running with the same permissions.

## Database-only

Generate `live_probe.probe_request(root=..., prepared=prepare_dev(root=...),
run_id=..., executor_id=..., selected_role=..., credential_channel_id=...)`.
Scope is `LAB_DATABASE_METADATA_PROBE_LIVE`. No model loading or evaluation is
part of preparation. The request binds exact target/schema/profile/descriptors,
code hashes, role, protected credential channel identifier, new audit destination
and timeouts. `database_probe.execute_live_probe` delegates to this scoped wiring.
Execution independently calls `prepare_dev` again and compares the entire request.

Operator must supply the actual SELECT-only login role and an immutable
`CredentialChannel(credential_channel_id, reader)` as `credential_provider`.
Its label must equal the channel ID in the exact approved request; bare callables
and mismatched bindings are rejected before consumption. The protected zero-argument
reader returns the password only when called after consumption/audit.
This is a trusted callable, not a sandbox or credential-discovery
mechanism. Never pass a DSN, scan .env, use a default role, fall back to another
account, or put secrets in approval artifacts. The provider implementation and
verifier integration require operator review; the channel ID does not authenticate
an arbitrary callable. No role, credential source or real verifier is provided here.

Before approval consumption, an explicit invariant gate additionally checks fixed
endpoint/version/cluster/schema identity, canonical approved profile, compatible
complete A/B snapshots and counts, independent descriptor hashes, role/channel,
read-only settings, isolation, autocommit and all fixed timeouts. Exact canonical
regeneration and independent manual approval remain required as separate checks.

The connector lazy-imports psycopg only after consumption, passes explicit
host/port/database/user/password, default read-only mode, 5s connection timeout
and autocommit for the single explicitly owned transaction. Existing shared probe
performs REPEATABLE READ READ ONLY, 10s statement timeout, 5s lock timeout and 15s
idle timeout with identity, permission and structural checks. It rejects privileged
roles and fails closed on TEMP warnings rather than silently accepting them.
It performs no vector retrieval or migrations. The verified success audit binds
the returned sanitized metadata by SHA-256. Vectors are not reverified.

## Shared boundaries and failures

Use the existing independent manual verifier contract and durable ConsumptionLedger,
not flags, environment approval or a new issuer. Reviewer must differ from executor;
request hash, scope and expiry must match. Model and probe approvals are not
interchangeable. Local ledger custody still has no anti-restoration guarantee.

Consumption precedes credential delivery, connection and model initialization.
Failure never resets a claim or automatically retries. Audit writes are read back
and canonical/hash checked; audit failure cannot report success. Exceptions are
classified and sanitized, not logged verbatim. Exclusive audit paths prevent
overwriting earlier output. A crash after consumption requires human review and a
new independently approved request; it does not authorize replay.

First live use still requires explicit human approval of the regenerated exact
request/code map, real verifier and reviewer authentication, ledger/artifact custody,
runtime environment/logging controls, and (for database) the named role and protected
credential delivery. This checkpoint supplies none of these operational inputs and
does not execute either entry point.
