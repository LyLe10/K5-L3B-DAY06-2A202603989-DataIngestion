# Corpus & Manifest — giai đoạn 2

Hiện trạng: đã tải PostgreSQL 16.16 PDF A4 từ nguồn chính thức. Manifest ghi đủ 3.074 trang vật lý; chọn 40 trang nội dung: 97–132 và 148–151. Xem báo cáo `results/corpus_validation.md` để kiểm tra kết quả mới nhất.
Ví dụ `format-example.json` không phải corpus. Chỉ hỗ trợ PDF có text trong phiên bản này; không OCR.

## Nguồn đã được xác nhận và thu thập

- Chủ đề: PostgreSQL — định nghĩa bảng, ràng buộc và thao tác dữ liệu.
- Tài liệu: PostgreSQL 16 Documentation, The PostgreSQL Global Development Group.
- Trang chọn PDF: https://www.postgresql.org/docs/
- PDF A4: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf
- Phạm vi thực tế: Data Definition (97–132, 36 trang) và Data Manipulation (148–151, 4 trang); không dùng Queries.
- Quyền: https://www.postgresql.org/docs/16/legalnotice.html
- Ghi nhận nguồn/quyền: `rights/postgresql-16.16.md`.

URL nhánh 16 có thể thay đổi bản minor. Bản đã tải được xác minh là **16.16** qua cover và PDF metadata; không suy từ HTML.

- SHA-256: `4cf9a4f56001191572e07959396120de0d61ca65d29072df66f9e656c24ae568`.
- Lấy lúc: 2026-11-14T02:51:40.1664984Z (09:51 giờ Việt Nam/Thái Lan).
- URL cuối xác minh HTTP 200, application/pdf, không chuyển sang miền khác.
- Legal Notice ở trang vật lý 2; bản nguyên văn được giữ local tại `normalized/postgresql-16.16-a4/NOTICE.txt`.
- pypdf thực tế: **6.21.4**; jsonschema: **4.26.0**. Dùng cùng pypdf để tái lập text/checksum.
- Metadata section có hai giá trị từ chương gốc: `Data Definition`, `Data Manipulation`.
- Trang 132 có cả caveat Inheritance và mở đầu Table Partitioning; không khẳng định bao phủ toàn bộ chương 5. Trang 151 có 735 ký tự và vẫn hợp lệ theo quy tắc PDF.

Sau khi lấy đúng PDF và xác minh hash, tái tạo text (không thay manifest hoặc nhãn duyệt):

```powershell
python -m pip install "pypdf==6.21.4" "jsonschema==4.26.0"
python starter/scripts/extract_corpus.py --manifest data/manifest.json
python starter/scripts/check_corpus.py --manifest data/manifest.json
```

Nếu URL đổi snapshot, dừng khi checksum không khớp; cần lấy lại đúng bản hoặc công khai đổi phiên bản và duyệt corpus lại. Script extraction không tự tải PDF và không tự gán nhãn duyệt.

## Cấu trúc và cách lấy lại

Dữ liệu được quản lý tại `data/` ở root; không tạo bản thứ hai trong `starter/data/`.
`local/raw/` chứa PDF nguyên bản; `local/normalized/` chứa UTF-8 text từng trang. Cả `data/local/` bị Git ignore. Báo cáo không chứa nguyên văn trang.

Quy trình đã áp dụng và dùng khi thay snapshot:

1. Lấy PDF từ URL nguồn, giữ nguyên bytes trong `data/local/raw/`; lưu ngày truy cập có múi giờ và SHA-256.
2. Kiểm tra phiên bản, số trang và Legal Notice trong PDF. Ghi người duyệt, thời điểm, căn cứ quyền và điều kiện giữ thông báo bản quyền trong `rights/`.
3. Tạo bản ghi nguồn theo `manifest.schema.json`. Nếu không có phiên bản đáng tin, dùng null và giải thích trong retrieval_instructions; không đoán.
4. Trích xuất tất cả trang bằng pypdf; chuẩn hóa bằng hàm `normalize_text` trong checker. Ghi bytes UTF-8 không BOM, không tự thêm newline cuối file. Tính SHA-256 và số ký tự Python `len(text)` trên text đó.
5. Ghi một bản ghi cho từng trang vật lý (1-based), cả trang loại. Đặt ID ổn định, ví dụ cấu trúc `<source_id>:p<physical_page>`; printed_page_label có thể null.
6. Duyệt từng trang: loại bìa, mục lục, trắng, chỉ tham khảo, không liên quan hoặc lỗi/scan. Trang loại cần exclusion_reason; lỗi trích xuất cần notes. Text rỗng vẫn có file UTF-8 rỗng và checksum thật.
7. Trang tính cần included=true, review_status=approved, extraction_status=ok, exclusion_reason=null. Ghi section từ heading thật và section_evidence là vị trí chứng minh (trang/heading/URL); không suy diễn metadata. Trang nối tiếp có thể dẫn về trang đầu section.
8. Điền retrieval_instructions đủ rõ để người chấm lấy đúng snapshot, vị trí file, checksum và tái tạo. Nếu URL đã đổi bytes, dừng và tìm bản khớp; không sửa checksum để che thay đổi. Khi đổi snapshot phải duyệt lại.

Không yêu cầu 1.500 ký tự cho trang PDF. Không tính trang trùng để đạt 30. Section cần ít nhất hai giá trị có ý nghĩa, đủ để thiết kế ít nhất ba câu filter (một thuộc test) ở giai đoạn benchmark.

## Chạy kiểm tra

Từ root, dùng Python của môi trường đã setup:

```powershell
python -m pip install -r starter/requirements.txt
python starter/scripts/check_corpus.py --manifest data/manifest.json
python -m unittest discover -s starter/tests -v
```

Nếu `.venv` được tạo trong WSL (`.venv/bin/python`), chạy trong WSL tại root bằng `.venv/bin/python`, không dùng `.venv/Scripts/python.exe`.

Checker chỉ đọc dữ liệu local, ghi `results/corpus_validation.json` và `.md`; không tải, không tạo normalized text, không gọi API/database. Mã thoát: 0 đạt, 1 kiểm tra không đạt, 2 không chạy được (file JSON lỗi, thiếu dependency, lỗi ghi report). Báo cáo cũ không đại diện cho lần chạy lỗi mã 2; luôn kiểm tra mã thoát và checked_at. Trường `$schema` của manifest phục vụ editor; checker luôn dùng schema của repository.

Chuẩn hóa `nfc-whitespace-paragraphs-v1`: Unicode NFC, CRLF/CR thành LF, gom khoảng trắng ngang từng dòng, bỏ khoảng trắng mép dòng, gom từ ba newline về hai, strip hai đầu; giữ newline và đoạn, không tự bỏ header/footer hoặc sửa nội dung.

## Nghiệm thu và giới hạn

- Ít nhất 30 trang nội dung duy nhất, đã duyệt và truy vết được, không phải tổng số trang PDF.
- Mọi trang có bản ghi, text/checksum/count khớp khi trích xuất lại; nguồn và page ID duy nhất.
- Quyền xử lý verified, có ghi nhận bằng chứng local và URL; ghi riêng quyền tái phân phối, không mặc định được chia sẻ.
- Có ít nhất hai section có căn cứ. Ánh xạ source_id → document_id, source_path_or_url → source, physical_page → page, metadata → metadata của starter.
- Duyệt thủ công nội dung, quyền và section là bắt buộc. Checker xác minh tính nhất quán, không tự chứng nhận giấy phép hoặc chất lượng nội dung.
- Bản sao chính xác sau gom whitespace bị loại khỏi tổng; nội dung gần giống cần người duyệt phát hiện. Ghi quyết định loại, không tự tạo nhãn duyệt.
- Ghi phiên bản pypdf thực tế khi tạo corpus; khi đổi extractor, đối chiếu lại text và checksum.
- Không đưa dữ liệu gốc/normalized vào Git; chưa triển khai embedding, indexing hay benchmark.
