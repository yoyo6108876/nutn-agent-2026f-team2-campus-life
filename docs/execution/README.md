# 基準執行紀錄

執行日期：2026-09-23。資料全部來自 [合成案例](../../examples/assignment/normal.request.json)，沒有上傳真實學生作業。原始設計見 [Baseline Declaration](../week2-baseline-declaration.md)，執行方式見 [API 說明](../api-usage.md)。

## 已執行結果

| 案例 | 執行方式 | HTTP | 結果／證據 |
| --- | --- | --- | --- |
| AC-B01 正常比對 | 一次真實 OpenAI HTTPS 呼叫，經本機 FastAPI TestClient | 200 | R1=`met`、R2=`missing`，雙方需補 R2；符合人工預期。[完整紀錄](live-normal.json) |
| AC-B01 控制案例 | 固定 provider 替身一次 | 200 | 符合固定預期。[紀錄](mock-normal.json) |
| AC-B02 非法輸入 | 空的學生段落陣列，provider 呼叫零次 | 422 | 在 request_validation 停止。[紀錄](mock-invalid.json) |
| AC-B03 無根據引用 | 替身回覆只將 S1 改為不存在的 S99 | 502 | 在 grounding 停止，沒有產生通知。[紀錄](mock-ungrounded.json) |
| KF-01 驗證層限制 | 故意注入附錄提及即算完成的錯誤替身回覆 | 200 | 人工預期 R2=`uncertain`，替身卻是 `met`，gate 放行，matches_expected=false。[紀錄](mock-known-failure.json) |

KF-01 是已重現的**驗證層限制**：引用真的存在，仍不保證語意判定正確。它不是實際 LLM 錯判紀錄；真實模型在此案例的表現尚未測試。

### 真實呼叫量測

- 模型：`gpt-4.1-mini-2025-04-14`。
- Prompt：`assignment-check-v1.1`，程式實際讀取 [prompt.txt](../../assignment_checker/prompt.txt)；初稿的 v1.0-draft 保留供歷史比較。
- 呼叫時間：`2026-09-23T03:45:57Z` 左右；JSON 使用 UTC，台灣為上午 11:45。
- Provider 延遲：5.966 秒；不是完整網頁互動或資料擷取的延遲。
- 輸入 858 tokens、輸出 305 tokens，合計 1163 tokens。
- 額度／費用：未核對帳務，不把 token 數當成已出帳金額。
- 樣本量：只有一份合成正常案例，不能據此推估通用正確率、延遲分布或真實作業品質。

### 自動測試

實際執行：

```sh
.venv/bin/python -m pytest tests/test_environment.py tests/test_assignment_api.py tests/test_assignment_provider.py -q
```

結果：**43 passed, 2 warnings in 1.22s**。兩項為 Starlette／AnyIO 依賴的棄用提醒，不影響此次結果。版本固定於 [requirements-lock.txt](../../requirements-lock.txt)。

測試涵蓋：輸入非法時不呼叫 provider、200／422／502、空與重複欄位、提交版本、要求漏列、假引用、兩端提醒一致性、故意注入的語意錯判、SDK 驗證失敗／額度／速率限制、拒絕／未完成回覆與無金鑰處理。所有 pytest 測試使用替身，不發出真實 API 請求；真實請求證據獨立保存於 live-normal.json。

## 與初稿的差異

- 初稿的功能現在已實作為文字 JSON API；PDF、OCR、教學平台整合仍未實作。
- 422 與 502 的錯誤文案採用安全訊息，不回傳上游原始錯誤或輸入值；狀態碼、code、stage 為驗收依據。
- HTTP 回覆依原協定包含兩端提醒；模型只產生 checks 與提交識別，提醒由程式計算。
- 額外提供輸入長度限制、provider 錯誤分類及 45 秒逾時，沒有自動重試。
- Gate 能核對引用與結構，無法保證語意真實；老師仍需確認不確定或主觀項目。

## 證據可重現性

每份 JSON 都包含實際執行 command、輸入、provider 種類、呼叫次數、provider 輸出、最終 HTTP 回覆及 expected result。命令中的 `python` 指專案 `.venv` 的 Python。真實呼叫命令會再次消耗 API 額度；固定替身命令不會。

檔案從本機 `tmp/assignment-evidence/` 複製後納入版本控制；這批只有公開合成資料。之後若處理真實作業，不應自動將其執行紀錄提交至公開儲存庫。
