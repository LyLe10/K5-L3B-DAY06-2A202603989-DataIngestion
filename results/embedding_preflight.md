# Checkpoint 4.1 — Embedding Preflight

Cập nhật: 2026-11-14T05:36:31.054470+00:00. Thiết kế chính: `docs/stage4_embedding_pgvector_plan.md`.

**PASS kỹ thuật — chờ người dùng nghiệm thu trước 4.2.** Đã cài dependency trong venv riêng, tải và xác minh model thật, load CPU offline, tokenize đủ 510 input không truncation và kiểm tra psycopg chỉ đọc. Không encode corpus, không triển khai 4.2, không ghi PostgreSQL. Có sự kiện Git bên ngoài lượt: origin/main được fetch tiến thêm một commit rename; xem mục 1.

## 1. Git, phạm vi và tính toàn vẹn

- Trước lượt: HEAD và origin/main cùng `3996c7566f36d5951c311779e29905132580aee8`; 0 tracked modified, không staged; 7 untracked cũ và báo cáo này đã tồn tại.
- Sau lượt: HEAD vẫn `3996c7566f36d5951c311779e29905132580aee8`; origin/main hiện `9a2964e037716e1179d845ec8e5c21675c90a2e0`; `main...origin/main [behind 1]`.
- Reflog ghi `9a2964e fetch: fast-forward`; commit `Rename` là con trực tiếp của 3996c75, chỉ đổi report/individual/MSSV_HoTen.md thành 2A202603989_LeThiLy.md, 0 dòng nội dung đổi. Lượt preflight không chạy fetch/pull/commit/push và không đồng bộ ref trở lại.
- 54 tracked files, 7 untracked cũ, .git/config và .git/index: đủ 63 SHA-256 giữ nguyên trước/sau. Không staged. Chỉ cập nhật báo cáo này ngoài các artifact local bị ignore.
- Venv riêng: `data/local/stage4/venv/`; package trong `.venv` baseline giữ nguyên.
- Xây lại chunk từ PDF/manifest thật, đối chiếu từng dict với JSONL baseline: ID/text/metadata/thứ tự khớp. 40 trang; A=246, B=264; C dùng chính B. Coverage A/B đều 103371/103371; audit không lỗi.
- Manifest SHA-256: `6ec73dc52b8cb5d83f5b08baeffcb231109cc2bbd95525c3315ae72c1f29db5d`. Không sửa checksum hoặc tạo dữ liệu giả.

## 2. API và khả năng tương thích

`DocumentPage` và `Chunk` vẫn là dataclass với document_id, source, page, text, metadata. Không cần thêm vector vào dataclass hoặc đổi constructor. `page` tiếp tục là số trang vật lý bắt đầu từ 1; printed_page_label nullable được giữ trong metadata.

`Embedder` có model_name, dimensions, embed_documents(texts) và embed_query(question). `MyEmbedder` hiện còn TODO; giữ các phương thức này, thêm cấu hình revision/cache/device qua keyword-only khi triển khai. Input công khai là text chưa thêm prefix; adapter thêm đúng một prefix theo hợp đồng, không sửa text/ID của chunk.

`PgVectorStore` còn TODO; các chữ ký upsert/search đã phù hợp. Kế hoạch thêm dataset_id/profile_id vào constructor cần mô tả rõ: không đổi thứ tự hai tham số đầu; giữ khả năng gọi hai tham số nếu yêu cầu tương thích toàn bộ starter, đồng thời từ chối thao tác ghi khi profile chưa được cấu hình/xác minh. Không tự suy ra profile từ model_name. Không có call site đang sử dụng adapter/store ngoài định nghĩa hiện tại.

Giữ nguyên load_pdf, normalize_text, fixed_size, by_paragraph, load_manifest_pages và build_strategies. C không có chunk/vector riêng. run.py giữ nguyên khung TODO trong checkpoint này.

## 3. Môi trường và dependency thực tế

- WSL2 x86_64/glibc 2.39; Python 3.12.3. Ban đầu còn 70.45 GiB đĩa; RAM WSL tổng khoảng 7.69 GiB, khả dụng khoảng 6.62 GiB; 8 logical CPU.
- TLS với PyPI/PyTorch CPU/Hugging Face đạt qua WSL; pip và tải model hoàn tất với xác minh chứng chỉ bật. Không thay CA hoặc dùng trusted-host/verify=False.
- Resolver dry-run exit 0, 106.08 giây. Đối chiếu pin trực tiếp với kết quả resolver, rồi cài đúng 48 wheel bằng URL+SHA-256/--require-hashes; không tự đổi phiên bản.
- Thời gian cài: 1146.361 giây, gồm tải/kiểm tra hash/giải nén/cài; không phải thời gian mạng riêng. Cài nhiều tệp trên thư mục Windows qua WSL chậm.
- `pip check`: exit 0, No broken requirements found. Import/runtime Sentence Transformers, PyTorch và psycopg thực tế đạt.
- Pin chính: torch 2.9.1+cpu; sentence-transformers 5.1.2; transformers 4.57.1; tokenizers 0.22.1; huggingface-hub 0.36.0; sentencepiece 0.2.1; pgvector 0.4.1; psycopg/psycopg-binary 3.3.8; python-dotenv 1.2.4.
- Giữ pypdf 6.21.4, jsonschema 4.26.0, pytest 9.2.0 trong venv mới. torch.version.cuda=None; không cài torchvision/torchaudio.

### Dung lượng đã đo

| Thành phần | Byte | MiB |
|---|---:|---:|
| Payload model/tokenizer đã tải | 493292828 | 470.441 |
| Toàn bộ model cache/snapshot | 493292828 | 470.441 |
| Venv Stage 4 | 1083378023 | 1033.190 |
| Pip cache Stage 4 | 297346137 | 283.571 |

Dung lượng thư mục là apparent size đo bằng du -sb; không phải băng thông mạng. Đĩa còn 68.706 GiB. Không đo tổng byte HTTP của pip; payload model không bao gồm HTTP headers/metadata.

## 4. Model snapshot và artifact

- Model intfloat/multilingual-e5-small; resolved API sha `fd1525a9fd15316a2d503bf26ab031a61d056e98`.
- Snapshot: `data/local/models/intfloat--multilingual-e5-small/fd1525a9fd15316a2d503bf26ab031a61d056e98`.
- License metadata/model card snapshot: mit. Model card giữ local; không có file LICENSE riêng trong danh sách artifact snapshot đã chọn.
- Download: 61.18 giây; hoàn tất 2026-11-14T05:12:56.572147+00:00. Chỉ 10 artifact dưới đây, một model.safetensors; không .bin/ONNX/OpenVINO.
- Mỗi file đối chiếu kích thước upstream; LFS đối chiếu SHA-256, file Git nhỏ đối chiếu Git blob ID. Tính lại SHA-256 trước load cũng khớp.

| Artifact | Byte | SHA-256 |
|---|---:|---|
| README.md | 497538 | `0038de97aee16258cecbad7ffda4b4febd6953e747a00e0ddbc8e6ed241e9c1c` |
| config.json | 655 | `69137736cab8b8903a07fe8afaafdda25aac55415a12a55d1bffa9f581abf959` |
| modules.json | 387 | `c6e29747481e8b5dd2b58401966aeac910de39092f90cda9a704b1545f902b04` |
| sentence_bert_config.json | 57 | `948201d8329907aae938fa62f9ceeed53f5694dacc2b87b9f3b78b37ee986529` |
| 1_Pooling/config.json | 200 | `987f7a67a38fa564c849bb5d277c52ab9088a84368fc0be31a354125aebb12a0` |
| tokenizer_config.json | 443 | `a1d6bc8734a6f635dc158508bef000f8e2e5a759c7d92f984b2c86e5ff53425b` |
| special_tokens_map.json | 167 | `d05497f1da52c5e09554c0cd874037a083e1dc1b9cfd48034d1c717f1afc07a7` |
| sentencepiece.bpe.model | 5069051 | `cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865` |
| tokenizer.json | 17082730 | `0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39` |
| model.safetensors | 470641600 | `1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477` |

## 5. Runtime và phân bố token thực tế

- Load bằng SentenceTransformer từ local, local_files_only=True, trust_remote_code=False và offline mode; safetensors, CPU, torch.float32, eval mode.
- BertModel; get_sentence_embedding_dimension()=384; mọi parameter trên CPU/float32. Modules Transformer → Pooling → Normalize. Mean-token pooling bật, các pooling mode khác tắt.
- Normalize xác nhận từ module runtime; chưa encode nên chưa đo norm vector đầu ra. Kiểm tra numeric finite/norm/order thuộc bước encode 4.2.
- Tokenizer XLMRobertaTokenizerFast, use_fast=True; tokenizer.model_max_length=512, SentenceTransformer.max_seq_length=512, max_position_embeddings=512. Effective limit=512; 2 special tokens cho input đơn.
- 510 input phân biệt: `passage: ` + nguyên chunk.text; add_special_tokens=True, truncation=False, padding=False, return_length=True; kiểm tra length bằng len(input_ids). Không ghi prefix vào text gốc.
- p95 dùng nearest-rank, vị trí ceil(0.95*n) trong dãy tăng dần.

| Strategy | Inputs | Min | Mean | Max | p95 | >512 |
|---|---:|---:|---:|---:|---:|---:|
| A | 246 | 18 | 121.707317 | 212 | 156 | 0 |
| B | 264 | 15 | 103.996212 | 208 | 144 | 0 |
| A+B | 510 | 15 | 112.539216 | 212 | 152 | 0 |

- Overflow=0; danh sách chunk ID/page/token length vượt giới hạn rỗng. Không cần sửa baseline hoặc truncation.
- Constructor/load model: 3.607 giây; kiểm tra chunk + tokenize A/B: 0.115 giây. Toàn runtime process (cold imports, checksum, PDF/chunk audit, DB): 114.503 giây.
- Không gọi encode/embed_documents/embed_query; không tạo embedding corpus hoặc benchmark. Query length guard cần triển khai/test riêng ở 4.2.

## 6. PostgreSQL/pgvector — kết nối psycopg thực

- psycopg/psycopg-binary 3.3.8, đọc DATABASE_URL từ starter/.env qua python-dotenv 1.2.4; không in hoặc lưu URL/secret vào log/report.
- Kết nối ứng dụng WSL đạt: day6_lab, PostgreSQL 16.16 (Debian 16.16-1.pgdg12+1), pgvector 0.8.7.
- default_transaction_read_only=on, statement timeout 10 giây, connect timeout 5 giây; SELECT xác nhận transaction_read_only=on; rollback tường minh.
- Quyền CREATE có sẵn nhưng không dùng; day6_ingestion chưa tồn tại. Không CREATE/ALTER/INSERT/UPDATE/DELETE, không tạo bảng/index/schema.

## 7. Kiểm thử và bằng chứng local

- `.venv` baseline: 82 passed, 12 subtests passed, 0 skip/error; pytest ghi 9.87 giây.
- Venv Stage 4: 82 passed, 12 subtests passed, 0 skip/error; pytest ghi 10.10 giây.
- Corpus integration/audit: 40 trang, A=246/B=264, coverage=103371/103371; JSONL baseline khớp, C dùng B.
- Bằng chứng ở data/local/stage4/preflight/: resolver.json/resolver.log, resolved-requirements.txt (URL+hash), install.log/install_metrics.json, installed_freeze.txt, pip_check.log, model_remote_metadata.json/model_artifacts.json, runtime_preflight.py/runtime_result.json/runtime.log, token_lengths.json (510 bản ghi ID/page/section/token length/input hash, không full text), storage.json, baseline_pytest.log/stage4_pytest.log và integrity.json.
- Chạy lại từ root trong WSL: `data/local/stage4/venv/bin/python -B data/local/stage4/preflight/runtime_preflight.py`. Script chỉ load/tokenize/đọc DB; không encode/ghi DB.
- Log/cache/venv/model/script preflight ở data/local/ bị ignore; không đưa weights hoặc secret vào Git.

## 8. Schema và điều chỉnh thiết kế đề xuất — chưa triển khai

Giữ namespace day6_ingestion, vector(384), exact cosine và PK chunk (dataset_id, profile_id, strategy, chunk_id). Chỉ lưu strategy A/B; C ánh xạ B. Bảng chunks giữ document_id, source, physical_page, printed_page_label nullable, section, text, các checksum và metadata JSONB đầy đủ, embedding NOT NULL.

Bổ sung vào thiết kế trước triển khai:

1. **Migration có phiên bản:** schema_migrations(version, checksum, applied_at). DDL chạy tường minh, trong transaction và có khóa migration; kiểm tra kiểu cột, FK, dimension và extension hiện có. CREATE TABLE IF NOT EXISTS đơn thuần không chứng minh schema tương thích. Không tự nâng extension hoặc tự thay dimension. create_schema() là entry point gọi migration đã kiểm chứng, không chạy DDL khi constructor/search.
2. **Profile bất biến:** canonical JSON gồm model/revision, tokenizer và artifact checksums, fast/slow tokenizer, pooling, prefix, effective token limit, dtype, normalization, phiên bản thư viện; hash thành profile_id. Conflict phải so sánh cấu hình đầy đủ, không ghi đè profile khác. Model/tokenizer đều pin revision, trust_remote_code=False, ưu tiên safetensors.
3. **Snapshot ledger:** strategy_snapshots khóa theo dataset/profile/strategy; lưu manifest hash, corpus selection hash, hash danh sách chunk ID/content/metadata theo thứ tự chuẩn, expected_count và trạng thái hoàn tất. Không chỉ so sánh manifest hash để chứng minh A/B cùng dữ liệu. Bắt buộc A/B có cùng corpus snapshot và profile trước phép so sánh.
4. **Transaction sync:** encode/validate toàn bộ snapshot trước transaction; khóa transaction theo namespace bằng khóa ổn định (không dùng Python hash ngẫu nhiên). Upsert và xóa stale trong đúng namespace, cập nhật ledger trong cùng transaction; lỗi phải rollback. Từ chối input rỗng/trùng ID/thiếu corpus. Re-ingest không đổi count hoặc payload; không cập nhật timestamp vô cớ nếu payload không đổi. Không xóa ngoài namespace.
5. **Metadata:** section là cột text có B-tree (dataset_id,profile_id,strategy,section); metadata JSONB vẫn giữ provenance và _chunking offsets. Kiểm tra cột typed khớp metadata; không suy đoán printed label, section, version. Kiểm tra physical_page>0, offsets hợp lệ, text checksum, vector finite/384 chiều/norm sau chuyển float32 trước ghi.
6. **Filtering:** allowlist chỉ section equality với giá trị string; khóa sai/kiểu sai phải báo lỗi, không bỏ filter âm thầm. Giá trị không có dữ liệu trả rỗng. A/B không filter trong so sánh; C đọc B, không filter thì cùng kết quả B. Mọi query ràng buộc dataset/profile/strategy và tham số hóa giá trị; tên schema/bảng cố định/quote an toàn. Không lấy filter từ gold.
7. **Retrieval:** exact ORDER BY embedding <=> query_vector ASC, chunk_id ASC; score=1-distance, không phải xác suất. Validate query vector và top_k trước SQL. Chưa thêm HNSW/IVFFlat. Profile lookup/query/snapshot cần nhất quán khi có sync đồng thời.

Giữ nguyên yêu cầu GUIDE/BENCHMARK: freeze ít nhất 20 câu (15 dev/5 test, >=3 câu filter và >=1 filter ở test) trước thử nghiệm retrieval để lựa chọn/tinh chỉnh. Smoke kỹ thuật không được dùng làm kết quả benchmark.

## 9. Rủi ro và giới hạn còn lại

- 510 input hiện tại không overflow; không suy rộng sang query tùy ý hoặc corpus khác.
- Load/tokenizer đạt; chưa kiểm chứng chất lượng embedding/retrieval, numeric output norm, idempotency, transaction write hoặc migration trên DB thật. Các việc này thuộc 4.2 sau duyệt.
- Cài/import lạnh qua NTFS/WSL chậm; thời gian tách theo từng bước. Không chuyển môi trường hoặc đổi thiết kế cache trong lượt này.
- origin/main tiến thêm commit bên ngoài lượt; local HEAD/source không đổi. Không pull/rebase/merge/reset; quyết định đồng bộ riêng trước checkpoint có sửa source.
- Mmap WSL của init.sql là vấn đề đã biết từ checkpoint trước; không sửa thêm trong lượt này.

## 10. Danh sách thay đổi dự kiến cho 4.2 — chưa thực hiện

- starter/src/embeddings.py: adapter thật, profile, prefix, token guard, validation vector, cache theo profile+input hash.
- Module cấu hình/profile riêng và dependency constraints/lock; lệnh setup CPU/cache local trong README.
- starter/src/store.py: psycopg/pgvector adapter, migration entry point, full-snapshot sync, exact search/filter allowlist.
- Migration SQL phiên bản đầu và snapshot ledger, sau phê duyệt DDL riêng.
- CLI riêng cho encode/ingest/smoke; không biến run.py thành pipeline benchmark.
- Tests unit và integration model/DB thật: thứ tự/dimension/norm, metadata, idempotency, rollback, stale deletion, namespace isolation và B=C không filter. Fixture DB biệt lập cho tình huống thay đổi dữ liệu.
- Reports thực về thời gian, token, checksum, encode/cache, ingest/retrieval smoke; vector/model cache chỉ local. Không thêm điểm đánh giá giả.

## 11. Toàn bộ package runtime

48 package được resolver/cài, cộng pip có sẵn trong venv mới. Inventory đo thực tế; lock URL+hash đầy đủ nằm local như mục 7.

| Package | Version |
|---|---|
| Jinja2 | 3.1.6 |
| MarkupSafe | 3.0.4 |
| PyYAML | 6.0.3 |
| Pygments | 2.21.0 |
| attrs | 26.1.0 |
| certifi | 2026.10.23 |
| charset-normalizer | 3.5.2 |
| cloudpickle | 3.1.2 |
| filelock | 4.2.10 |
| fsspec | 2026.9.0 |
| hf-xet | 1.8.0 |
| huggingface-hub | 0.36.0 |
| idna | 3.20 |
| iniconfig | 2.3.1 |
| joblib | 1.6.0 |
| jsonschema | 4.26.0 |
| jsonschema-specifications | 2025.9.1 |
| mpmath | 1.3.0 |
| narwhals | 2.28.0 |
| networkx | 3.7 |
| numpy | 2.5.4 |
| packaging | 26.3 |
| pgvector | 0.4.1 |
| pillow | 13.0.0 |
| pip | 24.0 |
| pluggy | 1.7.0 |
| psycopg | 3.3.8 |
| psycopg-binary | 3.3.8 |
| pypdf | 6.21.4 |
| pytest | 9.2.0 |
| python-dotenv | 1.2.4 |
| referencing | 0.37.0 |
| regex | 2026.11.9 |
| requests | 2.34.2 |
| rpds-py | 2026.9.1 |
| safetensors | 0.8.0 |
| scikit-learn | 1.9.1 |
| scipy | 1.18.1 |
| sentence-transformers | 5.1.2 |
| sentencepiece | 0.2.1 |
| setuptools | 84.2.1 |
| sympy | 1.14.0 |
| threadpoolctl | 3.8.0 |
| tokenizers | 0.22.1 |
| torch | 2.9.1+cpu |
| tqdm | 4.70.1 |
| transformers | 4.57.1 |
| typing_extensions | 4.16.0 |
| urllib3 | 2.8.0 |

## Nguồn đối chiếu

- [Model card chính thức](https://huggingface.co/intfloat/multilingual-e5-small) và [lịch sử revision](https://huggingface.co/intfloat/multilingual-e5-small/commits/main).
- [API revision cố định](https://huggingface.co/api/models/intfloat/multilingual-e5-small/revision/fd1525a9fd15316a2d503bf26ab031a61d056e98).
- [Tokenizer config snapshot](https://huggingface.co/intfloat/multilingual-e5-small/resolve/fd1525a9fd15316a2d503bf26ab031a61d056e98/tokenizer_config.json), [ST config snapshot](https://huggingface.co/intfloat/multilingual-e5-small/resolve/fd1525a9fd15316a2d503bf26ab031a61d056e98/sentence_bert_config.json), [model config snapshot](https://huggingface.co/intfloat/multilingual-e5-small/resolve/fd1525a9fd15316a2d503bf26ab031a61d056e98/config.json), [modules](https://huggingface.co/intfloat/multilingual-e5-small/resolve/fd1525a9fd15316a2d503bf26ab031a61d056e98/modules.json), [pooling](https://huggingface.co/intfloat/multilingual-e5-small/resolve/fd1525a9fd15316a2d503bf26ab031a61d056e98/1_Pooling/config.json).
- Metadata PyPI: [ST 5.1.2](https://pypi.org/pypi/sentence-transformers/5.1.2/json), [Transformers 4.57.1](https://pypi.org/pypi/transformers/4.57.1/json), [torch 2.9.1](https://pypi.org/pypi/torch/2.9.1/json), [tokenizers 0.22.1](https://pypi.org/pypi/tokenizers/0.22.1/json), [hub 0.36.0](https://pypi.org/pypi/huggingface-hub/0.36.0/json), [pgvector adapter 0.4.1](https://pypi.org/pypi/pgvector/0.4.1/json), [sentencepiece 0.2.1](https://pypi.org/pypi/sentencepiece/0.2.1/json).
- [PyTorch CPU installation](https://pytorch.org/get-started/previous-versions/) và [pgvector 0.8.7](https://github.com/pgvector/pgvector/blob/v0.8.7/README.md).
