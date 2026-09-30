# Week 3 講義核對與修正

依使用者提供的 `Lecture03_Agentic_AI_Engineering_RAG (1).pdf` 核對，檔案共 8 頁、投影片頁碼 47–54。沒有外部連結或嵌入附件；`week03/project_studio.md`、`docs/STUDENT_STUDIO_LAB.md` 為講義提及的參考檔案路徑，未包含檔案內容或儲存庫網址。未將 PDF 全文上傳儲存庫。

| PDF／投影片頁 | 要求 | 先前不足 | 本版處理 |
| --- | --- | --- | --- |
| 2–3／48–49 | 一個需要外部證據的 claim，使用者、資料範圍、拒答、baseline | 專案範圍描述較廣 | Proposal 明確聚焦「此版提交能否通過已確認要求的完整性預檢」 |
| 3／49 | Source card 含 owner、原始 URL／檔案、權限、update cadence、validity、delete/reindex、衝突優先序、PII、retention | 卡片缺 owner、頻率、保留與衝突細節 | 補可讀與機器欄位；實作已宣告衝突的優先序與拒答，人工保留／刪除流程如實列出 |
| 4／50 | 3–10 stable chunks；normal、paraphrase、no-answer 三題 | 原三題用 coverage failure 取代 paraphrase | 固定 Q1、QP、Q2；Q3 另測 coverage；ID 保持既有意義 |
| 4／50 | trace 包含 gold／acceptable IDs、是否拒答、失敗觀察、重現指令 | 舊 trace 沒有完整標註欄位 | 生成後附 evaluator reference，不傳給 generator |
| 5／51 | 羽球館 eligibility／weekday_rate／holiday_exception；三個指定 chunk | 舊 B1 是開放時間／預約／鞋款，題意不符 | 明確降為歷史補充；T1 依正確教師題目建入口，因原文缺失拒答 |
| 5／51 | coverage 不足回 `MISSING_REQUIRED_ASPECT`；所有 generator 不呼叫 | 只有一般 coverage_failure | 保留狀態另加精確 refusal_code，記錄 generator_invocations=0 |
| 6／52 | Offline／Gemini Fixture 或 Live；provider 與實際呼叫如實標示 | 舊輸出為通用 fixture 或 OpenAI，欄位未對齊 | 課堂 fixture 以 gemini_fixture／false 標示，註明專案自撰，非 Gemini 錄製；OpenAI 另列 |
| 6／52 | `same_selected_evidence`、`same_citations`、fact coverage、`unsupported_numeric_claims` | 部分結果需人工從 JSON 比對 | 明確計算並保存欄位；引用原文驗證另列 |
| 6／52 | `python -m scripts.run_studio_generator_lab --path auto`，輸出 artifacts/week03-generator-comparison.json | 指令與路徑不同 | 新增相同入口與預設輸出；auto 固定 fixture、不自動使用 key |
| 7–8／53–54 | 提交完整證據，由教師 checkpoint 驗收 | 曾以合成替代例說明 3/3 | 不將補充例當教師案例；`teacher_checkpoint_complete=false` |

可完成的規格修正與本機測試已完成。原始 pricing 文字、費率與例外規則仍缺，詳細缺件列於 [教師案例](teacher-case.md)。講義允許 fixture，並未要求為本週新增 live key。
