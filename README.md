# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](REPORT_TEMPLATE.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.

## Corpus & Manifest (giai đoạn 2)

Xem [hướng dẫn corpus](data/README.md), [manifest](data/manifest.json) và [JSON Schema](data/manifest.schema.json).
Chạy từ root: `python starter/scripts/check_corpus.py --manifest data/manifest.json`.
Corpus hiện dùng PostgreSQL 16.16 PDF A4: chọn 40 trang vật lý (97–132, 148–151). Xem `results/corpus_validation.md` để đối chiếu báo cáo kiểm tra; PDF và text chỉ lưu local, không đưa vào Git.

## Document Ingestion & Chunking (giai đoạn 3)

Xem [thiết kế và lệnh chạy](docs/ingestion_chunking.md). Chạy từ root: `python starter/scripts/check_ingestion_chunking.py` và `python -m pytest -q`.
Báo cáo thực tế: [ingestion/chunking](results/ingestion_chunking.md). Chunk chứa text lưu trong `data/local/stage3/chunks/`; báo cáo này là checkpoint lịch sử trước embedding và benchmark.

## Kết quả bài làm

Đã hoàn thành pipeline trên 40 trang PostgreSQL 16.16, ingest 510 vectors (A=246, B=264; C dùng lại B), DEV `dev-002` COMPLETE với 45 traces và TEST `test-001` COMPLETE với 15 traces. **B được chọn trên DEV và đóng băng trước TEST**. Bốn proposal chấm thủ công trong `review_proposals/` đã được người học xác nhận và nhập vào bảng review.

| Strategy | DEV Hit@1 | DEV Evidence Hit@3 | TEST Hit@1 | TEST Evidence Hit@3 | Coherence /2 (n=10) | Metadata đúng/đủ | Grounding /2 (n=5) |
|---|---|---|---|---|---:|---|---:|
| A | 5/15 | 7/15 | 4/5 | 5/5 | 1.00 | 15/15 | 2.00 |
| B | 7/15 | 10/15 | 4/5 | 5/5 | 1.70 | 15/15 | 2.00 |
| C | 7/15 | 10/15 | 4/5 | 5/5 | 1.70 | 15/15 | 2.00 |

Trên câu TEST yêu cầu scope, A/B có top-3 đúng scope 0/1 nhưng không áp dụng filter; C áp dụng filter và đạt 1/1. Đây khác metadata mỗi hit có đúng nguồn/trang hay không. Grounding đo evidence retrieval, không đo câu trả lời LLM. TEST chỉ có 5 câu, không chứng minh strategy tối ưu tổng quát.

- [Báo cáo cá nhân](report/individual/2A202603989_LeThiLy.md): năm khía cạnh, hai ví dụ lỗi, tài nguyên và giới hạn.
- [Manual evaluation](results/manual_evaluation/README.md): nhãn đã xác nhận, evidence và provenance.
- [Traces chia sẻ](results/manual_evaluation/retrieval_traces.jsonl), [metrics](results/manual_evaluation/retrieval_metrics.csv), [summary](results/manual_evaluation/summary.json), [experiment log](artifacts/experiment_log.csv).
- [Corpus và cách lấy snapshot](data/README.md), [model/dependency setup](docs/stage4_reproduction.md), [DEV/TEST runtime](docs/local_lab_test.md).

Giữ `results/manual_evaluation/NOTICE.txt` cùng trích đoạn PostgreSQL. PDF, model, vector cache và raw runs ở `data/local/` bị Git ignore; trace chia sẻ có đủ ID/text/score/metadata để kiểm chứng.

## Tái lập và kiểm tra

Đọc `data/README.md` để lấy PDF đúng checksum, rồi `docs/stage4_reproduction.md` để dựng Python/model/database trên môi trường mới. Store: PostgreSQL 16.16 + pgvector 0.8.7, exact cosine; schema trong `starter/migrations/`. Không chạy lại migration/ingest trên database hiện có chỉ để đọc báo cáo. `python -m src.run` vẫn là skeleton; các entrypoint thực tế là các scripts dưới đây.

Operator chạy từ root trong WSL/Python 3.12.3, sau khi đã chuẩn bị model local và dữ liệu Stage 4. Password nhập qua `getpass`, không đưa vào CLI. Dùng output/cache mới; tên `repro-*` chỉ là ví dụ, không phải run đã thực hiện:

```bash
PY=data/local/stage4/venv/bin/python
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
"$PY" -B starter/scripts/run_local_lab_dev.py \
  --role day6 \
  --output data/local/lab_benchmark/dev/repro-dev \
  --query-cache data/local/lab_benchmark/query_cache/repro-dev

# Không ghi đè selection freeze gốc của dev-002.
"$PY" -B starter/scripts/run_local_lab_test.py freeze \
  --dev-run data/local/lab_benchmark/dev/repro-dev/raw_run.json \
  --selection results/selection_freeze_reproduction.json

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
"$PY" -B starter/scripts/run_local_lab_test.py run \
  --selection results/selection_freeze_reproduction.json \
  --role day6 \
  --output data/local/lab_benchmark/test/repro-test \
  --query-cache data/local/lab_benchmark/query_cache/repro-test
```

Không cần chạy lại runtime để review bài hiện tại. Kiểm thử offline dùng fixtures/mocks:

```bash
PYTHONDONTWRITEBYTECODE=1 data/local/stage4/venv/bin/python -B -m pytest -q \
  -p no:cacheprovider starter/tests/test_local_lab_test.py \
  starter/tests/test_local_lab_dev.py starter/tests/test_evaluation.py \
  starter/tests/test_evaluation_runner.py
```

Stage reports cũ mô tả trạng thái tại thời điểm tạo; báo cáo cá nhân là bản tổng hợp cuối. Họ tên đã cập nhật trong STUDENT và nội dung kỹ thuật đã được người học duyệt. Còn xác nhận diff/danh sách file cuối, chốt commit, kiểm quyền truy cập repo và nộp link theo hướng dẫn lớp. Chưa commit/push bản hoàn thiện này.
