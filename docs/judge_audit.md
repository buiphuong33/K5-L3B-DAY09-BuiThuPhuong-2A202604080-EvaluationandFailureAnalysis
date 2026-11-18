# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

Đầu vào: replay judge công khai, 100 dòng mỗi tiêu chí (`src/data/eval/judge_tone_public.csv`, `src/data/eval/judge_helpful_public.csv`). Lớp dương = `FAIL` (việc của judge là tìm lỗi). Số liệu bên dưới là output của `lab9.judge` với `lab9/stats.py`, chép nguyên văn.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (exit 0) | **dùng**, chỉ cho giọng văn, không blocking cho tiền |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt**: κ < 0.6, R < 0.7 (exit 1) | **loại** |

Ma trận nhầm lẫn và tỉ lệ lỗi:

| Tiêu chí | tp | fp | fn | tn | Specificity | Fail rate judge quan sát | Fail rate hiệu chỉnh (Rogan-Gladen) | Fail rate theo nhãn người |
|---|---|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 66/70 = 0.943 | 0.28 | 0.30 | 30/100 = 0.30 |
| helpful | 9 | 0 | 21 | 70 | 70/70 = 1.000 | 0.09 | 0.30 | 30/100 = 0.30 |

## ≥5 case audit thủ công

Tone có 10 bất đồng (6 fn, 4 fp). Bảng dưới audit cả 10, sau đó audit thêm các nhóm bất đồng của helpful.

### tone_ok

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | **Người** | Judge coi "em… nha" là thân thiện. **Sửa rubric:** CS xưng "LogiX", gọi khách "anh/chị"; xưng "em/bạn", từ đệm "nha/nhé" là FAIL. Thêm H-008 làm ví dụ few-shot FAIL. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ… rồi nha." | PASS | FAIL | **Người** | Cùng lỗi với #1 (xưng "bạn"). Gộp chung vào quy tắc xưng hô ở #1. |
| 3 | H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | **Người** | Judge chỉ bắt từ khóa lịch sự ("Dạ, vui lòng") mà bỏ qua câu gạt khách. **Sửa rubric:** chấm cả câu; câu mệnh lệnh hoặc ngăn khách liên hệ ("không cần nhắn thêm") là FAIL dù có kính ngữ. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | **Người** | Judge phạt vì "thiếu xin lỗi". Reply lịch sự, đủ ý. **Sửa rubric:** xin lỗi không bắt buộc khi yêu cầu đã được giải quyết; ngắn gọn không phải lỗi giọng văn. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | **Người** | Quy định CS LogiX cho phép từ "refund"; judge phạt vì dùng tiếng Anh. **Sửa rubric:** ghi rõ danh sách thuật ngữ tiếng Anh được phép (refund, ship, COD). |
| 6 | H-063 "Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | **Người**, nhưng **sai tiêu chí** | Giọng văn ổn; lỗi là *nội dung*: hứa "hoàn thêm" ngoài kết quả của hệ thống. **Hành động:** không đưa vào rubric tone; chấm bằng code (reply so với ledger, FM-08). Nhãn tone của dòng này nên tách sang một tiêu chí khác. |
| 7 | H-070 "Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | **Người** | Emoji cười trong ngữ cảnh khiếu nại là thiếu tôn trọng. **Sửa rubric:** cấm emoji trong reply khiếu nại/hoàn tiền. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** (nhãn người sai) | Theo ghi chú, người gán nhãn đọc nhầm ticket. **Hành động:** **sửa nhãn người**, không sửa rubric. Nếu sửa, judge tone có tp=25, fp=3 (P ≈ 0.893). Bài học: nhãn người cũng cần audit hai người. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ cho đơn O-233 ạ." | FAIL | PASS | **Người** (lỗi nhẹ) | Lặp "Dạ" do gõ, không phải thái độ sai; khách vẫn thấy lịch sự. **Sửa rubric:** lỗi gõ/lặp từ không làm FAIL tone trừ khi làm câu khó hiểu. Ca biên: ghi nhận để người thứ hai chấm lại. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ cho don O-341, xin loi vi su bat tien." | PASS | FAIL | **Người** | Tiếng Việt mất dấu (dịch máy) trông thiếu chuyên nghiệp; judge chỉ thấy có câu xin lỗi. **Sửa rubric:** reply tiếng Việt không dấu là FAIL. |

Tổng kết tone: 10 bất đồng, người đúng 8, judge đúng 1 (H-081), 1 ca sai tiêu chí (H-063). Lỗi của judge có hai kiểu: (a) bắt từ khóa lịch sự thay vì đọc cả câu (#1, #2, #3, #7, #10); (b) phạt quá tay theo luật tự đặt (#4, #5, #9). Cả hai đều sửa được bằng rubric rõ ràng và ví dụ few-shot.

### helpful (vì sao loại)

Helpful có 21 bất đồng, **tất cả đều là fn** (judge PASS, người FAIL); fp = 0. Đọc cột `note`, chia thành 3 nhóm:

| # | Nhóm | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|---|
| 11 | Reply nói sai số tiền so với ledger | HL-015 "đã hoàn 55.000đ" (ledger 40.000đ); HL-020 "90.000đ" (ledger 120.000đ); HL-062, HL-087, HL-100 | PASS | FAIL | **Người** | Judge chỉ đọc reply, **không thấy ledger**, nên không thể biết số tiền sai. Đây là FM-08. Không rubric nào sửa được vì judge thiếu dữ liệu. **Hành động:** chấm bằng code (reply so với `refund_vnd` của ledger). |
| 12 | Xin lỗi dài, văn hoa, che số tiền sai | HL-016, HL-028, HL-035, HL-041, HL-043, HL-053, HL-058, HL-070, HL-072, HL-074, HL-090, HL-096, HL-098 (đều có ghi chú "ledger ghi …") | PASS | FAIL | **Người** | Câu xin lỗi dài làm reply *nghe* helpful (judge thiên vị độ dài/độ lịch sự), nhưng số tiền vẫn sai ledger. Cùng nguyên nhân gốc với #11. |
| 13 | Không nói kết quả cụ thể | HL-047, HL-091, HL-097 "Ok bạn, đơn O-xxx xử lý rồi nhé." | PASS | FAIL | **Người** | Không nêu số tiền, không nói hoàn hay từ chối; khách không biết chuyện gì xảy ra. **Sửa rubric** (nếu muốn thử lại judge): reply phải nêu trạng thái và số tiền. Nhưng phần số tiền vẫn phải kiểm bằng code. |

## Kết luận

- **tone_ok: dùng được.** κ = 0.757, P = 0.857, R = 0.800, đều qua FLOORS. Tỉ lệ lỗi judge quan sát 0.28, hiệu chỉnh Rogan-Gladen 0.30, khớp tỉ lệ theo nhãn người (30/100). Judge tone chỉ dùng để theo dõi giọng văn, **không làm metric blocking cho tiền hay approval**. Áp dụng các sửa đổi rubric ở #1–#10 rồi calibrate lại trước khi tin hơn.
- **helpful: loại, không được dùng làm gate.** Dẫn ma trận nhầm lẫn tp=9, fp=0, fn=21, tn=70:
  - **Recall 0.30:** judge bỏ sót 21/30 reply lỗi. Một gate dùng judge này sẽ cho qua 70% reply sai.
  - **Precision 1.0 là cái bẫy:** judge chỉ nói FAIL 9 lần nên lần nào cũng đúng, nhưng gần như luôn cho qua. Nhìn riêng precision sẽ tưởng judge rất tốt.
  - **κ = 0.375 < 0.6:** đồng thuận chỉ hơn mức ngẫu nhiên (p_o = 0.79 nhưng p_e = 0.664).
  - **Rogan-Gladen:** judge thấy 9% lỗi, tỉ lệ thật sau hiệu chỉnh là 30%. Dùng judge này sẽ đánh giá thấp tỉ lệ lỗi khoảng 3 lần.
  - **Nguyên nhân gốc:** 18/21 ca bỏ sót là reply nói sai số tiền so với ledger. Judge không có ledger trong đầu vào nên về nguyên tắc không thể chấm tiêu chí này. Đúng quy tắc "tiền và approval luôn chấm bằng code": phần "đúng số tiền" chuyển sang metric FM-08 bằng code ở M3.
- **Quy ước code:** `cohen_kappa` raise `ValueError` khi p_e = 1 (judge hoặc nhãn hằng số), nên `lab9.judge` ghi κ = NaN và trả FAIL floors; `rogan_gladen` trả NaN khi sensitivity + specificity − 1 ≤ 0 (judge không tốt hơn đoán bừa), thay vì chia cho số ≤ 0.
- **Rủi ro còn lại:**
  - Judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.
  - n = 100 nên khoảng tin cậy của κ còn rộng; recall 0.8 nghĩa là vẫn bỏ sót khoảng 1/5 reply có giọng văn sai.
  - Nhãn người có ít nhất 1 lỗi (H-081); cần người thứ hai gán nhãn độc lập và đo κ giữa hai người.
  - Sau khi sửa rubric, judge trả lời khác đi, nên phải calibrate lại, không dùng lại số ở trên.
