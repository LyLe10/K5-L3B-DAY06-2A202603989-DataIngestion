# PostgreSQL 16.16 A4 — nguồn và quyền sử dụng

Nguồn đã được người dùng chọn ngày 2026-11-14. Codex đã tải PDF từ PostgreSQL chính thức và đối chiếu cover, PDF metadata, Legal Notice cùng các trang corpus. Đây là kiểm tra của trợ lý, không phải xác nhận đã có người học duyệt thủ công.

- Trang dẫn PDF: https://www.postgresql.org/docs/
- URL yêu cầu và URL cuối xác minh bằng HTTP HEAD (200, application/pdf): https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf
- Snapshot: PostgreSQL 16.16 Documentation; tác giả The PostgreSQL Global Development Group; 3.074 trang vật lý.
- SHA-256: `4cf9a4f56001191572e07959396120de0d61ca65d29072df66f9e656c24ae568`.
- Lấy PDF: 2026-11-14T02:51:40.1664984Z; HTTP HEAD đối chiếu: 2026-11-14T02:55:13.8719454Z.
- Last-Modified HTTP: Thu, 12 Nov 2026 14:03:51 GMT. Đây là metadata máy chủ, không phải ngày hiệu lực.
- Legal Notice: trang vật lý 2 (nhãn in ii), đối chiếu với https://www.postgresql.org/docs/16/legalnotice.html.

## Quyền và điều kiện

PostgreSQL License cho phép xử lý, sao chép, sửa đổi và phân phối software/documentation. Điều kiện là giữ thông báo bản quyền và toàn bộ các đoạn điều khoản liên quan trong các bản sao. Bản PDF nguyên vẹn giữ Legal Notice tại trang 2; bản text của notice được giữ trong `data/local/normalized/postgresql-16.16-a4/NOTICE.txt`, bên cạnh các trang trích xuất. Không đưa PDF hoặc text trích xuất vào Git.

Thông báo bản quyền trong PDF gồm The PostgreSQL Global Development Group (1996–2026) và The Regents of the University of California (1994). Các đoạn miễn trừ bảo đảm và giới hạn trách nhiệm vẫn được giữ nguyên trong bản local. Ghi nhận này tóm tắt căn cứ, không thay thế Legal Notice gốc.

## Phạm vi đã chọn

- Trang vật lý 97–132: 36 trang Data Definition; nhãn in 59–94.
- Trang vật lý 148–151: 4 trang Data Manipulation; nhãn in 110–113.
- Tổng 40 trang, hai giá trị section từ heading chương và running header có thật.
- Trang 132 chứa phần cuối caveats của Inheritance và phần mở đầu Table Partitioning; corpus là trích đoạn, không khẳng định bao phủ toàn bộ chương 5 hoặc toàn bộ Table Partitioning.
- Trang 151 có ít hơn 1.500 ký tự nhưng có nội dung RETURNING hữu ích; ngưỡng 1.500 ký tự không áp dụng cho PDF.
- Các trang khác ngoài phạm vi được giữ bản ghi và lý do loại; bìa và front matter không được tính.

Đã xem nội dung trích xuất các trang chọn: văn bản kỹ thuật/SQL, không phải bìa, mục lục, trang trống hoặc trang chỉ có tham khảo. Các tên và số điện thoại trong ví dụ SQL là ví dụ xuất bản sẵn của tài liệu gốc, không phải dữ liệu cá nhân do bài lab thu thập hoặc corpus giả do học viên tạo.
