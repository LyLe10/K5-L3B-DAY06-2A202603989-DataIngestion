# Checkpoint 4.2 — Schema & Migration Review

Ngày kiểm tra: 2026-11-14. **Hoàn tất phần chuẩn bị offline; chưa áp dụng DDL.**

Thiết kế chi tiết: [docs/schema_migration.md](../docs/schema_migration.md). Kế thừa plan Stage 4 và Checkpoint 4.1 đã nghiệm thu, nhưng phạm vi lượt này chỉ là schema/migration/contracts/unit tests; không triển khai embedding adapter, encode, ingest hoặc search.

## 1. Trạng thái thực tế trước và sau

- HEAD giữ `3996c7566f36d5951c311779e29905132580aee8`.
- Ref local origin/main giữ `9a2964e037716e1179d845ec8e5c21675c90a2e0` (`Rename`); branch main đang behind 1. Không fetch/pull/rebase/merge/reset, commit hoặc push.
- Không staged, không tracked modified phía Windows. Các thay đổi chuẩn bị đều là file mới, chưa stage. Diff mmap giả của init.sql phía WSL là vấn đề đã ghi nhận trước đó, không sửa trong lượt này.
- Truy vấn PostgreSQL chỉ dùng BEGIN READ ONLY/SELECT/ROLLBACK: database day6_lab, PostgreSQL 16.16, public.vector 0.8.7. Schema day6_ingestion không tồn tại ở cả đầu và cuối kiểm tra.
- Đã xác nhận hàm public.vector_norm(vector) và pg_catalog.sha256(bytea) có sẵn. Không cài extension hoặc package.

## 2. Schema đề xuất

| Đối tượng | Vai trò và guard chính |
|---|---|
| schema_migrations | Version/name/checksum/catalog fingerprint; lịch sử bất biến |
| embedding_profiles | Config canonical + JSONB; profile_id content-addressed, 384 chiều, immutable UPDATE/DELETE/TRUNCATE |
| strategy_snapshots | Một current snapshot mỗi dataset/profile/A-or-B; manifest/corpus/chunkset hashes, snapshot_id, counts, page count, chunking config, completion state |
| chunks | PK(dataset_id,profile_id,strategy,chunk_id), embedding public.vector(384), text/provenance/metadata/checksums/offsets |
| compatible_snapshots | Chỉ ghép A/B complete cùng corpus/manifest/profile/dataset/số trang; C đọc B |

- Composite FK ngăn chunk tham chiếu sai namespace hoặc snapshot/manifest/corpus. FK và completion triggers deferred để full-snapshot sync có thể thực hiện trong một transaction.
- Kiểm tra complete tại commit: số hàng và số trang thực khớp ledger; chunking config đúng baseline. Trạng thái syncing không được tồn tại sau commit.
- Khóa advisory transaction theo namespace, chặn đổi namespace/chunk ID. Profile/migration ledger bất biến; không có tác vụ xóa profile hoặc toàn snapshot trong v1.
- B-tree cho section và document/page trong namespace; chưa ANN. Vector norm tolerance 1e-5, dimension 384, text/offset/page/JSONB constraints.
- Tách chunk text_sha256 với page_text_sha256; metadata.text_sha256 vẫn là checksum cả trang. Không thay metadata baseline để phù hợp DB.
- Profile canonicalization, corpus/chunkset digest computation và typed metadata mapping có hợp đồng rõ trong thiết kế; adapter ingest chưa được viết. DB không tự hash PDF hoặc tự kiểm chứng cấu hình Python canonical JSON.

## 3. Migration review

- SQL: [0001_day6_ingestion.sql](../starter/migrations/0001_day6_ingestion.sql).
- Registry: [manifest.json](../starter/migrations/manifest.json), version **1**.
- SHA-256 SQL bytes UTF-8 LF:

```text
7fc18ceaf9342501cfff7b844df1532998ba3b0e2067d575399d11dadc8fcddc
```

Migration chỉ tạo mới trong day6_ingestion và ghi một row ledger mới sau DDL; không DROP/ALTER/TRUNCATE schema/database/tables, không sửa public hoặc bảng khác. Có transaction lock, timeout và preconditions database/version/extension/checksum.

Tính idempotent: replay đã được review chỉ no-op khi version/name/checksum/history và catalog fingerprint khớp; schema lạ/drift/history khác thì dừng. Không dùng IF NOT EXISTS để bỏ qua sai khác schema. Cần caller quản lý một transaction và set_config(..., true) checksum đã xác minh; không nhúng checksum tự tham chiếu vào SQL.

`starter/src/schema.py` chỉ là code pure/offline: loader xác minh registry/hash, planner history, immutable profile, namespace, filter input và snapshot compatibility. Không import driver, kết nối hoặc thực thi SQL. Store/model/ingestion/chunking/run API hiện tại giữ nguyên; `PgVectorStore.create_schema()` chưa nối migration runner.

CLI đã chạy:

```text
python -B starter/scripts/plan_schema.py
mode: offline-review-only
database_connected: false
ddl_executed: false
```

Không có --apply; truyền --apply bị từ chối.

## 4. Unit tests và kết quả

Lệnh cuối cùng dùng baseline venv, không ghi cache vào data/local:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
```

**146 passed, 12 subtests passed in 24.22s; 0 fail, 0 skip/error.** Gồm 64 test case mới và 82 test baseline.

Phạm vi mới:

- Profile canonical hash ổn định, frozen/detached config, immutable conflict, version/artifact/tokenizer/prefix/dimension/dtype/config sai bị chặn.
- 8 namespace dataset/profile/strategy phân biệt; lock key signed deterministic; C→B; identifier sai và filter key/type sai bị chặn, filter value giữ dưới dạng bind data.
- A/B khác chunkset/count vẫn hợp lệ nếu cùng corpus/profile; khác namespace/manifest/corpus/page count/trạng thái bị chặn. Snapshot identity không phụ thuộc counters/time mutable.
- Loader phát hiện SQL bị sửa, CRLF/BOM, thiếu/file lạ, path escape, checksum sai, version/history không biết. Planning replay khớp trả rỗng; schema tồn tại thiếu catalog evidence bị chặn.
- Static SQL contract checks cho phạm vi schema, PK/FK namespace, dimension, checksum/metadata mapping và commit guards; CLI chỉ in inventory.

Lượt đầu có một test fail do regex test tên bảng bỏ sót chữ số 6; đã sửa test và chạy lại toàn bộ suite đạt kết quả trên. Không sửa baseline để làm test qua.

**Giới hạn:** unit/static checks không chạy PostgreSQL DDL, không chứng minh parser/trigger/FK/transaction isolation đã hoạt động trên server. Chưa có integration DDL hoặc kết quả embedding/retrieval. Không báo unit PASS thành migration đã triển khai.

## 5. Tính toàn vẹn

- 64 file được bảo vệ giữ nguyên SHA-256: 54 tracked, 7 untracked local cũ, embedding_preflight.md, .git/config và .git/index.
- Inventory data/local gồm **26.453 file** giữ nguyên: tên/size/mtime; không thêm/sửa/xóa file tại đó. Đây là inventory metadata, không phải tuyên bố đã hash lại toàn bộ weights/venv.
- Tests baseline đọc corpus thật; không thay PDF, normalized text, manifest, chunk IDs/text/metadata. Không cài dependency, load model, encode hoặc ghi vector trong lượt này.

## 6. Danh sách file mới

1. docs/schema_migration.md — thiết kế và quy trình review/apply tương lai.
2. starter/migrations/0001_day6_ingestion.sql — migration body, chưa chạy.
3. starter/migrations/manifest.json — version/name/SHA-256.
4. starter/src/schema.py — pure contracts và offline planning.
5. starter/scripts/plan_schema.py — CLI chỉ đọc migration files, không DB.
6. starter/tests/test_schema.py — unit/static contract tests.
7. results/schema_migration.md — báo cáo này.

Không sửa 7 file untracked đã giữ local, preflight report, store.py/models.py/embeddings.py hoặc public API giai đoạn 3.

## 7. Rủi ro và phê duyệt trước DDL thật

1. Review SQL, checksum registry, schema/config v1 và transaction contract. Sau áp dụng, SQL version 1 phải bất biến; thay đổi cần migration mới.
2. Phê duyệt một môi trường PostgreSQL cô lập có database tên day6_lab, PostgreSQL 16/public.vector 0.8.7 để chạy first-apply/replay, rollback, drift/checksum mismatch, profile immutability, deferred constraints, concurrency và namespace tests. Không dùng DB hiện tại làm fixture cho destructive cases.
3. Sau integration, review kết quả và phê duyệt riêng apply trên day6_lab hiện tại: kiểm tra lại schema vẫn vắng, quyền, backup, timeout và checksum. Nếu đã tồn tại hoặc có nguy cơ ảnh hưởng dữ liệu khác, dừng; không tự sửa hoặc migrate tiếp.
4. Deferred completion triggers quét namespace cho từng row event, chi phí có thể bậc hai; cần đo tại 510 rows. Chưa có performance claim.
5. Catalog fingerprint không hash dữ liệu/grants và không chống superuser can thiệp. Logical namespace không thay RLS. Không tự thêm quyền/RLS trong migration này.
6. Cần quyết định Git riêng nếu muốn đồng bộ commit rename từ origin/main; lượt này giữ nguyên trạng thái behind 1.

**Điểm dừng hiện tại:** chỉ chuẩn bị để người dùng review. Chưa DDL, chưa profile/chunk INSERT, chưa encode/ingest và chưa commit/push.
