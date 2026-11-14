# Document Ingestion & Chunking — giai đoạn 3

Chạy từ root với Python của môi trường lab (WSL dùng `.venv/bin/python`):

```text
python -m pip install -r starter/requirements.txt
python -m pytest -q
python starter/scripts/check_ingestion_chunking.py --manifest data/manifest.json
```

Test có marker `integration` đọc đúng corpus local. Nếu máy chưa có PDF, test integration sẽ skip; không coi skip là bằng chứng đã kiểm tra corpus. Unit test dùng PDF tạm và mock có chủ đích, không phải corpus hay benchmark của bài nộp.

## Luồng dữ liệu và tính bất biến

- `load_pdf(path, document_id, source)` giữ API, dùng pypdf đọc mọi trang vật lý từ 1; trang rỗng/lỗi vẫn giữ vị trí với extraction_status và log. Thiếu PageLabels thì không tự tạo nhãn trang in.
- `load_manifest_pages()` là bước điều phối riêng: kiểm tra JSON Schema tại `data/manifest.schema.json`, quyền xử lý, SHA-256 PDF, page mapping; chỉ trích xuất các trang đồng thời included=true, extraction_status=ok, review_status=approved.
- Từng trang được chọn phải khớp text chuẩn hóa trích xuất lại, file text local, số ký tự, checksum và nhãn PDF (nếu PDF có PageLabels). Không thay manifest, file nguồn, text chuẩn hóa hay checksum khi sai.
- Chuẩn hóa dùng đúng `nfc-whitespace-paragraphs-v1` từ giai đoạn 2. Checker corpus và ingestion dùng chung hàm. Giữ header/footer, SQL punctuation và ranh giới dòng/đoạn; không tự sửa hyphenation hoặc reflow.
- `DocumentPage` và `Chunk` không đổi field/signature. document_id ánh xạ source_id; page là trang vật lý. Metadata giữ source_id, page_id, physical_page, printed_page_label, section, section_evidence, version, text checksum/count. Không suy đoán section hoặc version.

## Cấu hình và truy vết chunk

- A: `fixed_size(page, size=500, overlap=50)`; lát cắt ký tự cố định.
- B: `by_paragraph(page, max_size=500)`; ưu tiên ranh giới đoạn bằng dòng trống; paragraph dài dùng câu/dòng/từ rồi cắt cứng khi cần. Không bỏ whitespace phân cách nên B ghép lại đúng text nguồn.
- C tham chiếu chính danh sách B: cùng object, ID, text và metadata. Chưa áp dụng filter khi chưa triển khai retrieval.
- Các câu SQL phát hiện được và vừa max_size được giữ cùng chunk; parser ranh giới xét dấu nháy, dollar quote và comment. Đây là heuristic, không phải SQL parser hoàn chỉnh. SQL quá dài phải chia và được gắn cờ `split_sql_statement`.
- Không ghép qua trang; SQL bắt đầu từ trang trước có thể không được nhận diện đầy đủ. Không thay text để sửa vấn đề đó.
- Metadata `_chunking` ghi start_char/end_char theo khoảng [start, end), policy version, tham số và cờ chia SQL. ID dùng SHA-256 của cấu hình A/B, định danh nguồn/trang, checksum toàn text trang và offsets; không dùng UUID hay hash ngẫu nhiên. Đổi text/cấu hình đổi ID; metadata gốc được deepcopy. Metadata đầu vào có `_chunking` sẽ báo lỗi để tránh ghi đè.

## Artifacts và kiểm tra

- `results/ingestion_chunking.md` và `.json`: số trang chọn/bỏ qua, lý do loại, số chunk, min/mean/max ký tự, coverage, cảnh báo và lỗi thực tế, phiên bản thư viện, thời điểm/thời gian chạy.
- Chunk chứa text chỉ lưu `data/local/stage3/chunks/A.jsonl` và `B.jsonl`, đã được Git ignore; C không tạo bản text thứ ba.
- Audit kiểm tra mỗi chunk là lát cắt đúng của đúng trang, metadata không mất, không mất ký tự, overlap A đúng 50, B liên tục, ID duy nhất và ổn định khi chạy lại. Coverage không thay thế chấm coherence/grounding thủ công sau này.
- CLI chỉ nghiệm thu nếu đọc đúng 40 trang; lỗi source/schema/checksum làm FAIL, không tự sửa hoặc âm thầm bỏ trang được chọn.

Chưa triển khai embedding, pgvector ingestion, retrieval hoặc benchmark; `starter/src/run.py` giữ nguyên khung TODO.
