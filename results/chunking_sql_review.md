# SQL chunking review — baseline A/B

Trạng thái: 5 ví dụ SQL bị chia giữa chunk A và 5 ví dụ SQL tương ứng nằm trọn trong chunk B; lấy từ corpus PostgreSQL 16.16 thật.
Không thay thuật toán, corpus, manifest hoặc chunk artifacts. Không chấm điểm coherence/grounding và không tạo benchmark.

## Phương pháp và quy ước

- Dùng đúng A.jsonl và B.jsonl đã được chấp nhận ở giai đoạn 3. C dùng chính B nên không tạo ví dụ riêng.
- Chọn có chủ đích các câu SQL hoàn chỉnh trong một trang: không chunk A nào chứa trọn câu, nhưng có một chunk B chứa trọn câu. Sắp theo physical_page rồi SQL start offset và lấy 5 cặp đầu (7 cặp thỏa tiêu chí trong nhóm câu lệnh được rà soát). Đây là mẫu minh họa có điều kiện chọn, không phải mẫu đại diện hay phép đo chất lượng tổng thể.
- Mọi start_char/end_char là offset ký tự Unicode 0-based trong text trang đã chuẩn hóa; khoảng [start_char, end_char) không gồm ký tự tại end_char. physical_page bắt đầu từ 1.
- start_char/end_char của chunk là toàn bộ lát cắt chunk. excerpt_start_char/excerpt_end_char bên dưới là phần SQL được trích, không phải vị trí bắt đầu/kết thúc chunk.
- A overlap=50: hai đoạn SQL được trích có thể lặp 50 ký tự. Điều kiện chọn đã kiểm tra rằng không có một chunk A khác phục hồi đầy đủ cả câu.
- Đã kiểm tra SHA-256 PDF, checksum text các trang được chọn trong corpus và đối chiếu toàn bộ 510 chunk A/B với lát cắt text nguồn và metadata trước khi tạo báo cáo.
- 19 cờ split_sql_statement trên B là tín hiệu heuristic, không đồng nghĩa 19 câu SQL thực bị cắt. Rà soát cho thấy có cờ trên văn xuôi/bảng mô tả (ví dụ trang 100 và 114). Không dùng các cờ này làm nhãn gold; 5 ví dụ bị cắt ở đây thuộc A và được xác minh bằng offset câu SQL cụ thể.

document_id: `postgresql-16.16-a4`; source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf
PDF SHA-256: `4cf9a4f56001191572e07959396120de0d61ca65d29072df66f9e656c24ae568`
Manifest SHA-256: `6ec73dc52b8cb5d83f5b08baeffcb231109cc2bbd95525c3315ae72c1f29db5d`

## Danh sách cặp ví dụ

| Cặp | physical_page | section | SQL start | SQL end |
|---|---:|---|---:|---:|
| 1 | 97 | Data Definition | 2683 | 2756 |
| 2 | 98 | Data Definition | 2229 | 2313 |
| 3 | 101 | Data Definition | 886 | 1001 |
| 4 | 102 | Data Definition | 398 | 604 |
| 5 | 103 | Data Definition | 885 | 974 |

## Cắt 1 — A

- document_id: `postgresql-16.16-a4`
- physical_page: 97
- printed_page_label: `59`
- section: `Data Definition`
- SQL source span: [2683, 2756); 73 ký tự.
- Xác minh: câu SQL bị chia; không chunk A nào trên trang chứa đủ câu lệnh. Các fragment dưới đây là lát cắt nguyên văn, có overlap.

### Fragment A.1

- chunk_id: `A:bf337fb834b7989a51905d4a4c667577f3d049af67e7a8f3cac18eb592f05874`
- start_char: 2250
- end_char: 2750
- excerpt_start_char: 2683
- excerpt_end_char: 2750

```sql
CREATE TABLE my_first_table (
first_column text,
second_column inte
```

### Fragment A.2

- chunk_id: `A:fc645c1982ec315c9ed83896c48dbb2c141bdf5fb68269cad3b847a50596a548`
- start_char: 2700
- end_char: 3200
- excerpt_start_char: 2700
- excerpt_end_char: 2756

```sql
irst_table (
first_column text,
second_column integer
);
```

## Không cắt 1 — B

- document_id: `postgresql-16.16-a4`
- physical_page: 97
- printed_page_label: `59`
- section: `Data Definition`
- chunk_id: `B:b5ad29c6166964239e856792f3bd470a6fb06e3a35c0716d50047b2cb46afd54`
- start_char: 2670
- end_char: 3112
- excerpt_start_char: 2683
- excerpt_end_char: 2756
- Xác minh: toàn bộ câu SQL sau nằm trong một chunk B, không cần nối chunk.

```sql
CREATE TABLE my_first_table (
first_column text,
second_column integer
);
```

## Cắt 2 — A

- document_id: `postgresql-16.16-a4`
- physical_page: 98
- printed_page_label: `60`
- section: `Data Definition`
- SQL source span: [2229, 2313); 84 ký tự.
- Xác minh: câu SQL bị chia; không chunk A nào trên trang chứa đủ câu lệnh. Các fragment dưới đây là lát cắt nguyên văn, có overlap.

### Fragment A.1

- chunk_id: `A:f98fb0f03a05b38aa9c93e47a4afb62518cefb9c4c46f5366198d278082801f3`
- start_char: 1800
- end_char: 2300
- excerpt_start_char: 2229
- excerpt_end_char: 2300

```sql
CREATE TABLE products (
product_no integer,
name text,
price numeric DE
```

### Fragment A.2

- chunk_id: `A:8292878e9174119516993f55f05030e840de2449991200f9588c2b12f553f312`
- start_char: 2250
- end_char: 2710
- excerpt_start_char: 2250
- excerpt_end_char: 2313

```sql
 (
product_no integer,
name text,
price numeric DEFAULT 9.99
);
```

## Không cắt 2 — B

- document_id: `postgresql-16.16-a4`
- physical_page: 98
- printed_page_label: `60`
- section: `Data Definition`
- chunk_id: `B:d16656f576e01d0761765c48394f400205e9f1c94df43ea3254b947736502949`
- start_char: 2216
- end_char: 2710
- excerpt_start_char: 2229
- excerpt_end_char: 2313
- Xác minh: toàn bộ câu SQL sau nằm trong một chunk B, không cần nối chunk.

```sql
CREATE TABLE products (
product_no integer,
name text,
price numeric DEFAULT 9.99
);
```

## Cắt 3 — A

- document_id: `postgresql-16.16-a4`
- physical_page: 101
- printed_page_label: `63`
- section: `Data Definition`
- SQL source span: [886, 1001); 115 ký tự.
- Xác minh: câu SQL bị chia; không chunk A nào trên trang chứa đủ câu lệnh. Các fragment dưới đây là lát cắt nguyên văn, có overlap.

### Fragment A.1

- chunk_id: `A:31d49a98b24f5d35a7d32304ec268e58d112c9b8c20f8d86a91034694aa73906`
- start_char: 450
- end_char: 950
- excerpt_start_char: 886
- excerpt_end_char: 950

```sql
CREATE TABLE products (
product_no integer,
name text,
price num
```

### Fragment A.2

- chunk_id: `A:624c1199e68accb41511baeaf7abddfb8bd0ec9b474f5ae23fdb338ce5c0c0a5`
- start_char: 900
- end_char: 1400
- excerpt_start_char: 900
- excerpt_end_char: 1001

```sql
roducts (
product_no integer,
name text,
price numeric CONSTRAINT positive_price CHECK (price > 0)
);
```

## Không cắt 3 — B

- document_id: `postgresql-16.16-a4`
- physical_page: 101
- printed_page_label: `63`
- section: `Data Definition`
- chunk_id: `B:5bd0576c5d375f1144a8b2ba788acee8705346c59de2ae2e27b5e70af37330a8`
- start_char: 871
- end_char: 1273
- excerpt_start_char: 886
- excerpt_end_char: 1001
- Xác minh: toàn bộ câu SQL sau nằm trong một chunk B, không cần nối chunk.

```sql
CREATE TABLE products (
product_no integer,
name text,
price numeric CONSTRAINT positive_price CHECK (price > 0)
);
```

## Cắt 4 — A

- document_id: `postgresql-16.16-a4`
- physical_page: 102
- printed_page_label: `64`
- section: `Data Definition`
- SQL source span: [398, 604); 206 ký tự.
- Xác minh: câu SQL bị chia; không chunk A nào trên trang chứa đủ câu lệnh. Các fragment dưới đây là lát cắt nguyên văn, có overlap.

### Fragment A.1

- chunk_id: `A:eadba93116f82da63a34d30c32934cda28fa95a7b91252f867ac6bc52c3dd7af`
- start_char: 0
- end_char: 500
- excerpt_start_char: 398
- excerpt_end_char: 500

```sql
CREATE TABLE products (
product_no integer,
name text,
price numeric,
CHECK (price > 0),
discounted_pr
```

### Fragment A.2

- chunk_id: `A:a4ca5ae91d9c8acfafb3911aeea914cef443c9e258c4793bb5dde3b1383d2b92`
- start_char: 450
- end_char: 950
- excerpt_start_char: 450
- excerpt_end_char: 604

```sql
t,
price numeric,
CHECK (price > 0),
discounted_price numeric,
CHECK (discounted_price > 0),
CONSTRAINT valid_discount CHECK (price > discounted_price)
);
```

## Không cắt 4 — B

- document_id: `postgresql-16.16-a4`
- physical_page: 102
- printed_page_label: `64`
- section: `Data Definition`
- chunk_id: `B:7c3322cc1c9ad1b3f2ae10b481e43270f2c37c80cf1dc0097b74e96bf361ce73`
- start_char: 316
- end_char: 722
- excerpt_start_char: 398
- excerpt_end_char: 604
- Xác minh: toàn bộ câu SQL sau nằm trong một chunk B, không cần nối chunk.

```sql
CREATE TABLE products (
product_no integer,
name text,
price numeric,
CHECK (price > 0),
discounted_price numeric,
CHECK (discounted_price > 0),
CONSTRAINT valid_discount CHECK (price > discounted_price)
);
```

## Cắt 5 — A

- document_id: `postgresql-16.16-a4`
- physical_page: 103
- printed_page_label: `65`
- section: `Data Definition`
- SQL source span: [885, 974); 89 ký tự.
- Xác minh: câu SQL bị chia; không chunk A nào trên trang chứa đủ câu lệnh. Các fragment dưới đây là lát cắt nguyên văn, có overlap.

### Fragment A.1

- chunk_id: `A:8d7e4364d8f77a5347cf29fe86cbb6b0a654f22db8212788967625eb0f4891ca`
- start_char: 450
- end_char: 950
- excerpt_start_char: 885
- excerpt_end_char: 950

```sql
CREATE TABLE products (
product_no integer NOT NULL,
name text NO
```

### Fragment A.2

- chunk_id: `A:1c139e8f9b26ae9e0f5a5f98cf3a72b390fd752de60bde7dd8318d1f41a65b7b`
- start_char: 900
- end_char: 1400
- excerpt_start_char: 900
- excerpt_end_char: 974

```sql
oducts (
product_no integer NOT NULL,
name text NOT NULL,
price numeric
);
```

## Không cắt 5 — B

- document_id: `postgresql-16.16-a4`
- physical_page: 103
- printed_page_label: `65`
- section: `Data Definition`
- chunk_id: `B:f619e42075c0d7b00078f8ff401575e3e173ec99da456a30899beb1450874af0`
- start_char: 867
- end_char: 1326
- excerpt_start_char: 885
- excerpt_end_char: 974
- Xác minh: toàn bộ câu SQL sau nằm trong một chunk B, không cần nối chunk.

```sql
CREATE TABLE products (
product_no integer NOT NULL,
name text NOT NULL,
price numeric
);
```

## Tính bất biến và giới hạn

- SHA-256 trước/sau của chunking.py, ingestion.py, manifest, schema và hai chunk artifacts A/B đều không đổi.
- Không thực thi các câu SQL trích dẫn; không kết nối database hoặc tạo embedding trong bước rà soát này.
- Người rà soát: Codex, đối chiếu bằng text/offset/checksum; chưa có điểm hoặc nhãn audit thủ công của học viên.
- Các fragment không bổ sung ký tự vào SQL; newline dùng để đóng Markdown code fence chỉ phục vụ trình bày.
- Thời điểm tạo: 2026-11-14T03:43:17.292627+00:00.

## Nguồn và Legal Notice

SQL trích nguyên văn từ PDF PostgreSQL 16.16 A4. Giữ nguyên thông báo dưới đây từ trang vật lý 2 cùng các đoạn trích. Điều khoản online: https://www.postgresql.org/docs/16/legalnotice.html

```text
PostgreSQL 16.16 Documentation
The PostgreSQL Global Development Group
Copyright © 1996–2026 The PostgreSQL Global Development Group
Legal Notice
PostgreSQL Database Management System (also known as Postgres, formerly known as Postgres95)
Portions Copyright © 1996-2026, PostgreSQL Global Development Group
Portions Copyright © 1994, The Regents of the University of California
Permission to use, copy, modify, and distribute this software and its documentation for any purpose, without fee, and without a written
agreement is hereby granted, provided that the above copyright notice and this paragraph and the following two paragraphs appear in all copies.
IN NO EVENT SHALL THE UNIVERSITY OF CALIFORNIA BE LIABLE TO ANY PARTY FOR DIRECT, INDIRECT, SPECIAL,
INCIDENTAL, OR CONSEQUENTIAL DAMAGES, INCLUDING LOST PROFITS, ARISING OUT OF THE USE OF THIS SOFTWARE
AND ITS DOCUMENTATION, EVEN IF THE UNIVERSITY OF CALIFORNIA HAS BEEN ADVISED OF THE POSSIBILITY OF
SUCH DAMAGE.
THE UNIVERSITY OF CALIFORNIA SPECIFICALLY DISCLAIMS ANY WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. THE SOFTWARE PROVIDED
HEREUNDER IS ON AN “AS-IS” BASIS, AND THE UNIVERSITY OF CALIFORNIA HAS NO OBLIGATIONS TO PROVIDE
MAINTENANCE, SUPPORT, UPDATES, ENHANCEMENTS, OR MODIFICATIONS.
```
