# Plan triển khai: Trợ lý AI tra cứu văn bản nội bộ (RAG on-premise)

Nov 2, 2026 · @Viet Anh

## 1. Tổng quan sáng kiến

Sản phẩm demo là một trợ lý hỏi–đáp tiếng Việt về văn bản KH,CN&ĐMST: trả lời có trích dẫn đến từng Điều/Khoản, chạy toàn bộ bằng model mã nguồn mở, không gọi API bên ngoài. Hạn nộp 06/11/2026 nên code phải xong trước tối 04/11.

**Tên đề xuất:** Trợ lý ảo hỏi–đáp văn bản quy phạm về khoa học, công nghệ và đổi mới sáng tạo, ứng dụng mô hình ngôn ngữ lớn triển khai nội bộ tại Học viện ANND (tên gọi tắt gợi ý: *ViLex-ANND*).

**Phạm vi demo (chỉ văn bản công khai):** Nghị định 125/2026/NĐ-CP, Luật KH,CN&ĐMST 93/2025/QH15, Luật Giáo dục đại học 125/2025/QH15, các Nghị định hướng dẫn 262–268/2025, Thông tư 44/2026/TT-BGDĐT. Khoảng 8–12 văn bản là đủ để chứng minh.

**Năm nguyên tắc thiết kế (cũng là luận điểm "điểm mới" trong bài):**

1. **Nội bộ hoàn toàn:** mọi model (embedding, reranker, LLM) là open-weight, tải về và chạy trên máy chủ của đơn vị; không dữ liệu nào rời mạng nội bộ.
2. **Có căn cứ hoặc im lặng:** mỗi ý trong câu trả lời phải gắn trích dẫn \[Điều X, Văn bản Y\]; không đủ căn cứ thì trả lời "không tìm thấy quy định".
3. **Chunk theo cấu trúc pháp lý:** cắt theo Chương → Điều → Khoản, không cắt theo số ký tự, nên trích dẫn luôn trỏ đúng điều khoản.
4. **Truy xuất lai:** BM25 + dense embedding + reranker, vì văn bản pháp luật nhiều thuật ngữ chính xác mà dense đơn thuần dễ bỏ sót.
5. **Phân quyền theo đối tượng:** metadata `access_level` trên từng chunk, lọc trước khi truy xuất (demo: chỉ mức `public`).

**Ngoài phạm vi demo:** văn bản nội bộ/mật, đăng nhập thật, OCR văn bản scan, fine-tune model.

## 2. Kiến trúc hệ thống

Hệ thống có hai luồng: luồng offline dựng kho khi có văn bản mới, và luồng online trả lời từng câu hỏi. Hai ô được tô màu là điểm khác biệt so với một chatbot thông thường; sơ đồ này cũng dùng được thẳng cho mục "Nội dung và điểm mới" của bài.

&#91;embedded content: kiến trúc · luồng offline + online · 2 chốt kiểm soát\]

|  | Triển khai thật (đề xuất trong bài) | Bản demo (để lấy minh chứng) |
| --- | --- | --- |
| Hạ tầng | 1 máy chủ GPU trong mạng nội bộ | Colab Pro+ (A100/H100) |
| LLM | Cùng bản Q4 trên 1 GPU 24 GB (vLLM hoặc llama.cpp/Ollama) | vLLM + Qwen3.6-35B-A3B bản Q4 (AWQ/GPTQ-Int4), khoảng 22 GB |
| Truy cập | Cổng thông tin nội bộ, tài khoản thật | Một URL tunnel, chọn vai bằng dropdown |
| Dữ liệu | Công khai + nội bộ (sau phê duyệt) | Chỉ văn bản công khai + 1–2 văn bản mẫu tự viết |

Code giống nhau ở cả hai môi trường; chỉ khác `config.yaml` (địa chỉ LLM, đường dẫn index).

## 3. Kho văn bản và tiền xử lý

Kho văn bản được chuẩn hoá thành một file `chunks.jsonl`, mỗi dòng là một Khoản (hoặc một Điều nếu Điều ngắn) kèm metadata đầy đủ. Đây là bước quyết định chất lượng trích dẫn, nên làm kỹ nhất.

### 3.1 Thu thập

- Tải bản DOC/PDF text (không phải scan) từ vbpl.vn, congbao.chinhphu.vn hoặc thuvienphapluat.vn; lưu vào `data/raw/` với tên `<so_hieu>.docx`.
- Lập `data/registry.csv` bằng tay: `doc_id, so_hieu, loai (Luật/NĐ/TT/QC), ten, ngay_ban_hanh, hieu_luc, co_quan, url_nguon, access_level`.
- Kiểm tra nội dung NĐ 125 khớp với nguồn chính thức; ghi chú NĐ 125 thay thế NĐ 109/2022 (dùng để demo câu hỏi về hiệu lực).

### 3.2 Parser cấu trúc (module `ingest/parser.py`)

1. Chuyển về plain text (python-docx hoặc pdfplumber), chuẩn hoá Unicode NFC, gộp dòng bị ngắt giữa câu.
2. Nhận diện cấp bậc bằng regex theo thứ tự: `Chương [IVXLC]+` → `Mục \d+` → `Điều \d+\.` → khoản `^\d+\.` → điểm `^[a-zđ]\)`.
3. Dựng cây: Document → Chapter → Article → Clause → Point. Phần căn cứ đầu văn bản và phần "Nơi nhận" tách riêng, không đưa vào index.
4. Unit test bắt buộc: số Điều parse ra phải bằng số Điều thực tế của từng văn bản (đếm tay một lần, ghi vào registry).

### 3.3 Chiến lược chunk (module `ingest/chunker.py`)

- Đơn vị mặc định = 1 Khoản. Điều không có khoản hoặc ngắn hơn \~300 token → giữ cả Điều làm 1 chunk.
- Khoản dài hơn \~700 token → tách theo điểm a, b, c…, mỗi phần giữ lại câu dẫn của Khoản.
- **Contextual header** gắn đầu mỗi chunk trước khi embed: `[NĐ 125/2026/NĐ-CP > Chương II: ... > Điều 7: <tên điều> > Khoản 2]`. Header giúp model hiểu ngữ cảnh và cũng chính là chuỗi trích dẫn hiển thị.
- Lưu hai trường text: `text_for_embed` (header + nội dung) và `text_display` (nguyên văn để hiển thị bên khung nguồn).

### 3.4 Schema một chunk

| Trường | Kiểu | Ví dụ / ghi chú |
| --- | --- | --- |
| `chunk_id` | str | `nd125-2026_d7_k2` — ổn định, dùng làm khoá trích dẫn |
| `doc_id`, `so_hieu`, `loai` | str | `125/2026/NĐ-CP`, `Nghị định` |
| `chuong`, `dieu`, `ten_dieu`, `khoan`, `diem` | str/int | null nếu không có |
| `text_for_embed`, `text_display` | str | xem 3.3 |
| `hieu_luc` | enum | `con_hieu_luc` / `het_hieu_luc` |
| `access_level` | enum | `public` / `internal` (demo chỉ `public`) |
| `url_nguon` | str | link văn bản gốc |
| `parent_article_id` | str | để mở rộng ra cả Điều khi cần ngữ cảnh |

## 4. Pipeline truy xuất

Truy xuất chạy 4 tầng: tra cứu trực tiếp → BM25 + dense song song → hợp nhất RRF → rerank, trả về tối đa 5 chunk kèm điểm. Kho demo chỉ vài nghìn chunk nên không cần vector DB; FAISS hoặc ma trận numpy là đủ.

### 4.1 Các tầng (module `retrieval/`)

1. **Direct lookup (`router.py`):** regex bắt tham chiếu tường minh ("Điều 7 Nghị định 125", "khoản 2 điều 9") → lấy thẳng theo metadata, bỏ qua tìm kiếm. Nhanh, chính xác tuyệt đối, dễ gây ấn tượng khi demo.
2. **Sparse (`bm25.py`):** tách từ tiếng Việt bằng `underthesea` (hoặc pyvi), lowercase, bỏ stopword nhẹ; thư viện `bm25s`. Lấy top 30.
3. **Dense (`dense.py`):** encode query, cosine trên embedding đã L2-normalize. Lấy top 30.
4. **Fusion (`fusion.py`):** Reciprocal Rank Fusion, k = 60 → top 20.
5. **Rerank (`rerank.py`):** cross-encoder chấm (query, chunk) → giữ top 5 có điểm ≥ ngưỡng τ (hiệu chỉnh trên bộ dev). Không chunk nào qua ngưỡng → cờ `no_evidence = True`, chuyển sang câu từ chối.
6. **Parent expansion:** nếu ≥ 2 chunk cùng một Điều → gộp thành nguyên Điều để LLM đọc đủ mạch.
7. **Bộ lọc metadata** áp dụng ngay từ bước 2–3: `access_level ∈ quyền của user`, ưu tiên `con_hieu_luc`.

### 4.2 Lựa chọn model

Một model card công bố năm 2026 cho thấy các embedding đa ngôn ngữ phổ thông (mE5, BGE-M3) có thể thua cả BM25 trên văn bản luật tiếng Việt ([TELEN](https://huggingface.co/d4rkk3y/telen)). Đây là lý do dùng lai và phải tự benchmark trên bộ câu hỏi riêng (mục 8) trước khi chốt.

| Vai trò | Mặc định | Phương án so sánh | Ghi chú |
| --- | --- | --- | --- |
| Embedding | `BAAI/bge-m3` | [`huyydangg/DEk21_hcmute_embedding`](https://www.promptlayer.com/models/dek21hcmuteembedding) (fine-tune luật VN, 768-d, 512 token) | bge-m3 nhận đến 8192 token, ít phải cắt |
| Reranker | `BAAI/bge-reranker-v2-m3` | một reranker fine-tune tiếng Việt trên HF | Chạy FP16, batch 20 cặp |
| LLM | [`Qwen3.6-35B-A3B`](https://siliconflow.com/models/qwen3-5-27b) (MoE, 3B active) — **bản Q4** AWQ/GPTQ-Int4, khoảng 22 GB VRAM | [`Qwen3.5-27B`](https://dell.huggingface.co/models/Qwen/Qwen3.5-27B) (dense, chậm hơn); hoặc bản FP8 cùng model để đo mức suy giảm do Q4 | Apache 2.0, hỗ trợ 201 ngôn ngữ |
| Tách từ | `underthesea` | `pyvi` | chỉ cho BM25 |

Nếu một model embedding yêu cầu word-segmented input hoặc tiền tố `query:`/`passage:`, đóng gói việc đó trong `dense.py` để đổi model chỉ cần đổi config.

### 4.3 Index

- Script `scripts/build_index.py` đọc `chunks.jsonl` → sinh `bm25/`, `dense.npy`, `meta.parquet` vào `index/<embed_model_name>/`.
- Build trên Colab GPU, lưu lên Drive; backend chỉ load, không build lại lúc khởi động.

## 5. Sinh câu trả lời và chống ảo giác

LLM chỉ được viết từ các chunk được đưa vào, mỗi câu phải mang nhãn `[n]` trỏ về chunk; một bước hậu kiểm sẽ gỡ hoặc cảnh báo mọi câu không có căn cứ.

### 5.1 Serving LLM

- **Model chính: Qwen3.6-35B-A3B bản Q4.** Chạy bằng vLLM (OpenAI-compatible server, cổng 8000) với checkpoint 4-bit AWQ hoặc GPTQ-Int4. Ưu tiên bản của Qwen; nếu không có thì chọn bản cộng đồng nhiều lượt tải mà model card ghi rõ chạy được với vLLM.
- **Ngân sách VRAM:** trọng số khoảng 22 GB, KV cache cho 16k context gần như không đáng kể, bge-m3 + reranker khoảng 3 GB → tổng khoảng 26 GB. Đặt `gpu_memory_utilization` theo GPU được cấp (vLLM chiếm trước VRAM theo tỷ lệ này): A100 40GB ≈ 0.6; A100/H100 80GB ≈ 0.35–0.4. Phần còn lại dành cho embedding và reranker.
- **L4 24GB không đủ để chạy chung cả ba model.** Nếu chỉ được cấp L4: đẩy embedding và reranker sang CPU, hoặc dùng GGUF IQ4\_XS (khoảng 20 GB).
- `max_model_len` khoảng 16k. **Tắt thinking mode** (Qwen3.5/3.6 mặc định bật) qua `chat_template_kwargs: {enable_thinking: false}`. Temperature 0.1–0.2, `max_tokens` khoảng 800.
- **Phương án dự phòng:** GGUF Q4\_K\_M chạy qua `llama-server` của llama.cpp (cũng là API kiểu OpenAI). Backend chỉ cần đổi `LLM_BASE_URL`. Đây cũng là cấu hình đề xuất cho máy chủ nội bộ một GPU 24 GB.
- **Rủi ro riêng của Q4:** sai lệch con số hoặc thuật ngữ (ví dụ "giảm đến 50%" thành "giảm 50%"). RAG giảm phần lớn rủi ro này vì model chép từ nguồn, và bước hậu kiểm ở mục 5.3 gắn cờ các câu có con số mà không có nhãn nguồn.

### 5.2 Prompt (file `prompts/answer_vi.md`, không hard-code)

- **System:** vai trò "trợ lý tra cứu văn bản của Học viện ANND"; chỉ dùng thông tin trong NGUỒN; mỗi câu khẳng định kết thúc bằng `[số]`; không có căn cứ thì nói rõ "Các văn bản hiện có không quy định về…"; không tư vấn pháp lý ngoài văn bản; trả lời tiếng Việt, ngắn gọn, liệt kê khi có nhiều ý.
- **User:** khối `NGUỒN` đánh số `[1]..[5]`, mỗi nguồn mở đầu bằng contextual header, sau đó là `CÂU HỎI`.
- **Few-shot:** 2 ví dụ ngắn — một câu có căn cứ, một câu từ chối.
- **Hội thoại nhiều lượt:** trước khi truy xuất, dùng LLM viết lại câu hỏi nối tiếp thành câu độc lập (prompt `prompts/condense_vi.md`). Chỉ bật khi có lịch sử.

### 5.3 Hậu kiểm trích dẫn (module `generation/verify.py`)

1. Parse các `[n]`; `n` ngoài phạm vi nguồn → xoá nhãn.
2. Với mỗi câu có nhãn: điểm tương đồng giữa câu và chunk được trích (dùng lại reranker) dưới ngưỡng → đánh dấu `weak`.
3. Câu không nhãn mà chứa con số/tỷ lệ/thời hạn → đánh dấu `unsupported`.
4. Trả về `grounding_score = số câu có căn cứ / tổng câu`; frontend hiển thị như một chỉ báo độ tin cậy.
5. Nếu `no_evidence` từ bước rerank: không gọi LLM, trả câu từ chối chuẩn + 3 điều khoản gần nhất để người dùng tự xem.

### 5.4 Phân quyền

- Demo: hai vai `hoc_vien` (chỉ `public`) và `can_bo` (`public` + `internal`), chọn bằng dropdown trên UI, không cần đăng nhập thật.
- Để chứng minh cơ chế, tạo 1–2 văn bản *giả lập* gắn nhãn `internal` (nội dung tự viết, ghi rõ "dữ liệu mẫu"); học viên hỏi sẽ không thấy, cán bộ hỏi sẽ thấy. Tuyệt đối không dùng văn bản nội bộ thật.
- Mọi truy vấn ghi log `(thời gian, vai, câu hỏi, chunk_ids)` → đây là luận điểm "có thể kiểm toán" cho bài.

## 6. Backend API

Backend là một app FastAPI duy nhất: nạp index và model embedding/reranker vào RAM GPU lúc khởi động, gọi vLLM qua HTTP nội bộ, và phục vụ luôn bản build của frontend. Nhờ vậy chỉ cần một tunnel, một URL khi demo.

### 6.1 Endpoints

| Method | Path | Vai trò | Trả về |
| --- | --- | --- | --- |
| POST | `/api/chat` | Hỏi–đáp, streaming SSE | các event `sources` → `token`… → `done` |
| POST | `/api/search` | Chỉ truy xuất, không sinh (chế độ "tìm điều khoản") | danh sách chunk + điểm |
| GET | `/api/documents` | Danh mục văn bản trong kho | registry rút gọn |
| GET | `/api/article/{doc_id}/{dieu}` | Nguyên văn một Điều để mở ở khung nguồn | text + cấu trúc khoản |
| POST | `/api/feedback` | 👍/👎 cho một câu trả lời | 204 |
| GET | `/api/health` | Trạng thái index, vLLM, GPU | JSON |
| GET | `/` | Frontend tĩnh (`frontend/dist`) | HTML |

### 6.2 Hợp đồng `/api/chat`

- **Request:** `question: str`, `history: [{role, content}]` (tối đa 6 lượt), `user_role: "hoc_vien" | "can_bo"`, `doc_filter: [doc_id]?`, `mode: "answer" | "search"`.
- **Event `sources`** (gửi trước khi LLM chạy, để UI hiện nguồn ngay): `[{idx, chunk_id, citation_label, snippet, score, url_nguon}]`.
- **Event `token`:** chuỗi delta.
- **Event `done`:** `answer` đầy đủ, `citations_used: [idx]`, `grounding_score`, `flags: [{sentence_idx, type: weak|unsupported}]`, `latency_ms: {retrieve, rerank, generate}`, `no_evidence: bool`.
- **Event `error`:** thông báo thân thiện; không lộ stacktrace.

`latency_ms` được hiển thị trên UI — là số liệu thật để ghi vào phần "hiệu quả dự kiến".

### 6.3 Cấu hình và vận hành

- `config.yaml` + biến môi trường: `EMBED_MODEL`, `RERANK_MODEL`, `LLM_BASE_URL`, `LLM_MODEL`, `INDEX_DIR`, `RERANK_THRESHOLD`, `TOP_K`.
- Pydantic model cho mọi request/response; logging JSON vào `logs/queries.jsonl` (phục vụ cả đánh giá lẫn kiểm toán).
- Trên Colab: một cell khởi động vLLM chạy nền → cell chờ `/v1/models` trả 200 → cell chạy uvicorn nền cổng 7860 → cell mở tunnel (`cloudflared` quick tunnel, không cần tài khoản; hoặc ngrok) và in URL.
- CORS mở cho `localhost:5173` để dev frontend trên laptop trỏ vào backend Colab.

## 7. Frontend demo

Frontend là một SPA ba cột: danh mục văn bản bên trái, hội thoại ở giữa, khung nguồn bên phải. Điểm nhấn khi demo là bấm vào `[2]` trong câu trả lời thì khung phải mở đúng Khoản đó với đoạn được tô sáng.

**Stack:** Vite + React + TypeScript, Tailwind + shadcn/ui, `react-markdown`, `@microsoft/fetch-event-source` (đọc SSE qua POST). Build ra `frontend/dist`, FastAPI phục vụ.

### 7.1 Bố cục và component

| Vùng | Component | Nội dung |
| --- | --- | --- |
| Header | `TopBar` | Tên hệ thống, dropdown vai (Học viên / Cán bộ), trạng thái kết nối (chấm xanh khi `/api/health` OK), badge "Xử lý nội bộ – không kết nối Internet" |
| Trái | `DocSidebar` | Danh sách văn bản (số hiệu, tên, tag hiệu lực), checkbox lọc phạm vi, nút chuyển chế độ Hỏi–đáp / Tìm điều khoản |
| Giữa | `ChatPanel`, `MessageBubble`, `CitationChip`, `Composer` | Luồng hội thoại; câu trả lời render markdown, `[n]` thành chip bấm được; câu bị flag `weak`/`unsupported` gạch chân vàng |
| Giữa, dưới mỗi câu trả lời | `AnswerMeta` | Thanh độ tin cậy (grounding score), độ trễ 3 phần, nút 👍/👎, nút sao chép kèm trích dẫn |
| Phải | `SourcePanel`, `SourceCard`, `ArticleModal` | 5 thẻ nguồn hiện ngay khi event `sources` về; thẻ đang được trích có viền nhấn; "Xem toàn văn Điều" mở modal; link văn bản gốc |
| Trạng thái rỗng | `EmptyState` | 4–6 câu hỏi gợi ý lấy từ bộ đánh giá (bấm là hỏi) |

### 7.2 Luồng tương tác cần làm mượt

1. Gửi câu hỏi → khung phải hiện skeleton → thẻ nguồn đổ về (đây là lúc người xem thấy hệ thống "tra" trước khi "viết").
2. Token stream vào bubble; chip `[n]` xuất hiện đến đâu, thẻ tương ứng sáng lên đến đó.
3. Event `done` → hiện `AnswerMeta`, gắn flag lên câu.
4. `no_evidence` → bubble kiểu khác (viền xám, icon thông tin) + "Các điều khoản gần nhất".
5. Đổi vai sang Cán bộ → sidebar hiện thêm văn bản mẫu `internal` (minh hoạ phân quyền).

### 7.3 Yêu cầu phụ

- Giao diện tiếng Việt hoàn toàn; font hỗ trợ đủ dấu (Be Vietnam Pro hoặc Inter), đóng gói font cục bộ, không tải từ CDN — nhất quán với luận điểm chạy nội bộ.
- Tông màu trung tính, nghiêm túc; không dùng huy hiệu, logo chính thức nếu chưa được phép.
- Chụp màn hình ở độ rộng 1440px cho bài in: thiết kế sao cho ảnh chụp một câu hỏi + nguồn vừa một khung A4 ngang.

## 8. Đánh giá và minh chứng

Tiêu chí chấm cộng điểm cho "kết quả thử nghiệm", nên bài cần một bộ câu hỏi có đáp án và hai bảng số liệu thật: ablation truy xuất, và so sánh LLM có/không có RAG. Mọi con số trong bài phải lấy từ `eval/results/`, không ước lượng.

### 8.1 Bộ câu hỏi `eval/qa_set.jsonl` (\~60 câu)

| Nhóm | Số câu | Ví dụ dạng câu |
| --- | --- | --- |
| Tra cứu 1 điều khoản | 20 | "Trưởng nhóm nghiên cứu mạnh được giảm bao nhiêu định mức giờ chuẩn?" |
| Tổng hợp nhiều khoản/văn bản | 10 | "Điều kiện thành lập tổ chức KH&CN trực thuộc trường đại học gồm những gì?" |
| Diễn đạt đời thường / học viên hỏi | 10 | "Sinh viên làm NCKH có được hỗ trợ gì không?" |
| Hiệu lực / thay thế | 5 | "NĐ 109/2022 còn áp dụng không?" |
| Ngoài phạm vi (phải từ chối) | 10 | câu về lĩnh vực không có trong kho |
| Tham chiếu trực tiếp | 5 | "Điều 9 NĐ 125 quy định gì?" |

Mỗi dòng: `id, question, group, gold_chunk_ids[], gold_answer_short, should_refuse`. Cách làm nhanh: dùng LLM sinh câu hỏi nháp từ chunk (`scripts/gen_qa_draft.py`), rồi **bạn tự duyệt và sửa từng câu** — bộ này phải do bạn kiểm để số liệu đứng vững và thể hiện đóng góp cá nhân. Tách 15 câu làm dev (chỉnh τ, prompt), 45 câu làm test.

### 8.2 Chỉ số

- **Truy xuất:** Recall@5, MRR@10, nDCG@10 so với `gold_chunk_ids` (tính đúng nếu trúng cùng Điều — ghi rõ quy ước này).
- **Sinh:** độ chính xác câu trả lời (bạn chấm tay thang 0/1/2 trên 45 câu test); citation precision (tỷ lệ nhãn `[n]` mà chunk thật sự chứa thông tin); tỷ lệ từ chối đúng trên nhóm ngoài phạm vi; tỷ lệ bịa điều khoản (trích điều không tồn tại).
- **Vận hành:** độ trễ p50/p95 theo từng giai đoạn, VRAM sử dụng.

### 8.3 Hai thí nghiệm cần chạy

1. **Ablation truy xuất** (`eval/run_retrieval.py`): BM25 · Dense bge-m3 · Dense DEk21 · Hybrid RRF · Hybrid + rerank · + direct lookup. Ra một bảng và một biểu đồ cột Recall@5.
2. **Có RAG vs không RAG** (`eval/run_e2e.py`): cùng LLM, cùng 45 câu; cấu hình A hỏi thẳng, cấu hình B qua pipeline đầy đủ. Đây là minh chứng mạnh nhất: NĐ 125 ban hành tháng 4/2026 nên model không có tri thức đó và dễ bịa hoặc trả lời theo NĐ 109/2022 cũ.

**Tuỳ chọn — Q4 vs FP8 (khoảng 30 phút nếu được cấp GPU 80 GB):** chạy lại `run_e2e.py` với bản FP8 và thêm một dòng vào bảng. Nếu chênh lệch nhỏ, bài có số liệu thật để khẳng định cấu hình Q4 trên một GPU 24 GB là đủ dùng.

### 8.4 Đầu ra cho bài viết

- `eval/results/retrieval.csv`, `e2e.csv`, `latency.csv` + `report.md` tự sinh.
- 3 hình: biểu đồ ablation, biểu đồ có/không RAG, 1–2 ảnh chụp UI trả lời kèm nguồn.
- 2–3 ví dụ định tính: cùng một câu, LLM trần bịa sai — hệ thống trả lời đúng kèm Điều.

## 9. Cấu trúc repo và thứ tự task cho Claude Code

Giao Claude Code 10 task theo thứ tự dưới, mỗi task có tiêu chí nghiệm thu riêng; không chuyển task khi chưa đạt. Task 1–4 chạy được trên laptop (CPU), từ task 5 trở đi cần Colab.

### 9.1 Cấu trúc thư mục

```text
vilex-annd/
├── config.yaml
├── data/
│   ├── raw/                  # docx/pdf gốc
│   ├── registry.csv
│   └── processed/chunks.jsonl
├── ingest/      parser.py  chunker.py  run_ingest.py
├── retrieval/   router.py  bm25.py  dense.py  fusion.py  rerank.py  pipeline.py
├── generation/  llm_client.py  prompt_builder.py  verify.py
├── prompts/     answer_vi.md  condense_vi.md  refuse_vi.md
├── api/         main.py  schemas.py  deps.py  logging.py
├── scripts/     build_index.py  gen_qa_draft.py
├── eval/        qa_set.jsonl  run_retrieval.py  run_e2e.py  make_report.py  results/
├── notebooks/   colab_serve.ipynb  colab_eval.ipynb
├── frontend/    (Vite + React + TS)
└── tests/       test_parser.py  test_fusion.py  test_verify.py
```

### 9.2 Task list

| # | Task | Nghiệm thu |
| --- | --- | --- |
| T1 | Khung repo, `config.yaml`, schema Pydantic cho chunk | `pytest` chạy được, schema validate 1 chunk mẫu |
| T2 | `parser.py` + `chunker.py` + `run_ingest.py` | Số Điều parse khớp registry cho mọi văn bản; in thống kê số chunk, độ dài token |
| T3 | `bm25.py` + `router.py` (direct lookup) | 5 câu tham chiếu trực tiếp trả đúng Điều; BM25 trả kết quả hợp lý cho 5 câu thử |
| T4 | `fusion.py` (RRF) + `verify.py` + unit test | Test RRF với ranking giả; test parse `[n]` và flag câu không nhãn |
| T5 | `dense.py`, `rerank.py`, `build_index.py`; notebook build index trên Colab | Index lưu lên Drive; `pipeline.retrieve(q)` trả top 5 trong < 1 giây |
| T6 | `llm_client.py`, `prompt_builder.py`, prompts; cell vLLM trong `colab_serve.ipynb` | Hỏi 5 câu, mọi câu có `[n]`; câu ngoài phạm vi bị từ chối |
| T7 | `api/` FastAPI + SSE + logging + tunnel cell | `curl -N` thấy đủ 4 loại event; `/api/health` xanh |
| T8 | Frontend theo mục 7 | Chạy luồng 7.2 trọn vẹn qua URL tunnel |
| T9 | `gen_qa_draft.py` → bạn duyệt tay → `run_retrieval.py`, `run_e2e.py`, `make_report.py` | Sinh đủ 3 file CSV + 2 biểu đồ + `report.md` |
| T10 | Hardening demo: câu gợi ý, xử lý lỗi mạng, quay video dự phòng | Video 2–3 phút; demo chạy được 3 lần liên tiếp không lỗi |

### 9.3 Mẹo khi làm với Claude Code

- Đặt file này (export Markdown) vào `docs/PLAN.md` và trỏ CLAUDE.md vào đó; mỗi lần giao một task, dẫn đúng mục và cột nghiệm thu.
- Yêu cầu mọi tham số (top-k, τ, tên model) đọc từ `config.yaml` để chạy ablation không phải sửa code.
- Phần T2 hãy đưa cho Claude Code 1 văn bản thật làm fixture; regex Điều/Khoản hay hỏng ở đúng các ngoại lệ của văn bản thật.

## 10. Timeline đến 06/11 và rủi ro

Code phải xong tối 04/11, vì ngày 05/11 dành trọn cho viết bài — gồm cả Phần I (Câu 1–3). Thiếu Phần I thì bài không hợp lệ. Thể lệ chỉ yêu cầu nộp bài in, không yêu cầu demo trực tiếp, nên demo chủ yếu phục vụ ảnh chụp, số liệu và video minh chứng.

&#91;embedded content: lịch 5 ngày · 4 điều kiện chuyển giai đoạn\]

Nếu trượt một điều kiện, cắt phạm vi (bỏ condense hội thoại, bỏ phân quyền, bớt văn bản) chứ không lùi ngày viết bài.

### Rủi ro và phương án

| Rủi ro | Phương án |
| --- | --- |
| Colab không cấp A100/H100 hoặc ngắt phiên | Cache model + index trên Drive; bản Q4 chạy được cả trên A100 40GB; nếu chỉ có L4 thì dùng GGUF IQ4\_XS hoặc đẩy embedding sang CPU; luôn có video dự phòng |
| vLLM lỗi với Qwen3.6 bản Q4 (AWQ/GPTQ) | Thử bản vLLM mới nhất hoặc checkpoint Q4 khác; không được thì chuyển GGUF Q4\_K\_M qua llama-server; client OpenAI không đổi |
| Parser hỏng trên văn bản thật | Ưu tiên làm sạch tay NĐ 125 (văn bản trọng tâm), các văn bản khác chấp nhận mức Điều |
| Bộ câu hỏi duyệt không kịp | Giảm còn 30 câu test; vẫn giữ đủ 6 nhóm |
| Số liệu không đẹp | Báo cáo trung thực kèm phân tích lỗi; tiêu chí chấm là thiết thực và khả thi, không phải SOTA |
| In, đóng quyển bìa cứng mất thời gian | Hỏi tiệm in từ 04/11 về thời gian đóng bìa cứng; có thể phải gửi file tối 05/11 |

## 11. Ánh xạ sang 7 mục bắt buộc của phần sáng kiến

Mọi mục thể lệ yêu cầu đều đã có chất liệu trong plan này; bảng dưới chỉ ra lấy từ đâu để viết.

| Mục thể lệ | Nội dung chính cần viết | Lấy từ |
| --- | --- | --- |
| 1. Tên sáng kiến | Tên đầy đủ + tên gọi tắt | Mục 1 |
| 2. Vấn đề thực tiễn | Văn bản KH,CN&ĐMST mới dày đặc từ 2025–2026, khó tra cứu; công cụ AI công cộng không được dùng với tài liệu ngành; LLM trần không biết văn bản mới | Mục 1, kết quả thí nghiệm 2 (mục 8.3) |
| 3. Mục tiêu | Tra cứu có căn cứ, nội bộ, phân quyền; hỗ trợ tuyên truyền NĐ 125 | Mục 1 |
| 4. Nội dung và điểm mới | 5 nguyên tắc thiết kế + sơ đồ kiến trúc; nhấn mạnh chunk theo Điều/Khoản, hậu kiểm trích dẫn, phân quyền | Mục 1, 2, 3.3, 5.3 |
| 5. Cách thức thực hiện | Quy trình xây dựng (thu thập → index → truy xuất → sinh → kiểm) + lộ trình triển khai tại Học viện: thí điểm văn bản công khai → mở rộng quy chế nội bộ sau phê duyệt → tích hợp cổng thông tin | Mục 3–7 |
| 6. Điều kiện, nguồn lực | 1 máy chủ GPU nội bộ (LLM bản Q4 khoảng 22 GB chạy được trên 1 GPU 24GB — chính là cấu hình đã dùng cho demo), cán bộ cập nhật văn bản, phối hợp Phòng Lưu trữ và Thư viện; phần mềm toàn bộ mã nguồn mở | Mục 4.2, 5.1 |
| 7. Hiệu quả và khả năng áp dụng | Số liệu thật từ mục 8: Recall@5, độ chính xác, tỷ lệ từ chối đúng, độ trễ; khả năng nhân rộng sang quy chế đào tạo, NCKH, các trường CAND khác | Mục 8 |
| Kèm sản phẩm | Ảnh chụp UI, biểu đồ, QR tới video demo (lưu ý video không chứa thông tin nội bộ) | Mục 8.4, T10 |

**Lưu ý khi viết:** bài in tiếng Việt, Times New Roman 14/15; sơ đồ và biểu đồ ghi nguồn "Tác giả tự xây dựng"; trích dẫn model, thư viện, văn bản pháp luật vào Tài liệu tham khảo. Không nhắc tới hệ thống hoặc dữ liệu nội bộ có thật của Học viện.

## Nguồn

- [NĐ 125/2026/NĐ-CP — Cổng hành chính công Nghệ An (thông tin văn bản, file đính kèm)](https://hcc.nghean.gov.vn/laws/detail/Nghi-dinh-so-125-2026-ND-CP-cua-Chinh-phu-Quy-dinh-ve-hoat-dong-khoa-hoc-cong-nghe-va-doi-moi-sang-tao-trong-co-so-giao-duc-dai-hoc-2497/)
- [LSVN: Điều 7, Điều 9 NĐ 125/2026 (gợi ý câu hỏi demo)](https://lsvn.vn/giao-su-co-the-duoc-tam-dung-giang-day-mot-nam-de-nghien-cuu-a171462.html)
- [LuatVietnam: NĐ 109/2022 được thay thế bởi NĐ 125/2026](https://luatvietnam.vn/khoa-hoc/nghi-dinh-109-2022-nd-cp-239984-d1.html)
- [Danh mục văn bản KH,CN&ĐMST (Luật 93/2025, NĐ 262–268/2025)](https://vnuf2.edu.vn/vi/attachments/article/380/Danh%20m%E1%BB%A5c%20v%E1%BA%A3n%20b%E1%BA%A3n%20KHCN.pdf)
- [TELEN model card — so sánh BM25 với embedding đa ngôn ngữ trên luật VN](https://huggingface.co/d4rkk3y/telen)
- [DEk21\_hcmute\_embedding](https://www.promptlayer.com/models/dek21hcmuteembedding)
- [Qwen3.5-27B model card (vLLM/SGLang, thinking mặc định)](https://dell.huggingface.co/models/Qwen/Qwen3.5-27B)
- [Qwen3.6-35B-A3B — VRAM theo mức lượng tử hoá (Q4\_K\_M khoảng 21.9 GB, BF16 khoảng 72.3 GB)](https://llmrun.dev/model/qwen-qwen3-6-35b-a3b)
- [Qwen3.6-35B-A3B — KV cache theo độ dài context, IQ4\_XS](https://llmrun.dev/model/unsloth-qwen3-6-35b-a3b-mtp-gguf)
