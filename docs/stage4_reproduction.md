# Tái lập môi trường Stage 4

Stage 4 hiện đã hoàn tất embedding/schema/ingestion; retrieval và benchmark chưa triển khai. Hướng dẫn này không yêu cầu chạy lại ingestion trên database chính. Không đưa `.env`, venv, PDF, model hoặc vector cache vào Git.

## Credential lab và phạm vi sử dụng

Credential trong [starter/.env.example](../starter/.env.example) là credential lab mặc định công khai, chỉ dùng cho PostgreSQL local cô lập. Không sử dụng lại cho production, môi trường chia sẻ hoặc dịch vụ public. Port bind `127.0.0.1` giới hạn truy cập qua cổng được publish, nhưng không thay thế các biện pháp bảo vệ database, phân quyền và kiểm soát truy cập.

Khi triển khai môi trường khác, cần cấu hình credential riêng và đồng bộ cấu hình khởi tạo database với `DATABASE_URL` cùng các client liên quan; giữ credential thật ngoài Git. Thay `POSTGRES_PASSWORD` trong Compose không tự thay mật khẩu role PostgreSQL trên volume đã khởi tạo. Với database hiện có, việc đổi mật khẩu cần quy trình riêng được phê duyệt; không reset hoặc xóa volume để xử lý cấu hình.

## Python và dependency lock

Môi trường đã kiểm chứng: **WSL/Linux x86_64, CPython 3.12.3**, CPU. Dùng môi trường mới, không sửa venv baseline:

```bash
python3.12 -m venv data/local/stage4-reproduction/venv
PY=data/local/stage4-reproduction/venv/bin/python
"$PY" -m pip install --require-hashes -r starter/requirements-stage4-linux-py312.lock
"$PY" -m pip check
```

Lock chứa đúng 48 wheel URL và SHA-256 từ resolver đã nghiệm thu; đã đối chiếu version/URL/hash metadata với môi trường đã cài, không resolve lại hoặc nâng cấp. Đây là lock cho Linux x86_64/Python 3.12, không dùng trực tiếp cho Windows native, ARM hoặc Python khác. Python patch version cũng nằm trong embedding profile: để tái tạo đúng profile ID hiện tại cần 3.12.3.

Các phiên bản chính: torch 2.9.1+cpu; sentence-transformers 5.1.2; transformers 4.57.1; tokenizers 0.22.1; huggingface-hub 0.36.0; sentencepiece 0.2.1; numpy 2.5.4; safetensors 0.8.0; psycopg/psycopg-binary 3.3.8; pgvector Python 0.4.1; pypdf 6.21.4. Không nhầm pgvector Python với extension PostgreSQL 0.8.7.

Unit tests không cần tải model hoặc kết nối database:

```bash
PYTHONDONTWRITEBYTECODE=1 "$PY" -B -m pytest -q -p no:cacheprovider \
  starter/tests/test_schema.py starter/tests/test_embeddings.py \
  starter/tests/test_store.py starter/tests/test_store_test_target.py
```

## Model E5 cố định

Model: `intfloat/multilingual-e5-small`; revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`. Profile: `528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651`.

Chỉ khi cần dựng môi trường mới và đã được phép tải, chạy đoạn sau từ root. Không dùng nó để ghi đè snapshot đã có:

```python
import hashlib
from pathlib import Path
from huggingface_hub import snapshot_download
from starter.src.embeddings import ARTIFACTS, MODEL, REVISION

target = Path('data/local/models/intfloat--multilingual-e5-small') / REVISION
if target.exists():
    raise RuntimeError('Snapshot exists: verify existing files; never overwrite automatically')
snapshot_download(repo_id=MODEL, revision=REVISION, local_dir=str(target),
                  allow_patterns=list(ARTIFACTS))
for name, expected in ARTIFACTS.items():
    assert hashlib.sha256((target / name).read_bytes()).hexdigest() == expected, name
```

Danh sách 10 artifact/checksum nằm trong `starter/src/embeddings.py`; weights safetensors SHA-256 là `1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477`. Không tải ONNX/OpenVINO/weights khác, không tắt TLS. Sau khi có snapshot, dùng `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`; adapter tự kiểm tra checksums trước khi load. Không encode corpus chỉ để kiểm tra cài đặt. Profile còn kiểm tra CPU float32/eval, mean pooling, normalization, prefixes và giới hạn 512 token.

## Bootstrap PostgreSQL integration cô lập

Yêu cầu Docker và image PostgreSQL **16.16** / pgvector **0.8.7** đã có local. Tag dưới đây có thể thay đổi; kiểm tra image/version trước khi dùng. Runner từ chối mọi server version khác `160016` và extension khác `0.8.7`; không tự pull hoặc sửa version khi mismatch.

**Migration 0001 bắt buộc tên database `day6_lab`.** Database test cũng mang tên này nhưng nằm trong cluster tmpfs khác, user `tester`, cổng `127.0.0.1:55434`. Không kết nối ghi đến cluster chính ở cổng 55433. Tên database không đủ để xác định đích an toàn.

Chạy trong Bash/WSL ở root, chỉ tạo container mới; không dùng container hoặc volume database chính:

```bash
export DAY6_TEST_CONTAINER="day6-store-test-$(date +%Y%m%d%H%M%S)"
export DAY6_TEST_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
export POSTGRES_PASSWORD="$DAY6_TEST_PASSWORD"
docker run --pull never -d --name "$DAY6_TEST_CONTAINER" \
  --label day6.role=store-integration \
  --tmpfs /var/lib/postgresql/data:rw \
  -p 127.0.0.1:55434:5432 \
  -e POSTGRES_DB=day6_lab -e POSTGRES_USER=tester -e POSTGRES_PASSWORD \
  pgvector/pgvector:0.8.7-pg16
docker exec "$DAY6_TEST_CONTAINER" pg_isready -U tester -d day6_lab
# Chỉ chạy khi pg_isready thành công; nếu cổng/container đã tồn tại, dừng.
PYTHONDONTWRITEBYTECODE=1 "$PY" -B starter/scripts/check_store_postgres.py \
  --report "results/store_postgres_run_$(date +%Y%m%d%H%M%S).json"
# Giữ evidence và exit code. Không chạy lại runner trên cluster đã có schema.
docker stop "$DAY6_TEST_CONTAINER"
unset DAY6_TEST_PASSWORD POSTGRES_PASSWORD
```

Đây là mật khẩu fixture sinh mới, không phải credential thật. Không commit giá trị, không dump Docker inspect hoặc environment vào evidence. Có thể kiểm tra lại readiness thủ công khi container vừa khởi động; không tự retry migration/test suite sau lỗi. Dừng container tmpfs làm mất dữ liệu test, không ảnh hưởng volume chính; không chạy prune/reset hoặc lệnh xóa volume.

Guard xác minh: container đang chạy, label đúng, không privileged/bind/volume mounts, PGDATA tmpfs đúng, network không host/container sharing, duy nhất port binding loopback 55434, database/user đúng. Cluster ID được đọc qua Docker exec SELECT và đối chiếu qua SQL của từng kết nối fixture/store; luôn từ chối cluster chính `7707847059457269799`. Không dùng DATABASE_URL làm DSN test. Guard không cần giữ cluster ID test cũ; mỗi container mới có ID riêng.

Runner tạo extension/schema và dùng synthetic fixtures chỉ trên cluster cô lập. `starter/.env` được dùng riêng cho snapshot database chính **READ ONLY** trước/sau; giữ credential này local, dùng cấu hình môi trường đã được phép truy cập. Môi trường không có database chính của lab cần thiết kế chế độ read-only snapshot riêng trước khi chạy runner hiện tại; không tự thay URL bằng production khác. Bootstrap này không đụng tới Migration 0001 đã áp dụng trên database chính.

## Script nào có tác dụng ghi?

| Script | Hành vi / điều kiện |
|---|---|
| `plan_schema.py` | Offline planner; không kết nối database |
| `check_store_postgres.py` | Ghi synthetic fixtures/DDL vào cluster Docker test đã xác minh; database chính chỉ đọc; report phải là file JSON mới |
| `check_schema_isolated.py` | Harness lịch sử CP4.2, yêu cầu container/labels/network riêng theo code; không thay bằng bootstrap CP4.3B ở trên |
| `check_embedding_smoke.py` | Encode tập nhỏ và tạo cache/report; yêu cầu cache mới và database rỗng của checkpoint lịch sử; không chạy trên trạng thái hiện tại |
| `check_full_corpus_preflight.py` | Encode A/B khi cache thiếu, ghi cache/report; database chỉ đọc; không chạy lại trong fixup |
| `apply_migration_0001.py` | **Ghi DDL database chính**, runner một lần ràng buộc môi trường đã duyệt; không chạy để kiểm tra checkout |
| `apply_full_corpus.py` | **Ghi profile/ledger/chunks database chính**, không encode; yêu cầu duyệt riêng và evidence preflight đúng |

Các reports cũ là lịch sử, không bị overwrite khi kiểm tra lại. Full-corpus preflight JSON được giữ nguyên để bảo toàn 510 receipts và dependency của apply runner; chứa metadata/checksums, không chứa toàn văn corpus hoặc mảng vectors. Database hiện tại đã có 510 rows, nên không chạy lại các script yêu cầu trạng thái rỗng.

Nguồn corpus và cách lấy đúng snapshot nằm ở `data/README.md`, `data/rights/postgresql-16.16.md`; PDF/normalized text/cache luôn local và giữ notice/điều khoản. Không sửa corpus hoặc manifest để vượt qua checksum mismatch.
