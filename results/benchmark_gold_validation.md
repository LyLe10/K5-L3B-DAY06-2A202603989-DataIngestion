# Stage 5.2 - Approved replacement and benchmark freeze

Status: **STAGE5_2_FROZEN_READY_FOR_REVIEW**. Effective content approval is user-assisted review, with AI assistance; no independent verifier, named reviewer, signature or approval timestamp is invented.

## Approved scope

Only pg16-t04 question content was replaced: DELETE/no condition on physical page 150 becomes COPY efficiency/flexibility on physical page 149. Exact normalized evidence span [558,705) is verified against the source. Source ID, test split and Data Manipulation filter are retained. Topic becomes bulk_insertion; related page checksum/offsets and provenance notes follow the approved replacement. The 19 other JSONL records, including d15 and t03, remain unchanged; dev.jsonl is byte-identical.

## Validation and tests

- Corpus/source identity: existing loader reverified the 40 approved pages and source/page checksums; no corpus modification, chunking, model, retrieval or PostgreSQL access.
- 20 English questions: 15 dev / 5 test; 3 filters: 2 dev / 1 test. 21 exact source evidence spans, including the existing d08 alternative.
- No source/quote/offset/checksum errors. No shared-page or threshold lexical near-duplicate warning remains; d15/t04 overlap is resolved by using page 149 for t04.
- 75 unit tests PASS / 0 FAIL (5.32 seconds), synthetic fixtures only. New tests cover frozen identity, counts, approved IDs, source/page bindings, review provenance, holdout rule and tampering without checksum repair.
- Real freeze candidate validated in a temporary directory before publication, followed by actual frozen bundle validation. No quality metrics computed.
- Only a methodological warning remains: user-assisted approval and automatic checks do not independently certify semantics, exhaustive alternatives or holdout independence. The single-document domain remains shared.

## Freeze and provenance

benchmark/freeze_manifest.json binds dev/test SHA-256, schema/version, notice, source/manifest and 40 selected page identities, counts, all 20 approved IDs and holdout rule NO_TEST_ADJUSTMENT_FROM_RETRIEVAL_RESULTS. benchmark/manifest.json binds the freeze file hash without a circular checksum dependency.

The 19 unchanged questions were reviewed by the user; option A for t04 was explicitly approved. Per-record draft review fields are preserved as authoring provenance to avoid rewriting the other records. The effective approval is the external freeze record. Validation records that approval; it does not authenticate a human signature or claim a separate semantic review.

After freeze, test/gold may not be adjusted from retrieval results. Changes need explicit approval, new identity/checksums and test-exposure disclosure. The freeze does not authorize retrieval or Stage 5.3. No stage/commit/push was performed.

## Hashes

- dev.jsonl: `92489488ef5ffa9c2ba4cbc1f8bb8f40fe04457cd89f5d9ba857fe76e3546ac0`
- test.jsonl: `53966ab40ac337aaf2ef7ae1974bf1f09390af53245a2914dbfc4dc0a1fbab47`
- freeze_manifest.json: `f1aafb9c62ccf63a8f98d47283a8286abe0c46087f8546cec82121d9b9586f5d`
- manifest.json: `e333e2f0e0a7bb47569079ab2f9dd461aa15773c505ab5e7dcf0f26a8ff6bde3`
