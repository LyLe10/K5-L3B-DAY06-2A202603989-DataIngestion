# Day06 — manual evaluation đã được người dùng xác nhận

**Trạng thái: nhãn manual và nội dung kỹ thuật đã được người dùng duyệt; chờ xác nhận diff/danh sách commit cuối.** Bốn file proposal được người dùng xác nhận trước khi nhập; bản gốc giữ trong workspace, không đưa `review_proposals/` vào commit. Chỉ thay trường chấm thủ công ở lượt nhập nhãn; giữ nguyên evidence, ID, số dòng và thứ tự. Không chạy lại model/retrieval/database, không thay benchmark, raw runs hoặc selection B.

## Kết quả tổng hợp

| Strategy | Coherence /2 (n=10) | Coherence 0/1/2 | Metadata đủ/đúng | Grounding 0/1/2 (n=5) | Grounding /2 | Top-3 trong scope TEST |
|---|---:|---|---|---|---:|---|
| A | 1.00 | 0 / 10 / 0 | 15/15 | 0 / 0 / 5 | 2.00 | 0/1, không áp dụng filter |
| B | 1.70 | 0 / 3 / 7 | 15/15 | 0 / 0 / 5 | 2.00 | 0/1, không áp dụng filter |
| C | 1.70 | 0 / 3 / 7 | 15/15 | 0 / 0 / 5 | 2.00 | 1/1, filter áp dụng |

Xem [summary.json](summary.json), [báo cáo cá nhân](../../report/individual/2A202603989_LeThiLy.md). Grounding là độ đủ evidence retrieval, không phải độ chính xác câu trả lời LLM. Metrics tự động và nhãn thủ công được giữ riêng.

## File và provenance

| File | Nội dung/trạng thái |
|---|---|
| [coherence.csv](coherence.csv) | 30 dòng H01–H10 × A/B/C, nhãn và lý do xác nhận |
| [metadata.csv](metadata.csv) | 45 hits TEST, các nhãn đủ/đúng và lý do xác nhận |
| [grounding.csv](grounding.csv) | 15 tổ hợp TEST × strategy, nhãn/lý do/supporting IDs xác nhận |
| [filter_review.csv](filter_review.csv) | 3 dòng `pg16-t04` × A/B/C; scope khác enforcement |
| [coherence_evidence.md](coherence_evidence.md) | 20 chunks nguyên văn và ngữ cảnh; C trỏ tới B, giữ nguyên |
| [test_evidence.md](test_evidence.md) | 5 TEST questions/gold, 45 chunks top-3 nguyên văn, giữ nguyên |
| [retrieval_metrics.csv](retrieval_metrics.csv) | 6 dòng DEV/TEST exact metrics/timing, giữ nguyên |
| [retrieval_traces.jsonl](retrieval_traces.jsonl) | 60 traces phái sinh có gold để review, giữ nguyên |
| [provenance.json](provenance.json) | Snapshot lịch sử lúc tạo hồ sơ chưa chấm; không sửa thành lịch sử giả |
| [summary.json](summary.json) | Thống kê mới từ labels xác nhận, nguồn proposal và lịch sử runs |
| [finalization_validation.json](finalization_validation.json) | Đối chiếu proposal/gốc, checksum, các kiểm tra hoàn thiện |
| [NOTICE.txt](NOTICE.txt) | Quyền PostgreSQL, giữ kèm trích đoạn |

`original_trace_sha256` ở JSONL liên kết trace raw gốc, không phải checksum của record phái sinh. Không dùng bản review có gold làm input retrieval. Raw artifacts `dev-002`/`test-001` và `selection_freeze.json` không đổi.

Các proposal chưa cung cấp `reviewer`/`reviewed_at`; giữ trống thay vì tự gán danh tính/ngày. Họ tên được cung cấp cho STUDENT không dùng để tự sửa provenance chấm thủ công. Căn cứ xác nhận là lời người dùng trong cuộc trao đổi, không phải người chấm độc lập. Lý do coherence vẫn giữ chữ “Đề xuất” nguyên từ file đã xác nhận. Proposal filter đổi cách viết boolean máy sang `True/False`; giữ nguyên `true/false` trong evidence gốc, chỉ nhập nhãn/lý do manual. Nhãn manual được đọc boolean không phân biệt hoa/thường. Status/remaining requirements trong JSON provenance, summary và validation là snapshot lịch sử tại lần tạo; không sửa các kết quả này để cập nhật trạng thái hành chính. Diff tạm không thuộc submission.

## Phương pháp theo GUIDE/BENCHMARK

Căn cứ: [GUIDE §4–5](../../GUIDE.md), [BENCHMARK](../../BENCHMARK.md), [RUBRIC](../../RUBRIC.md), [REPORT_TEMPLATE](../../REPORT_TEMPLATE.md), [SUBMISSION](../../SUBMISSION.md).

### Coherence

Giữ [10 anchors](../coherence_anchors.csv) ở trang vật lý 97–106, offset `floor(length/2)`, tính từ 0 trên Unicode text chuẩn hóa. Chunk chứa anchor thỏa `start<=offset<end`; chọn start nhỏ nhất rồi chunk ID. C dùng đúng chunk B và labels xác nhận giống B. Không đổi mẫu sau khi thấy kết quả.

Thang 0: cắt ý/thiếu chủ thể không hiểu; 1: hiểu phần nào nhưng thiếu ngữ cảnh; 2: tự hiểu và giữ trọn ý. Mỗi strategy n=10, mean=sum(label)/10. Cả mẫu chỉ Data Definition; không tuyên bố đại diện toàn corpus.

### Metadata usefulness và filter

Audit đủ 5 TEST × top-3 mỗi strategy. `source`, trang vật lý/nhãn in và section khớp manifest theo labels xác nhận; 15/15 cho từng strategy. Cột `automatic_` vẫn là đối chiếu máy, khác với nhãn manual. Metadata đúng không đồng nghĩa hit liên quan câu hỏi.

Usefulness: URL/trang/chunk ID giúp truy nguồn; section giúp giữ scope. `pg16-t04` yêu cầu Data Manipulation: A trả 1/3 hits đúng scope, B 2/3, C 3/3. C đạt 1/1 câu TEST tuân thủ scope, không có empty results. A/B có scope compliance 0/1 nhưng filter enforcement là **N/A**, vì baseline không áp dụng filter. Không coi A/B là lỗi triển khai filter. Mẫu không có câu filter phải N/A; không tự tính retrieval rỗng là thành công.

Hạn chế: section ở mức chương, không ở tiểu mục; URL nguồn có thể đổi snapshot; đúng metadata không bảo đảm đủ evidence. C không tăng Hit@3/grounding trên mẫu này vì B đã lấy được hit đúng trong top-3.

### Grounding

5 TEST × A/B/C. Thang 0: không evidence; 1: thiếu điều kiện/ngữ cảnh; 2: đủ trả lời và truy nguồn. Có 5 mức 2 cho mỗi strategy theo proposal xác nhận, kèm supporting IDs thực sự thuộc top-3 và chứa quote gold. Không suy nhãn từ Hit@3 hoặc similarity. Không đo output LLM.

### Retrieval và strategy impact

DEV A=5/15 Hit@1, 7/15 Hit@3; B/C=7/15, 10/15. TEST cả ba=4/5, 5/5. B đã chọn bằng DEV trước TEST. A–B cải thiện coherence/DEV retrieval nhưng thêm 18 chunks; B–C giữ vectors, cải thiện scope mà metrics chính hòa. Chi tiết tài nguyên, hai ví dụ lỗi và giới hạn ở báo cáo cá nhân.

Hai ví dụ kiểm chứng: `pg16-d01` A thiếu đầu gold span dù đúng trang (JSONL dòng 1); `pg16-t05` B có gold ở rank 2, không ở rank 1 (dòng 59). Không tự adjudicate hoặc sửa exact metrics.

AI/Codex hỗ trợ bảng/trích xuất/tổng hợp; người dùng xác nhận proposals. Không tuyên bố review mù/độc lập; có nguy cơ thiên lệch vì người chấm xem được metrics. `dev-001` INCOMPLETE/0 traces được ghi ở run history và không dùng chọn strategy.

## Trạng thái submission

Đã cập nhật experiment log hồi cứu, README và báo cáo theo mẫu, không ghi giả thuyết hồi cứu thành preregistration. Họ tên và nội dung kỹ thuật đã được xác nhận. Còn xác nhận diff/danh sách file cuối, chốt commit, kiểm quyền truy cập repo và nộp link theo kênh lớp. Không commit/push lượt này.
