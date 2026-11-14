# Stage 5.7B-A4: disabled SELECT-only database probe

> **Historical status - checkpoint A4.** The disabled-entry and Mock-only statements below describe the earlier offline checkpoint, not all current guarded entry points. See [current model/probe wiring](stage5_minimal_live_wiring.md) and [current guarded DEV runtime](stage5_live_dev_runtime.md). Regenerate current canonical requests and code identities from the actual executing workspace; do not reuse historical identities as current approval inputs. Guarded runtime availability does not constitute live execution approval. Separate explicit approval is required; TEST remains blocked.

Offline design and synthetic tests only. `execute_live_probe()` always raises;
`OneShotOfflineProbe.inspect()` requires a Mock connection factory. No driver,
DSN discovery, secret reading, approval issuance, Docker operation or live CLI
has been added. `execute_dev()` remains disabled and test holdout remains blocked.

## Interface and identity contract

`OneShotOfflineProbe().inspect(prepared, *, selected_role, connection_factory)`
accepts an existing verified dev preparation and an explicit role name. One
attempt per instance is allowed, even on failure, protected by an in-process lock.
This is not a durable authorization claim or protection against creating another
object/process. All current execution is mock-only. A future real one-shot probe
must receive its own manual approval and consumption gate before enabling a connector.

Approved constants remain unchanged: endpoint 127.0.0.1:55433/day6_lab; PostgreSQL
16.16; vector 0.8.7; cluster 7707847059457269799; Migration 0001 and catalog hashes
from Stage 4; approved embedding profile, A/B snapshots and descriptors from verified
corpus context. Expected namespace counts are A=246/B=264 with 40 pages each.
Global counts must be one profile, two snapshots and 510 chunks. Matching global
counts together with the existing namespace guard rule out extra namespace rows.
C has no separate rows. No model or query vector is needed.

The approved `dev_bootstrap.probe_database()` now accepts an optional trusted
`inspection(connection, *, privileged)` callback. Existing two-argument callers
retain their contract. An inspection uses REPEATABLE READ and READ ONLY, runs after
the existing identity/schema/role checks and before transaction exit. This avoids
a second connection and copied migration or cluster checks.

The injected factory receives fixed target, explicit selected role, readonly=True,
connect_timeout=5, autocommit=True and default_transaction_read_only=on options.
It must never discover a DSN or change authentication identity automatically.
The existing probe sets statement_timeout=10000ms; the inspection verifies the
server reports 10s, READ ONLY and REPEATABLE READ. The metadata preflight adds a
5s lock timeout and 15s idle transaction timeout for transaction advisory locks.
No whole-operation hard deadline is claimed. Connection/transaction cleanup belongs
to the existing probe's context managers; no retry or reconnect occurs.

## Permission policy

Only fixed SELECT/transaction-setting statements are used. Role names are compared
against session_user/current_user, not interpolated into SQL. Schema predicates
use parameters. Required access:

- CONNECT to day6_lab; USAGE on day6_ingestion and public.
- SELECT on exactly the four required schema tables. An unexpected table or missing
  effective read grant blocks inspection rather than guessing permission coverage.
- Effective EXECUTE on pg_catalog.pg_control_system() and
  day6_ingestion.catalog_fingerprint(). Actual call failures still block.
- Metadata visibility for the existing catalog fingerprint and permission queries.

The selected role must equal both login/session and current role. Checks reject:
superuser, CREATEDB, CREATEROLE, replication or BYPASSRLS; direct/indirect membership
in another role; CREATE on non-system schemas/database; write grants on non-system
tables/views; and object ownership found in pg_namespace/pg_class/pg_database/pg_proc.
Membership is rejected conservatively even if an individual membership's INHERIT
or SET option would restrict it. The implementation does not switch roles or use
GRANT, REVOKE, ALTER ROLE, pg_read_all_data or pg_monitor as a fallback.

TEMP may be inherited from PUBLIC. It is reported as
`TEMP_PRIVILEGE_PRESENT_QUERY_LIST_ONLY`, not silently removed or treated as proof
of a globally SELECT-only account. Function/sequence rights and capabilities outside
the inspected policy are not exhaustively certified. The existing probe's role
label describes the inspected grants, not universal read-only enforcement. The
future approved operation must remain restricted to this reviewed query list.
Role provisioning or any permission change needs separate explicit approval.

## Metadata preflight reuse

The probe constructs PgVectorStore without connecting, then calls the existing
`retrieval.preflight(store, connection, baseline)` inside the same transaction.
That guard reuses schema verification, shared advisory locks A/B in key order,
canonical profile comparison, complete/compatible ledgers, namespace counts,
selected pages, snapshot/corpus/manifest provenance and descriptor hashes.
No extra retrieval_session is opened. Some schema checks repeat through existing
helpers; their implementations are reused rather than duplicated.

Descriptor checks exclude text and embedding columns. Raw descriptors stay inside
the guard; the report exports only identities, counts, descriptor hashes and
integrity labels. There is no cosine SQL, vector payload export, query encoding,
retrieval benchmark, schema repair, migration, registration or sync operation.
`STRUCTURAL_INTEGRITY_VERIFIED` does not imply vectors were reverified.

## Failure contract and offline evidence

Any mismatch, insufficient privilege, connection/timeout/backend failure or unknown
response produces sanitized `ProbeBlocked` (BLOCKED), with no backend message,
DSN or credential text. SQLSTATE 42501 is classified as insufficient privileges;
other unexpected errors also fail closed. The one-shot object remains spent.
No partial identity report is returned as PASS. No automatic GRANT, role switch,
fallback, credential lookup or retry is performed.

Synthetic tests exercise fixed factory parameters, existing identity/schema code,
same-transaction callback, role policy, counts and guard rejection propagation.
The structural guard itself is additionally covered by its existing offline tests.
New permission SQL has not been executed on PostgreSQL in this checkpoint; mock
tests do not prove its SQL syntax, privilege behavior or fingerprint visibility
on a live SELECT-only role. No existing integration evidence is a new probe result.

## Exact future manual approval

Before one real probe, review a guarded connector/entry point and bind its code
hashes, purpose DB_IDENTITY_PERMISSION_PROBE_ONLY, exact target/cluster/schema/
profile/snapshot identities, explicit selected database role, one probe run ID and
new private report destination. Specify validity window and one-shot consumption
procedure; do not reuse an approval for the 45-search dev evaluation.

The reviewer must name the credential-delivery mechanism: for example a separately
reviewed protected operator channel supplied directly to the factory. Do not paste
credentials into the request/report, scan .env or choose another role implicitly.
Approve one READ ONLY identity/permission/metadata transaction with 5s connection
and 10s statement timeout, plus the stated metadata-lock limits. A short-lived
server authentication exchange is part of that connection, not permission to run
retrieval. No model/tokenizer, vectors, encoding, benchmark, writes or Docker changes
are included. Missing rights or a TEMP warning require explicit review; this
checkpoint neither grants rights nor approves live execution.
