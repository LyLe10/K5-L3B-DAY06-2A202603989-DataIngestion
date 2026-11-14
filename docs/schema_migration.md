# Checkpoint 4.2 — PostgreSQL Schema & Migration

## Trạng thái thực hiện (cập nhật sau Checkpoint 4.3C-2)

Migration 0001 đã áp dụng thành công trên day6_lab; kiểm thử cô lập đạt 55/55. Embedding và ingestion A/B đã hoàn thành: 1 profile, 2 complete snapshots, 510 chunks (A=246, B=264); C dùng lại B. Retrieval và benchmark chưa triển khai.

Các đoạn bên dưới mô tả thiết kế và phạm vi tại thời điểm chuẩn bị Checkpoint 4.2; câu “chưa áp dụng DDL” là trạng thái lịch sử, không phải trạng thái database hiện tại. Xem results/schema_apply.md và results/full_corpus_apply.md. Không sửa SQL hoặc checksum sau khi áp dụng.

Hướng dẫn tái lập môi trường: [stage4_reproduction.md](stage4_reproduction.md).

Trạng thái: **chuẩn bị để review, chưa áp dụng DDL**. Thiết kế kế thừa `stage4_embedding_pgvector_plan.md` và kết quả 4.1. Phạm vi 4.2 hiện tại chỉ là schema/migration/contracts/tests; adapter embedding, encode, upsert và retrieval chưa triển khai.

## Namespace và bảng

Schema cố định `day6_ingestion`; database `day6_lab`, PostgreSQL 16 UTF8, extension `public.vector` 0.8.7 phải có sẵn. Migration không cài/nâng extension, không sửa đối tượng ngoài schema và không DROP/ALTER/TRUNCATE dữ liệu.

| Đối tượng | Khóa và nội dung |
|---|---|
| schema_migrations | PK version; name UNIQUE; SHA-256 file SQL, catalog fingerprint, applied_at |
| embedding_profiles | PK profile_id; model_name, revision, dimensions=384, config_canonical, config JSONB, created_at |
| strategy_snapshots | PK (dataset_id, profile_id, strategy); snapshot_id, manifest/corpus/chunkset hashes, chunking config, số trang, expected/actual count, status, completed_at |
| chunks | PK (dataset_id, profile_id, strategy, chunk_id); snapshot identity, provenance, text/checksums, offsets, metadata JSONB và embedding vector(384) NOT NULL |
| compatible_snapshots | View ghép A/B complete cùng dataset/profile/manifest/corpus/số trang; không tạo dữ liệu C |

Dataset ID v1 là 1–128 ký tự `[a-z0-9_.-]`, bắt đầu bằng chữ/số; mặc định dự kiến `day06-postgresql`. Profile ID là SHA-256 chữ thường. Chỉ strategy A/B được lưu; C được ánh xạ B tại hợp đồng retrieval. Đây là logical namespace isolation qua PK/FK/WHERE và khóa transaction, **không phải RLS hoặc cam kết bảo mật multi-tenant**.

## Profile bất biến

`EmbeddingProfile.from_config()` kiểm tra rồi serialize UTF-8 JSON: sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False. profile_id=SHA256(config_canonical). Dataclass frozen chỉ giữ string; property config trả bản sao mới, không lộ dict mutable.

Config schema v1 yêu cầu đúng các khóa: profile_schema_version, model_name, revision, dimensions, dtype, pooling, normalize_embeddings, document_prefix, query_prefix, tokenizer, max_seq_length, artifact_sha256, library_versions, device, backend, trust_remote_code và pooling_include_prompt.

- CPU/torch/float32, 384 chiều, mean pooling/include_prompt=True, Normalize=True; passage/query prefix đúng và giới hạn 512.
- Revision model đầy đủ 40 hex; tokenizer cùng tên/revision, fast=True, class được ghi rõ, model_max_length=512.
- Artifact checksums và library versions không rỗng; không dùng main trôi nổi, UUID hoặc Python hash(). Các artifact/version thực của 4.1 sẽ được đưa vào profile lúc có adapter được duyệt, chưa INSERT profile trong 4.2.
- DB CHECK xác minh hash trên config_canonical, JSON tương đương và các cột/config chính nhất quán. Canonical serialization và kiểm tra từng artifact/version là trách nhiệm Python trước INSERT; DB không tự tái tạo chuẩn canonical JSON Python.
- Trigger chặn UPDATE/DELETE/TRUNCATE profile; thay config tạo profile_id mới, không update profile cũ. Conflict phải kiểm tra config, không dùng ON CONFLICT DO UPDATE cho profile. Không có tác vụ xóa profile v1.

## Traceability của chunks

Giữ nguyên `DocumentPage`, `Chunk` và public API giai đoạn 3. `page` ánh xạ `physical_page` integer>0; printed_page_label nullable, không suy đoán. Source PDF checksum lấy từ manifest, không tự tạo metadata mới trong chunk baseline.

- `text_sha256`: SHA-256 UTF-8 của **chunk.text**, DB tính lại để kiểm tra.
- `page_text_sha256`: checksum text chuẩn hóa của **cả trang**, phải bằng metadata.text_sha256. Không đánh đồng hai checksum.
- `normalized_char_count`: số ký tự của trang, không phải độ dài chunk.
- `start_char/end_char`: khoảng `[start,end)`, `end-start=char_length(text)`, end không vượt độ dài trang; chunk text 1–500 ký tự.
- Metadata phải là object, giữ source_id/page_id/physical_page/printed_page_label/section/section_evidence/version/normalized_char_count/text_sha256/extraction_status và `_chunking` đầy đủ. CHECK dùng IS TRUE để thiếu khóa hoặc NULL không vượt qua ràng buộc; version/printed label có thể là JSON null theo provenance.
- Baseline config A={size:500,overlap:50}, B={max_size:500}, algorithm_version=1, unit=characters. Khi hoàn tất snapshot, `_chunking` trừ offsets/split flag phải bằng config ledger. Không thay thuật toán trong migration.
- Vector type cố định 384 chiều; pgvector loại phần tử NaN/Infinity, CHECK norm gần 1 với tolerance 1e-5. Adapter tương lai vẫn phải kiểm tra số lượng/thứ tự/finite/norm sau chuyển float32; chưa encode để chứng minh numeric output.

## Snapshot ledger và consistency

`corpus_sha256` sẽ hash canonical descriptor các trang được chọn, sắp theo document_id/physical_page; mỗi phần tử gồm source PDF hash, page_id, page text hash, page label và metadata được kiểm chứng. Không chỉ hash số trang hoặc tên tài liệu.

`chunkset_sha256` sẽ hash danh sách canonical sắp theo chunk_id gồm ID, text checksum và metadata đầy đủ. A/B có chunkset khác nhau là bình thường. `snapshot_id` hash namespace + manifest/corpus/chunkset hashes + selected_page_count/expected_count; loại actual_count/status/time vì đó là trạng thái đồng bộ.

Các digest này là hợp đồng ứng dụng (module Snapshot hiện cung cấp content identity); chưa có adapter tính descriptor từ corpus hoặc ingest. DB kiểm tra format và các FK/constraints, không tự tính lại corpus/chunkset SHA từ PDF/chunks. Trước khi ingest phải đối chiếu descriptor/digest thật với baseline.

Composite FK của chunks gồm dataset/profile/strategy/snapshot_id/manifest_sha256/corpus_sha256. FK deferred bảo đảm cập nhật snapshot và thay rows trong một transaction, không để hàng cũ mang snapshot khác tồn tại tại commit.

Commit contract:

1. Encode/validate toàn snapshot bên ngoài transaction sau một phê duyệt riêng. Reject empty/duplicate/missing pages/profile mismatch trước ghi.
2. Bắt đầu transaction; khóa namespace theo SHA256 của `day6_ingestion:sync:<dataset>:<profile>:<strategy>`, lấy 8 byte đầu signed big-endian. Dataset không chứa dấu `:` nên không nhập nhằng. SQL và Python cùng định nghĩa này; không dùng hash() ngẫu nhiên. Va chạm 64 bit chỉ làm serialize thêm, không thay namespace trong WHERE/FK.
3. Ledger chuyển `syncing`, completed_at=NULL; upsert full snapshot, xóa stale đúng namespace; hoàn tất ledger thành complete với counts/hash đã xác minh. Không update timestamp nếu snapshot không đổi.
4. BEFORE triggers khóa transaction cho mọi mutation chunks/ledger và chặn đổi namespace/ID. INSERT/UPDATE/DELETE cần đúng namespace; v1 không hỗ trợ xóa toàn ledger hoặc TRUNCATE.
5. Deferred constraint triggers từ cả ledger và chunks bắt buộc complete tại ranh giới constraint, count thực=expected=actual, số trang distinct khớp và chunking config đúng. Lỗi rollback toàn transaction, trạng thái cũ vẫn còn. `SET CONSTRAINTS ... IMMEDIATE` sớm sẽ kiểm tra ngay và có thể fail khi đang syncing.

Mỗi strategy một transaction; sau khi A cập nhật mà B chưa cập nhật, view/`require_compatible()` chặn so sánh nếu khác corpus snapshot/profile. Retrieval/benchmark tương lai bắt buộc kiểm tra view trong cùng read transaction/snapshot; view không tự ngăn người dùng SQL tùy ý bỏ qua guard. A/B có thể có counts khác nhau (246/264); không bắt hai counts bằng nhau. C dùng snapshot B.

## Indexes và transaction migration

Ngoài indexes PK/UNIQUE/FK parent: B-tree `chunks_section_idx(dataset_id,profile_id,strategy,section)` và `chunks_page_idx(dataset_id,profile_id,strategy,document_id,physical_page)`. Chưa tạo HNSW/IVFFlat/GIN; retrieval dự kiến exact cosine, section equality tham số hóa trước xếp hạng. Allowlist chỉ section; khóa/kiểu sai bị từ chối, không âm thầm bỏ filter. Không lọc từ gold answer/source.

Migration file dùng LF UTF-8 không BOM. `starter/migrations/manifest.json` khóa version/name/SHA-256 **byte thực**, không tự chuẩn hóa trước hash. Chỉnh SQL đã áp dụng phải tạo version mới; không cập nhật checksum lịch sử để che sửa đổi.

`load_migrations()` chặn checksum sai, CRLF/BOM, path escape, thiếu file, file SQL ngoài registry, version không liên tiếp hoặc history không biết. `plan_migrations()` chỉ quyết định offline, không kết nối DB. Schema đang tồn tại mà thiếu history/catalog evidence sẽ fail closed.

File SQL chỉ là body của một transaction do runner tương lai quản lý. Sau khi có phê duyệt thật, trình tự cần review là:

1. Kiểm tra lại database/version/extension/schema/history/quyền, snapshot/backup trước thay đổi. Nếu schema đã tồn tại ngoài trạng thái đã review: **dừng**, không sửa chữa tự động.
2. Mở một transaction; đặt checksum đã được loader xác minh bằng `set_config('day6_ingestion.migration_checksum', checksum, true)` tham số hóa. Không ghi setting vĩnh viễn. Không nhúng checksum của file vào chính file để tránh tự tham chiếu.
3. Thực thi body: lock_timeout=5s, statement_timeout=30s, advisory transaction lock cố định 6753728366513601. DDL và một migration ledger row mới nằm trong cùng transaction. Không encode hoặc ingest profile/chunk rows.
4. Lần đầu tạo schema mới cùng các bảng/function/trigger/view/index. Không CREATE EXTENSION hoặc sửa public.vector. SQL cố ý không dùng CREATE TABLE IF NOT EXISTS để che sai schema.
5. Replay đã được review: version/name/checksum/history phải khớp hoàn toàn, catalog fingerprint khớp; trả về không chạy DDL/DML. Schema lạ, drift hoặc version khác thì exception. Fingerprint lấy columns/defaults/types, constraints, indexes, functions, triggers/enabled và views trong namespace; không hash rows hay grants, không chống superuser cố ý can thiệp.
6. Kiểm tra catalog và bảng rỗng, COMMIT nếu đạt; mọi lỗi ROLLBACK. Không có down migration DROP; rollback trước commit hoặc forward migration được review sau commit.

`PgVectorStore.create_schema()` chưa nối vào runner, constructor/upsert/search còn TODO. Không có công cụ apply trong checkpoint này; `plan_schema.py` chỉ in inventory, không nhận --apply.

## Kiểm thử và các điểm chưa được chứng minh

Unit tests dùng fixtures cấu hình/history/temp files độc lập, không phải dữ liệu corpus hoặc kết quả embedding giả. Kiểm tra profile hash/immutability/provenance, namespace & C→B, filter allowlist, compatibility gate, snapshot identity/counts, migration tampering/history/idempotent planning và các điều kiện SQL trọng yếu.

Không thực thi SQL trong unit tests; static SQL contract checks không thay PostgreSQL parser hoặc integration. Cần phê duyệt riêng để kiểm tra trên môi trường DB cô lập trước rollout: first apply/replay, catalog drift, checksum mismatch, rollback DDL, concurrent migration locks, immutable profile, deferred FK/count checks, stale deletion, namespace isolation và so sánh norm tolerance.

Deferred count triggers hiện quét namespace sau mỗi row event tại commit (tối đa cỡ 510 rows của lab); cần đo chi phí trong integration, chưa tuyên bố hiệu năng. Chuẩn canonical profile và digest corpus/chunkset phải có test end-to-end trước ingest. Không diễn giải unit PASS thành migration PostgreSQL đã áp dụng thành công.

## Nguồn

- [PostgreSQL 16 constraints](https://www.postgresql.org/docs/16/ddl-constraints.html).
- [Transaction advisory locks](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS).
- [Built-in SHA-256 trên bytea](https://www.postgresql.org/docs/16/functions-binarystring.html).
- [pgvector 0.8.7](https://github.com/pgvector/pgvector/blob/v0.8.7/README.md).
