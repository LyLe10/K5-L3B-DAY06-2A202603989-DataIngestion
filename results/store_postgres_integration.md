# Checkpoint 4.3B-3 — PASS

- PostgreSQL integration: **25 PASS / 0 FAIL / 0 BLOCKED**, 12.97 giây; runner gồm setup/read-only production checks: 13.896 giây.
- Full pytest chạy **đúng một lần sau integration PASS**: **263 passed, 12 subtests passed**, 0 fail/skip, 15.14 giây.
- Không phát hiện lỗi implementation/schema; không sửa store.py, test_store.py hoặc Migration 0001. Không retry, hạ assertion hoặc bỏ test.

## Môi trường và phạm vi

Container `day6-cp43b3-isolated-20261114`, ID `2db0dce083c01d57e5fcc927abae006a864a9e37751dc4935885d1567a10ed5c`; PostgreSQL **16.16**, pgvector **0.8.7**, localhost **55434**. Cluster **7707931395030798375**, khác production **7707847059457269799**. Image ID `sha256:484e838076e04939d27d3e176e91c86eea96236126023be8d3059761122e579f`.

PGDATA tmpfs riêng, không shared mount/volume với database chính. Database trong container có tên day6_lab để đáp ứng precondition migration; mọi mutation chỉ nhắm test endpoint/cluster đã pin, không dùng DATABASE_URL làm fallback. Container đã dừng sau kiểm thử, giải phóng fixture tmpfs. Không reset volume/database chính.

Áp dụng nguyên Migration 0001 trong một transaction; checksum:
`04f891492379e9800dd023d604b61e9bd7a60d40e48a1179dd4d6840633166e6`.
Catalog fingerprint sau mọi mutation:
`209b3597e6f2a6ff8cf13f4c12f5cfc45f3bb34c07f9ff363204902323a2da55`, khớp migration ledger.

## Bằng chứng chính

| Nội dung | Kết quả thực |
|---|---|
| First sync, registration, ON CONFLICT | 30 rows/snapshot; profile tạo đúng; registration replay không đổi xmin |
| Vector/metadata round-trip | 384 chiều, float32 finite/unit, đọc bằng kết nối mới và khớp chính xác |
| Replay | completed_at, chunk/profile xmin, text/metadata/vector giữ nguyên; 0 written/deleted rows |
| Vector đổi nhưng snapshot ID không đổi | Phát hiện thay đổi, đúng 1 row UPDATE; replay tiếp theo no-op |
| Metadata/text/source provenance đổi | Digest đổi; chunk giữ lại cập nhật snapshot provenance; text đổi tạo ID mới và xóa ID cũ |
| Stale/count reduction | 31→30 expected/actual, stale deletion=1, status complete; không vi phạm CHECK tức thời |
| Isolation | Dataset khác, profile khác, strategy B giữ nguyên khi sync A |
| Parameter binding | Chuỗi URL có dấu nháy và SQL giả được lưu nguyên dạng dữ liệu; không thực thi |
| Rollback tại 7 vị trí | Sau profile/ledger/chunk/delete/complete/constraint check và tại COMMIT; không còn profile/ledger/chunks một phần |
| Rollback snapshot đã có | Khôi phục completed_at, rows, vectors và xmin cũ |
| Deferred FK/completion | Mutation statement thành công, COMMIT bị chặn; dữ liệu khôi phục |
| A/B compatibility và C | Missing/mismatched snapshot bị chặn; đồng bộ B phù hợp thì PASS; C bị từ chối, 0 C rows |
| Concurrency cùng namespace | Hai writer thật; quan sát pg_stat_activity chờ advisory lock; serialize và vector cuối đúng writer sau |
| Concurrency khác namespace | B hoàn tất khi A vẫn giữ lock: 0.131 giây |
| Timeout | lock_timeout thực tế 5.092 giây; rollback, không retry |

SQLSTATE âm tính đúng kỳ vọng: **22012** (lỗi chia cho 0 được chèn), **P0001** (immutability/completion trigger), **23503** (deferred FK), **55P03** (lock timeout). Đây không phải test FAIL. Fault/coordination wrappers chỉ chèn lỗi/điều phối quanh cursor psycopg thật; không giả rows hoặc transaction results.

Cuối lượt: **18 synthetic profiles, 21 complete snapshots, 630 synthetic chunks**; mỗi snapshot có actual_count khớp count thực. Vectors là fixture số học hợp lệ, **không phải embedding model thật**, không encode hoặc ingest corpus thật. Thời gian integration: **2026-11-14 07:56:05–07:56:19 UTC**.

## Baseline, production và files

- Production chỉ được SELECT với `default_transaction_read_only=on`; ledger/applied_at/checksum/catalog giữ nguyên trước–sau, profiles/snapshots/chunks vẫn **0/0/0**.
- Tất cả file cũ đối chiếu SHA-256 giữ nguyên; inventory **26.462 file data/local** không đổi tên/size/mtime. Full-suite corpus tests xác minh baseline 40 trang, coverage 103371/103371 và deterministic metadata/IDs; không encode model hoặc sửa baseline A/B/C.
- Git refs không đổi; không staged changes, pull/rebase/commit/push. Các thay đổi tracked từ 4.3A/B-1/B-2 vẫn được giữ nguyên.
- Lượt này thêm 4 file: `starter/tests/postgres_store_cases.py`, `starter/scripts/check_store_postgres.py`, `results/store_postgres_integration.json`, báo cáo này.
- Cases PostgreSQL là opt-in qua runner, không thuộc discovery `test_*.py`; chúng đã chạy đủ 25 trước full pytest, không bị skip để đạt PASS. Không chạy retrieval.

Evidence từng ca, SQLSTATE, counts, identity và production snapshots: [store_postgres_integration.json](store_postgres_integration.json).

## Trước 4.3C

Chưa chứng minh full encode/ingest 510 input thật, hiệu năng deferred triggers trên snapshot lớn hoặc recovery sau mất kết nối khi COMMIT chưa rõ kết quả. Concurrency đã kiểm tra với profile có sẵn; chưa mở rộng stress test nhiều writer/registration race lần đầu. Context/receipt vẫn cần producer đáng tin cậy và loader xác minh checksum; fixture PASS không chứng minh chất lượng retrieval.

**Dừng chờ nghiệm thu; chưa được ingest corpus thật vào database chính.**
