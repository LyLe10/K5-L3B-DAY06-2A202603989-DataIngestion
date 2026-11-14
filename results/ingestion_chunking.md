# Kiểm tra Document Ingestion & Chunking

Kết quả: PASS

Trang được đọc: 40; trang bỏ qua: 3034.
Lỗi: 0; cảnh báo: 2.

| Cấu hình | Số chunk | Min | Mean | Max | Ký tự nguồn được phủ |
|---|---:|---:|---:|---:|---:|
| A | 246 | 62 | 462.077 | 500 | 103371/103371 |
| B | 264 | 58 | 391.557 | 499 | 103371/103371 |
| C | 264 | 58 | 391.557 | 499 | 103371/103371 |

A: fixed_size(size=500, overlap=50); B: by_paragraph(max_size=500). Đơn vị: ký tự Unicode.
ID ổn định khi chạy lại: True; C dùng chính danh sách B: True.
C chưa áp dụng filter vì chưa triển khai retrieval. Không có embedding, database ingestion hoặc benchmark.

## Trang được chọn

| PDF page | Printed label | Section | Characters | A chunks | B chunks |
|---:|---|---|---:|---:|---:|
| 97 | 59 | Data Definition | 3443 | 8 | 8 |
| 98 | 60 | Data Definition | 2710 | 6 | 6 |
| 99 | 61 | Data Definition | 2487 | 6 | 7 |
| 100 | 62 | Data Definition | 3386 | 8 | 8 |
| 101 | 63 | Data Definition | 2504 | 6 | 6 |
| 102 | 64 | Data Definition | 2252 | 5 | 6 |
| 103 | 65 | Data Definition | 2408 | 6 | 6 |
| 104 | 66 | Data Definition | 1808 | 4 | 5 |
| 105 | 67 | Data Definition | 1862 | 5 | 5 |
| 106 | 68 | Data Definition | 1974 | 5 | 5 |
| 107 | 69 | Data Definition | 1978 | 5 | 6 |
| 108 | 70 | Data Definition | 2997 | 7 | 8 |
| 109 | 71 | Data Definition | 2976 | 7 | 7 |
| 110 | 72 | Data Definition | 2848 | 7 | 7 |
| 111 | 73 | Data Definition | 2299 | 5 | 6 |
| 112 | 74 | Data Definition | 2041 | 5 | 5 |
| 113 | 75 | Data Definition | 2782 | 7 | 7 |
| 114 | 76 | Data Definition | 2933 | 7 | 7 |
| 115 | 77 | Data Definition | 2920 | 7 | 7 |
| 116 | 78 | Data Definition | 2296 | 5 | 7 |
| 117 | 79 | Data Definition | 2211 | 5 | 6 |
| 118 | 80 | Data Definition | 4119 | 10 | 11 |
| 119 | 81 | Data Definition | 2185 | 5 | 6 |
| 120 | 82 | Data Definition | 1918 | 5 | 5 |
| 121 | 83 | Data Definition | 2185 | 5 | 6 |
| 122 | 84 | Data Definition | 2320 | 6 | 6 |
| 123 | 85 | Data Definition | 2320 | 6 | 6 |
| 124 | 86 | Data Definition | 2703 | 6 | 7 |
| 125 | 87 | Data Definition | 2047 | 5 | 5 |
| 126 | 88 | Data Definition | 2644 | 6 | 6 |
| 127 | 89 | Data Definition | 3234 | 8 | 9 |
| 128 | 90 | Data Definition | 4024 | 9 | 10 |
| 129 | 91 | Data Definition | 1895 | 5 | 6 |
| 130 | 92 | Data Definition | 1962 | 5 | 5 |
| 131 | 93 | Data Definition | 4651 | 11 | 11 |
| 132 | 94 | Data Definition | 3573 | 8 | 9 |
| 148 | 110 | Data Manipulation | 2281 | 5 | 6 |
| 149 | 111 | Data Manipulation | 2472 | 6 | 6 |
| 150 | 112 | Data Manipulation | 2988 | 7 | 7 |
| 151 | 113 | Data Manipulation | 735 | 2 | 2 |

## Trang bỏ qua

- cover: 1 trang; số vật lý 1.
- legal_notice: 1 trang; số vật lý 2.
- front_matter: 36 trang; số vật lý 3–38.
- outside_selected_scope: 2996 trang; số vật lý 39–96, 133–147, 152–3074.

## Lỗi

- Không có.

## Cảnh báo và giới hạn

- Selected pypdf text has no blank-line paragraph delimiters; B uses sentence/line/word boundaries without changing normalized text.
- B has 19 boundaries inside detected SQL spans longer than 500 characters or continuing to the page end; inspect local chunks. SQL detection is heuristic.
- Không ghép qua trang vật lý; SQL đã bị ngắt tại ranh giới trang không được tự nối.
- Giữ nguyên text chuẩn hóa, kể cả header/footer và whitespace; không tự khôi phục paragraph hoặc sửa checksum.
- Coverage kiểm tra lát cắt và mọi ký tự, không phải điểm coherence/grounding.

Thời điểm: 2026-11-14T03:31:16.483769+00:00; thời gian chạy: 14.332 giây.
Môi trường: {'python': '3.12.3', 'pypdf': '6.21.4', 'jsonschema': '4.26.0'}.
Manifest SHA-256: `6ec73dc52b8cb5d83f5b08baeffcb231109cc2bbd95525c3315ae72c1f29db5d`.
Chunk chứa text chỉ lưu trong data/local/stage3/chunks/.
