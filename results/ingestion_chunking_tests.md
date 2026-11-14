# Kết quả pytest — ingestion/chunking

Đã chạy từ root bằng Python trong .venv WSL:

```text
python -m pytest -q --junitxml=results/ingestion_chunking_pytest.xml
82 passed, 12 subtests passed in 24.46s
```

JUnit ghi 94 trường hợp (82 test + 12 subtest), 0 failures, 0 errors, 0 skipped. Hai integration test đọc corpus PostgreSQL thật, không skip. Bộ test cũng chạy lại các test Corpus & Manifest của giai đoạn 2.

Bao phủ: parser PDF thực với trang text/rỗng và nhãn trang; lỗi trích xuất; chuẩn hóa/idempotence; chọn trang theo đủ ba cờ; checksum PDF/text, số ký tự, schema, quyền và page mapping; overlap và coverage; paragraph/SQL boundary; Unicode; ID ổn định và phân biệt A/B; metadata deepcopy, giá trị null; C dùng chính B; integration trên 40 trang và 103.371 ký tự.

Unit test dùng fixture tạm/mocks, không tạo corpus hay benchmark giả. Coverage ở báo cáo ingestion là độ phủ ký tự nguồn; chưa đo line coverage của test suite và chưa chấm coherence/grounding.
