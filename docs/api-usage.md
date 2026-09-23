# 作業比對 API：執行與驗證

目前已實作 **single LLM call + 輸入驗證 + 引用核對 + 雙方提醒**。接收整理好的文字 JSON；本版本尚未提供教師 PDF 上傳、OCR、學生登入或教學平台自動收件。測試資料均為合成案例。

## 安裝

在專案根目錄執行（macOS / Linux）：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
```

Windows 可將 `.venv/bin/python` 換成 `.\.venv\Scripts\python.exe`，建立環境使用 `py -m venv .venv`。`requirements-lock.txt` 保存此次通過測試的依賴版本；`requirements.txt` 與 `requirements-dev.txt` 則記錄可接受的版本範圍。

專案根目錄的 `.env` 使用 `OPENAI_API_KEY`，可參考 [.env.example](../.env.example)。程式自動讀取此檔案，已設定的 shell 環境變數優先。金鑰不由 request 傳入，也不會放入 API 回覆；`.env` 已被 Git 忽略。`.env.local` 不是此版本的讀取位置。

## 啟動與呼叫

```sh
.venv/bin/python -m uvicorn assignment_checker.api:app --host 127.0.0.1 --port 8000
```

瀏覽器開啟 `http://127.0.0.1:8000/docs` 查看 API 規格。這是本機教學版本，不含使用者認證，請保持綁定 `127.0.0.1`。

在另一個終端機、專案根目錄執行以下指令，將固定合成範例送往已啟動的 API。**每次成功進入 provider 都會發出一次真實 OpenAI 請求，使用 API 額度。**

```sh
curl -sS http://127.0.0.1:8000/assistant/check-submission \
  -H 'Content-Type: application/json' \
  --data-binary @examples/assignment/normal.request.json
```

請求範例：[normal.request.json](../examples/assignment/normal.request.json)。資料包含老師兩段範例、學生一段作業與兩項教師確認的要求。回覆逐項列出 status、原文引用、理由與補充建議，並提供 `student_notice`、`teacher_notice`。兩端的提醒 ID 都由同一份 checks 推導。

預期結果：R1 已描述使用者，判定 `met`；R2 未提供失敗案例，判定 `missing`；雙方的 `needs_revision` 均為 `["R2"]`。HTTP 200 代表檢查流程完成，不代表學生作業沒有缺漏。

`GET /health` 只檢查服務存活，不呼叫模型，不能用它判斷金鑰或 API 餘額是否有效。

## 回覆與錯誤

| HTTP | stage | 意義 |
| --- | --- | --- |
| 200 | 成功回覆無 error | 完成結構及引用驗證，內文仍需語意品質評估 |
| 422 | `request_validation` | 必填、型別、空文字、重複 ID、無效教師引用或輸入長度不符；不呼叫模型 |
| 502 | `response_schema` | 模型回覆結構不符 |
| 502 | `grounding` | 原文沒有引用、提交識別不一致或缺少要求等 |
| 502 | `provider` | 金鑰失效、額度不足、連線錯誤、拒絕／未完成回覆等；以 error.code 區分 |
| 503 | `configuration` | 本機沒有可讀取的 API 金鑰 |
| 504 | `provider` | 超過 45 秒未完成回應 |

所有錯誤只回傳 error，不會把 API 失敗當成學生缺交。正常情況每次檢查只呼叫一次 Responses API，不自動重試；最多輸出 3000 tokens，`store=False`。錯誤訊息不直接回傳上游原始錯誤內容。

輸入限制：每份文件 1–30 段，每段及要求描述上限 12,000 字元；所有文件文字與要求描述合計 20,000 字元；教師確認要求最多 10 項。模型設定預設沿用 `gpt-4.1-mini-2025-04-14`，程式使用 [prompt.txt](../assignment_checker/prompt.txt)，版本 `assignment-check-v1.1`。

## 不消耗 API 的測試

```sh
.venv/bin/python -m pytest tests/test_environment.py tests/test_assignment_api.py tests/test_assignment_provider.py -q
.venv/bin/python -m scripts.run_assignment_evidence --case normal --output tmp/assignment-evidence/mock-normal.json
.venv/bin/python -m scripts.run_assignment_evidence --case invalid --output tmp/assignment-evidence/mock-invalid.json
.venv/bin/python -m scripts.run_assignment_evidence --case ungrounded --output tmp/assignment-evidence/mock-ungrounded.json
```

上述測試使用 provider 替身，保存的 `provider_kind` 是 `fixture_test_double`。422 案例應記錄 provider_attempts=0；502 引用案例只呼叫替身一次。即使本機 `.env` 有金鑰，這些指令也不會發出真實請求。

## 真實 API 證據

以下指令透過 FastAPI TestClient 在程序內測試 HTTP 路由，再發送一次真實 OpenAI HTTPS 請求；不需要另啟伺服器。

```sh
.venv/bin/python -m scripts.run_assignment_evidence --live --case normal --output tmp/assignment-evidence/live-normal.json
```

證據包含合成 request、provider 結構化原始輸出、最終 response、狀態碼、實際模型與 prompt 版本、token 使用量、延遲及與人工預期的比對。`tmp/` 被 Git 忽略，方便之後處理非公開資料；本次僅將已檢查的合成證據另外保存至 [執行紀錄](execution/README.md)。

## 已知限制與固定失敗

```sh
.venv/bin/python -m scripts.run_assignment_evidence --case known-failure --output tmp/assignment-evidence/mock-known-failure.json
```

這個指令故意注入「學生提到另檔附錄，就視為已完成」的錯誤判定。引用確實存在，所以目前的結構與引用 gate 會放行，HTTP 200；但人工預期應是 `uncertain`。指令因此回傳 exit code 1、`matches_expected=false`。這是**已重現的驗證層限制**，不是宣稱真實 LLM 曾經犯同一錯誤。

日後若要檢查真實模型是否犯此錯，另執行 `--live --case known-failure`；它會消耗 API 額度，目前尚未執行。單一正常案例成功不代表任意作業皆能正確判定。

此版本只處理教師已確認的要求；「只有範例、尚未確認必做項目」仍需後續實作，不能把未確認的範例差異直接當成學生缺交。引用檢查也無法保證論述充分性、外部事實或老師主觀標準。

## 串接參考

採用 OpenAI 官方的 [Structured Outputs 說明](https://developers.openai.com/api/docs/guides/structured-outputs)，以 Responses API 與 Pydantic 結構定義取得可解析結果，再執行本專案的引用核對；不是只憑 JSON 能解析就判定內容正確。
