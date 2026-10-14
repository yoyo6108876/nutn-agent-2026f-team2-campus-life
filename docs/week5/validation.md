# Week 5 前後驗收證據

驗證日期：2026-10-14。受測程式 commit：**a572b7e8f579a370a1c7d7ebb6685973f3aac074**；執行 runner 時 tracked files 無修改。後續提交的文件與證據，不冒稱為這次受測程式 SHA。原版參考 commit：`9535ccb9d7b921004925c46d2aa61adc5065c8de`；共享的 Week 4 workflow、store、provider、prompt 原檔沒有修改。

**131 項 pytest 通過，1 個 AnyIO 棄用提示，3.23 秒。** 指令見 [README](README.md)。另執行以下完整流程；pytest 的 mock 與這裡的真實模型紀錄分開。

## 相同案例的離線比較

兩版分別執行同一 JSON 輸入、同一合成資料、相同 prompt／模型設定及故障注入。[索引](../../artifacts/week5/fixture/index.json) 中九個 paired cases 全部通過（18 次版本流程），商業事實與執行次數一致。

| 五組案例 | 子案例 | 預期與實際結果（兩版） |
| --- | --- | --- |
| 正常查詢 | read-only | 完成摘要、引用可追溯，0 筆草稿 |
| 等待後重啟／確認／重送 | restart-confirm-replay | start 0 筆，新的 PID 讀回同提案；確認後 1 筆，重送維持相同收據 |
| 拒絕／過期 | decline-replay、expired-confirmation | 拒絕後再送同意仍拒絕；模擬確認時鐘前進 601 秒即 PROPOSAL_EXPIRED，皆 0 筆 |
| 證據／API／格式錯誤 | source-unavailable、provider-429、invalid-arguments | 缺必要來源時 0 模型呼叫；429 僅 2 attempts；缺參數被拒絕，皆 0 筆 |
| 寫入後失敗 | summary-failed-after-write、write-response-lost | 已寫入的 1 筆收據保留；新程序重送不重寫、不冒稱摘要成功 |

每個 JSON 均含 `expected`、各檢查的 expected/actual/passed、各版原始 operations、provider metadata、audit、MCP trace、模型與工具次數。候選另有真實 checkpoint／interrupt ID；重開程序後 ID 與提案內容都必須一致。

缺來源、429、缺參數、過期、摘要逾時與回覆遺失均為**明示注入**。其中寫入遺失使用 Week 4 的 after_write 故障點，不假稱作業系統硬崩潰測試。離線模型是 authored fixture，狀態為 `LIVE_NOT_RUN`；MCP 往返仍為真正 stdio。

## 本週真實 OpenAI 比較

[Live 索引](../../artifacts/week5/live/index.json)：兩個 paired cases、共四條流程均為 `LIVE_PASS`。原版與候選各自重新呼叫 OpenAI，沒有回放 Week 4 歷史回覆。

| 真實案例 | 原版 calls／tokens／耗時 | LangGraph calls／tokens／耗時 | 比較 |
| --- | --- | --- | --- |
| [正常查詢](../../artifacts/week5/live/read-only.json) | 2／1,941／8.235 秒 | 2／1,941／7.983 秒 | 摘要與引用事實相同，0 筆寫入 |
| [重啟後確認與重送](../../artifacts/week5/live/restart-confirm-replay.json) | 3／3,980／9.589 秒 | 3／3,972／14.535 秒 | 同提案接續，確認後各 1 筆、重送不增筆 |

模型為 `gpt-4.1-mini-2025-04-14`，提示版本 `assignment-tools-v1`。合計 **10 次真實模型回應、11,399 input tokens＋435 output tokens＝11,834 total tokens**；未查帳單金額。每列耗時是該案例所有 worker 程序的執行時間合計，包含新程序與套件載入、MCP、模型請求；不包含真人思考等待時間，不是單次 API 延遲。只有一輪樣本，不能據此宣稱速度差異具有統計意義。

候選真實確認 run：`run-82272194d01346d8bc4bf44ee70f7daa`。所有確認都是 runner 對合成沙盒資料的測試決定，非真實教師批准；草稿沒有寄出。

## 差異與限制

- 離線正常查詢：原版 1.114 秒、候選 1.455 秒；重啟確認重送：原版 3.431 秒、候選 4.204 秒。此量測含多次 Python 啟動，不單獨歸因於 checkpoint。
- 新增候選編排 172 行，API／路由／UI 共三個既有檔案轉接；新增 2 個直接框架依賴，鎖檔增加 27 個套件。沒有移除原版業務規則或模型程式；不能宣稱總程式量減少。
- 不一致提案、損壞／缺少 checkpoint、併發接續、外站 Origin、決策多餘欄位與引擎繞過另由 [Week 5 測試](../../tests/test_week5_orchestration.py) 及既有測試驗證；候選的 seal／checkpoint 診斷是額外檢查，未冒充原版已有同一框架能力。
- UI 實際操作與畫面檢查見 [UI 紀錄](ui-check.md)。真正跨程序復原由 JSON 的各 worker PID 證明。
- 未測 Linux、Windows WSL、多機服務、真實學生文件品質、任意 PDF 匯入及中斷每一個 checkpoint 的硬崩潰。使用者仍需保留兩個 SQLite 與原 run ID；來源有效期沿用 Week 3。

## 講義提交對照

| 交付 | 狀態 | 位置 |
| --- | --- | --- |
| 原版＋候選、實驗分支、接回原入口與切換 | 已完成 | [README 保留／替換／轉接](README.md)、程式 commit |
| 同資料 3–5 組案例、前後結果、失敗與 trace | 已完成 | 五組九個離線案例、兩個 live 案例 |
| 等待後重啟、拒絕、過期、冪等 | 已完成（合成資料） | runner 及測試；checkpoint 不取代交易唯一鍵 |
| 實際模型驗證、用量、版本、無金鑰或個資 | 已完成（OpenAI） | live JSON 與鎖檔，合成資料限定 |
| 一頁重構決策與回退 | 已完成 | [decision.md](decision.md)，原版仍為預設 |

這次提交完成不代表任意學生作業辨識品質或正式部署已通過。Week 3 教師案例缺來源等既有未完成項目，仍保留原週文件，不用 Week 5 比較代替。
