# Đề xuất giai đoạn 4 — Embedding thật & pgvector

## Trạng thái thực hiện (cập nhật sau Checkpoint 4.3C-2)

Thiết kế gốc bên dưới được giữ nguyên như tài liệu lịch sử. Embedding, Migration 0001, PgVectorStore và full-corpus ingestion đã được nghiệm thu. Database có 1 profile, 2 complete snapshots và 510 chunks A/B; C không tạo dữ liệu riêng. Retrieval và benchmark chưa triển khai; các mục mô tả retrieval bên dưới vẫn là kế hoạch.

Bằng chứng: results/schema_apply.md, results/store_postgres_integration.md và results/full_corpus_apply.md. Hướng dẫn môi trường: [stage4_reproduction.md](stage4_reproduction.md).

Trạng thái: **chờ người dùng phê duyệt, chưa triển khai**. Baseline A/B đã được chấp nhận; không thay thuật toán, manifest, 40 trang corpus hay chunk IDs. Giữ nguyên C dùng chunk/vector của B; khác biệt C chỉ là metadata filtering lúc retrieval.

## 1. Model và cấu hình cố định

Đề xuất **intfloat/multilingual-e5-small**, chạy local bằng Sentence Transformers trên CPU, batch size ban đầu 16, float32, eval mode. Model có 384 chiều, giấy phép MIT, có hướng dẫn dùng prefix query/passage và L2 normalization; ví dụ tokenizer dùng giới hạn 512 token. Tham chiếu [model card chính thức](https://huggingface.co/intfloat/multilingual-e5-small). Lựa chọn đa ngữ nhằm thử câu hỏi tiếng Việt trên tài liệu tiếng Anh; chưa khẳng định chất lượng trên corpus này.

- Khóa revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`, được ghi trong [lịch sử repository model](https://huggingface.co/intfloat/multilingual-e5-small/commits/main). Không dùng main trôi nổi khi ingest. Sau khi được duyệt mới tải, kiểm tra revision, ghi checksum các artifact và license tại snapshot.
- Document input: `passage: ` + nguyên text chunk; query input: `query: ` + câu hỏi. Prefix chỉ phục vụ embedding, không sửa text gốc hoặc chunk_id.
- Preflight tokenize toàn bộ A/B với prefix và special tokens, không truncation. Nếu bất kỳ input vượt 512 token: dừng và trình phương án, không âm thầm cắt hoặc sửa baseline. Query quá dài cũng báo lỗi.
- L2-normalize cả document/query vectors. Kiểm tra đủ 384 giá trị hữu hạn, norm khác 0 và gần 1; batch phải trả đúng số lượng và thứ tự. Không fallback mock hoặc đổi model khi lỗi.
- Ghi model/revision, tokenizer, pooling, prefix, normalization và phiên bản thư viện trong cấu hình profile; profile_id là SHA-256 cấu hình chuẩn hóa. Giữ cùng profile cho A/B/C. C không embed lại.
- Sau duyệt: bổ sung Sentence Transformers/PyTorch CPU và pgvector Python adapter, khóa phiên bản thực tế đã kiểm tra. Cache model/vector chỉ ở data/local/, không đưa weights hoặc secret vào Git. Không dùng dịch vụ embedding trả phí; ghi thời gian tải/encode, số input/token, cache hit và chi phí API thực tế (0 nếu chỉ local).

## 2. Lưu trữ trong PostgreSQL hiện có

Preflight bằng DATABASE_URL local, xác minh database day6_lab, PostgreSQL/pgvector thực tế và quyền tạo schema; không reset database/volume. Dùng schema riêng `day6_ingestion`, không thay dữ liệu của bài khác. Chưa chạy DDL trong bước lập kế hoạch.

| Bảng | Thiết kế dự kiến |
|---|---|
| embedding_profiles | profile_id PK, model_name, revision, dimensions CHECK=384, cấu hình encode JSONB và library versions; không trộn các profile |
| chunks | dataset_id, profile_id FK, strategy CHECK IN ('A','B'), chunk_id, document_id, source, physical_page CHECK>0, printed_page_label nullable, section, text, text_sha256, source_sha256, manifest_sha256, metadata JSONB, embedding vector(384); PK(dataset_id, profile_id, strategy, chunk_id) |

- Dataset mặc định: `day06-postgresql`. Giữ toàn bộ metadata gốc gồm page_id, section_evidence, version, normalized character count, text checksum và `_chunking` offsets; các cột typed lấy từ cùng metadata, kiểm tra khớp trước khi ghi.
- C ánh xạ sang các hàng strategy B, không tạo ID hoặc vector C thứ ba. Dự kiến sau ingest: **246 hàng A + 264 hàng B = 510 hàng**, C đọc lại 264 hàng B.
- B-tree theo dataset/profile/strategy/section để hỗ trợ phạm vi và filter. Giai đoạn này dùng **exact cosine search**, chưa HNSW/IVFFlat; phù hợp quy mô hiện tại và tránh khác biệt approximate search trong so sánh A/B/C. [pgvector 0.8.7 README](https://github.com/pgvector/pgvector/blob/v0.8.7/README.md).

## 3. Idempotency và giao diện

- Triển khai Embedder.embed_documents()/embed_query() và PgVectorStore.create_schema()/upsert()/search(). Constructor store bổ sung keyword-only dataset_id và profile_id để mỗi instance gắn rõ namespace/model; kiểm tra dimensions khớp profile. Không thay API ingestion/chunking giai đoạn 3.
- CLI riêng cho embedding/index và smoke retrieval, không biến run.py thành pipeline benchmark hoàn chỉnh. Trước encode: kiểm tra hash manifest/source, chuẩn hóa và ID/content/metadata của các chunk so với baseline.
- Embedding cache theo `(profile_id, SHA-256 của input có prefix)`. Input trùng có thể tái sử dụng vector nhưng vẫn giữ mọi hàng chunk riêng. Không hứa số lần encode cụ thể trước khi đo thực tế.
- Hợp đồng upsert trong v1: **nhận toàn bộ snapshot của một strategy**, không gọi theo từng batch model. Encode có thể batch 16 nhưng chỉ đồng bộ database sau khi toàn bộ vectors đã hợp lệ.
- Mỗi strategy sync trong một transaction, khóa theo dataset/profile/strategy; stage toàn bộ ID đầu vào, INSERT ON CONFLICT và chỉ UPDATE khi dữ liệu đổi, xóa ID cũ không còn trong snapshot ở đúng namespace đó. Không xóa ngoài dataset/profile/strategy đang nạp. Snapshot rỗng hoặc không đủ corpus hợp lệ bị từ chối trước khi ghi.
- Nếu đổi nội dung hoặc thu hẹp tài liệu sau khi được duyệt, full-snapshot sync loại chunk lỗi thời, kể cả khi tài liệu đã biến mất hoàn toàn. A/B phải cùng manifest_sha256 mới được dùng để chạy so sánh. Nếu một sync thất bại, rollback strategy đó và báo trạng thái chưa đồng bộ; chặn thí nghiệm trên snapshot A/B không khớp.
- Re-ingest snapshot giống nhau không tăng số hàng, không đổi ID/text/metadata hoặc tính lại embedding đã cache. Model/prefix/revision khác tạo profile riêng; không tự migrate dimension hoặc ghi đè profile cũ.

## 4. Retrieval và nghiệm thu

- `search(strategy, query_vector, top_k=3, filters=None)` trả chunk_id, text, source, physical_page, metadata, cosine_distance và score. Score = `1 - cosine_distance`, không phải xác suất hoặc điểm grounding.
- SQL dùng `embedding <=> query_vector`, ORDER BY distance ASC rồi chunk_id ASC để ổn định khi đồng điểm. Toàn bộ giá trị tham số hóa; dataset/profile luôn được ràng buộc trong WHERE.
- A/B chạy không filter; C đọc B và nhận filter section equality do người dùng/ngữ cảnh cung cấp trước truy xuất. V1 chỉ cho phép khóa section, từ chối khóa không hỗ trợ; không lấy filter từ gold source/answer. C không có filter phải trả cùng kết quả B với cùng query vector và top_k.
- Unit test: prefix, input order, kiểm tra dimension/finite/zero vector/token overflow, filter allowlist và ánh xạ C→B. Test doubles chỉ dùng trong unit test, không báo thành kết quả embedding thật.
- Integration dùng model thật và PostgreSQL thật: 510 hàng bền vững sau đóng/mở kết nối; vectors 384 chiều hợp lệ; metadata/offsets/page mapping nguyên vẹn; cosine distance của một vector với chính nó gần 0; top-k được sắp đúng; filter chỉ trả section phù hợp; B=C khi không filter.
- Chạy lại hai lần và đối chiếu count/ID/hash không đổi. Kiểm tra cập nhật/xóa chunk lỗi thời, rollback và namespace isolation trong schema/fixture test riêng, không sửa corpus thật để kiểm thử.
- Xuất log ingest thực, cấu hình model, số token, token overflow, thời gian, chi phí và báo cáo idempotency/retrieval smoke. Chưa tạo Hit@k, coherence, grounding hay so sánh chất lượng từ smoke tests.
- Theo GUIDE/BENCHMARK: chốt bộ tối thiểu 20 câu, split 15 dev/5 test và gold evidence **trước thí nghiệm retrieval để chọn/tinh chỉnh chiến lược**. Giai đoạn 4 chỉ kiểm tra kỹ thuật; chưa tạo hoặc chạy benchmark khi chưa được yêu cầu riêng.

Phê duyệt cần thiết: đồng ý model/revision local, profile 384 chiều, schema và transaction sync nêu trên, exact cosine retrieval và phạm vi test. Sau phê duyệt mới cài/tải model, tạo bảng, encode hoặc ghi PostgreSQL. Không commit/push nếu chưa được yêu cầu.
