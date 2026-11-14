# Minimal Day06 benchmark — offline validation

Status: **OFFLINE IMPLEMENTATION VERIFIED; REAL RUNTIME NOT EXECUTED**.

## Validation

Final related suite: **144 passed, 0 failed**, 16.74 seconds, exit 0.
Executed in the existing WSL Stage 4 Python environment:

```bash
PYTHONDONTWRITEBYTECODE=1 data/local/stage4/venv/bin/python -B -m pytest -q \
  -p no:cacheprovider starter/tests/test_local_lab_test.py \
  starter/tests/test_local_lab_dev.py starter/tests/test_evaluation.py \
  starter/tests/test_evaluation_runner.py
```

Tests use temporary synthetic benchmark bundles, numeric fixture vectors and fake
model/database objects. No real model was loaded, no query was encoded by a real
model, and no PostgreSQL connection or real DEV/TEST benchmark was executed.
The anchor check reads the ten existing normalized source files and verifies
their hashes, character counts and midpoint offsets.

Coverage includes complete DEV validation (45 ordered successful traces, receipt
and source/evidence checks, recomputed metrics), frozen benchmark and selection
tampering, all selection tiebreaks, TEST split/count isolation, five-query producer
inputs without gold, 15 A/B/C top-3 searches, filter behavior, unchanged protected
TEST rejection, partial/error artifacts, no retry, secret sanitization and
no-overwrite. Runtime factory wiring is tested with a mocked adapter and store;
the interactive credential reader is not called during those tests.

WSL wall-clock corrections exposed an unnecessary timestamp-order check during
development. Timestamps now remain reporting fields; COMPLETE DEV artifacts and
their hashes establish the required DEV -> selection -> TEST sequence. The final
suite includes a backwards-clock case. No trusted-clock/approval infrastructure
was introduced.

## Files added

- `starter/scripts/run_local_lab_test.py`
- `starter/tests/test_local_lab_test.py`
- `results/benchmark_config.json`
- `results/coherence_anchors.csv`
- `docs/local_lab_test.md`
- This validation report.

DEV entrypoint, protected Stage 5 source/gates, corpus, frozen benchmark/gold,
model, vectors, schema and migrations were not edited. No tracked-file diff was
present at final verification. Existing unrelated untracked files were retained.
No commit or push was performed.

## Remaining work

`results/selection_freeze.json` has deliberately not been created: a real COMPLETE
DEV run is required. No real local benchmark output/cache directory was created.
Operator runtime, real connectivity/permissions, model initialization, DEV/TEST
quality metrics, manual coherence/metadata/grounding labels, experiment log and
final submission/report remain to be completed. See `docs/local_lab_test.md` for
the DEV, offline selection and TEST commands. Runtime still awaits operator
approval.
