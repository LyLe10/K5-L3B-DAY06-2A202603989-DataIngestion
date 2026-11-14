# Checkpoint 4.3C-1 — PASS, sẵn sàng trình duyệt sync

Đã xử lý đủ 510 chunk thật: 8 vector lấy từ cache đã duyệt, 502 input được encode mới. Chưa ghi PostgreSQL, chưa register profile hoặc sync snapshot. C tái sử dụng chính danh sách vector B, không encode và không tạo rows riêng.

## Corpus và model

- Loader kiểm tra manifest, quyền, SHA-256 PDF/text và page mapping trước khi tạo SnapshotContext. 40 trang vật lý: **97–132, 148–151**; A=246, B=264. Mỗi strategy phủ **103371/103371** ký tự. Chunks tái tạo khớp nguyên dữ liệu JSONL baseline, gồm IDs, thứ tự, text, metadata và offsets.
- Model `intfloat/multilingual-e5-small`, revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`; artifact checksums và dependency versions được kiểm tra bởi embedder, ghi trong JSON evidence.
- Profile ID: `528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651`.
- CPU, float32, eval, mean pooling, L2 normalization; prefix `passage: `. Tokenizer và Sentence Transformers limit đều 512. Tokenize toàn bộ trước encode, special tokens bật, truncation tắt.

| Input | Count | Min | Mean | Max | p95 | Vượt 512 |
|---|---:|---:|---:|---:|---:|---:|
| A | 246 | 18 | 121.7073 | 212 | 156 | 0 |
| B | 264 | 15 | 103.9962 | 208 | 144 | 0 |
| Tổng | 510 | 15 | 112.5392 | 212 | 152 | 0 |

Tất cả vector có 384 giá trị hữu hạn; norm min/max **0.9999999143 / 1.0000001368**, đạt tolerance 1e-5. Từng vector được đối chiếu với cache theo input SHA và hàng dự kiến theo chunk ID. `validate_batch()` xác minh receipt order, profile, toàn bộ chunk và context; không mở transaction ghi. JSON evidence có đủ 510 receipts, gồm chunk ID, trang, section, offsets, input/vector checksum và token length; không sao chép text corpus vào báo cáo.

## Hiệu năng và cache

- Encode CPU thực tế: **35.619 giây**, 33 batches (A 20.793 giây; B 14.826 giây). Tổng preflight **207.474 giây**, gồm khởi tạo thư viện/model, kiểm tra corpus/cache/database và chuẩn bị snapshot.
- Cache hit 8, miss/encode mới 502, không có input miss trùng nhau; chỉ hai lần gọi embed_documents A/B. Cache tăng 9 → 511 entries, gồm 510 passage và một query cũ.
- Cache JSON sau chạy **4,232,775 bytes**; riêng payload vector float32 của 510 chunk **783,360 bytes**, chưa gồm text/metadata, indexes, WAL và overhead PostgreSQL.
- Peak RSS tiến trình **1,031,264 KiB (~1007 MiB)**, gồm model và toàn bộ quá trình; không phải mức tăng RAM riêng lúc encode.
- SHA-256 của 9 cache cũ không đổi. Inventory các file data/local đã tồn tại giữ nguyên size/mtime; chỉ thêm 502 cache entries. Không sửa implementation, corpus, manifest, chunks hoặc metadata.

## Database và kế hoạch sync chưa thực thi

SELECT-only trên `127.0.0.1:55433`, `day6_lab`, PostgreSQL **16.16**, pgvector **0.8.7**, cluster **7707847059457269799**; transaction_read_only=on. Migration 0001 trên đĩa khớp registry/checksum `04f891492379e9800dd023d604b61e9bd7a60d40e48a1179dd4d6840633166e6`, catalog fingerprint khớp ledger đã duyệt. Trước/sau: embedding_profiles=0, strategy_snapshots=0, chunks=0; ledger namespace A/B chưa tồn tại.

| Namespace dataset/profile/strategy | Expected rows | Snapshot dự kiến, chưa lưu |
|---|---:|---|
| day06-postgresql / profile nêu trên / A | 246 | `d06b89acda8d08a5c423bfb5d4cd82662a962481cd7a2f81b2ab324e08b3e860` |
| day06-postgresql / profile nêu trên / B | 264 | `c7d9d92e6695709595d044e5a5a09bb8f91826fb692474c7b1806751015ec1e0` |
| C → B | 0 thêm | Tái sử dụng B |

SnapshotContext được dựng từ IngestionResult đã xác minh, không suy ra completeness từ chunks. Hai snapshot dự kiến tương thích cùng manifest/corpus/profile; trạng thái complete trong đối tượng kế hoạch không thể hiện đã ingest. Chờ duyệt riêng: mỗi strategy một transaction theo runner/store đã kiểm thử, register profile → advisory lock namespace → ledger syncing → conditional upsert → stale deletion cùng namespace → ledger complete → kiểm tra dữ liệu/deferred constraints → COMMIT. Tổng dự kiến 510 rows, 1 profile, 2 ledger entries.

Không chạy EXPLAIN trên DML hoặc thêm thử nghiệm cô lập ở checkpoint này: contract SQL đã được kiểm thử PostgreSQL thật tại 4.3B; chỉ 510 rows nên chưa có nhu cầu tối ưu plan mới. **Chưa đo** thời gian transaction thật cho corpus, WAL/disk thực tế hoặc khả năng đáp ứng timeout 30 giây của sync; thời gian encode không phải thời gian SQL. Đây là rủi ro cần theo dõi khi sync được duyệt, không tự nâng timeout.

## Nếu mất kết nối khi COMMIT

Không tự retry hoặc tuyên bố rollback. Ghi namespace, snapshot IDs, input/vector receipts và thời điểm lỗi; mở kết nối mới chỉ đọc, kiểm tra đúng cluster/migration, canonical profile, ledger complete, counts và **toàn bộ nội dung hàng/vector/provenance** so với kế hoạch, không chỉ snapshot ID (ID không chứa vector). Kiểm tra không có stale rows và A/B compatibility. Phân loại đã lưu đúng / chưa có trạng thái đích / không xác định; báo trạng thái thực tế và xin duyệt trước mọi lần ghi tiếp. Nếu chỉ A thành công thì chặn so sánh A/B cho đến khi B đồng bộ; không DROP để hoàn tác và không coi hai transaction A/B là một transaction nguyên tử chung.

## Kiểm thử và giới hạn

- Targeted tests `test_embeddings.py`, `test_store.py`: **117 PASS**, exit 0; không chạy full pytest vì implementation không đổi.
- Preflight thực: PASS, 0 lỗi, 0 token overflow; không dùng synthetic vectors để thay kết quả embedding thật.
- Kiểm tra Git: các file đã tồn tại giữ nguyên SHA-256; refs HEAD/origin/main không đổi, không stage/commit/push. Chỉ thêm runner/evidence của checkpoint và cache local mới.
- Một phép kiểm tra phụ ban đầu so chuỗi version tuyệt đối đã không chấp nhận hậu tố Debian; xác minh lại bằng `server_version_num=160016` PASS. Không có lỗi model/vector, retry sync hoặc ghi database.
- Chưa đánh giá chất lượng retrieval, grounding hoặc coherence. Chưa thực hiện ingestion thật. Dừng để nghiệm thu 4.3C-1.

Evidence: [full corpus JSON](full_corpus_embedding_preflight.json), [database identity](full_corpus_database_preflight.json), [integrity](full_corpus_integrity.json).
