# Stage 5.6 dev bootstrap: offline preparation only

This module prepares a dev evaluation plan. It does not load a model, connect a
database, encode queries or run any actual benchmark. Tests use synthetic fixtures
and mocked connections only. Existing frozen gold and Stage 4 are unchanged.

## API and gates

`prepare_dev(split='dev', config=None, root=ROOT, output=...)` returns a
`DevPreparation` containing a displayable plan plus private in-memory benchmark
bundle, verified `SnapshotContext`, canonical `EmbeddingProfile` and independent
`RetrievalBaseline`. Only dev is accepted. Configuration must match approved A/B/C,
Top-K=3, 120-second deadline and 15 dev questions. Plan checks do not authorize a run.

The implementation uses the existing loader to verify original PDF, normalized
text, physical page mapping and source/manifest hashes, then checks 40 distinct
physical pages. It validates the frozen bundle without running retrieval/evaluation.
The frozen SHA, source checksums, canonical profile ID and A/B snapshot identities
are pinned to approved Stage 4/5.2 values. Baseline counts must be A=246/B=264.
The baseline is constructed from verified context, never database rows or vectors.

`execute_dev()` always raises `RUNTIME_EXECUTION_DISABLED`, even if supplied flags
claim approval. Test remains blocked by the existing independent-approval gate;
this bootstrap rejects test before local loading. No runtime bypass flag is added.

CLI (plan-only, no automatic output directory creation):

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B \
  starter/scripts/prepare_dev_evaluation.py --split dev \
  --output data/local/stage5/runs/planned-dev
```

This command is documented for later approved local preflight; it was not run on
the real corpus in this implementation checkpoint. CLI tests exercise help/test
rejection only; preflight tests use temporary synthetic bundles.

## Model and runner integration plan

The plan names `MyEmbedder`, pinned model/revision, local snapshot, CPU/float32/eval,
normalization and the canonical dependency/profile configuration. It does not
construct the adapter. The future runtime boundary must use the approved Stage 4
Python 3.12.3 environment and verify artifacts/runtime profile before inference.
Installed packages, model checksums and runtime compatibility are not newly attested
by a plan alone.

Future approved construction order:

1. Complete local preflight and retain its code/config/source/plan hashes.
2. Load pinned local `MyEmbedder` using `data/local/stage5/embedding_cache/`.
3. Compare runtime canonical profile to `preparation.profile`, then create the
   unchanged `QueryProducer`. The adapter adds `query: ` itself.
4. Verify main database identity read-only and approve role privileges.
5. Create namespace-bound `PgVectorStore`; run with the prepared bundle/baseline.
   The run's one read-only session performs structural preflight once.
6. Only after separate approval: 15 dev embeddings and 45 A/B/C calls at Top-K=3,
   with 120 seconds for retrieval, no retry. No corpus vectors are re-encoded.

The current CLI cannot perform those runtime steps. Model inference stays outside
the retrieval transaction. No existing ingest or migration runner is invoked.

## Read-only database probe contract

`probe_database(target, connection_factory)` is an explicit, separate API. It has
no default driver/factory, DSN discovery or `.env` access, and is never called by
local preflight or CLI. Tests supply mocks. A live factory requires separate approval.

Before factory invocation target must exactly equal host `127.0.0.1`, integer port
`55433`, database `day6_lab`. Actual client connection info is checked again. The
factory is requested to use default read-only mode; the probe also sets its own
transaction read-only and verifies `transaction_read_only=on` on the server.

Only transaction control/SELECT statements execute. The probe verifies PostgreSQL
16.16, pgvector 0.8.7, cluster `7707847059457269799`, Migration 0001's approved
checksum/catalog fingerprint and schema history. It reports identity only; the
retrieval session still must verify profile, complete snapshots, counts and descriptors.

Prefer a pre-provisioned SELECT-only role. Table read/write grants and elevated
role/database/schema CREATE capabilities are checked. Elevated capabilities produce
`role_review_required=true`; this is not permission to execute with that role.
Identity/catalog queries also need suitable read/function permissions, including
cluster-identity inspection. If denied, fail explicitly; never grant permissions,
elevate role, retry with an owner or create a role automatically. No DDL is part of
this bootstrap. Function-execution/inherited-role privileges need review before
claiming a fully least-privilege production role.

## Raw/exported artifacts

`save_dev_artifacts(result, directory)` is an explicit post-run storage API; it is
not called by preflight. Output must be a new child of `data/local/stage5/runs/`.
Traversal, symlinks/junctions, paths escaping the workspace, Stage 4/cache paths and
existing output directories are rejected. The Stage 5 cache path is checked for
symlink escape during local planning as well. No protected local file is modified.

```text
data/local/stage5/runs/<new-run>/
  private/raw_run.json
  exported/run.json
  artifact_manifest.json
```

Raw keeps original exact trace content/identity in a private local file. Exports use
the existing redaction/export hash contract. Vectors, DSNs, credential material and
cache payload are refused before writing, even for private storage. Export redaction
may remove personal paths that private traces retain. No file is published or committed.

`verify_dev_artifacts()` checks file SHA-256 values and every raw/exported trace
link. Hashes use the existing `raw-trace-v1` and `exported-trace-v1` canonical JSON
contracts; these prove integrity/linkage, not approval or authenticity.

Private directories/files request owner-only POSIX modes (0700/0600). Effective
Windows/WSL filesystem ACLs must be reviewed before storing real raw traces; chmod
alone is not an assurance about NTFS access. Keep all artifacts local pending review.

The checksum manifest is written last. A disk/write error propagates, does not
retry, and leaves an unfinalized directory without a manifest; the verifier refuses
that bundle. Do not treat it as a valid run or overwrite it. Incomplete runs may be
stored only with `summary=null`. No quality results are synthesized for them.

Artifact storage and verification use closed schemas for run manifests, traces,
receipts, hits and nested metadata, in addition to secret-content checks. Unknown
fields and nested payload objects are rejected before creating an output directory.
Dynamic checksum/version maps permit scalar values only; vectors and cache payloads
are not part of this contract.

A `COMPLETE` bundle requires 15 unique dev question IDs, all 45 successful A/B/C
traces, 15 matching query receipts and consistent profile/snapshot/provenance
identities. Its summary must equal the existing evaluator's trace aggregation;
exact diagnostic metrics are checked for internal consistency. These checks do not
authenticate evidence or independently establish semantic correctness. Storage-only
test fixtures use `INCOMPLETE`, not fabricated complete benchmark results.

The requested workspace root is passed explicitly to evaluator identity generation.
Evaluator and bootstrap file hashes are checked against that same root; a mixed
workspace identity or a source path escaping the root is rejected.

## Approval still required

- Review this offline bootstrap and its tests.
- Separately approve real model load, 15 dev query embeddings/cache writes and
  main PostgreSQL read-only identity/retrieval access, including role selection.
- Review/implement the future execution entry point before one actual dev run.
- Test holdout remains BLOCKED; no approval authority is introduced here.

The 120-second budget is unchanged and is not a hard real-time guarantee. No new
measurement on the 510 real chunks or 45 searches was made by this checkpoint.
