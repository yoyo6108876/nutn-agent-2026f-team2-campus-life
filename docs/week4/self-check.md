# Week 4 自我檢核與繳交狀態

依 Lecture4_Agentic_AI_Engineering_Tool_Use_MCP.pdf，PDF 頁 1–10／投影片 62–71；以作業缺漏助手作為本組專題，不照搬球館資料。使用者指定沿用 OpenAI，以下區分專案通過與講義供應商差異。

| 自查項目 | 狀態 | 證據／限制 |
| --- | --- | --- |
| 自然語言經模型轉成結構化工具提案 | PASS（OpenAI live） | [live-success.json](../../artifacts/week4/live/live-success.json) 中 model_output → tool_validated |
| 格式與語意驗證 | PASS（固定範圍） | strict schema、identity／version／requirement 集合；[invalid-arguments](../../artifacts/week4/fixture/invalid-arguments.json)、[report-mismatch](../../artifacts/week4/fixture/report-mismatch.json) |
| 回覆符合工具結果 | PASS | live 最終 summary_verified；模型需複製實際 draft ID 與兩種項目集合 |
| RAG 來源、日期、版本、必要面向、引用 | PASS（合成專案資料） | live rag_trace、report citations；每次讀與確認時重驗 |
| MCP 一個唯讀能力 tools/list＋tools/call | PASS（真實 stdio） | live mcp_trace；MCP 只列 get_submission_review |
| 未確認不寫入，確認才建立 | PASS | live before_decision draft_count=0；確認後=1 |
| 使用者拒絕不寫入、不重提案 | PASS（離線流程） | [declined.json](../../artifacts/week4/fixture/declined.json)：accepted=false、executed=false，重送 true 仍為 declined |
| 重放、並發不重複寫入 | PASS | live replay；[pytest 的 parallel replay test](../../tests/test_week4_tools.py) |
| 可重現失敗、有限預算與停止 | PASS（故障注入） | [provider-429](../../artifacts/week4/fixture/provider-429.json)、[summary-failed-after-write](../../artifacts/week4/fixture/summary-failed-after-write.json)、[write-response-lost](../../artifacts/week4/fixture/write-response-lost.json) |
| 模型不能偽造 confirmed | PASS | [model-forged-confirmation](../../artifacts/week4/fixture/model-forged-confirmation.json) |
| UI 預覽、取消、確認與結果 | PASS（瀏覽器操作） | [UI 檢查](ui-check.md)，offline 清楚標示 |
| 工具結果回送後取得真實模型摘要 | PASS（OpenAI） | 3 次實際 API 回合，含 function_call_output 與最後摘要 |
| 講義指定「真實 Gemini＋functionResponse」 | 未執行／供應商差異 | 使用者指定 OpenAI；以 provider=openai、LIVE_PASS 記錄，不冒稱 Gemini。若教師嚴格限定 Gemini，需另補 provider 與實測 |
| MRTR 補問延伸協議 | 未測／未實作 | PDF 第 10 頁明示現有 demo 尚未實作；不當成本週已完成功能 |

**本次程式測試：107 passed、2 warnings。** 實測版本 `9b59df92db7d2f2c2803883ca3929aa501d57d0a`；live run `run-3df5baba98fd474cb60a0e7141412f30`，完整 metadata 見 JSON。

Repository：https://github.com/yoyo6108876/nutn-agent-2026f-team2-campus-life 。提交狀態以 GitHub 分支實際包含程式與證據為準，功能狀態以上表為準，不能只用本機 commit 或離線通過代表 live 成功。

後續優先保留與改善：將 UI 的確認等待接回相同 run；摘要失敗時先讀原收據。任意作業匯入、學生權限隔離、真實評閱品質、外部通知與自動清理均未完成。Week 3 教師費率案例缺件仍保留在該週文件，未由本週專案測試代替。
