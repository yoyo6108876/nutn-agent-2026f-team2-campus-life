# Week 3 Source Card

資料集：`week3-synthetic-v1`，建立／檢閱日 **2026-09-30**。機器可讀設定與全文：[dataset.json](../../examples/week3/dataset.json)。只包含本專案新撰合成文字，未複製講義全文、真實作業或校方公告。

| 欄位 | 說明 |
| --- | --- |
| Authority | `teacher-demo` 在此模擬作業內定義要求；`student-demo` 僅為提交內容，不得覆蓋教師要求；`court-*-demo` 只對合成場館案例有效，非南大官方資料。 |
| Permission | 自製合成測試文字，准許本專案本機測試、API 測試與公開儲存庫展示；來源記錄 `permission=true`。不推定已取得真實教師教材或學生作業授權。 |
| Freshness | 每份來源 `version=synthetic-v1`、`updated_at=2026-09-30`、`valid_until=2026-12-31`。執行時依主機日期篩選；到期要重新檢閱及更新來源，不可只為通過測試任意延長。trace 記錄 policy date、來源版本與資料集 hash。 |
| PII | 全部 `synthetic_no_pii`；測試文字沒有姓名、學號、帳號或真實學生內容。README 的團隊姓名學號不進入檢索資料集或 LLM 請求。非此標記的來源先排除。此欄依人工宣告，沒有自動 PII 偵測。 |
| 撤回 | 將來源 `withdrawn` 改成 `true`，下一次請求重新載入並排除；不保留向量索引。另人工清理含原文的 trace、比較結果與公開 Git 歷史。排除新請求不代表已發布副本自動刪除。 |
| 提供者處理 | Live 僅將選定的合成段落、問題與輸出規格送 OpenAI；`store=false`，無工具、無自動重試。此設定不代表供應商所有日誌零留存。API key 不在資料集、trace 或 Git。 |

| source_id | 角色／權威範圍 | Chunks | 狀態 |
| --- | --- | --- | --- |
| `teacher-demo` | 模擬教師的確認要求 | T1、T2、T3 | 可用 |
| `student-demo` | 模擬學生提交，不得新增評分要求 | S1、S2、S3 | 可用 |
| `court-hours-demo` | 合成開放時間公告 | B-hours | 可用 |
| `court-booking-demo` | 合成預約公告 | B-booking | 可用 |
| `court-shoes-demo` | 合成鞋款公告 | B-shoes | 可用 |
| `court-old-demo` | 已撤回的合成舊公告 | B-old | 排除，不可引用 |

來源依段落手動切成 chunk，穩定 ID 連回此卡與版本。`fact_ids`、`role` 由教材作者標註，只表示段落主題與角色，不包含 oracle 正確答案，也不等同語意蘊含的證明。

真實課程導入前，由老師確認要求、使用目的與資料授權；限制可存取對象並去識別化。現行端點只接受固定 query ID，不能用來上傳真實文件；來源權限欄也不是身分驗證或學生隔離機制。
