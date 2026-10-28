# Week 7：Session 清除與失效資料排除

題目沿用「以教師範例為參考的作業規格與完成度檢查助手」，第 02 組。

- 路線：**C，Session 清除**。不另建永久偏好記憶或多 Agent 框架。
- 開工基線：`031d336922622056c619e41871b9c5cb9425aae0`。
- 本週受測程式：`6a5bc9b5c3831a40620d4d38bb659899e269561c`，2026-10-28。
- Repository：https://github.com/yoyo6108876/nutn-agent-2026f-team2-campus-life
- [Memory ADR](memory-adr.md) · [三層比較](comparison.md) · [證據索引](../../reports/midterm/evidence-index.md) · [報告入口](../../reports/midterm/README.md)

## 缺口與修改位置

原工具流程沒有可清除、可隔離的 Session context。本週只把最近一次成功報告摘要接到下一次 context，讓換人、清除及來源更新時能驗證排除行為。

`week4/workflow.py` 抽出 `create_run`、`build_history` 接入點，保留原工具檢查。`week7/workflow.py` 在模型呼叫前後驗證 owner/session，組裝有來源版本的 context，只保存成功摘要。`week7/memory.py` 使用 SQLite 保存 Session、摘要與 run 綁定，清除時停用舊 Session 並刪除其摘要，重送清除要求不會重複清空新 Session。`week7/routes.py` 提供 HttpOnly cookie 與示範身分綁定，Week 7 業務資料庫與舊端點隔離。`week7/ui.html` 提供清除控制、工具紀錄與文字比對介面。

程式差異：`git diff 031d336 6a5bc9b -- assignment_checker tests/test_week7_memory.py scripts/run_week7_evidence.py`。

## 完成與限制

| 項目 | 實際狀態 |
|---|---|
| 清除／新 Session 排除舊摘要 | 離線通過；OpenAI 真實查詢通過 |
| 同 Session 使用最近成功摘要 | 離線與 OpenAI 通過；trace 指向先前 run |
| 跨使用者讀寫隔離 | 單元與 HTTP 測試通過；合成身分不等於正式帳號驗證 |
| 權威來源更新排除舊摘要 | 使用 v2 合成資料副本，執行真實檢索／引用 gate；離線通過，未做真實模型 v2 測試 |
| 未確認不寫、同 ID 重送只一份草稿 | 離線與 OpenAI 通過；不重試新的 run ID 來冒充同一請求 |
| 非法參數、服務 429 有限停止 | 故障注入通過；明確標示 fixture，非真實服務故障 |
| 原版／候選正常案例比較 | 離線通過；真實比較未全過，原版工具序列失敗，候選成功 |
| Google Cloud／ADC Gemini | `LIVE_NOT_RUN`，依組員指示使用 OpenAI，課程此項尚未達成 |

只保存一筆小於 4096 bytes 的結構化摘要，不保存原始學生文字、自由文字指令、草稿 ID 或先前同意。來源以 `source + evidence_hash` 比對；摘要是非權威資料，每次仍查新來源。清除只排除模型 context 並停用舊提案，**既有草稿與稽核紀錄仍留在本機**，目前沒有自動稽核清理政策。選擇 Session 清除，未宣稱實作記憶 TTL；24 小時 cookie 到期是瀏覽器存取邊界。

## 重現

環境與 API key 設定見根目錄 README。不要把 `.env`、cookie、SQLite 資料庫上傳 GitHub。

```sh
.venv/bin/python -m uvicorn assignment_checker.api:app --host 127.0.0.1 --port 8000
# 另一個終端
.venv/bin/python -m pytest tests/test_environment.py tests/test_assignment_api.py tests/test_assignment_provider.py tests/test_week3_retrieval.py tests/test_week4_tools.py tests/test_week5_orchestration.py tests/test_week5_comparison.py tests/test_week7_memory.py -q
.venv/bin/python -m scripts.run_week7_evidence --output-dir tmp/week7-recheck/fixture
# 下列命令實際使用 OpenAI 額度，請保留失敗紀錄，勿覆蓋提交版證據
.venv/bin/python -m scripts.run_week7_evidence --live --output-dir tmp/week7-recheck/live
```

真實模型有非決定性，溫度 0 不保證每次相同。腳本任一案例未達預期會回傳 exit 1。提交證據保留原始失敗而不反覆重跑挑選成功結果。

來源：課程 Lecture07（PDF 第 1–14 頁／投影片 77–90），特別是路線 C（84）、測試矩陣（86）、三層比較（87）、ADR（88）與證據要求（89）。教材內容作為作業規格；供應商依組員明確指示採 OpenAI，沒有把這項差異寫成符合 Gemini 要求。
