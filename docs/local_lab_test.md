# Minimal local Day06 DEV -> selection -> TEST

Offline implementation only. No real DEV/TEST run or selection is supplied by
this change. The operator must authorize runtime separately and enter the existing
local PostgreSQL password in an interactive WSL terminal. Do not put the password
in command arguments, an artifact, or chat. These commands use role `day6` at
`127.0.0.1:55433/day6_lab`, the Stage 4 endpoint. They do not create a dedicated role.

## 1. DEV (operator runtime, not executed during implementation)

From the repository root in WSL, use the existing Stage 4 Python environment:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
data/local/stage4/venv/bin/python -B starter/scripts/run_local_lab_dev.py \
  --role day6 \
  --output data/local/lab_benchmark/dev/dev-001 \
  --query-cache data/local/lab_benchmark/query_cache/dev-001
```

DEV remains unchanged. It encodes 15 queries and performs 45 top-3 searches. C
uses B's vectors and applies only the supplied section filter. Each query vector
is shared across A/B/C. Existing outputs/caches are rejected, not overwritten.

## 2. Record selection (offline, only after complete DEV)

```bash
data/local/stage4/venv/bin/python -B starter/scripts/run_local_lab_test.py freeze \
  --dev-run data/local/lab_benchmark/dev/dev-001/raw_run.json \
  --selection results/selection_freeze.json
```

This command does not load a model, request a password, or connect to PostgreSQL.
It validates frozen benchmark/corpus identities, DEV COMPLETE, 15 receipts, all
45 ordered successful traces, trace checksums, returned text against the source,
per-query evidence metrics and aggregate metrics. It requires the original raw
DEV artifact, not its publication-redacted copy. Evaluation source files and the
DEV entrypoint must still match the run; uncommitted file changes are covered by
the recorded source hashes. A changed Git dirty flag alone is not a methodology
change and is not used to reject a run.

The predeclared policy in `results/benchmark_config.json` chooses highest DEV
Evidence Hit@3, then highest DEV Hit@1, then fewer stored chunks, then A -> B -> C.
C's stored chunk count is 264 because it shares B; it is not treated as zero.
No strategy is chosen before actual DEV results exist. The selection record binds
the DEV file, benchmark/config, profile/snapshots and this TEST implementation.
It records selection time and refuses overwrite. This is an experiment record,
not an authorization token, independent signature, or replay ledger. Hashes check
consistency; they do not prove authenticity against a workspace owner.
Timestamps are recorded with a timezone for reporting. DEV-before-TEST is enforced
by validating COMPLETE DEV artifacts and their selection hashes; wall-clock order
is not a gate, because WSL/host clock corrections can move time backwards.

## 3. TEST (operator runtime, after selection)

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
data/local/stage4/venv/bin/python -B starter/scripts/run_local_lab_test.py run \
  --selection results/selection_freeze.json \
  --role day6 \
  --output data/local/lab_benchmark/test/test-001 \
  --query-cache data/local/lab_benchmark/query_cache/test-001
```

Before constructing a model or requesting credentials, TEST checks the complete
DEV run again, selection record, current frozen benchmark, exact five TEST IDs
and split, and new output/cache paths. Only `{id, question, filter}` reaches the
query producer. Gold stays in source validation/evaluation. TEST encodes five
queries, makes 15 top-3 A/B/C searches in one read-only retrieval session, and
keeps the DEV-selected strategy in its configuration. It does not choose again
from TEST. Do not modify benchmark/gold or retrieval in response to TEST scores.

The local script reuses the existing embedder, QueryProducer, read-only connector,
store/session, hit validation, metrics, manual templates and exporter. Its small
local execution loop does not invoke or modify protected Stage 5 authorization.
The protected `authorize_test_execution()` continues rejecting TEST unchanged.
No corpus encoding, database mutation, schema creation or model download is called.

## Artifacts and manual work

Each runtime writes `raw_run.json` and `exported/run.json` under its new local run
directory. Exit 0 requires COMPLETE; exit 1 means failure. Run-time
embedding/retrieval/scoring failures retain partial artifacts, a sanitized error
and `summary=null`; no retry or fallback occurs. Preflight/model-construction
failures may occur before an artifact exists and print a generic error only.
Keep an operator error note in that case without recording credentials.

Local run directories are ignored by Git. After review, provide permitted exports
in `results/` for submission, retaining the PostgreSQL notice with excerpts.
Manual labels remain blank until the author reviews the chunks/evidence.

`results/coherence_anchors.csv` fixes the first ten selected physical pages and
their midpoint offsets (zero-based Python Unicode character indices). For each
strategy choose a containing chunk with the smallest start offset, then chunk ID;
C reuses B's labels for the same chunk. Do not change anchors after viewing scores.
This sample covers Data Definition only; disclose the limited coverage.

Complete coherence (10 anchors x A/B/C), metadata (five TEST x top-3 x A/B/C),
grounding (five TEST x A/B/C), and A-B/B-C analysis. Existing filter diagnostics
exclude empty results from their compliance denominator; additionally report all
filter questions and empty-result counts in the manual report. Do not silently
treat empty retrieval as successful compliance.

Then fill experiment_log.csv, STUDENT.md, README and the individual report with
DEV/TEST n/N metrics, timing/cost, examples and limitations. No real selection,
quality metrics, manual labels, commit or push is produced by offline tests.

## Offline validation

```bash
PYTHONDONTWRITEBYTECODE=1 data/local/stage4/venv/bin/python -B -m pytest -q \
  -p no:cacheprovider starter/tests/test_local_lab_test.py \
  starter/tests/test_local_lab_dev.py starter/tests/test_evaluation.py \
  starter/tests/test_evaluation_runner.py
```

These tests use temporary synthetic DEV/TEST bundles and mocked runtime. The
anchor test only reads the ten real normalized text files and checks offsets and
hashes; it does not load a model, connect a database or run corpus retrieval.
