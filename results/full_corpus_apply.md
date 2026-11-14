# Checkpoint 4.3C-2 — APPLY INGESTION: SUCCESS

Thực hiện ngày 2026-11-14, từ 08:19:30.796453 đến 08:19:40.412335 UTC. Tổng thời gian runner 11.432 giây, gồm corpus/cache precheck và hậu kiểm. Không có lỗi, retry, encode hoặc DDL.

## PRE-APPLY: PASS

- Endpoint lấy từ DATABASE_URL và xác minh: `127.0.0.1:55433`, database `day6_lab`, PostgreSQL 16.16 (`160016`), pgvector 0.8.7, cluster `7707847059457269799`. Không công khai connection string hoặc mật khẩu.
- Migration 0001 SQL được tính lại SHA-256 qua load_migrations, khớp registry và ledger: `04f891492379e9800dd023d604b61e9bd7a60d40e48a1179dd4d6840633166e6`.
- Catalog fingerprint trước/sau khớp: `209b3597e6f2a6ff8cf13f4c12f5cfc45f3bb34c07f9ff363204902323a2da55`.
- Trước ghi: embedding_profiles=0, strategy_snapshots=0, chunks=0.
- Profile canonical configuration được hash lại, đúng ID `528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651`, model `intfloat/multilingual-e5-small`, revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`.
- Loader kiểm tra lại manifest, PDF/source checksum, normalized text và 40 trang; A=246, B=264, mỗi strategy phủ 103371 ký tự. Chunks khớp baseline JSONL cả text, IDs, metadata, thứ tự và offsets.
- Đọc đúng 510 vector từ cache: kiểm tra cache identity/canonical vector SHA-256, khớp 510 receipts, float32, dimension 384, finite và unit norm tolerance 1e-5. Không load/encode model lại, không ghi cache.
- SnapshotContext lấy từ corpus đã xác minh; planned snapshots A/B khớp preflight và cùng corpus/manifest/profile identity.
- Không thấy tiến trình Python ingestion khác trong kiểm tra Windows/WSL; không có client transaction đang hoạt động khác hoặc advisory lock trên database tại precheck. Kiểm tra Windows ban đầu bị sandbox từ chối truy cập CIM, sau đó kiểm tra read-only với quyền thích hợp thành công. Đây là kiểm tra tại thời điểm chạy; khóa namespace trong sync vẫn là cơ chế bảo vệ concurrency.

## INGEST: hai transaction riêng, đều COMMITTED

Chỉ gọi PgVectorStore.sync_snapshot() hiện có, không sửa implementation/SQL/schema. Contract: profile registration bất biến → advisory lock namespace → ledger syncing → conditional upsert → namespace-scoped stale deletion → ledger complete → kiểm tra toàn bộ rows/vectors và deferred constraints → COMMIT.

| Strategy | Rows ghi | Rows xóa | Thời gian gọi sync | Transaction outcome |
|---|---:|---:|---:|---|
| A | 246 | 0 | 1.0831 giây | COMMITTED, hậu kiểm CONFIRMED_COMMITTED |
| B | 264 | 0 | 1.0507 giây | COMMITTED, hậu kiểm CONFIRMED_COMMITTED |
| C | 0 | 0 | Không gọi | Dùng lại B |

- Dataset: `day06-postgresql`; cả hai namespace dùng profile ID nêu trên.
- A snapshot: `d06b89acda8d08a5c423bfb5d4cd82662a962481cd7a2f81b2ab324e08b3e860`.
- B snapshot: `c7d9d92e6695709595d044e5a5a09bb8f91826fb692474c7b1806751015ec1e0`.
- A ledger completed_at: `2026-11-14 08:19:38.099021+00:00`; B: `2026-11-14 08:19:39.163776+00:00`. Đây là transaction_timestamp được contract lưu vào ledger, không phải phép đo chính xác thời điểm COMMIT.

## POST-APPLY: PASS trên kết nối mới, read-only

- embedding_profiles: **1 row**, canonical config đúng profile đã duyệt.
- strategy_snapshots: **2 rows**, A/B đều complete; expected_count=actual_count lần lượt 246/264.
- chunks: **510 rows**, A=246, B=264; không có namespace/row C hoặc rows ngoài dataset/profile/strategy được duyệt.
- Đối chiếu toàn bộ cột của từng row với kế hoạch và cache, gồm text, metadata, offsets, source/text/page checksum, snapshot/manifest/corpus provenance và vector: **khớp chính xác sau float32 round-trip**, đạt yêu cầu tolerance. Không chỉ kiểm tra snapshot ID hoặc row counts.
- Tập IDs khớp hoàn toàn, không thiếu/thừa/stale rows. require_compatible_snapshots() xác nhận hai ledger đã lưu tương thích và snapshot IDs đúng kế hoạch.
- Migration ledger/checksum/catalog fingerprint không đổi; không chạy migration mới, sửa object, reset database/volume hoặc ghi ngoài namespace A/B đã duyệt. Profile chung được đăng ký đúng contract.

## File và baseline

Thêm bốn file:

1. `starter/scripts/apply_full_corpus.py` — runner một lần, chặn chạy lại nếu evidence đã tồn tại; chỉ dùng cache và store hiện có.
2. `results/full_corpus_apply.json` — database identity, precheck, transaction results, ledger/counts và round-trip evidence.
3. `results/full_corpus_apply_integrity.json` — kiểm tra file và Git refs trước/sau.
4. `results/full_corpus_apply.md` — báo cáo này.

Mọi file đã tồn tại được kiểm tra giữ nguyên SHA-256; inventory 26,964 file data/local không đổi size/mtime. Không sửa/xóa 7 file local được bảo vệ. Embeddings/store vẫn có các thay đổi đã nghiệm thu từ trước, không thêm thay đổi implementation lượt này. HEAD và origin/main không đổi; không stage, pull, rebase, commit hoặc push. Không chạy lại pytest vì không đổi implementation; xác minh lượt này bằng precheck và hậu kiểm PostgreSQL thật.

## Rủi ro còn lại và điểm dừng

A/B là hai transaction riêng, không phải một COMMIT nguyên tử chung. Lượt này cả hai đã được xác nhận lưu bền vững, không có trạng thái COMMIT mơ hồ. Runner không tự retry khi lỗi: chỉ mở kết nối read-only để phân loại CONFIRMED_COMMITTED / CONFIRMED_NOT_COMMITTED / UNKNOWN và dừng. Chưa mô phỏng mất kết nối khi COMMIT trên database chính.

Chưa triển khai retrieval hoặc benchmark; ingestion thành công không chứng minh chất lượng retrieval/grounding. Dừng tại Checkpoint 4.3C-2 để nghiệm thu.
