# 教師多證據案例：已知 contract 與缺件

使用者提供 PDF 第 3–6 頁（投影片 49–52）指定的是**持學生證者平日 17:00 前每小時場租**，不是開放時間或鞋款規則。

已知來源 ID：`mock-pricing-2026-fall`。三個 required aspects 與指定 stable IDs：

| Aspect | 指定 chunk ID | 目前資料狀態 |
| --- | --- | --- |
| eligibility | price-student-eligibility | PDF 提及學生證情境，沒有該 chunk 完整原文與中繼資料 |
| weekday_rate | price-student-weekday-rate | PDF 提及平日 17:00 前，沒有金額、計費細節或 chunk 原文 |
| holiday_exception | price-student-holiday-exception | PDF 提及假日例外，沒有具體規則與 chunk 原文 |

教師固定題：normal「學生平日場租」、paraphrase「學生證＋星期四下午」、no-answer「今天晚上哪面場可訂」。多證據比較題是「學生證＋週五 16:00＋假日」。這些已保存於 [dataset.json 的 teacher_reference](../../examples/week3/dataset.json)。

目前 T1 以正確的多證據題與 required aspects 執行，但原始 pricing corpus 尚未匯入，回 `NO_EVIDENCE`、零 generator 呼叫、沒有報價。這證明缺資料時安全拒答，**不等於通過教師 3/3 checkpoint**。未以常識或網路場館價格填補，也未把投影片提及的概念假冒成原始 chunk。

待取得 `week03/project_studio.md`、參考 repository，或老師提供三段原始資料後：

1. 檢查 owner、來源權限、版本、有效期、衝突及撤回資訊，補 source card。
2. 按指定三個 ID 匯入 `teacher-pricing-pending` 對應語料（正式命名可再調整），保留完整原文及 metadata；不得只填預期答案。
3. 依原文補可選輸出值、正常／改寫／無答案題與教師確認的 oracle；建立適用的 fixture，不能直接複用 B1。
4. 重跑 coverage 缺件與完整資料兩種情境；完整案例必須選同一三份證據、citation 一致、fact coverage 3/3、unsupported claims=0、unsupported_numeric_claims=[]。
5. 保存新 JSON，待教師 checkpoint 確認後再標完成。

`artifacts/week03-generator-comparison.json` 目前明示 `teacher_checkpoint_complete=false`。此旗標不能因其他合成案例通過而改成 true。
