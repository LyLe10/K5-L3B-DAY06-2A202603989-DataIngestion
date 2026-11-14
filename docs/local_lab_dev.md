# Local lab DEV benchmark (Checkpoint 2A)

Implementation and offline tests do not authorize a real run. Obtain Checkpoint
2B authorization before loading the model, entering a password, connecting to
PostgreSQL, encoding queries or creating real cache/output artifacts.

This DEV-only entrypoint leaves protected Stage 5 orchestration, approval,
CredentialChannel, ledger, audit and TEST gates unchanged. Its provenance is
`local_lab_dev`; it does not claim protected approval or replay protection.

From the repository root in WSL, after separate execution authorization:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
data/local/stage4/venv/bin/python -B starter/scripts/run_local_lab_dev.py \
  --role <operator-approved-login> \
  --output data/local/lab_benchmark/dev/<new-run-id> \
  --query-cache data/local/lab_benchmark/query_cache/<new-cache-id>
```

Use an interactive terminal. Password entry uses getpass with no echo; lack of a
terminal or secure input support fails closed. No password/DSN argument, .env
lookup or credential fallback exists. The connector supplies explicit host, port,
database, role and password. Never use the role argument for a secret.

The endpoint is fixed to 127.0.0.1:55433/day6_lab. Connections default to read-only;
writable connection requests fail. The existing retrieval transaction is repeatable
read/read-only, verifies structural identities, and additionally checks PostgreSQL
16.16, vector 0.8.7, the pinned cluster and login/current role before searches.
In that same transaction, both the stored catalog hash and actual catalog
fingerprint must equal the independent `dev_bootstrap.APPROVED_CATALOG` pin.
A missing/invalid pin, missing/extra rows, mismatch or introspection error blocks
all vector searches; database self-consistency alone is insufficient.
Required cluster introspection must be granted by the DBA; there is no privilege
fallback. This local path does not certify the complete SELECT-only privilege
policy of the protected runtime. An operator-approved least-privilege role remains
necessary. No database write APIs are invoked; inherited write paths cannot obtain
a writable connection.

prepare_dev validates the frozen DEV and TEST files, including source/evidence
consistency, but only returns the 15 DEV questions. TEST is never embedded,
retrieved or scored. Frozen-file validation is not holdout evaluation. Gold fields
are removed from producer/retrieval inputs by the existing runner.

The real adapter verifies the pinned local snapshot before loading; no downloads
are requested. Exact file inventory rejects extra entries and links. Only 15 DEV
queries are encoded; no corpus encoding or Stage 4 mutation occurs. Query vectors
are shared across A/B/C (45 top-3 searches). Configuration and metrics are unchanged.

Both output and cache roots must be new children of their dedicated local-lab
directories, outside Stage 5. Existing roots and linked paths are rejected. This
checkpoint intentionally does not reuse an earlier run's cache. Adapter cache
records bind profile (including revision), prefixed query hash and vector checksum,
and malformed records fail rather than being overwritten. Filesystem checks assume
a trusted local operator; concurrent mutation and hostile parent replacement remain
outside this boundary.

raw_run.json contains complete local traces and labels; exported/run.json uses the
existing redaction/export contract. Output is never overwritten. INCOMPLETE runs
retain available traces with summary=null and return exit 1. Other failures return
a generic error without backend exception text; failures before output creation
may leave no run file. No retries or cleanup overwrite partial evidence.

Directory/file modes request private raw storage, but effective Windows ACLs must
be reviewed. Third-party logging/native initialization and filesystem TOCTOU are
not prevented. A fresh controlled process and no simultaneous development are
recommended. The five GUIDE criteria remain unchanged: automatic DEV metrics do
not replace coherence, metadata, grounding and strategy-impact human review.
TEST execution requires a later separately reviewed plan after DEV configuration
selection; this entrypoint offers no TEST switch.
