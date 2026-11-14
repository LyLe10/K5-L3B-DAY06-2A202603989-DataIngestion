# Migration 0001 — APPLY: SUCCESS

Đã áp dụng duy nhất bản SQL được duyệt lên database chính; không sửa chữa SQL, retry, DROP/ALTER, reset database/volume, encode hoặc ingest embedding. Đã dừng trước Checkpoint 4.3.

## Precheck — PASS

- DATABASE_URL được xác minh thực bằng psycopg, không công khai mật khẩu: `127.0.0.1:55433`, database `day6_lab`, user `day6`.
- PostgreSQL **16.16**, UTF8, extension `public.vector` **0.8.7**.
- Cluster ID **7707847059457269799**; đối chiếu lại qua psql trước ghi và trong write transaction.
- Trước ghi, schema `day6_ingestion` không tồn tại; không có bảng migration; quyền CREATE đủ.
- Loader xác minh registry version 1; SQL SHA-256 tính từ bytes file và khớp chính xác checksum/evidence bản **55 PASS / 0 FAIL / 0 BLOCKED**:

```text
04f891492379e9800dd023d604b61e9bd7a60d40e48a1179dd4d6840633166e6
```

Không sửa migration SQL hoặc registry trong lượt apply.

## Transaction và pre-COMMIT — PASS

Runner `starter/scripts/apply_migration_0001.py` dùng cùng Docker/psql executable, flags `-X -q -A -t -v ON_ERROR_STOP=1 -v VERBOSITY=verbose` và cơ chế SQL qua stdin như integration harness; chỉ đổi endpoint sang container chính đã được duyệt. Không gọi fixture hoặc đường chạy integration test trên database chính.

Transaction contract giữ nguyên: **BEGIN → set_config(checksum, true) → nguyên migration → kiểm tra catalog → COMMIT**. Có kiểm tra identity/schema trong transaction; kiểm tra sau migration chỉ SELECT/RAISE, không SQL sửa chữa. Advisory transaction lock **6753728366513601**, lock timeout **5s**, statement timeout **30s** do nguyên migration thiết lập.

Trước COMMIT đã xác nhận:

- Schema và tên 4 bảng/1 view/5 hàm đúng thiết kế; đủ 10 user trigger và 8 index.
- Ledger đúng một dòng, version/name/checksum chính xác; catalog fingerprint khớp giá trị ghi trong ledger.
- Mọi constraint được validate, mọi index valid/ready; `embedding` có type `public.vector`, typmod 384 và NOT NULL.
- `embedding_profiles=0`, `strategy_snapshots=0`, `chunks=0`.
- Fingerprint catalog ngoài schema bằng giá trị trước migration.

Nếu kiểm tra trên thất bại, ON_ERROR_STOP sẽ đóng kết nối mà không COMMIT và transaction chưa commit được rollback; không có nhánh retry hoặc repair. Thực tế không xảy ra lỗi/rollback.

**COMMIT thành công, SQLSTATE 00000, transaction ID 745.**

| Mốc | Timestamp UTC |
|---|---|
| Bắt đầu orchestration | 2026-11-14 07:05:53.416742 |
| Bắt đầu write call | 2026-11-14 07:05:59.514924 |
| Ledger applied_at / transaction_timestamp | 2026-11-14 07:05:59.656279 |
| Client xác nhận COMMIT | 2026-11-14 07:05:59.919144 |
| Hoàn tất hậu kiểm/integrity | 2026-11-14 07:06:05.981273 |

## Post-COMMIT — PASS

Mở process psql/kết nối PostgreSQL **mới**, chạy trong **BEGIN READ ONLY** rồi ROLLBACK transaction đọc. Đã chạy lại các validation catalog, đọc identity/ledger/counts và so sánh toàn bộ catalog snapshot trước COMMIT với hậu kiểm: khớp. Đúng cluster/versions/database; schema và objects đã lưu qua ranh giới kết nối/transaction.

Ledger duy nhất:

| version | name | applied_at UTC |
|---:|---|---|
| 1 | 0001_day6_ingestion.sql | 2026-11-14 07:05:59.656279 |

Checksum SQL như trên. Catalog fingerprint thực tế, khớp ledger và hậu kiểm:

```text
209b3597e6f2a6ff8cf13f4c12f5cfc45f3bb34c07f9ff363204902323a2da55
```

Fingerprint catalog bên ngoài `day6_ingestion` trước/sau giữ nguyên:

```text
08cb19f8d3ec7163304728e3af473001158efdceeb83f7ebb29fbbfb1741cf40
```

Fingerprint ngoài schema là kiểm tra catalog namespace/extension/function/relation, không phải checksum toàn bộ database hoặc dữ liệu hệ thống. Trước apply không có bảng ứng dụng; SQL được duyệt chỉ tạo objects trong schema mới và INSERT một dòng ledger.

## Objects thực tế

Schema: **day6_ingestion**. Tất cả objects dưới đây thuộc schema này.

| Loại | Tên |
|---|---|
| 4 bảng | chunks, embedding_profiles, schema_migrations, strategy_snapshots |
| 1 view | compatible_snapshots |
| 5 hàm | assert_snapshot_complete, catalog_fingerprint, guard_namespace, namespace_lock_key, reject_mutation |

| Trigger | Bảng |
|---|---|
| chunks_complete | chunks |
| chunks_namespace | chunks |
| chunks_no_truncate | chunks |
| migrations_immutable | schema_migrations |
| migrations_no_truncate | schema_migrations |
| profiles_immutable | embedding_profiles |
| profiles_no_truncate | embedding_profiles |
| snapshots_complete | strategy_snapshots |
| snapshots_namespace | strategy_snapshots |
| snapshots_no_truncate | strategy_snapshots |

| Index | Bảng |
|---|---|
| chunks_page_idx | chunks |
| chunks_pkey | chunks |
| chunks_section_idx | chunks |
| embedding_profiles_pkey | embedding_profiles |
| schema_migrations_name_key | schema_migrations |
| schema_migrations_pkey | schema_migrations |
| strategy_snapshots_dataset_id_profile_id_strategy_snapshot__key | strategy_snapshots |
| strategy_snapshots_pkey | strategy_snapshots |

Sau COMMIT: **embedding_profiles=0, strategy_snapshots=0, chunks=0**. Chưa có corpus/vector/profile/snapshot được ingest.

## Git và baseline — PASS

- Tracked diff và cached diff rỗng; branch main vẫn behind origin/main một commit. HEAD `3996c7566f36d5951c311779e29905132580aee8`, origin/main `9a2964e037716e1179d845ec8e5c21675c90a2e0`.
- 71 file được đối chiếu checksum trước/sau orchestration (70 file trước lượt này và runner mới) giữ nguyên. Inventory data/local gồm **26.453 file** giữ nguyên tên/size/mtime; không tuyên bố hash lại toàn bộ venv/model weights.
- Đọc lại corpus và tạo chunks trong bộ nhớ: **40 trang, 103371 ký tự, A=246, B=264, C cùng list B**; coverage A/B **103371/103371**, không lỗi. So sánh toàn bộ chunk dataclass với JSONL snapshot: ID/text/metadata/provenance khớp. Không ghi lại corpus hoặc chunk files.
- Không pull/rebase/stage/commit/push. Không cài dependency, load/encode model hoặc ghi vector.
- Lượt này thêm 3 file untracked: `starter/scripts/apply_migration_0001.py`, `results/schema_apply.json`, `results/schema_apply.md`. Các file local được bảo vệ giữ nguyên. Không chạy lại pytest vì source/baseline/dependencies không thay đổi; lượt trước đạt 146 tests và 12 subtests, lượt này xác minh trực tiếp catalog production và corpus/chunk integrity.

Evidence máy đọc: [schema_apply.json](schema_apply.json), chứa stdout/stderr, SQLSTATE, pre/post catalog, ledger, identity, timestamps và integrity snapshots. Runner sẽ từ chối chạy lại khi schema đã tồn tại; không thực thi lại để kiểm thử cơ chế này trên database chính.

**Điểm dừng: APPLY SUCCESS; chờ nghiệm thu trước Checkpoint 4.3 — Embedding & Ingestion.**
