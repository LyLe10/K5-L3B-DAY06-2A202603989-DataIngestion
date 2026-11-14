# Checkpoint 4.2 — Kiểm thử migration sau bản sửa được duyệt

**Kết quả migration: 55 PASS / 0 FAIL / 0 BLOCKED.** Toàn bộ pytest: **146 passed, 12 subtests passed in 31.09s**, không fail/skip. Chưa áp dụng DDL lên database chính.

## Bản sửa và checksum

Lượt trước thất bại với SQLSTATE 42725 tại phép nối `text || "char"`. Theo phê duyệt, lần này chỉ sửa một biểu thức SQL thành `t.tgenabled::text` và cập nhật checksum trong registry. Không đổi version 1, filename hoặc các trường khác của registry; không sửa thêm migration.

SHA-256 được tính trực tiếp từ bytes của file SQL **sau khi ghi bản sửa**, không lấy giá trị trong diff làm checksum đầu vào. Sau đó đọc lại cả SQL/registry để kiểm tra; loader `load_migrations()` và pytest cùng xác minh lại:

```text
04f891492379e9800dd023d604b61e9bd7a60d40e48a1179dd4d6840633166e6
```

Diff thực tế hai file: [schema_integration.final.diff](schema_integration.final.diff). `schema_integration.proposed.diff` giữ nguyên để lưu đề xuất đã được duyệt. Báo cáo chuẩn bị `schema_migration.md` là snapshot lịch sử trước lần sửa này; registry và báo cáo hiện tại ghi checksum mới.

## Môi trường cô lập và an toàn database

- Container: `day6-cp42-isolated-20261114`, ID `db8169bc01a5c41c8d0a0a323e04cc321be7277b55cc42eb44db5cb247e3bc5a`.
- Image đã có sẵn `pgvector/pgvector:0.8.7-pg16`, ID `sha256:484e838076e04939d27d3e176e91c86eea96236126023be8d3059761122e579f`.
- Runtime xác nhận PostgreSQL **16.16**, `server_version_num=160016`, pgvector **0.8.7**.
- Không network, không published port, không mount/volume dữ liệu chính. PGDATA là tmpfs riêng và được khởi tạo mới khi restart container; xác nhận schema thử nghiệm vắng trước chạy.
- Database thử nghiệm bên trong container có tên `day6_lab` vì migration có precondition tên này; đây là **cluster/container khác**. Harness xác minh container ID và system identifier khác cluster chính trước khi DDL.
- Không DDL/DML trên database chính tại `day6_student_starter-postgres-1`. Chỉ đọc catalog trong transaction READ ONLY và hash luồng `pg_dump` trước–sau; không lưu nội dung dump.
- Container thử nghiệm đã được dừng sau kiểm thử; fixture trên tmpfs không được giữ lại. Database chính không bị dừng.
- Lượt integration: **2026-11-14 06:40:09–06:40:51 UTC**. Không cài package, tải model, encode hoặc ingest embedding thật.

## Kiểm thử và fixture

Harness `starter/scripts/check_schema_isolated.py` được mở rộng để chạy các ca SQL thật, dừng tại kết quả không đúng kỳ vọng, ghi SQLSTATE/stdout/stderr và checksum SQL từng ca. Harness chỉ nhắm container được kiểm tra label/network/tmpfs, không nhận URL production hoặc fallback sang database chính.

Fixture tổng hợp gồm 2 profile, 6 snapshot hoàn chỉnh, mỗi snapshot 30 trang/30 chunk: tổng cộng 180 hàng chunk. Text, metadata, checksum nguồn và profile là fixture ghi rõ synthetic; vector cơ sở đơn vị 384 chiều chỉ dùng kiểm thử kiểu dữ liệu/norm. Không đọc corpus thật để tạo fixture mutation SQL, không gọi model hoặc tạo embedding từ corpus.

Các nhóm đã đạt:

- First apply, catalog fingerprint, 4 bảng, 1 view và 2 index phụ trợ; replay trước/sau mutation, lịch sử vẫn một migration.
- Thiếu checksum, checksum mismatch, catalog drift bị từ chối; index drift thử nghiệm được rollback.
- Chèn lỗi chia cho 0 sau toàn bộ DDL rồi xác minh schema không tồn tại; rollback mutation cũng khôi phục dữ liệu fixture.
- Profile UPDATE/DELETE/TRUNCATE bị chặn; duplicate và config dimension sai bị từ chối.
- Không cho commit snapshot còn syncing, thiếu chunk hoặc đếm sai; missing profile vi phạm FK.
- Cùng chunk ID ở dataset/profile khác được chấp nhận; duplicate trong cùng namespace bị chặn; không cho đổi namespace/chunk identity.
- View chỉ trả cặp A/B cùng dataset/profile/corpus; cặp khác corpus bị loại. Section filter giới hạn trong namespace trả đúng 15 fixture.
- Text/checksum/page/offset/metadata/norm/dimension sai bị chặn; snapshot FK sai, chunking config sai, xóa gây mất chunk, xóa ledger và TRUNCATE bị chặn.
- Xóa rồi chèn lại chunk trong cùng transaction hợp lệ; lock key SQL khớp Python; cuối lượt vẫn 6 snapshot complete/180 chunk.

SQLSTATE lỗi trong các ca âm tính là **kết quả mong đợi**, không phải lỗi kiểm thử: `P0001` (trigger/precondition), `23505` (unique), `23514` (CHECK), `23503` (FK), `22000` (vector dimension), `22012` (lỗi được cố ý chèn để kiểm tra rollback). Các ca thành công ghi `00000`.

Kết quả này xác minh các ca được liệt kê, chưa phải kiểm thử hiệu năng, cạnh tranh nhiều writer hoặc mọi tổ hợp dữ liệu có thể có. Chưa có adapter ingest/retrieval production.

## Baseline và Git

- **40 trang**, bỏ qua 3.034 trang; **103.371 ký tự**. A=**246**, B=**264**, C dùng chính cùng list B; coverage A/B **103371/103371**, không lỗi.
- So sánh chunk được tạo lại với JSONL local đã duyệt bằng toàn bộ dataclass: **ID, text, provenance và metadata khớp** cho cả A/B. Không ghi lại JSONL hoặc thay đổi corpus.
- 70 file được đối chiếu trước/sau integration; ngoài hai file migration và harness đã được sửa trước khi chạy, không có thay đổi trong lúc kiểm thử. Đối chiếu lại sau pytest/audit cũng giữ nguyên.
- Inventory `data/local/`: **26.453 file**, tên/size/mtime không đổi. Không tuyên bố đã hash lại toàn bộ venv/weights. Corpus được loader kiểm tra checksum và audit lại; 7 file untracked local được bảo vệ vẫn giữ checksum.
- Database chính: catalog và dump trước–sau khớp; SHA-256 dump đã bỏ các dòng điều khiển ngẫu nhiên `\restrict`/`\unrestrict` là `7e0ffac2ba5f815244d5508e4ffa991c70db1b286f45ea46ec270a2153e43195`. Schema `day6_ingestion` trên database chính vẫn vắng.
- HEAD `3996c7566f36d5951c311779e29905132580aee8`, origin/main `9a2964e037716e1179d845ec8e5c21675c90a2e0`, vẫn behind 1. Tracked diff và cached diff rỗng; các file Stage 4 vẫn untracked. Không pull/rebase/stage/commit/push.

## File thay đổi trong lượt này

1. `starter/migrations/0001_day6_ingestion.sql` — ép kiểu tối thiểu đã duyệt.
2. `starter/migrations/manifest.json` — SHA-256 được tính lại, giữ version/name.
3. `starter/scripts/check_schema_isolated.py` — mở rộng harness và fixture SQL tổng hợp.
4. `results/schema_integration.json` — thay evidence lần thất bại bằng kết quả lượt kiểm thử mới, thêm baseline/pytest/integrity.
5. `results/schema_integration.md` — báo cáo hiện tại.
6. `results/schema_integration.final.diff` — file mới, diff thực tế hai thay đổi migration/registry.

Evidence chi tiết: [schema_integration.json](schema_integration.json). Danh sách SQLSTATE từng ca được trích từ evidence ở bảng dưới.

**Điểm dừng:** tất cả ca kiểm thử hiện tại đạt; chờ nghiệm thu và phê duyệt riêng trước khi áp dụng DDL lên database chính.

## Chi tiết 55 ca PostgreSQL

| Ca | Kết quả | SQLSTATE thực tế | SQLSTATE kỳ vọng |
|---|---|---|---|
| isolated_cluster_identity | PASS | `00000` | `00000` |
| empty_isolated_schema | PASS | `00000` | `00000` |
| install_test_extension | PASS | `00000` | `00000` |
| isolated_versions | PASS | `00000` | `00000` |
| missing_checksum | PASS | `P0001` | `P0001` |
| ddl_rollback_injected_error | PASS | `22012` | `22012` |
| ddl_rollback_schema_absent | PASS | `00000` | `00000` |
| first_apply | PASS | `00000` | `00000` |
| catalog_objects | PASS | `00000` | `00000` |
| catalog_fingerprint | PASS | `00000` | `00000` |
| replay | PASS | `00000` | `00000` |
| replay_history_unchanged | PASS | `00000` | `00000` |
| checksum_mismatch | PASS | `P0001` | `P0001` |
| catalog_drift_rejected | PASS | `P0001` | `P0001` |
| catalog_drift_rolled_back | PASS | `00000` | `00000` |
| profiles_insert | PASS | `00000` | `00000` |
| profile_duplicate | PASS | `23505` | `23505` |
| profile_immutable_update | PASS | `P0001` | `P0001` |
| profile_immutable_delete | PASS | `P0001` | `P0001` |
| profile_immutable_truncate | PASS | `P0001` | `P0001` |
| profile_invalid_config | PASS | `23514` | `23514` |
| snapshot_syncing_cannot_commit | PASS | `P0001` | `P0001` |
| snapshot_completion_requires_chunks | PASS | `P0001` | `P0001` |
| snapshot_missing_profile | PASS | `23503` | `23503` |
| snapshot_valid_atomic_fixture | PASS | `00000` | `00000` |
| namespace_isolation_counts | PASS | `00000` | `00000` |
| namespace_shared_ids_allowed | PASS | `00000` | `00000` |
| snapshot_compatible_view | PASS | `00000` | `00000` |
| section_filter_namespace | PASS | `00000` | `00000` |
| chunk_duplicate_same_namespace | PASS | `23505` | `23505` |
| chunk_checksum | PASS | `23514` | `23514` |
| chunk_page_zero | PASS | `23514` | `23514` |
| chunk_offsets | PASS | `23514` | `23514` |
| chunk_empty_text | PASS | `23514` | `23514` |
| chunk_missing_metadata | PASS | `23514` | `23514` |
| chunk_wrong_metadata | PASS | `23514` | `23514` |
| chunk_zero_vector | PASS | `23514` | `23514` |
| chunk_wrong_dimension | PASS | `22000` | `22000` |
| chunk_namespace_update | PASS | `P0001` | `P0001` |
| chunk_identity_update | PASS | `P0001` | `P0001` |
| chunk_wrong_snapshot | PASS | `23503` | `23503` |
| chunk_bad_chunking | PASS | `P0001` | `P0001` |
| chunk_delete_incomplete | PASS | `P0001` | `P0001` |
| snapshot_delete_blocked | PASS | `P0001` | `P0001` |
| snapshot_namespace_update | PASS | `P0001` | `P0001` |
| snapshot_wrong_count | PASS | `P0001` | `P0001` |
| snapshot_strategy_c | PASS | `P0001` | `P0001` |
| migration_history_immutable | PASS | `P0001` | `P0001` |
| chunks_truncate_blocked | PASS | `P0001` | `P0001` |
| atomic_delete_reinsert | PASS | `00000` | `00000` |
| mutation_rollback | PASS | `22012` | `22012` |
| mutation_rollback_preserved | PASS | `00000` | `00000` |
| namespace_lock_key | PASS | `00000` | `00000` |
| final_snapshot_counts | PASS | `00000` | `00000` |
| final_replay_after_mutations | PASS | `00000` | `00000` |
