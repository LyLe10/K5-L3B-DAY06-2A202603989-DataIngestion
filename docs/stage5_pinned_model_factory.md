# Pinned model factory readiness (offline only)

> **Historical status - checkpoint A6.** The synthetic-only description below records the earlier offline review; the historical hash table is preserved evidence, not a current code manifest or approval. See [current model/probe wiring](stage5_minimal_live_wiring.md) and [current guarded DEV runtime](stage5_live_dev_runtime.md). Regenerate current canonical requests and code identities from the actual executing workspace. The factory direct public call remains disabled; later guarded wiring does not constitute live execution approval. Separate explicit approval is required; TEST remains blocked.

## Execution boundary

`PinnedLocalModelFactory(root=..., request_canonical=...)` regenerates the exact
canonical request. Its public call always raises `PINNED_MODEL_FACTORY_LIVE_DISABLED`.
Only `synthetic_binding(constructor_double=Mock(...))` exercises the proposed
constructor bridge. No real constructor is imported or invoked by that bridge.
Mock acceptance is a test convention, not a sandbox: a Mock side effect is arbitrary
Python. No live approval is issued here. All existing live gates remain disabled.

## Reviewed initialization call graph

The existing Stage 4 API is
`MyEmbedder(model_name, *, revision=REVISION, snapshot_path=SNAPSHOT,
cache_dir=CACHE, batch_size=16)` in `starter/src/embeddings.py`.

Its constructor validates pins and paths, verifies ten artifact hashes and package
versions, then imports torch and Sentence Transformers. It constructs
`SentenceTransformer(local_snapshot, device='cpu', local_files_only=True,
trust_remote_code=False, model_kwargs={'use_safetensors': True,
'dtype': torch.float32}, tokenizer_kwargs={'use_fast': True})`, calls `eval()`,
checks modules, tokenizer limits, CPU parameters, float32 and mean pooling, builds
the immutable profile, and configures the adapter with zero encoding counters.

Static inspection of the installed pinned Sentence Transformers dependency follows
local module/config loading into Transformer, Pooling and Normalize. Transformer
loads AutoConfig, AutoModel and AutoTokenizer with local-only settings propagated.
Model-card initialization skips remote metadata lookup in local-only mode. This is
source inspection, not a runtime verification or proof about every native import.

| Side effect | Reviewed behavior / limitation |
| --- | --- |
| Model/tokenizer loading | Intended constructor operation, forbidden in this checkpoint. |
| Encoding/inference | No encode, forward or smoke test in the reviewed initialization path. |
| PostgreSQL | No connection in that path. |
| Vector cache | Adapter configuration assigns a path; cache creation/writes belong to later encoding. Explicit Stage 5 path is mandatory; the default is Stage 4. |
| Network | Local-only and remote-code-disabled arguments are hard-coded in the pinned constructor. Import/native behavior is not an OS network sandbox. |
| Other local writes | Dependency logging, bytecode/native initialization and environment-selected Hugging Face cache behavior need a controlled live environment. No universal zero-write guarantee. |
| Sensitive logs | Dependencies may log the absolute snapshot path. Future live logging must suppress/redact private paths and raw exceptions. |

The bridge rejects files beyond the ten approved artifacts, unknown directories,
symlinks and junctions. It permits the empty built-in `2_Normalize` directory.
This prevents optional unpinned configs such as `adapter_config.json` from selecting
another initialization branch. Filesystem checks do not eliminate adversarial TOCTOU;
live artifact custody must prevent concurrent modification.

## Authorization, consumption and audit

Use the existing outer `simulate_model_load_only` sequence: regenerate exact request,
compare canonical bytes, independently verify the manual decision, durably consume,
write sanitized audit, verify artifacts, invoke the synthetic bridge, verify returned
profile/runtime contract, then verify the success audit. Failure never resets the
claim or retries initialization. The bridge also rechecks code/evidence hashes and
asserts an existing consumption row before invoking the constructor double.

`ConsumptionLedger.require_consumed` is a read-only ordering assertion, not an
approval verifier or independent execution lease. The local SQLite ledger retains
the accepted lab custody limitations, including no anti-restoration guarantee.
The bridge spends its own attempt even on failure. Do not expose it as a standalone
authorization service. `verify_model_load_approval` remains a partial validator;
exact canonical regeneration is essential. Adapter counters cannot prove absence
of arbitrary factory side effects.

## Future approval inputs

A separate explicit approval is required before any first real model/tokenizer load.
It must bind a newly regenerated request (old requests become stale on code changes),
run/executor/reviewer/authority identities, expiration, durable single-use claim and
new audit destination. No caller flags or environment variables authorize execution.

The request contains full SHA-256 values for every entry in
`model_load_only.CODE_FILES`, their canonical aggregate, the Stage 4 evidence hash,
the complete profile and ten artifact hashes. This includes the factory itself,
MyEmbedder, schema, authorization, lab runtime, bootstrap, evaluation, evaluation
runner, retrieval and store code. Review the exact generated hash map before approval.

Required model inputs: `intfloat/multilingual-e5-small`, revision
`fd1525a9fd15316a2d503bf26ab031a61d056e98`, profile
`528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651`,
snapshot `data/local/models/intfloat--multilingual-e5-small/<revision>`, cache
`data/local/stage5/embedding_cache`, CPU float32/eval, batch size 16 and the
approved dependency environment. Pin/hash checks precede initialization.

No mandatory Stage 4 constructor change was identified for the reviewed local-load
contract. Remaining live prerequisites are an independently verified manual approval,
reviewed real constructor wiring, artifact/ledger custody, controlled cache/network
and logging behavior, and separate permission to enable that narrowly scoped entry.
Any such code change requires fresh code identities and review. Loading only must
not encode queries/documents, access PostgreSQL or execute evaluation; test remains
blocked. This document grants none of those permissions.

## Reviewed code SHA-256 map

These are offline review identities, not an approval. Regenerate before any live request.

| Code file | SHA-256 |
| --- | --- |
| `starter/src/model_load_only.py` | `a25e91d36971b41c9202376e4ecd189f728d9bd8cd0c37832c2a6687f5c4dc7b` |
| `starter/src/pinned_model_factory.py` | `7f1dcb65297d95ac6513d4ae112fd4c43295b87fe516b8113032ba5892a07893` |
| `starter/src/embeddings.py` | `a76d1943d75d578b9d16b3b7a2f970280bc8fc8ab8f7dc9a282be84ed10d686a` |
| `starter/src/schema.py` | `44af24d061e2d1b84f43302964661f7ef610131a8d3a2d975cc80704af779479` |
| `starter/src/dev_authorization.py` | `3e0f5d8f952e545053af737c7fa1c2127e35920fe5808e37b13b345fd1b4cc5a` |
| `starter/src/lab_dev_runtime.py` | `d332ddfd59ec5af31a5c1dda8cc4c93192547268a08d9cacace1e83e6896b673` |
| `starter/src/dev_bootstrap.py` | `071b9846a69e719a9f09f2a32b7fd077d4cfa234126c114413658c644a53ff13` |
| `starter/src/evaluation.py` | `d41a6d524dfc43cbd164fa6b00e455323d2a08fc6607762796927f59d4f0d575` |
| `starter/src/evaluation_runner.py` | `91b4c2bdb8a1f19e5bdcee23fb1f90fbb9fc1b5c1749e270593015d1642aa1e7` |
| `starter/src/retrieval.py` | `5dc9129e0a1e1fced6e21da3dc5b92d7a0f2a07bd72e7bcd5ede77cc1d4bb19d` |
| `starter/src/store.py` | `ef11b678d0d41b99a9911e280342c963cd8d310c19a0bef77253c16537cf7dfc` |
