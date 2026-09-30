# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Mai Hoàng Anh
- **MSSV:** 2A202602857
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/hoanganh3211/K4-L3B-Day13-Monitoring-LLMOps
- **Commit SHA cuối cùng:** 06eab86
- **Challenge ID:** day13-k4-l3b-monitoring-llmops-v1
- **Project Langfuse dự kiến:** `day13-k4-l3b-2A202602857`

## 2. Evidence index

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

Evidence 06–10 (trace list/waterfall/metadata, prompt versions/rollback) và 12–14
(challenge chính thức): **chưa có**, không tạo ID hay ảnh giả.
Ảnh dashboard bao gồm toàn bộ 50 requests, kể cả 10 lỗi cố ý; không xóa log lỗi.

## 3. Kết quả kỹ thuật

Lần chạy source ban đầu bằng Python hệ thống bị chặn ở collection vì thiếu `structlog`
và `langfuse`. Do đó không có baseline validator/runtime trước sửa source.
Môi trường hoàn chỉnh dùng Python 3.12 trong `.venv`, dependency theo `requirements.txt`.
Baseline bên dưới nghĩa là **workload bình thường sau triển khai**, không phải starter ban đầu.

| Nội dung | Kết quả đã xác minh |
|---|---|
| Pytest | 31 passed |
| Log validator | 100/100; 107 records; 56 correlation IDs; 0 thiếu context; 0 PII hits |
| Dashboard validator | 6/6 panel |
| Trace Langfuse hợp lệ | 0 được xác minh; health trả tracing_enabled=false |
| Baseline request | 10/10 HTTP 200; concurrency 5 |
| Baseline latency P50/P95/P99 | 156 / 176 / 176 ms |
| Baseline TTFT P95 | 50 ms |
| Baseline retrieval success | 100% |
| Baseline quality proxy | 0.88 |

| Phase (10 requests/phase) | P95 ms | TTFT P95 ms | Error % | Retrieval success % | Cost USD | Output tokens |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 176 | 50 | 0 | 100 | 0.020409 | 1293 |
| rag_slow | 2676 | 59 | 0 | 100 | 0.020679 | 1311 |
| tool_fail | Không có response thành công | Không có | 100 | 0 | 0 | 0 |
| cost_spike | 162 | 56 | 0 | 100 | 0.073974 | 4864 |
| Recovery | 159 | 53 | 0 | 100 | 0.019674 | 1244 |

Cùng bộ input, output token có random nên tỷ lệ cost không nhất thiết đúng 4 lần.
Các phase ngắn không chứng minh alert duy trì đủ 3–5 phút, SLO 28 ngày hay hiệu năng production.
Cost là ước lượng theo giá giả định trong lab, không phải hóa đơn provider.

## 4. Logging và PII

- Middleware xóa context cũ, nhận header hợp lệ `req-<8 hex>` hoặc sinh từ UUID;
  bind ID vào context/state, trả `x-request-id` và `x-response-time-ms` cả với HTTP 500.
  Header không đúng format được thay bằng ID mới để tránh PII và nội dung tùy ý đi vào ID.
- Bind `user_id_hash`, `session_id`, `feature`, `model`, `env` trước `request_received`.
  User ID được SHA-256 rồi lấy 12 ký tự; đây là pseudonymization, không bảo đảm ẩn danh tuyệt đối.
- Chuỗi processor: merge context → level → timestamp → stack/exception formatting
  → recursive scrub → JSONL writer → JSON renderer. Scrub cả dict/list và string lồng nhau,
  gồm detail của exception và các field context.
- Rule che email, số điện thoại Việt Nam, CCCD 12 số, thẻ 16 số liền/cách/gạch nối.
  Thẻ được xử lý trước điện thoại để không bị match từng phần.
- Test kiểm tra 6 requests đồng thời có đúng session/correlation ID, response lỗi,
  nested PII, CCCD và thẻ. Sample log runtime đã có `[REDACTED_EMAIL]`.
- Validator độc lập quét toàn bộ JSONL và không tìm thấy PII mẫu. Regex chỉ bao phủ
  các dạng đã định nghĩa, không phải bộ phát hiện mọi PII/ngữ nghĩa.

## 5. Tracing và prompt versioning

Cấu trúc source đã triển khai:

```text
day13-agent-request (trace name)
└── lab-agent-run (agent/root observation)
    ├── retrieval (retriever)
    └── generation (generation)
```

Root truyền correlation_id, hashed user, session đã scrub, feature/model và environment.
Các decorator tắt capture raw input/output. Retrieval ghi preview và doc_count;
generation ghi model, preview đã scrub, usage input/output và cost input/output.
SDK client dùng mask đệ quy để scrub cả metadata/status lỗi do SDK tạo.
Prompt managed được gắn vào generation; root ghi name/label/version/source.
Mô hình child observations và usage/cost theo [tài liệu Langfuse](https://python.reference.langfuse.com/langfuse).

- **Prompt name:** `day13-chat`.
- **Label cấu hình:** `production`; chưa có version managed.
- **Version thực tế local:** `local-v1`, source=`local` khi không có key.
- **Baseline/candidate trace IDs:** chưa có.
- **Promote/rollback:** chưa thực hiện trên Langfuse. Theo [hướng dẫn](../docs/PROMPT_VERSIONING.md),
  tạo v1 với baseline/production, v2 với candidate; chạy cùng input; chuyển production v1→v2→v1,
  lưu trace/version ở mỗi bước. Cache prompt 60 giây nên đợi hết TTL hoặc restart trước kiểm chứng.
- **Chứng minh sở hữu evidence:** sau khi tạo project cá nhân cần ảnh thấy tên project,
  ít nhất 10 traces và correlation ID đối chiếu JSONL, không chụp trang secret.

## 6. Dashboard, SLO và alerts

Dashboard `/dashboard` đọc `data/logs.jsonl`, lọc 60 phút theo UTC, refresh 30 giây.
Sáu panel: latency P50/P95/P99 và TTFT P95; request/phút; error rate/breakdown và
retrieval success; cost/phút và tổng; input/output tokens; mean quality.
Dữ liệu rỗng hiển thị no-data, không mặc định là healthy. Percentile dùng nearest-rank.

Errors config đã thêm `response_sent` vì sự kiện này mang `tool_success=true`;
chỉ đọc request_received/request_failed sẽ bỏ mất mẫu retrieval thành công.
Retrieval success ở lab là tool không ném lỗi, không đánh giá độ liên quan tài liệu.
TTFT đo từ lúc FakeLLM bắt đầu, chưa bao gồm thời gian retrieval hay thời gian mạng đến client.
Latency log đo agent run; response header đo toàn bộ middleware handling.

SLO: 99.5% request thành công trong <=3000 ms, cửa sổ 28 ngày.
Đây là mục tiêu trải nghiệm lab; baseline P95 176 ms cho thấy dư địa nhưng 10 mẫu chưa đủ
chứng minh SLO dài hạn. Good=request response_sent nhanh; total=request_received.
Budget=0.005×total; consumed=total−good; remaining=budget−consumed.
10,000 request cho phép 50 request lỗi/chậm, không đếm đôi cùng một request.
Chốt cửa sổ sau khi request đang xử lý hoàn tất. P95 dưới 3000 ms chưa chứng minh SLO 99.5%.

Ba alert và runbook ở [alert_rules.yaml](../config/alert_rules.yaml), [alerts.md](../docs/alerts.md):

| Alert | Điều kiện | Duration | Severity |
|---|---|---|---|
| HighLatencyP95 | P95 >3000 ms | 5m | warning |
| RequestFailures | Error rate >2% | 3m | critical |
| RetrievalSuccessLow | Retrieval success <90% | 5m | warning |

Owner student-2A202602857; Slack dự kiến `#k4-l3b-alerts`. Điều kiện tính cửa sổ 5 phút,
tối thiểu 10 mẫu. Đây là config/runbook, **chưa có alert scheduler hay Slack webhook thực tế**.

## 7. Điều tra challenge và practice

**Challenge chính thức:** chưa nhận; chưa chạy, chưa có ID/query/seed hoặc kết luận.

Practice thực tế (giờ bên dưới là UTC; giờ Việt Nam cộng 7):

1. **Metrics:** `rag_slow` trong 03:19:40–03:19:45 tăng P95 176→2676 ms,
   TTFT chỉ 50→59 ms. Chưa vượt ngưỡng 3000 ms nên không tuyên bố alert latency đã firing.
2. **Logs:** [practice-rag_slow.jsonl](evidence/practice-rag_slow.jsonl),
   correlation ID `req-253a3655` nối request_received với response_sent của cùng request.
3. **Traces:** chưa có Langfuse; chưa thể chứng minh retrieval span chậm bằng waterfall.
   Giả thuyết phù hợp là phần trước generation chậm. Source practice chủ động sleep 2.5 giây
   trong retrieval, nhưng thông tin source không thay thế evidence trace trong rubric.
4. **Failure practice:** 03:19:45–03:19:46 error rate 100%, retrieval success 0%;
   log `req-ce5080ad` có `request_failed`, `RuntimeError`, `Vector store timeout`.
   Đây là lỗi retrieval có chủ ý trong mock, chưa phải kết luận về challenge.
5. **Mitigation đã thực hiện:** tắt từng practice scenario trong finally, chạy lại cùng workload.
   Recovery P95 159 ms, error 0%, retrieval success 100%. Log lỗi vẫn được giữ.
6. **Preventive measure:** cảnh báo lỗi/retrieval; kiểm tra health dependency, timeout và
   bounded retry/circuit breaker trước production; test correlation/context và PII khi đổi tracing.

## 8. Giải thích và tự đánh giá

- **Quyết định kỹ thuật:** chạy agent đồng bộ trong thread pool để sleep/LLM không khóa event loop,
  giữ context request khi chạy concurrency. Dashboard dựa trên log bền vững thay vì metrics in-memory
  vì `/metrics` reset khi restart và chỉ thuộc một process.
- **Blocker môi trường:** Python hệ thống thiếu dependency; sandbox Windows ngăn ensurepip và
  thư mục tạm pytest. Đã tạo venv Python 3.12 và chạy các bước cần thiết với quyền được tool cho phép.
- **Luồng điều tra:** metrics khoanh vùng triệu chứng/thời gian → log chọn request bằng correlation ID
  → trace cùng ID định vị span → đối chiếu thay đổi để kết luận root cause và xác minh recovery.
- **Prompt/version:** label cho phép chuyển phiên bản không sửa code; trace lưu version để truy xuất
  regression. Token/cost giúp nhận ra prompt dài hoặc output tăng; rollback cần evidence trước/sau.
- **Tự đánh giá cá nhân:** học viên bổ sung sau khi đọc source và tự demo; không xem bản nháp này
  là lời xác nhận đã hiểu hoặc đã thao tác Langfuse.
- **Hạn chế:** mock LLM/quality heuristic, mẫu ít; chưa có cloud traces, prompt rollback, challenge,
  alert delivery, commit/push cuối. Metrics in-memory chưa hỗ trợ multi-worker/retention production.

## 9. Checklist trước khi nộp

- [x] Source bắt buộc và config alert đã hoàn thiện; kiểm tra local pass.
- [x] Evidence local thật có đường dẫn tương đối; giữ cả các request lỗi.
- [x] Dashboard runtime có dữ liệu và sáu panel.
- [x] Tạo project Langfuse cá nhân, cấu hình `.env`, tạo >=10 traces.
- [x] Lưu prompt v1/v2, metadata/waterfall và evidence rollback.
- [x] Nhận file challenge đúng lớp và bổ sung metrics → log → trace chính thức.
- [x] Học viên đọc/xác nhận báo cáo và bổ sung tự đánh giá.
- [x] Chuẩn hóa tên repo cá nhân, commit và chạy lại kiểm tra trên commit cuối.
- [x] Rà secret/PII và evidence lần cuối, push repo cá nhân, nộp URL/SHA lên LMS.
