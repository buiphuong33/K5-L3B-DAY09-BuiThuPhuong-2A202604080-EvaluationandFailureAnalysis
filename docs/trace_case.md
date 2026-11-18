# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case: `seeded_regression C-002@11` (FM-03 ticket_trust)

Bối cảnh: ticket C-002 viết "Đơn giao trễ **5** ngày, hoàn phí ship giúp."; DB ghi đơn O-202 `delay_days: 2`, phí ship 20.000đ. Clause hiện hành `SHIP-LATE-03` chỉ hoàn khi trễ ≥ 3 ngày, nên nhãn là `denied`, `refund_vnd` 0.

Output của `lab9.trace_case` (rút gọn):

```text
== seeded_regression C-002@11  lab8 grader: FAIL (status resolved != denied)
-- trace (step, kind, payload)
   1 handoff            {"principal_scope": "owner_order_only", "allowed_tools": ["lookup_order", "lookup_po…
   2 investigator       {"lookup_order": {"visible": true, "reason": "ok", "order": {"order_id": "O-202", "status": "delivered", "dela…
   3 model_override     {"delay_days": 5}
   4 quote              {"amount_vnd": 20000, "reason": "entitled", "clause_ids": ["SHIP-LATE-03"], "parts": {"SHIP-LATE-03": 20000}}
   5 refund_history     {"refund_count": 0, "refunded_vnd": 0}
   6 reply              {"text": "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."}
-- ledger vs label
  refund_vnd     ledger=20000    label=0   <-- differs
  refund_count   ledger=1        label=0   <-- differs
  status         result=resolved label=denied
  unexpected ledger rows: 0
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, item E-002; run ID `E-seeded_regression-20261118-c4c3` (`src/reports/eval_seeded_regression.json`, eval set `c4c3a9299881`) |
| Triệu chứng | Grader Lab 8 FAIL `status resolved != denied`. Ledger ghi **20.000đ** (`refund_count` 1) trong khi nhãn là 0. Reply "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." trôi chảy, lịch sự và *khớp ledger*, nên đọc reply sẽ không thấy lỗi: tiền đã bị chi sai. Trong report, dòng E-002@11 có `refund_amount_correct` = false, `pass_rate` = false, `db_fact_kept` = false, còn `reply_amount_matches_ledger` = true. |
| Bước sai đầu tiên | **Event #3 `model_override`**, payload `{"delay_days": 5}`: agent ghi đè số ngày trễ của DB (2) bằng số khách tự viết trong ticket (5). |
| Vì sao là bước *đầu tiên* | #1 `handoff` đúng contract (`principal_scope: owner_order_only`, chỉ cho tool read-only). #2 `investigator` đọc đúng DB: `order_id O-202`, `delay_days: 2`, nghĩa là agent **đã có** dữ kiện đúng trước khi sai. #4 `quote 20000 entitled` dùng đúng công thức nhưng trên `delay_days` = 5 đã bị ghi đè, nên chỉ là hệ quả của #3. #5 và #6 cũng là hệ quả (ghi refund, báo khách). |
| Failure mode | **FM-03** ticket_trust (`docs/failure_taxonomy.md`), layer model/prompt. |
| Đối chứng | `fixed C-002@11`: #1 `handoff`, #2 `investigator` (cùng `delay_days: 2`), **không có `model_override`**, #3 `quote {"amount_vnd": 0, "reason": "no_entitlement", "clause_ids": []}`, #4 reply "chưa đủ điều kiện hoàn theo chính sách hiện hành". Ledger 0 = nhãn, status `denied`, grader PASS. Khác biệt duy nhất giữa hai trace là event `model_override`. |
| Regression test | `src/tests/test_lab9_trace_case.py` (marker `student`, chạy trong CI qua `-k "lab9 and not advanced"`): `test_trace_case_first_wrong_step_is_model_override` (bước 1–2 là `handoff`, `investigator`; DB `delay_days` = 2; event kế tiếp là `model_override {"delay_days": 5}`), `test_trace_case_graders_catch_seeded_regression` (`RefundAmountCorrect`, `DbFactKept`, `TrialPass` đều fail), `test_trace_case_fixed_passes_same_trial` (cùng trial trên `fixed`: không có override, status `denied`, 4 grader đều pass). Đã chạy: **3 passed**. Trong eval set, item E-002 gắn `FM-03`, nên gate bắt lại lỗi này qua `refund_amount_correct` và `pass_rate` (blocking). |
| Chưa chắc chắn | (1) Trace chỉ cho thấy agent *chọn* tin ticket, không cho thấy *vì sao* (prompt, seed hay logic parse); với MockLLM đó là công tắc `ticket_trust` cài sẵn. (2) Trên `swarm`, cùng lỗi chỉ xuất hiện ở seed 55 (1/5 seed): một bug thưa như vậy chỉ làm `pass_rate` giảm 0.014, cần đủ 5 seed mới thấy và gate trung bình không chặn ổn định. (3) `reply_amount_matches_ledger` không bắt được case này vì reply nói đúng số đã ghi; đây là lỗi FM-03, không phải FM-08, nên phải dựa vào grader đọc ledger. (4) Test chỉ khóa một trial; ticket khai *ít* ngày hơn DB (agent hoàn thiếu) chưa có item. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
