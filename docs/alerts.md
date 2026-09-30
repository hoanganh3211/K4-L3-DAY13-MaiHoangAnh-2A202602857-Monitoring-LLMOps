# Alert và runbook

Owner: Mai Hoàng Anh (student-2A202602857). Kênh dự kiến: Slack `#k4-l3b-alerts`.
Đây là định nghĩa alert, chưa kết nối webhook hay gửi thông báo thực tế.
Cửa sổ tính 5 phút; tối thiểu 10 mẫu để giảm báo động do ít traffic.
Không đủ mẫu: no-data, không kết luận healthy. Duration là thời gian điều kiện duy trì liên tục.

## Alert 1

`HighLatencyP95`: warning khi P95 > 3000 ms liên tục 5 phút. Người dùng chờ lâu.
1. Xác nhận latency/TTFT và time range trên dashboard.
2. Lọc response_sent có latency cao, lấy correlation_id.
3. Mở trace cùng ID, so sánh retrieval và generation; kiểm tra prompt version.

Mitigation: khôi phục dependency chậm hoặc rollback prompt nếu evidence chỉ ra regression.
Trong practice, tắt rag_slow sau khi lưu evidence. Xác nhận P95 phục hồi dưới 3000 ms
với cùng workload trong ít nhất 5 phút. Không xem P95 đạt là bằng chứng SLO 99.5% đạt.

## Alert 2

`RequestFailures`: critical khi error rate > 2% liên tục 3 phút. Request không trả lời được.
1. Xem error rate và error breakdown trên dashboard.
2. Lọc request_failed theo khoảng thời gian, chọn correlation_id và error_type.
3. Mở trace tương ứng để tìm span lỗi, đối chiếu deployment và dependency.

Mitigation: khôi phục vector store khi timeout; rollback thay đổi gây lỗi sau khi xác minh.
Chỉ retry có giới hạn/backoff; tránh khuếch đại tải. Kiểm tra error rate <= 2% trong 5 phút.

## Alert 3

`RetrievalSuccessLow`: warning khi retrieval success < 90% liên tục 5 phút.
Success ở đây nghĩa là tool thực thi thành công, không phải độ liên quan của tài liệu.
1. Xem retrieval success cùng error/quality; mẫu số chỉ gồm tool_success khác null.
2. Lọc log tool_name=retrieval và tool_success=false, lấy correlation_id.
3. Mở retrieval span cùng ID, kiểm tra timeout và khả năng truy cập vector store.

Mitigation: khôi phục dependency; fallback chỉ khi sản phẩm cho phép và đánh dấu rõ.
Trong practice tắt tool_fail. Chạy lại cùng workload, xác nhận success >= 90% và không còn timeout.

## SLO/error budget

Trong 28 ngày: good = response_sent có latency_ms <= 3000; total = request_received.
Budget = 0.005 * total; consumed = total - good; remaining = budget - consumed.
Chỉ chốt cửa sổ sau khi các request đang chạy kết thúc để tránh tính inflight thành lỗi.
Ví dụ 10,000 requests cho phép 50 request lỗi hoặc chậm (không cộng trùng).
Ngưỡng 3 giây là mục tiêu trải nghiệm của lab; cần đối chiếu baseline và tải thực trước production.
