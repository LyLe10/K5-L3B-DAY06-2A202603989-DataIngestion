# Checkpoint 4.3A — Embedding Implementation

**PASS kỹ thuật; dừng chờ nghiệm thu trước 4.3B.** Đã triển khai adapter model thật, unit tests và smoke test giới hạn. Không ghi PostgreSQL, chạy migration, sửa corpus/baseline hoặc encode toàn bộ 510 inputs.

## API và implementation

Đã đọc thiết kế Stage 4, preflight 4.1, thiết kế schema và báo cáo APPLY 0001; đối chiếu embeddings/models/store/schema/preparation và thư viện Sentence Transformers đã cài.

- `Embedder` tiếp tục là Protocol, `MyEmbedder` hiện thực `embed_documents(texts)` và `embed_query(question)`. Giữ đối số constructor `model_name`; thêm keyword-only revision/snapshot/cache/batch_size. Không đổi DocumentPage/Chunk, ingestion/chunking/preparation/run/store hoặc SQL migration.
- Chỉ chấp nhận `intfloat/multilingual-e5-small` tại revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`; xác minh lại SHA-256 của 10 artifact theo preflight trước khi load. Local-only, safetensors, trust_remote_code=False; không tải bổ sung hoặc fallback mock.
- CPU/float32/eval; Transformer → mean Pooling → Normalize, include_prompt=True. Prefix được thêm vào input embedding, không ghi vào chunk text: `passage: ` và `query: `. Encode dùng `prompt=''` để không bị thêm prompt ngầm lần nữa.
- Tokenize toàn bộ input của mỗi lời gọi, có special tokens, `truncation=False`; từ chối mọi input >512 trước cache/encode. Chấp nhận đúng 512; query cũng có guard. Sentence Transformers encode có giới hạn nội bộ, nhưng mọi input đã được kiểm tra nằm trong giới hạn đó trước khi gọi; không tự cắt hoặc chia lại input.
- Vector phải có 384 giá trị số, finite sau chuyển float32, norm khác 0 và lệch 1 không quá **1e-5**. Sai vector/batch count bị từ chối, không tự sửa hoặc ghi cache vector lỗi. Kết quả được ánh xạ theo input hash rồi trả theo đúng thứ tự ban đầu, kể cả cache hit/miss, dedup và nhiều batch.
- Cache nằm dưới `data/local/stage4/embedding_cache/<profile_id>/<SHA256(prefixed_input)>.json`. Lưu profile/input identity, vector và vector checksum; không lưu full text. Mọi lần đọc kiểm tra identity/checksum/numeric. Ghi tệp tạm rồi publish bằng hard link nguyên tử, không ghi đè entry có sẵn; entry lỗi gây dừng, không xóa/re-encode che lỗi.
- C dùng chính list vector B trong smoke orchestration, không gọi embedding lần thứ ba. Adapter nhận text không nhận strategy; orchestration 4.3B cần tiếp tục ánh xạ C→B.

## Profile bất biến

Profile ID thực tế, SHA-256 canonical UTF-8 JSON theo EmbeddingProfile v1 đã được thiết kế:

```text
528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651
```

Config đầy đủ và SHA-256 từng artifact nằm trong trường `profile` của [embedding_implementation.json](embedding_implementation.json). Profile là dataclass frozen, chỉ giữ canonical string; đọc config trả bản sao. ID bao gồm revision, 10 artifact hashes, tokenizer, prefixes, pooling/include_prompt, normalization, dimensions, device/dtype/backend và library versions; không dùng tên đường dẫn cache hoặc UUID.

| Thành phần | Giá trị thực |
|---|---|
| Model/revision | intfloat/multilingual-e5-small / fd1525a9fd15316a2d503bf26ab031a61d056e98 |
| Dimensions/device/dtype | 384 / cpu / float32 |
| Pooling | mean tokens, include_prompt=True; các pooling mode khác False |
| Normalization | module Normalize và encode normalize_embeddings=True |
| Tokenizer | XLMRobertaTokenizerFast, fast=True, cùng model/revision |
| Tokenizer/ST limit | 512 / 512 |
| Python | 3.12.3 |
| torch | 2.9.1+cpu |
| sentence-transformers | 5.1.2 |
| transformers | 4.57.1 |
| tokenizers | 0.22.1 |
| huggingface-hub | 0.36.0 |
| sentencepiece | 0.2.1 |
| numpy / safetensors | 2.5.4 / 0.8.0 |

Không thay đổi/cài dependency. Dùng venv Stage 4 đã được nghiệm thu; venv baseline giữ nguyên.

## Kiểm thử

**Unit tests mới: 38 passed in 0.72s.** Test doubles chỉ dùng cho unit, không phải bằng chứng model thật. Bao phủ prefix/query-vs-document, không double prompt, token guard toàn batch/query/cache hit và ngưỡng 512, bad inputs, batch rỗng, dimension/zero/nonunit/nonfinite/float32 overflow, sai batch count, thứ tự qua nhiều batch/cache/dedup, cache reload và isolation theo profile, corrupt cache fail-closed, frozen profile và profile identity, runtime limit drift, pin model/revision và snapshot tampering.

**Toàn bộ pytest baseline venv: 184 passed, 12 subtests passed in 11.31s; 0 fail/skip.** Lệnh:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
```

Smoke thật chạy CPU/offline bằng venv Stage 4:

```bash
PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
HF_HUB_DISABLE_TELEMETRY=1 TOKENIZERS_PARALLELISM=false \
data/local/stage4/venv/bin/python -B starter/scripts/check_embedding_smoke.py
```

**Smoke PASS:** 4 chunk A + 4 chunk B, hai section Data Definition/Data Manipulation, trang vật lý 97 và 148. Query là một câu kỹ thuật kiểm thử, không phải benchmark. Danh sách chunk ID/page/section/input hash và norm từng vector được ghi trong JSON.

| Nhóm document | Inputs | Min token | Mean | Max | p95 nearest-rank | >512 |
|---|---:|---:|---:|---:|---:|---:|
| A | 4 | 118 | 126.5 | 137 | 137 | 0 |
| B | 4 | 90 | 108 | 118 | 118 | 0 |
| A+B | 8 | 90 | 117.25 | 137 | 137 | 0 |

Query: **18 token**, 384 chiều. Toàn bộ document/query vectors finite và norm trong khoảng **0.999999987078–1.000000060107**. Đối chiếu batch với hai encode đơn độc lập: max absolute differences **3.725290298461914e-08** và **0.0**, đều <1e-5. Cache replay input đảo thứ tự trả đúng vector tương ứng; query replay khớp; C dùng cùng object B và không tăng encode calls.

## Cache và thời gian thực

| Chỉ số | Kết quả |
|---|---:|
| Adapter calls / input positions | 5 / 18 |
| Inputs thực encode qua adapter | 9: 8 document + 1 query |
| Encode batches qua adapter | 3 |
| Cache hits | 9: 8 document replay + 1 query replay |
| Dedup miss trong batch smoke | 0; unit test có kiểm tra |
| Encode tham chiếu ngoài adapter | 2 document inputs đã có, chỉ để đối chiếu numeric/order |
| Tổng model input encode events | **11**, không phải 510 |
| Cache entries / bytes | **9 / 74.501** |
| Artifact verification | 4.095011 giây |
| Load model sau import | 2.915227 giây |
| Encode qua adapter | 3.194887 giây |
| Encode tham chiếu | 0.153256 giây |
| Tokenize 18 input positions | 0.016138 giây |
| Tổng smoke process | 105.475352 giây, gồm cold imports, hash, load, corpus audit, encode và DB read |
| API calls/chi phí API | 0 / 0 |

Smoke chạy **2026-11-14 07:16:20–07:18:01 UTC**. Không suy diễn latency/throughput toàn corpus từ batch nhỏ. Cache vector chỉ nằm trong data/local bị ignore; không đưa vector hoặc weights vào báo cáo public.

## PostgreSQL, baseline và file integrity

- Snapshot PostgreSQL trước/sau lấy bằng psycopg với `default_transaction_read_only=on`; xác minh `transaction_read_only=on`, đúng day6_lab/cluster `7707847059457269799`.
- Ledger version/checksum/applied_at và catalog fingerprint giữ nguyên. `embedding_profiles=0`, `strategy_snapshots=0`, `chunks=0` ở cả hai lần; không INSERT profile hoặc vector.
- Corpus loader đối chiếu checksum thật; 40 trang, 103371 ký tự, A=246/B=264, C cùng B; coverage A/B 103371/103371. Toàn bộ ID/text/metadata/provenance/thứ tự khớp JSONL baseline.
- So sánh SHA-256 các file đã tồn tại: chỉ `starter/src/embeddings.py` thay đổi đúng phạm vi. Các file khác, gồm 7 untracked local được bảo vệ, preflight/apply evidence, migration/schema và baseline source giữ nguyên.
- Inventory **26.453 file data/local cũ** giữ nguyên tên/size/mtime; chỉ thêm **9 cache entries** trong thư mục mới đã được phép. Không tuyên bố hash lại toàn bộ venv/weights; 10 model artifact đã được hash thật lại trước load.
- HEAD vẫn `3996c7566f36d5951c311779e29905132580aee8`, origin/main `9a2964e037716e1179d845ec8e5c21675c90a2e0`; behind 1. Không staged, không pull/rebase/commit/push.

## File thay đổi

1. `starter/src/embeddings.py` — hiện thực MyEmbedder, numeric/token validation, pinned profile và cache.
2. `starter/tests/test_embeddings.py` — mới, 38 unit cases.
3. `starter/scripts/check_embedding_smoke.py` — mới, bounded smoke thật và DB read-only snapshots.
4. `results/embedding_implementation.json` — mới, model/profile/token/cache/numeric/timing/DB evidence và integrity.
5. `results/embedding_implementation.md` — báo cáo này.

Ngoài ra có 9 cache files local bị ignore. Không sửa requirements, store/models/schema/ingestion/chunking/run hoặc migration.

## Rủi ro và công việc trước 4.3B

1. Smoke chỉ xác minh 8 document khác nhau, không chứng minh encode/full ingest 510 inputs. Trước ghi DB cần prevalidate toàn snapshot, giữ cùng profile và ánh xạ C→B; chờ phê duyệt riêng cho full encode/ingestion.
2. Cache không thay kiểm tra corpus/manifest/chunk metadata. 4.3B phải tính corpus/chunkset/snapshot digests thật, mapping typed metadata và xác minh vector thứ tự/số lượng trước transaction.
3. Cache lỗi phải dừng, không xóa hoặc ghi đè tự động. Atomic hard-link publication đã chạy trên WSL/filesystem hiện tại; chưa kiểm thử native Windows hoặc nhiều process writer. Tranh chấp cùng key nhưng vector khác sẽ bị từ chối.
4. Float32 batch có sai khác nhỏ với encode đơn như số đo trên; dùng numeric tolerance, không hứa bitwise equality khi encode lại. Cache reuse trả chính giá trị float32 đã lưu. Đổi dependency/artifact/config tạo profile ID mới; không trộn namespace hoặc ghi đè profile cũ.
5. Profile đã được tính nhưng chưa INSERT PostgreSQL. Store vẫn TODO; 4.3B cần triển khai idempotent full-snapshot transaction, advisory lock/deferred constraints và kiểm thử rollback/namespace/stale removal trong môi trường cô lập trước mutation thực.
6. Chưa chạy retrieval/benchmark hoặc đánh giá chất lượng, không tạo coherence/grounding/Hit@k. Hiệu năng commit triggers và chất lượng retrieval vẫn chưa được chứng minh.

**Dừng tại 4.3A, chờ nghiệm thu.**
