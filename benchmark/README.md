# PostgreSQL 16 English benchmark — Stage 5.2 frozen

Status: **FROZEN — user-assisted review recorded**. The user reviewed the 19 unchanged questions and approved COPY option A for `pg16-t04`; AI assisted drafting and source review. No independent verification, reviewer name, signature or approval timestamp is claimed. No retrieval has run and no quality metrics have been computed.

There are 20 English questions: 15 dev and 5 test. Exactly three currently have an explicit, pre-retrieval section scope: `pg16-d12` (Data Definition), `pg16-d14` and `pg16-t04` (Data Manipulation). A/B will not use these filters; C will use the supplied context. Filter values were not inferred from an answer, gold ID or retrieval output.

## Files and review

- `dev.jsonl`, `test.jsonl`: separate records with English questions, answers and exact source quotes.
- `question.schema.json`: version 1 authoring-record schema, including alternatives and original draft review fields.
- `manifest.json`: SHA-256 of question files, schema, source notice, corpus manifest and the freeze manifest.
- `freeze_manifest.json`: effective user-assisted approval of all 20 IDs, file/schema/source identities, counts and the rule prohibiting test adjustment from retrieval results.
- `gold_review.md`: readable rendering of all questions, answers and gold spans, generated from JSONL for review; not a second authoritative gold dataset.
- `NOTICE.txt`: exact source notice copied from the approved local PostgreSQL PDF notice. Corpus source/permission provenance is recorded in [the source rights record](../data/rights/postgresql-16.16.md).

Per-record `review_status=NEEDS_HUMAN_REVIEW` and `reviewer=null` are retained as original authoring provenance so the 19 other question records remain byte-for-byte unchanged. Effective approval is recorded in the freeze manifest, not inferred from automatic validation or those historical fields. The validator checks the approved ID set and bound hashes/counts before reporting a frozen benchmark. Later question/gold changes require explicit approval, a new identity/checksums and disclosure of test exposure; the frozen test cannot be tuned from retrieval results.

Gold is source/page/span based, independent of chunk IDs. Offsets are zero-based Unicode character positions `[start,end)` in the exact saved normalized page, not PDF byte offsets or printed page labels. The 21 spans include one alternative for `pg16-d08` on the same physical page. Alternatives are not claimed to be exhaustive.

## Validation

From repository root, using the existing baseline Python environment and dependencies:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B starter/scripts/check_benchmark.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest starter/tests/test_benchmark.py -q -p no:cacheprovider
```

The validator uses `load_manifest_pages()` to verify the 40 approved PDF/text pages and their checksums. It reads only source documents and benchmark records; it does not read retrieval results, embed, connect to PostgreSQL, alter the corpus or rewrite checksums. Exit codes: 0 = structural/source integrity passes (inspect the reported draft/frozen review state); 1 = invalid records; 2 = cannot validate/integrity error. Frozen input additionally requires matching freeze integrity, user-assisted approval provenance, counts, source identity and no unresolved overlap/near-duplicate warning. The CLI prints a report and does not overwrite any report file.

English validation checks `language=en`, text structure and obvious non-English alphabetic characters. This heuristic cannot establish language semantics: ASCII text in another language may pass, while some valid English technical text with non-ASCII identifiers may need separate review. Source substring matching does not prove an answer is correct or evidence is sufficient. There is no automatic semantic approval or LLM judge.

## Split and leakage limitations

Split and gold were authored before any benchmark retrieval. Dev covers table basics, defaults, generated columns, constraints, column changes, search path, row security, INSERT and UPDATE. Test covers system columns, inheritance, privileges, COPY bulk-insertion trade-offs and trigger-aware RETURNING. Question wording/category diversity is intentional, not a measured retrieval result.

The whole benchmark comes from one document. The original `pg16-t04` DELETE question on page 150 was replaced, with explicit user approval, by the COPY trade-off question on page 149, span [558,705). `pg16-d15` remains unchanged on page 150; the shared-page warning is resolved. No lexical near-duplicate/shared-page warning remains, but domain vocabulary still overlaps and this is not proof of document-level or semantic independence. Neither split has been retrieved or used to select a strategy.

Do not use test results to edit retrieval or gold. After dev configuration is frozen and approved, test execution requires the next checkpoint approval. See [Stage 5 protocol](../docs/stage5_retrieval_evaluation_plan.md).

## Publication and scope

Only selected evidence excerpts are included, with PostgreSQL copyright/license notice; no PDF, full pages, model weights, document/query vectors or caches are included. Keep the notice with copied excerpts and review the submission rights. Protect the local source corpus and Stage 4 receipts. This frozen benchmark contains no Hit@K/MRR, coherence or grounding scores. Freeze does not authorize Stage 5.3 or any retrieval/model/database execution.
