# Test verification — Corpus & Manifest

Command (repository root, WSL .venv):

```text
.venv/bin/python -m unittest discover -s starter/tests -v
Ran 10 tests in 1.321s
OK
```

Executed 2026-11-14, after adding extraction tests. Python 3.12 environment; pypdf 6.21.4; jsonschema 4.26.0.

Coverage: valid 30-page fixture, empty corpus, empty page, missing file, duplicate page content, invalid schema/metadata/permission/checksum/count/page range/timestamp, normalization, refusal of changed PDF snapshot, refusal of changed extracted content, restoration of normalized text.

Fixtures use temporary directories and mocked PDF extraction. They are isolated unit tests, not submitted corpus or benchmark evidence. Real-corpus verification is recorded separately in corpus_validation.json and corpus_validation.md.
