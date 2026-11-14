# Stage 5.5 evaluation runner: offline implementation

This checkpoint implements and tests orchestration with synthetic fixtures only.
The review fixup additionally tests cancellation on disposable PostgreSQL. No real
model, main PostgreSQL connection, dev/test evaluation or quality result is produced.
Existing frozen benchmark and Stage 4 evidence remain unchanged.

## Components and execution boundary

- `evaluation.py`: pure exact matching, aggregation, separate manual adjudication
  and blank five-aspect review templates. The existing `evaluate_query(question,
  hits)` and `summarize(traces)` signatures are retained.
- `evaluation_runner.py`: validates configuration/approval, loads one frozen split,
  wraps the unchanged Stage 4 adapter, prepares query vectors/receipts before the
  transaction, executes all A/B/C reads in one session and evaluates afterward.
- `run_evaluation.py`: **plan-validation CLI only** in this checkpoint. It cannot
  instantiate a model or database store and has no execution/approval-bypass flag.
  Runtime orchestration is available as an explicit dependency-injected API, tested
  only with doubles. Real CLI/backend wiring and execution need later approval.
- `retrieval.py`: optional total deadline watchdog, remaining-budget statement/
  lock timeouts and explicit no-retry failure. `search()` is unchanged.

The intended order is:

```text
verify frozen bundle + corpus -> approval/split gate -> query receipts/vectors
  -> independent baseline -> one read-only retrieval session for selected split
  -> release locks/connection -> verify returned text/provenance -> exact metrics
  -> optional separate human adjudication -> publication review
```

`load_benchmark()` uses the existing validator for both frozen files, source and
approval provenance, then only returns the selected split. A hash of loaded records
prevents unnoticed mutation between loading and execution. IDs, gold, freeze files
and historical `retrieval_executed=false` declarations are never rewritten.

`run_evaluation()` receives explicit `store`, `producer`, independent `baseline`,
configuration, code identity and backend identity. It never discovers `.env`, creates
schema, ingests data or guesses backend identity. Backend version/migration/catalog
identity must be supplied from a verified session/connection at the later approved
runtime boundary; tests supply explicitly synthetic metadata. This checkpoint does
not attest to current main-database versions or vectors.

## Config and holdout

Version 1 config fields are exactly:

```json
{
  "config_version": 1,
  "top_k": 3,
  "strategies": ["A", "B", "C"],
  "deadline_seconds": 120,
  "metric_version": "exact-evidence-v1",
  "filter_empty_policy": "NOT_APPLICABLE",
  "selected_strategy": null
}
```

Dev and test are separate runs. Before test, `selected_strategy` must be A/B/C and
a separately supplied JSON approval artifact must bind `freeze_sha256`,
`evaluator_sha256`, `config_sha256`, the same selected strategy, `split=test`,
`approval_version=1`, `approved=true`, a supplied reviewer and rationale. No actual
approval artifact is created here. `approval_gate()` validates self-declared metadata
only; recording `approved=true`, reviewer and matching hashes authenticates nobody.
It permits plan inspection, not execution authorization.

`authorize_test_execution()` is a separate fail-closed step at the execution boundary.
No independent approval authority/trust root is currently configured, so it always
raises `TEST_EXECUTION_BLOCKED` for test, before producer or database access. There is
no boolean, injected callback, locally minted token or CLI flag to unlock it. A future
real independent verification mechanism requires separate design approval. The CLI
remains plan-only. Even metadata-valid self-authored approval cannot execute test.

All three strategies are still evaluated for comparison after selecting the dev
strategy. The selected strategy is not chosen again from test scores. Hashes cover
the evaluator, runner, retrieval/store, embedding adapter, validator and CLI files,
including uncommitted bytes. Code revision and dirty state are recorded separately.

## Query producer

`QueryProducer` validates the adapter's canonical profile and separate Stage 5 cache
root. Use `data/local/stage5/embedding_cache/` for future real queries; do not reuse
the protected Stage 4 cache. Tests use temporary cache roots and synthetic adapters.

Call `embed_query(raw_question)`. The adapter adds exactly `query: `, checks 512
tokens including special tokens before encoding, and returns float32 normalized
vectors. The wrapper validates 384 dimensions/finite/unit norm and binds ordered
question IDs, prefixed-input SHA-256, producer profile, token count, vector checksum,
cache/encode counts and elapsed time. Raw vectors are used in memory only, not in
run artifacts. Numeric validation cannot independently prove semantic input order
or producer authenticity; the unchanged adapter is the trusted producer boundary.

Only `{id, question, filter}` is passed to the producer; no gold or expected answer
is supplied to embedding/retrieval. The same vector object is used for A/B/C and
only C receives the supplied section filter.

## Deadline and failures

The 120-second budget starts before session connection/preflight, after embeddings
and baseline preparation. One watchdog owns only that session's connection and
uses driver cancellation on expiry. Statement/lock limits are capped by remaining
time; checks before/after calls prevent silent continuation. The timer is disarmed
on cleanup. No reconnect, fallback or retry is allowed.

Cancellation and cleanup are not hard real-time guarantees: driver connect timeout,
network cancellation and OS scheduling have finite overhead. Driver cancellation
is best effort, followed by explicit deadline failure and connection cleanup.
Cancellation and disarm serialize under a mutex. Disarm detaches the connection and
waits for an in-flight callback to finish BEFORE driver COMMIT/ROLLBACK or connection
close; a stale callback is inert. This avoids sending a late cancel during cleanup.

The review fixup verified three cases on PostgreSQL 16.16 / pgvector 0.8.7 in a guarded
tmpfs cluster: actual CancelRequest of a query, cancellation during preflight, and
normal exit/stale-callback cleanup. Statement timeout was disabled only inside those
synthetic cancellation probes to distinguish watchdog cancellation. See
[cancellation evidence](../results/evaluation_fixup_cancellation.json). These results
do not establish a hard deadline or cover arbitrary network partitions/cancellation
transport failure. No main PostgreSQL connection was used.

Any embedding/retrieval/evaluation error produces `INCOMPLETE`, partial traces,
safe error type/SQLSTATE/stage and `summary=null`. Valid empty results are misses,
not backend errors. A complete run requires all question/strategy records. Exact
metrics are only aggregated after successful session exit and source validation.

## Exact evidence contract

For any one approved primary gold or alternative, one chunk must have:

1. Exact document/source ID and physical page.
2. Matching source and normalized-page checksums.
3. Half-open chunk offsets covering the entire gold span.
4. Exact quote at the relative offset; quote length equals gold span length.
5. Consistent text length/checksum, plus independent verification that the full
   chunk equals the corresponding normalized source substring.

Page-only, keyword/fuzzy match and evidence split across chunks are not hits.
Unmatched equivalent evidence is not automatically accepted. Each hit records
per-gold checks and match diagnostics.

- **Exact Evidence Hit@1**: queries whose first chunk matches / all queries.
- **Exact Evidence Hit@3**: queries with a matching chunk in top 3 / all queries.
- **MRR@3**: mean reciprocal first exact hit rank; no hit contributes zero.

These are evidence retrieval metrics, not answer accuracy, coherence or grounding.
Aggregation separates split and strategy and retains numerator/denominator.

For C filter diagnostics, a nonempty result with any wrong section is `VIOLATION`.
Empty results are `NOT_APPLICABLE`, never compliant or violating. Report their
count/rate separately, including filtered empty rate. Compliance uses only nonempty
filtered queries and reports that denominator; if none exist, compliance is null.
A/B have no applied filter and no filter-compliance claim.

## Adjudication and manual templates

`adjudicate()` requires reviewer, rationale, exact trace SHA-256, hit rank and explicit
boolean relevance. Trace identity excludes its own checksum field. Supplied decisions
can produce separate adjudicated metrics through `adjudicated_relevant`; `exact_match`
and exact metric fields remain unchanged even in copied diagnostics. Exact traces,
exact metrics and frozen gold are not mutated. No reviewer/decision is generated automatically. Duplicate,
unbound or checksum-mismatched decisions fail.

Blank review templates cover retrieval relevance, coherence at ten source anchors,
metadata, grounding and strategy impact. Test reviews use the same five test queries;
coherence anchors and selection rules require approval before scoring. C uses B
chunks. Labels, reviewers and conclusions remain null until actually supplied.

## Artifacts and publication

The run object contains manifest, producer receipts, ordered raw hits, exact-match
diagnostics, optional summary and blank manual templates. Manifest binds frozen file
hashes, source/corpus/manifest, dataset/profile/model config, A/B snapshot and descriptor
identities, code/config hashes, dependencies, timings and backend metadata.

Integrity labels remain `STRUCTURAL_INTEGRITY_VERIFIED` and
`VECTOR_INTEGRITY_NOT_REVERIFIED`. This is not a new audit of the 510 stored vectors.

`run_evaluation(output_directory=...)` persists the run, including partial traces on
failure, when an explicit new directory is supplied. Without one it returns the
in-memory run for the caller to inspect. `write_artifacts()` writes a new directory
only; no automatic overwrite.
Outputs should remain under `data/local/stage5/runs/` until reviewed. It drops vector
payloads, whitelists hit fields, redacts credentials/key material/personal paths and
marks publication redaction. Vector SHA-256 receipts remain available. Exceptions
never export raw messages that could include DSNs or credentials.

Raw and exported identities have separate canonical contracts:

- `raw_trace_sha256` (legacy alias `trace_sha256`): SHA-256 of UTF-8 canonical JSON
  `{hash_contract: "raw-trace-v1", payload: <raw trace excluding both own aliases>}`.
- `exported_trace_sha256`: SHA-256 of the entire redacted exported trace excluding
  only `exported_trace_sha256`. This includes `hash_contract="exported-trace-v1"`
  and its link `raw_trace_sha256`. Export never labels the raw hash as a checksum
  of redacted contents.

Canonical JSON uses sorted keys, compact separators, Unicode text (no ASCII escape
requirement), no NaN and UTF-8 without BOM/newline. No text/Unicode normalization is
introduced. `export_trace()` validates declared raw identity before redaction.
`verify_exported_trace()` verifies exported integrity without needing secrets; when
the original raw trace is provided it also verifies the deterministic redaction/link.
Without raw, the link cannot prove the unseen raw content. Hashes provide integrity,
not authenticity or independent approval.

Adjudication binds original raw traces, not public exports. Redaction may change
visible text, so raw source checks/diagnostics are not proof of altered public text.
Automatic redaction is not a substitute for manual secret, license and publication review.

Offline tests use synthetic benchmark bundles in temporary directories and mocks;
their fixture metrics are not performance measurements for the real corpus.
