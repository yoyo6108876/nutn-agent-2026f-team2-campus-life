# Action Readiness：作業缺漏與補件草稿

## 執行前提與契約

| 檢查 | 唯讀 | 寫入 |
| --- | --- | --- |
| 需求 | 自然語言非空、上限 1,000 字元；所選 assignment／submission／version 必填；本週只允許合成快照 | intent 必須為 draft，且已完成同一請求的讀取 |
| 模型參數 | 三個 identity 欄位，禁止額外欄位；型別與正整數版本由 Pydantic strict 驗證 | 額外 requirement_ids，必須恰好包含既有報告的所有需補件／待確認項目，不得重複或多帶欄位 |
| 語意範圍 | 提案身份需等於 UI 驗證範圍；訊息若明示另一 HW／SUB ID，模型呼叫前拒絕 | 模型不能改提交、版本、項目，也不能宣告使用者同意 |
| RAG | 沿用 Week 3 的來源權限、撤回、PII 宣告、日期／版本、衝突、coverage 與引用 gate | 確認時重讀、再驗來源與 report_hash，改版或撤回後不照舊草稿寫入 |
| 權限 | MCP 只公開 get_submission_review，readOnlyHint=true | Host 的決策端點接 accepted；模型沒有該決策能力 |
| 確認 | 不需要修改資料的確認 | 顯示具體兩個待處理項目、提交版本；確認後才執行。拒絕為 terminal，不自動重提案 |

只查詢原文並不表示取得使用者同意；RAG 通過也不代表現在可以寫入。這是沙盒中的應用程式批准流程，沒有外部通知。

## 成功證據

唯讀 report 包含來源 synthetic-review-v1、report_hash、evidence_hash、items 與 teacher/student citations；MCP 紀錄包含 initialize、tools/list 與 tools/call 的真實結果。

寫入在同一 SQLite transaction 內建立 drafts、更新 run 及 audit。draft receipt 包含 draft_id、status=draft_created、request_id、提交與版本、項目、report_hash、created_at、delivery=local_only_not_sent。最後模型收到實際 receipt，摘要必須與之完全一致；UI 使用驗證過的事實呈現。

## Timeout、重試、停止

| 範圍 | 精確預算 | 停止行為 |
| --- | --- | --- |
| OpenAI 單次請求 | SDK timeout 30 秒，Host 每 attempt 32 秒上限；SDK max_retries=0 | 429（非額度不足）、連線／逾時、5xx 可重試 1 次，間隔 0.2 秒；其餘立即停。無 fixture fallback |
| 模型迴圈 | 每 run 最多 3 個模型回合；每回合最多 2 attempts，至多 6 次 API 嘗試 | 唯讀正常 2 回合；草稿正常 3 回合。異常多工具、順序錯誤或 JSON 不合法立即停止 |
| MCP 唯讀 | 每次包含啟動、initialize、list、call 的總 timeout 10 秒；可重試 1 次，間隔 0.2 秒 | 記錄錯誤 layer 與 attempt，不用假報告取代失敗結果 |
| 使用者確認 | proposal 600 秒內有效 | 過期停止，須建立新提案；來源變更時以 STALE_REPORT／來源 gate 拒絕 |
| SQLite | busy timeout 5 秒；BEGIN IMMEDIATE | 唯一 request_id，決策／草稿／audit 同一交易提交；無寫入重試迴圈 |
| 摘要失敗 | 沿用模型有限重試 | receipt 已存在時維持 written，UI 顯示實際完成狀態，不重做寫入 |

## 冪等與不明結果

業務冪等鍵是 Host 產生的 run ID，不是模型 call_id 或 MCP JSON-RPC id。拒絕與確認只消耗一次提案狀態；相同 request replay 回傳原收據，並發確認也只能產生一筆草稿。新 run ID 是新提案，沒有跨請求自動去重。

故障注入模擬「寫入已提交但回覆遺失」：從持久 run/audit 找回原 draft_id，標記 write_result_reconciled，再停止摘要；不再次 INSERT。若前端 HTTP 結果不明，保留 run ID，重新整理 GET 原請求，不能直接以新提案當作重試。

寫入的 model arguments 不包含 confirmed 或 request_id；receipt 的項目由已驗證報告產生，不採信模型自造內容。最終摘要以完整集合核對，錯誤摘要不發布。

## 資料與已知範圍

資料皆為自製合成文字，沿用 Week 3 原始來源卡，來源有效至 2026-12-31。UI 的本機 SQLite、自然語言輸入、provider history 留在被 Git 忽略的 tmp/，未實作自動保留期限／清理。Git 只提交經檢查的合成驗證紀錄；沒有真實學生內容與 key。

本週 LLM 做自然語言工具提案與結果摘要；讀取內容是預先撰寫的模擬評閱結果，不能據此宣稱已完成任意文件自動評分。MCP transport 不是身分驗證機制，正式部署還需要使用者身份與資料隔離。
