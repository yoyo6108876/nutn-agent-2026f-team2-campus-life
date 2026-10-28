# 證據索引

第 02 組；2026-10-28；受測程式 `6a5bc9b5c3831a40620d4d38bb659899e269561c`。所有資料為合成，真實供應商為 OpenAI。UTC 時間記於 JSON，當地為 Asia/Taipei（UTC+8）。原版與候選在同一受測 commit 比較，開工基線另為 `031d336`。

**狀態分開記錄：** `LIVE_PASS` 表示該路徑實際呼叫成功；`LIVE_FAIL` 表示已呼叫但任務未達終點；`LIVE_NOT_RUN` 表示未執行。fixture / OFFLINE_PASS 不是 live。課程指定 Gemini／ADC 全部 `LIVE_NOT_RUN`。

## 真實執行與失敗

| 證據 | 預期 | 實際與 run ID |
|---|---|---|
| [C01 前後比較](../../artifacts/week7/live/C01-normal-comparison.json) | 兩者完成、摘要一致 | **比較 FAIL**；原版 `run-6f3dac3fe9c943b789cdfd04f37570a8`：`LIVE_FAIL / UNEXPECTED_TOOL_SEQUENCE`，未寫入；候選 `run-b2dcc5db19c54b1891a8efcd201013cc`：`LIVE_PASS / completed` |
| [W01/W02 確認與重送](../../artifacts/week7/live/W01-W02-confirmation-replay.json) | 確認前 0；確認後及同 ID 重送都是 1 | PASS，同候選 run、同一收據。腳本自動模擬沙盒確認，不是老師核准 |
| [C03 同 Session](../../artifacts/week7/live/C03-same-session.json) | 帶入最近成功摘要 | `run-fa3edd8c0f8d4961a5f1efb47616f3ea`，`LIVE_PASS`，context 指向先前正常 run |
| [C04 清除後](../../artifacts/week7/live/C04-clear-context.json) | 舊摘要與 run ID 不進入新 context，新查詢完成 | `run-b26767ea41b54abfbe6edb9360fd3704`，`LIVE_PASS`，`memory:null` |
| [C02 跨使用者](../../artifacts/week7/live/C02-cross-user.json) | 另一人不得讀取；他的 context 為空 | PASS，`RUN_NOT_FOUND`。這是 live suite 中的伺服器權限檢查，本項本身沒有 LLM 呼叫 |
| [語意比對](../../artifacts/week7/live/semantic-review.json) | R1 met、R2 partial | `LIVE_PASS`，結果符合預期，含教師／學生原文與 provider usage |
| [實際 UI 工具執行](../../artifacts/week7/live/ui-tool-run.json) | UI 提出需求、call、確認、result、模型摘要 | `run-36f871ae810848cc95360131840289ba`，`LIVE_PASS`，有收據及 `memory_persisted:true` |
| [實際 UI 語意執行](../../artifacts/week7/live/ui-semantic-review.json) | UI 文字經 GPT 比對並核對引用 | `LIVE_PASS`，R1 met、R2 partial；未接回草稿快照 |

完整 [live index](../../artifacts/week7/live/index.json) 的 `all_passed=false`，因 C01 基線失敗。不要只抽候選成功而稱整組比較通過。失敗原因是模型讀取後直接輸出摘要，Host 在 expected tool 檢查處停止；尚未證明是措辭或非決定性造成。

## 離線、故障注入與測試

8 個 [fixture 案例](../../artifacts/week7/fixture/index.json) 均符合預期，使用 authored fixture，不使用 API：正常比較、確認重送、同 Session、跨人、清除、來源更新、非法參數、provider 429。

- [來源 v2](../../artifacts/week7/fixture/C06-source-update.json)：修改合成來源副本的版本與文字，使用實際 retrieval／引用 gate，確認新 hash 與 `source_version_changed`。讀取器標示 in-process fixture，並非 MCP 或真實模型驗證。
- [非法參數](../../artifacts/week7/fixture/C07-invalid-arguments.json)：故障注入缺少必要欄位，預期與實際均 `INVALID_TOOL_ARGUMENTS`，無寫入。
- [模型服務 429](../../artifacts/week7/fixture/C08-provider-failure.json)：故障注入，預期與實際均有限重試後 `PROVIDER_429`，無新寫入。
- [pytest 原始輸出](../../artifacts/week7/pytest.txt)：**148 passed，1 個 AnyIO deprecation warning**；本週新測試 17 項。這是明列的專題回歸檔案清單，不包含已放棄的課表題目未追蹤檔案。
- [測試程式](../../tests/test_week7_memory.py)：另含舊提案清除後拒絕、跨人寫入、Cookie／Origin、來源不符、摘要無效、鎖定衝突、重送清除不傷新 Session、輸入總長上限。

重現命令與版本比較口徑見 [Week 7 說明](../../docs/week7/README.md) 與 [三層比較](../../docs/week7/comparison.md)。自動 runner 共 10 個實際模型回覆、12,703 tokens（去除同 run 重複紀錄）；UI 另 4 次、5,593 tokens，合計本輪保存的 14 次、18,296 tokens。這是 token 用量，不是帳單金額。

## 截圖備援

以下均為 2026-10-28、程式 `6a5bc9b`，由本機 `127.0.0.1:8001/week7` 實際操作擷取。交付啟動網址為 8000，程式相同。檔案本身未加裝飾標註，日期／版本由本索引與 manifest 綁定。

| 畫面 | 模式與意義 |
|---|---|
| [01 等待確認](screenshots/01-live-confirmation.jpg) | 真實 GPT 提案完成，`LIVE_IN_PROGRESS / awaiting_confirmation`，尚未寫入 |
| [02 草稿完成](screenshots/02-live-completed.jpg) | 真實 GPT `LIVE_PASS`、草稿收據，未對外通知 |
| [03 語意比對](screenshots/03-live-semantic.jpg) | 真實 GPT 指出缺失敗原因，引用可核對 |
| [04 清除對話](screenshots/04-cleared-session.jpg) | 真實 UI 操作，新 Session 的 `memory:null`；清除動作本身不呼叫 LLM |

本次備援採截圖序列，未錄製影片。PDF 第 8–9 頁使用相同截圖的結果區域，完整畫面保留於上列連結。若改用離線示範或截圖播放，現場必須明示。

## 已知缺口與補驗證

Gemini／ADC 未執行、Week 6 未核對、Week 3 教師費率案例缺原文。PDF 上傳、正式登入、教師角色、外部通知與語意結果接草稿仍規劃中。來源 v2 的 GPT 驗證尚未執行。下一步與驗收方式見 [分工進度](team-progress.md)。GitHub repository 已查詢為 PUBLIC，教師可讀取公開檔案；未宣稱教師已驗收或已閱讀。
