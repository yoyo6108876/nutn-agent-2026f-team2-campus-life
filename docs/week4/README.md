# Week 4：Tool Use 與 MCP

沿用「作業規格與缺漏檢查助手」，新增 **讀取缺漏報告 → 模型提出補件草稿 → 使用者確認 → 本機寫入 → 工具結果回送模型 → 核對摘要**。

使用者已明確指定沿用專案 **OpenAI key**。本次真實 OpenAI 迴圈為 `LIVE_PASS`，不標示為 Gemini 成功。Lecture4 PDF（10 頁、投影片 62–71）要求 Gemini 的部分列為供應商差異；其餘一讀一寫、MCP、確認、重試、冪等、UI 與證據流程依講義實作。

## 啟動與操作

```sh
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m uvicorn assignment_checker.api:app --host 127.0.0.1 --port 8000
```

開啟 **http://127.0.0.1:8000/week4**。沿用根目錄 `.env` 的 `OPENAI_API_KEY`／`OPENAI_MODEL`；[.env.example](../../.env.example) 沒有真實金鑰，不需要 Gemini key。

1. 選擇示範提交第 1 版，輸入需求；模式可選 OpenAI 實際 AI 或離線示範。
2. 「只看缺漏」只讀報告；「準備補件清單」先取得報告，再由模型提出草稿。
3. 檢查引用、需補件與待確認項目，按「確認建立草稿」才寫入；取消不建立。
4. 成功結果顯示 draft ID、request ID；重新整理可讀回同一筆狀態。草稿只存在本機，沒有寄信、傳訊或教學平台寫入。

目前只支援 **HW-DEMO-01／SUB-DEMO-01／第 1 版的合成示範資料**。MCP 讀取的是既有合成評閱快照，會重驗 Week 3 來源、有效期、coverage 與引用；不是在本週悄悄重新呼叫模型評分。任意作業文字比對仍使用 Week 2 API，PDF 上傳尚未實作。

## 一讀一寫與模型迴圈

| 工具 | 輸入 | 執行與輸出 |
| --- | --- | --- |
| `get_submission_review` | assignment_id、submission_id、submission_version | 真正 stdio MCP 往返 initialize → tools/list → tools/call；唯讀回傳既有 report、items、needs_revision、needs_confirmation、來源與 hash |
| `create_revision_draft` | 同上，另有 requirement_ids | 模型只提案。Host 核對報告項目、版本、來源及確認，SQLite 交易寫入本機草稿與 audit；回傳 draft_id、status、request_id |

模型參數不得帶 confirmed／accepted／request_id；額外欄位會拒絕。使用者從決策端點提交 accepted，Host 以 run ID 作業務冪等鍵。MCP server 只公開唯讀工具，寫入由本機 Host 控制。

完整操作規則見 [Action Readiness](action-readiness.md)。模型提出 function call 後，Host 驗證及執行，再回送 OpenAI `function_call_output`；這對應講義 Gemini `functionResponse` 的用途，但保留各自協定名稱。

最終摘要為模型產生的結構化 JSON，Host 逐一核對提交版本、缺漏清單、draft ID 與實際狀態，才顯示中文結果；不發布未驗證的自由敘述。完整模型訊息與模型回傳的 metadata 保留於合成測試證據，未取得欄位明示「未取得」。

## 本次驗證

受測程式 commit：**9b59df92db7d2f2c2803883ca3929aa501d57d0a**。證據在該程式提交完成、tracked files 無變更時執行；後續提交新增文件與證據，不把文件提交 SHA 假稱受測程式版本。

- **107 項測試通過**，2 個既有 Starlette／AnyIO 棄用提示。
- [真實 OpenAI 成功紀錄](../../artifacts/week4/live/live-success.json)：`LIVE_PASS`、3 次 API 呼叫，完成 MCP 讀取、草稿提案、測試確認、單筆寫入、結果回送與摘要驗證。
- 模型 `gpt-4.1-mini-2025-04-14`，prompt `assignment-tools-v1`；三次 input 合計 3,829、output 140、total **3,969 tokens**；模型請求延遲合計約 **7.908 秒**，不是端到端延遲。未查帳單金額。
- Live run ID：`run-3df5baba98fd474cb60a0e7141412f30`。本機測試草稿：`draft-621b468915964c7c8edd7eb1c467fec5`；request replay 後仍只有一筆。此為測試 runner 對合成資料模擬確認，非真實教師或學生的批准。
- [九個離線情境](../../artifacts/week4/fixture/index.json)全部符合預期；錯誤、429、摘要失敗、寫入回覆遺失皆有明確故障注入標記。
- [UI 檢查紀錄](ui-check.md)；[逐項自評與講義對照](self-check.md)。

以上是固定合成流程驗證，不代表對任意學生作業的判斷品質或正式多使用者服務已通過。

## 重現證據

```sh
# 九個離線情境：真實 MCP transport，但不呼叫 LLM
.venv/bin/python -m scripts.run_week4_evidence --output-dir tmp/week4-fixture

# 真實 OpenAI：三個模型回合，並模擬確認合成本機草稿；會使用 API 額度
.venv/bin/python -m scripts.run_week4_evidence --live --output-dir tmp/week4-live

# 回歸與新增工具流程測試
.venv/bin/python -m pytest tests/test_environment.py tests/test_assignment_api.py tests/test_assignment_provider.py tests/test_week3_retrieval.py tests/test_week4_tools.py -q
```

每次 runner 使用獨立暫存 SQLite，保存 sanitized JSON 後移除測試資料庫；不影響 UI 的 `tmp/week4/state.sqlite3`。不在 API 失敗後自動改用 fixture，live 未成功時保存 `LIVE_FAIL`；缺 key 則 `LIVE_NOT_RUN`。等待確認為 `LIVE_IN_PROGRESS`，使用者取消為 `LIVE_STOPPED_BY_USER`；這些中間／停止狀態不冒稱完整成功。

## API 與檔案

- GET `/week4`：操作 UI。
- POST `/assistant/week4/runs`：自然語言需求＋所選提交＋intent（read/draft）＋mode（fixture/live）。
- POST `/assistant/week4/runs/{run_id}/decision`：僅接受 `{"accepted":true}` 或 false，其他欄位拒絕。
- GET `/assistant/week4/runs/{run_id}`：恢復已存在請求與寫入收據。
- [工具契約](../../assignment_checker/week4/contracts.py)、[Host](../../assignment_checker/week4/workflow.py)、[SQLite](../../assignment_checker/week4/store.py)、[MCP server](../../assignment_checker/week4/mcp_server.py)、[模型 adapter](../../assignment_checker/week4/provider.py)。

本機示範限 localhost，沒有使用者登入或學生間權限隔離；前端外站 Origin 寫入請求會拒絕，但此措施不等同完整身分驗證。下一週可用「確認後接續同一請求」及「寫入完成但摘要失敗」比較流程編排方式，不必先換框架。

技術依據：[OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)、[官方 MCP Python v1 SDK](https://py.sdk.modelcontextprotocol.io/v1/)。保留既有相容介面，鎖定 `mcp==1.30.0`；未實作講義附錄標為延伸設計的 MRTR 補問協議。
