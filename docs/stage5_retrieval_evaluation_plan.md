# Stage 5.1 — Retrieval & Evaluation Protocol

Trạng thái: **protocol để review; chưa cho phép triển khai Stage 5.2–5.8**.

Baseline bất biến: `19ebfa1010002f7f725af7b8b8d881ed77259fd5`. Stage 4 đã hoàn thành embedding/schema/ingestion. Các số liệu 40 trang, A=246, B=264, 1 profile và 2 complete snapshots được kế thừa từ [evidence apply](../results/full_corpus_apply.json), không phải kết quả truy vấn database mới của Stage 5.1.

## Quy ước trạng thái và căn cứ

- **APPROVED**: quyết định người dùng đã xác nhận hoặc contract Stage 4 đã nghiệm thu; không đồng nghĩa cho phép chạy model/database trong checkpoint tài liệu này.
- **REQUIRED**: yêu cầu bắt buộc có căn cứ trong đề lab, không phải tiêu chí tự đặt thêm.
- **PROPOSED**: thiết kế cụ thể còn chờ duyệt trước khi triển khai hoặc chạy thí nghiệm. Việc mô tả trong tài liệu này không tự phê duyệt nó.

Căn cứ: [README](../README.md), [GUIDE](../GUIDE.md), [BENCHMARK](../BENCHMARK.md), [RUBRIC](../RUBRIC.md), [RULES](../RULES.md), [SUBMISSION](../SUBMISSION.md), [kế hoạch Stage 4](stage4_embedding_pgvector_plan.md), [hướng dẫn tái lập](stage4_reproduction.md). Không tìm thấy file `STAGE5_READINESS_REVIEW` riêng trong repository khi lập protocol; readiness review trong cuộc trao đổi là bối cảnh, không phải một spec bổ sung đã commit.

## A. Lab requirements và deliverables

### A.1. REQUIRED — phạm vi bắt buộc

| Yêu cầu | Căn cứ | Minh chứng nghiệm thu cuối |
|---|---|---|
| Tối thiểu 30 trang hữu ích, nguồn/quyền, manifest, truy vết | GUIDE §1; SUBMISSION | Tái sử dụng baseline 40 trang và checksum; không thay corpus để cải thiện điểm |
| Ít nhất ba cấu hình trên cùng corpus/model/store/metric cosine | GUIDE §3; RUBRIC | A/B/C chạy đủ, ghi tham số; A–B thay chunking, B–C chỉ thay filtering trong thiết kế đã chọn |
| Embedding thật, lưu bền vững, vector search và metadata filter | GUIDE §3; SUBMISSION | Tái sử dụng Stage 4, bổ sung retrieval thật; backend lỗi phải báo, không fallback mock |
| Ít nhất 20 câu, tối thiểu 15 dev/5 test, ít nhất 3 câu filter và ít nhất 1 test filter | BENCHMARK; GUIDE §2 | Benchmark/gold được kiểm chứng và split trước thí nghiệm retrieval |
| Câu hỏi có đáp án, nguồn/trang và evidence đủ; chấp nhận alternative gold hợp lệ | BENCHMARK | Evidence thực sự có trong nguồn sau chuẩn hóa; không lấy gold answer/source làm query/filter |
| Top-3 trace cho mọi câu và mọi chiến lược; Hit@1/Evidence Hit@3 riêng dev/test | GUIDE §4 | Số tử/mẫu, rank, chunk ID/text, score, metadata, evidence/nhãn; lỗi chạy được ghi đầy đủ |
| Coherence, metadata usefulness/correctness, grounding và strategy impact | GUIDE §4; RUBRIC | Mẫu/nhãn/lý do thủ công và phân tích năm khía cạnh, không thay bằng Hit@3 |
| Lệnh chạy, config, versions, chi phí, log lỗi, báo cáo cá nhân | GUIDE §5; SUBMISSION | Experiment log, artifacts đủ tái lập, báo cáo theo mẫu và giới hạn trung thực |

**REQUIRED:** rubric chấm bằng chứng và phương pháp, không quy định một ngưỡng Hit@3 tối thiểu. Không tự đặt chất lượng cao làm điều kiện PASS kỹ thuật; không tạo số liệu hoặc nhãn để đạt điểm.

### A.2. APPROVED — quyết định chính của Stage 5

- Corpus, questions, expected answers và evidence quotes của **benchmark chính đều tiếng Anh**. Evidence quotes phải được xác minh với corpus tiếng Anh.
- Không dùng câu hỏi tiếng Việt trong benchmark chính. Cross-lingual chỉ là optional extension, tách khỏi kết quả chính.
- Giữ nguyên embedding model/profile, corpus, manifest, chunks, IDs và metadata Stage 4. Không encode lại toàn corpus.
- Stage 5.1 chỉ tạo tài liệu này; không tạo câu hỏi, chạy model, truy cập PostgreSQL hoặc thay source/tests/evidence.

### A.3. PROPOSED — mở rộng tùy chọn, không phải điều kiện lab

MRR@3 là metric bổ sung đang đề xuất. Recall@K cần một định nghĩa đơn vị gold riêng nếu bổ sung sau; không dùng nó thay Hit@1/Hit@3. Hybrid/BM25 là mở rộng tùy chọn được GUIDE nêu, không thuộc baseline hiện tại. Cross-lingual, ANN search hoặc sinh câu trả lời LLM không thuộc benchmark chính. Không bắt buộc xây chatbot.

### A.4. REQUIRED / PROPOSED — artifacts cuối

**REQUIRED theo SUBMISSION:** benchmark và gold, cấu hình A/B/C, `artifacts/experiment_log.csv`, top-3 traces, metrics dev/test, nhãn audit, log lỗi, README và báo cáo cá nhân. Hoàn thiện `STUDENT.md` và báo cáo cá nhân ở bước nộp bài.

**PROPOSED về định dạng/vị trí:** schema và JSONL benchmark trong `benchmark/`; run manifest, metrics và bảng nhãn trong `results/`; traces đầy đủ có text cùng query cache trong `data/local/stage5/`. Các tên file cụ thể chốt ở checkpoint tương ứng. Bản submission phải cung cấp trace được phép chia sẻ hoặc cách tái tạo theo quyền dữ liệu; không chỉ giữ local mà bỏ khả năng kiểm chứng của người chấm.

## B. Retrieval contract

### B.1. APPROVED — kế thừa thiết kế Stage 4

| Strategy được yêu cầu | Namespace lưu trữ | Chunking | Filter retrieval |
|---|---|---|---|
| A | `day06-postgresql` / profile cố định / A | Fixed-size 500 ký tự, overlap 50; 246 chunks | Không filter |
| B | Cùng dataset/profile / B | Paragraph-aware, max_size 500; 264 chunks | Không filter |
| C | Chính namespace B | Chính chunks/IDs/vectors B | Section equality khi input có filter |

C không tạo namespace, rows, IDs hoặc vectors riêng. Với cùng query vector, K và snapshot, C không có filter phải trả đúng kết quả B, gồm thứ tự và scores. `_chunking.strategy` của chunk B vẫn là B dù trace được gắn requested strategy C.

- Model `intfloat/multilingual-e5-small`, revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`.
- Profile ID `528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651`.
- Query input: `query: ` + question nguyên văn. Prefix không được lặp hai lần hoặc thêm vào gold/evidence.
- CPU float32/eval, mean pooling và L2 normalization; 384 chiều, finite, norm gần 1 trong tolerance `1e-5`.
- Kiểm tra giới hạn hiệu dụng 512 token, kể cả prefix và special tokens, trước encode; không silent truncation.
- Exact cosine bằng pgvector `embedding <=> query_vector`; `score = 1 - cosine_distance`, không phải xác suất hoặc grounding score.
- Benchmark chạy **Top-K=3** theo GUIDE. Giữ public signature `search(strategy, query_vector, top_k=3, filters=None)` hiện có.
- `ORDER BY cosine_distance ASC, chunk_id ASC`; không dựa vào thứ tự vật lý database hoặc làm tròn score để xếp hạng.
- Dataset/profile/stored strategy bắt buộc trong WHERE. Section predicate áp dụng **trước SQL LIMIT**, mọi giá trị dùng parameter binding. Không dùng Python similarity thay vector store và không thêm ANN index/migration mới trong thiết kế này.

### B.2. PROPOSED — compatibility, kết quả và safety cụ thể

- Orchestrator đối chiếu profile của query producer với store và canonical config trong database. Dimension/norm không đủ chứng minh một vector đến từ đúng model; trace phải có producer profile và input hash. Không tự suy model từ vector.
- Kết quả gồm rank, chunk ID, document ID, source, physical page, printed label nếu có, section, text, offsets, metadata, snapshot ID, cosine distance và score; không trả vectors. Trace phân biệt `requested_strategy` và `stored_strategy`.
- Chỉ hỗ trợ filter `section`; giá trị lấy từ câu hỏi hoặc context có trước retrieval, không suy từ gold. Không tự đoán section theo đáp án.
- Đề xuất từ chối nonempty filters cho A/B để tránh thay baseline vô ý; runner chỉ truyền filter cho C. Khóa không hỗ trợ, K không hợp lệ hoặc filter sai kiểu phải báo lỗi.
- Filter hợp lệ không có hàng phù hợp trả `[]`; ít hơn ba hàng thì giữ số thực tế, không bổ sung hàng ngoài phạm vi. Cách tính filter compliance với kết quả rỗng được chốt ở D.3.
- Trước run: kiểm tra migration/checksum/catalog, canonical profile, ledger complete, expected/actual counts, A/B compatibility và corpus/manifest identity. So sánh count/ID/provenance với baseline đã xác minh; không coi chỉ snapshot ID là bằng chứng vector đúng vì snapshot ID không chứa vector.
- Dùng transaction read-only và cùng snapshot nhất quán khi so sánh A/B/C; đề xuất repeatable-read cùng helper compatibility trên cùng connection, giữ shared namespace locks trong thứ tự xác định nếu sử dụng contract này. Cách giữ transaction theo query hay theo run cần duyệt trước coding, kèm timeout để không giữ khóa quá lâu.
- Retrieval runner không gọi `create`/migration/register/sync/upsert/delete, không tự repair schema, không tự ingest khi thiếu dữ liệu. Kết nối database thật cần phê duyệt riêng ở 5.4.
- Backend/model lỗi, migration drift, profile mismatch, ledger syncing/incompatible, query rỗng/overflow hoặc vector sai phải fail rõ ràng và có log; không fallback, không đổi model và không bỏ câu lỗi âm thầm.

## C. Benchmark protocol

### C.1. REQUIRED và APPROVED — nội dung và holdout

- **REQUIRED:** ít nhất 20 câu answerable từ corpus; tối thiểu 15 dev/5 test, ít nhất ba câu filter và ít nhất một câu filter thuộc test.
- **APPROVED:** question, expected answer, evidence quote đều tiếng Anh; metadata section giữ giá trị nguồn tiếng Anh.
- **REQUIRED:** mỗi câu có `id`, `split`, `question`, `expected_answer`, `gold_source_id`, `gold_page`, `evidence_quote`, và `filter` khi dùng. Physical page bắt đầu từ 1; không nhầm printed label.
- **REQUIRED:** evidence có thật trên normalized page và đủ điều kiện/ngoại lệ để hỗ trợ đáp án. Nếu nhiều nguồn/trang hợp lệ, ghi alternatives và chấp nhận bất kỳ alternative đủ bằng chứng nào.
- **REQUIRED:** gold độc lập với chunking; source/page/evidence là căn cứ, không lấy chunk ID A/B làm gold chính. Không dùng câu không có đáp án trong nguồn cho metric bắt buộc.
- **REQUIRED:** split, gold và tiêu chí chọn strategy được xác định trước thí nghiệm retrieval. Không điều chỉnh retrieval/chunking/model/filter từ kết quả test. Nếu test đã được xem để sửa, công bố contamination; tạo test mới nếu có thể theo RULES, không tiếp tục gọi tập cũ là holdout độc lập.

### C.2. PROPOSED — phương án cho 5.2

- Bắt đầu đúng 20 câu: 15 dev/5 test, ít nhất 2 dev filter và 1 test filter. Đây là lựa chọn thiết kế tối thiểu, không phải giới hạn tối đa của lab.
- Phủ câu trực tiếp, diễn đạt lại, điều kiện/ngoại lệ và phân biệt phạm vi section; không áp đặt tỷ lệ loại câu vì BENCHMARK không yêu cầu tỷ lệ đó.
- Chia nhóm chủ đề khi khả thi, tránh câu dev/test gần như trùng nhau. Ghi giới hạn rò rỉ do cùng tài liệu và chỉ hai section; không tuyên bố độc lập theo document nếu không có.
- Bổ sung schema cho alternatives, offsets `[start_char,end_char)` trên trang chuẩn hóa, lý do filter/context, reviewer và trạng thái evidence review. Các trường bổ sung này chờ duyệt, không phải trường bắt buộc của đề.
- Validator kiểm tra schema/ID/split/page/checksum/quote/offset/filter; kiểm tra ngôn ngữ và tính đủ của đáp án/evidence vẫn cần người duyệt. Không coi detector tiếng Anh hoặc substring match là chứng nhận nội dung đúng.
- Tách file dev/test và khóa benchmark/config bằng SHA-256. Cho phép người soạn kiểm chứng gold test trước run nhưng không xem retrieval test trong giai đoạn điều chỉnh dev. CLI đề xuất yêu cầu freeze manifest đã duyệt mới chạy test; không tự chạy test khi chạy dev.

## D. Evaluation protocol

### D.1. REQUIRED — retrieval accuracy

Một hit khi **một chunk** thuộc source/page gold hợp lệ và chứa đủ evidence đã ghi, hoặc bằng chứng tương đương được người chấm xác nhận. Không tính hit chỉ vì đúng page hoặc chứa một từ khóa.

- `Hit@1 = số câu có top-1 hit / tổng số câu`.
- `Evidence Hit@3 = số câu có ít nhất một chunk hit ở rank 1..3 / tổng số câu`.
- Báo riêng từng strategy và dev/test, ghi tử số/mẫu số cùng tỷ lệ. Không đếm các overlap chunks như nhiều câu đúng.
- Evidence bị tách qua nhiều chunk là failure case của định nghĩa chính. Có thể báo multi-chunk evidence coverage bổ sung, không thay Hit@3 chính.

**PROPOSED:** kiểm tra source/page cùng span/quote coverage tự động cho trường hợp xác định được; lưu trạng thái cần review khi bằng chứng tương đương không khớp chính xác. Không tự suy equivalence từ score. Khóa mọi quyết định relevance trước khi tổng hợp metric cuối, ghi reviewer/lý do/alternative được chấp nhận.

### D.2. REQUIRED — manual audits

| Khía cạnh | Mẫu và thang điểm theo GUIDE | Output |
|---|---|---|
| Coherence | Cùng 10 vị trí nguồn được chọn trước khi xem điểm; 0: cắt ý/thiếu chủ thể; 1: hiểu một phần; 2: tự hiểu được, giữ trọn ý | Vị trí, chunk được chọn, nhãn/lý do, trung bình /2 |
| Metadata correctness/usefulness | 5 câu test × top-3 mỗi strategy; đối chiếu source/page/section và trường cần thiết với nguồn | Đủ và đúng `n/N`, lỗi từng record, ích lợi và hạn chế của metadata |
| Filter compliance | Trên các câu có filter: số câu có top-3 tuân thủ / số câu có filter; không có câu filter thì N/A | Tử/mẫu, lỗi và phạm vi đo |
| Grounding | Cùng 5 câu test mỗi strategy; 0: không bằng chứng; 1: thiếu điều kiện/context; 2: đủ trả lời và truy nguồn | Số lượng mức 0/1/2, trung bình /2, lý do từng câu |
| Strategy impact | So sánh A–B và B–C về retrieval, audits, tài nguyên, lỗi và đánh đổi | Lý do chọn trên dev, kết quả test sau freeze, giới hạn mẫu nhỏ |

**REQUIRED:** không tự tạo nhãn coherence/grounding; Hit@3 hoặc similarity không thay người chấm. Ghi người chấm là tác giả nếu đúng và nguy cơ thiên lệch; nếu dùng AI hỗ trợ phải công bố phương pháp và cách kiểm tra. Grounding đánh giá evidence truy xuất, không phải độ chính xác câu trả lời LLM.

**PROPOSED:** chọn 10 source anchors và quy tắc chọn chunk khi overlap trước audit, giữ cùng anchors cho A/B/C; C dùng cùng chunks B trong coherence audit, không giả lập khác biệt chunking. Báo cáo SQL lỗi Stage 3 có thể dùng minh họa failure, không thay mẫu coherence đại diện đã chọn trước.

### D.3. PROPOSED — quyết định còn mở về metric

- MRR@3: `mean(1 / rank_hit_đầu_tiên)` trong top-3, không hit thì 0; dùng cùng định nghĩa hit với D.1. Chưa mặc định bật, không bắt buộc theo rubric.
- Với filtered query trả rỗng, đề xuất filter compliance là 0 thay vì coi tập rỗng tự động tuân thủ 100%; ghi thêm empty-result count. Cách này phải được duyệt trước run. Metadata correctness dùng số records thực sự kiểm tra làm mẫu số, đồng thời công bố số records thiếu so với tối đa 15 cho mỗi strategy.
- Chỉ đo quality trên run hoàn tất theo protocol; lỗi backend không được biến thành synthetic hits hoặc bỏ khỏi mẫu số để làm tăng điểm. Đề xuất đánh dấu run incomplete, báo attempted/succeeded/failed và dừng tổng kết cuối cho đến khi xử lý có duyệt; kết quả rỗng hợp lệ vẫn là retrieval miss.
- Đề xuất tiêu chí chọn trên **dev**: Evidence Hit@3, sau đó Hit@1, sau đó latency. Không dùng grounding test hoặc metric test để chọn strategy. Cách phá hòa và số lần đo cần duyệt trước thí nghiệm.

## E. Experiment protocol

### E.1. APPROVED / REQUIRED — tính công bằng

**APPROVED:** dùng cùng query vector cho A/B/C, không encode câu hỏi ba lần vì có ba strategy. Không encode lại corpus; C dùng embeddings B. **REQUIRED:** cùng corpus/model/questions/gold/store/cosine và định nghĩa metric giữa strategies; chỉ thay các yếu tố đã công bố.

### E.2. PROPOSED — latency và cache

- Query cache mới dưới `data/local/stage5/embedding_cache/`, cùng key profile + SHA-256 input đã prefix; không ghi đè cache hoặc artifact Stage 4.
- Ghi riêng model load, tokenization/encode, cache lookup, retrieval round-trip và tổng thời gian theo định nghĩa công khai. Một query embedding dùng chung không được tính như ba lần encode thật.
- Tách cold start/warm-up khỏi measured run; xoay thứ tự A/B/C với seed cố định. Đề xuất 5 measured repetitions sau warm-up, báo median/p95 cùng số mẫu; số lần/seed chưa được phê duyệt. p95 trên mẫu nhỏ chỉ mang tính mô tả.
- Không trộn cache hit cho một strategy với encode miss cho strategy khác để kết luận nhanh/chậm. Ghi trạng thái cache, timings guard/connection và phạm vi stopwatch.
- Giữ riêng quá trình semantic evaluation và các lần lặp latency; không đổi gold/config giữa repetitions. Query test chỉ được chạy sau dev freeze, kể cả chạy để đo latency.

### E.3. REQUIRED / PROPOSED — trace schema và run identity

**REQUIRED:** lưu question, chunk IDs/text, ranks/scores, metadata và evidence/nhãn top-3; cấu hình, split và thời điểm chạy phải truy vết được.

**PROPOSED schema logic**, chưa phải file dữ liệu và không chứa kết quả giả:

| Cấp | Trường đề xuất |
|---|---|
| Run manifest | run_id, code commit/dirty state, benchmark/config hashes, manifest/corpus hashes, dataset/profile IDs, A/B snapshot IDs, migration checksum/catalog fingerprint, library versions, timestamp, metric version, seed và latency protocol |
| Query | question_id, split, English question, requested filter/context, query input hash, token count, producer profile, cache receipt, timings và status/error |
| Strategy result | requested/stored strategy, snapshot_id, top_k=3, applied filter, elapsed time, returned count và ordered hits |
| Hit | rank, chunk_id, document_id, source, physical_page/printed label, section, offsets, text/checksum, metadata, cosine_distance, score |
| Evaluation | accepted gold/alternative, hit decision/rank, automatic vs manual decision, reviewer, rationale và audit labels khi đã có |

Gold nằm trong evaluator/trace sau retrieval, không nằm trong query builder hoặc SQL filter derivation. Không lưu raw vectors, model weights, connection string, credentials hoặc absolute personal paths trong trace công khai.

### E.4. REQUIRED / PROPOSED — reproducibility, failure và publication

- **REQUIRED:** giữ model/config/benchmark giữa strategies, ghi dependencies/chi phí/versions, không giấu lỗi hoặc fallback. API cost bằng 0 khi thực tế chỉ local; không đồng nhất API cost 0 với toàn bộ compute/resource cost bằng 0.
- **PROPOSED:** dùng [lock Stage 4](../starter/requirements-stage4-linux-py312.lock) trên Linux x86_64/Python 3.12; để khớp profile hiện tại cần Python 3.12.3. Không tự nâng dependency hoặc đổi profile để chạy Stage 5.
- **PROPOSED:** failure taxonomy gồm evidence split, thiếu context/SQL bị cắt, sai scope filter, gold cần review, profile/snapshot drift, empty result, timeout và backend unavailable; lưu query/chunk IDs thay vì tự sửa corpus/chunking trong run.
- **REQUIRED:** chỉ công khai nội dung có quyền; giữ notice/điều khoản liên quan. Traces có text phải được rà trước submission. Nếu không chia sẻ được trace gốc, cung cấp cách lấy/tái tạo và output được phép, theo SUBMISSION.
- **PROPOSED:** raw traces/query cache ở local, bản summary/labels/config có thể commit sau security/license review; không commit PDF, weights, cache, `.env` hoặc secret. Không sửa 8 artifact local đã bảo vệ.
- **PROPOSED:** giữ ledger/snapshot identity suốt run; drift thì dừng, không tự sync/repair hoặc đổi dataset. A/B đã ingest bằng hai transaction riêng; chỉ so sánh khi cả hai compatible/complete. Không tuyên bố đã kiểm thử mất kết nối COMMIT hoặc PostgreSQL mới từ evidence cũ.

## F. Implementation checkpoints và cổng phê duyệt

Các hoạt động và tên file dưới đây là **PROPOSED**, không phải lệnh được phép thực hiện ở Stage 5.1. Tiêu chí nội dung benchmark/audit được đánh dấu REQUIRED ở các mục trên vẫn áp dụng.

| Checkpoint | Phạm vi/file dự kiến | PASS / FAIL và điểm dừng |
|---|---|---|
| 5.2 Benchmark & gold | Tạo `benchmark/` schema, questions, split/gold; validator/test tương ứng | Đủ câu/split/filter REQUIRED, English-only APPROVED, evidence/source/checksum khớp, có human review. Sai evidence/leakage thì FAIL. Dừng để duyệt gold và holdout trước retrieval experiments |
| 5.3 Retrieval implementation | Sửa `starter/src/store.py`, thêm retrieval unit tests; giữ public API Stage 3 | Test cosine SQL binding, namespace, ordering, filters, C→B/B=C và lỗi. Không bypass guard hoặc DDL. Dừng code review trước database test |
| 5.4 PostgreSQL integration | Runner/cases cô lập và retrieval smoke riêng | Synthetic tests kiểm chứng SQL thật trên PostgreSQL 16.16/pgvector 0.8.7; real query smoke chỉ sau phê duyệt model runtime và đọc database chính. Database chính chỉ read-only; không ingest/DDL. Dừng trước benchmark |
| 5.5 Evaluation implementation | Sửa `starter/src/evaluation.py`, thêm metric/trace tests và CLI | Fixture tests chứng minh hit đủ evidence, alternatives, split evidence failure, aggregation/split và error handling; không coi fixture là quality result. Dừng duyệt evaluator |
| 5.6 Dev benchmark | Dev traces, summary, experiment log, freeze manifest | Chạy đủ A/B/C với cùng inputs/snapshots; chỉ dev dùng chọn/tinh chỉnh. Run lỗi phải báo incomplete. Dừng duyệt cấu hình/metric freeze trước test |
| 5.7 Test & manual audit | Test traces, 10-anchor coherence labels, metadata và grounding labels | Test sau freeze; đủ nhãn/lý do REQUIRED, không điều chỉnh strategy từ test. Dừng nghiệm thu kết quả và giới hạn |
| 5.8 Final submission | README, STUDENT, experiment log, báo cáo cá nhân, artifacts được phép | Đủ năm khía cạnh và khả năng tái lập, ví dụ lỗi/đánh đổi/chi phí; secret/license review. Dừng trước stage/commit/push, cần duyệt riêng |

**PROPOSED:** ưu tiên CLI retrieval/evaluation riêng, chưa biến `run.py` thành pipeline tự động có thể ingest lại. Nếu cần thay schema, baseline, query model, benchmark test sau freeze hoặc API ngoài phạm vi, dừng và xin duyệt; không tự tạo migration mới.

## G. Các quyết định còn cần phê duyệt

1. Chốt đúng 20 câu hay nhiều hơn; phân nhóm dev/test, quy trình người duyệt và schema gold alternatives/offsets.
2. Nonempty filter cho A/B bị từ chối; hành vi empty-result/filter compliance; giới hạn Top-K ngoài benchmark nếu mở API dùng chung.
3. Thời hạn transaction/read snapshot, shared-lock/timeout và quyền kết nối read-only ở 5.4.
4. Bật MRR@3 hay chỉ metric REQUIRED; tiêu chí chọn dev và cách phá hòa.
5. Latency warm-up/repetitions/seed, các phạm vi stopwatch; vị trí query cache và trace cụ thể.
6. Quy tắc 10 source anchors và chọn overlap chunk; người chấm cùng quy trình xác nhận equivalent evidence.
7. Schema trace/run manifest, cơ chế freeze/test gate, nội dung được phép công khai và cách người chấm tái tạo raw trace.
8. Tên/phạm vi file implementation và thứ tự công việc; chấp thuận từng checkpoint trước khi thực hiện.

## H. Stage 5.1 acceptance

**REQUIRED cho checkpoint đã yêu cầu:** chỉ tài liệu này được thêm; các mục A–F có căn cứ và nhãn trạng thái; benchmark chính English-only; metric REQUIRED không bị thay bằng MRR/Recall; không có câu hỏi/nhãn/kết quả giả; không đổi source, migration, corpus hoặc evidence Stage 4. Đối chiếu rubric phải bao phủ corpus, ba cấu hình, benchmark/retrieval, năm khía cạnh và tái lập/báo cáo; không tự tuyên bố đã đạt điểm của phần chưa chạy.

Chạy kiểm tra whitespace và liên kết tài liệu, xác nhận Git scope đúng một file. Không chạy model/database/tests implementation ở Stage 5.1. Dừng để nghiệm thu protocol trước Stage 5.2.
