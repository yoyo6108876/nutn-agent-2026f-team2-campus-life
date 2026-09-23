# Week 2 Baseline Declaration：實作與驗證版

題目：**以教師範例為參考的作業規格與完成度檢查助手**

團隊：02；陳冠友（S11259039）、林崇偉（S11259031）。更新日期：2026-09-23。

依據：`Week2_LLMs_for_Builders_0922.pdf` 投影片 054–061，按 060 的六項提交清單整理。

**目前結果：**已完成文字 JSON API、一次真實 LLM 正常案例、200／422／502 驗收與 43 項自動測試。下文區分實際結果、固定替身與尚未驗證的功能；只有一個真實 LLM 樣本，不代表完整產品或通用準確率已達標。

## 1. 既有 User Story 與問題

> 身為學生，我希望提交作業後，系統先對照老師範例，告訴我哪些內容缺少、證據在哪裡，以及需要補充什麼，讓我能依老師規定修正。

> 身為老師，我希望學生提交後，系統先整理每份作業的缺漏與待確認項目，讓我能快速找到需要提醒或人工檢查的部分。

老師逐份核對作業容易花時間重複提醒缺漏，學生也可能直到批改後才知道漏做內容。本週用固定合成文字驗證「教師範例與確認項目 → 學生提交 → LLM 比對 → 雙方缺漏提醒」；實際使用者痛點尚待訪談驗證。

LLM 的任務是語意對照，例如範例使用「Target User」，學生寫「誰會用」仍應判為同一要求。真實案例已做到這一點；但尚未進行規則式方法與 LLM 的系統性比較，不能宣稱已證明 LLM 在所有情境都更好。

## 2. Scope / Out of Scope 與固定資料

| 本週已實作／驗證 | 尚未實作或不在本週範圍 |
| --- | --- |
| 一份教師範例、一份學生提交、教師已確認要求；文字 JSON 輸入 | PDF 上傳、文字擷取、OCR、圖片與版面分析 |
| 一次 LLM 呼叫；檢查結構、提交識別、要求完整性與原文引用 | 多工具 Agent、檢索或上網查證 |
| 由共同 checks 產生學生與老師的提醒 ID 清單 | 專用學生／老師網頁、登入、全班批次管理 |
| FastAPI 路由與本機 `/docs` 介面 | 教學平台自動收件、Email／LINE 通知 |
| 固定合成樣本與注入錯誤的驗收 | 真實學生作業品質評測、完整語意正確性保證 |
| 提醒缺漏及待確認項目 | 自動評分、代寫、接受或拒絕補交 |

只有範例、沒有教師確認項目的模式仍待開發。目前 API 必填 `confirmed_requirements`；不能把所有範例差異都當成缺交。完整產品目標見 [專案定義](week2-proposal.md)。

固定情境：`HW-DEMO-01`／`SUB-DEMO-01`／版本 `1`。教師 T1、T2 兩段；學生 S1 一段。R1 是目標使用者及情境，R2 是含輸入、結果與原因的失敗案例。所有文字均為合成資料，沒有傳送真實學生文件。

## 3. 已實作的輸入／輸出協定

介面：`POST /assistant/check-submission`。接收已整理好的文字 JSON，金鑰只由本機 `.env` 或伺服器環境變數讀取，不放入 request。正式型別及限制見 [models.py](../assignment_checker/models.py)。

### Request 必填欄位

| 欄位 | 型別與實際限制 |
| --- | --- |
| `assignment_id`、`submission_id` | 1–100 字元的無空白字串 |
| `submission_version` | 正整數，不接受布林或字串 |
| `teacher_example.sections`、`student_submission.sections` | 各 1–30 段；每段必填唯一 `id`、非空 `text` |
| `confirmed_requirements` | 1–10 項；每項必填唯一 `id`、非空 `description`、存在的 `teacher_section_id` |

所有 ID 均為 1–100 字元且不得含空白；每段文字及要求描述上限 12,000 字元，兩份文件文字與要求描述合計上限 20,000 字元。拒絕未知欄位與只有空白的文字。學生無法透過 request 覆寫模型。

固定輸入：[normal.request.json](../examples/assignment/normal.request.json)。

```json
{
  "assignment_id": "HW-DEMO-01",
  "submission_id": "SUB-DEMO-01",
  "submission_version": 1,
  "teacher_example": {
    "sections": [
      {
        "id": "T1",
        "text": "Target User：需要在提交後確認作業缺漏的南大學生。"
      },
      {
        "id": "T2",
        "text": "Known Failure：提供一個失敗案例，包含輸入、實際結果與原因。"
      }
    ]
  },
  "student_submission": {
    "sections": [
      {
        "id": "S1",
        "text": "誰會用：剛交完報告、想知道自己有沒有漏寫內容的南大同學。"
      }
    ]
  },
  "confirmed_requirements": [
    {
      "id": "R1",
      "description": "描述目標使用者及使用情境。",
      "teacher_section_id": "T1"
    },
    {
      "id": "R2",
      "description": "提供失敗案例，包含輸入、實際結果與原因。",
      "teacher_section_id": "T2"
    }
  ]
}
```

### Response 與真實正常結果

回覆必填：三個提交識別欄位、`checks`、`student_notice`、`teacher_notice`。每個 check 含要求 ID、狀態、教師證據、學生證據、理由與補充建議。

| status | 意義 | 提醒清單 |
| --- | --- | --- |
| `met` | 已符合 | 不加入提醒 |
| `partial` | 部分符合 | `needs_revision` |
| `missing` | 尚未符合 | `needs_revision` |
| `uncertain` | 無法判定 | `needs_confirmation` |

原文證據含 `section_id`、`quote`。每項要求恰有一個 check，順序依教師要求排列。兩端提醒由程式依共同 checks 計算，不分別叫模型判斷。`met`／`partial` 必須有學生引用；沒有證據使用空陣列，不捏造原文。

以下是 [live-normal.json](execution/live-normal.json) 中實際回覆，不是人工預期或替身結果：

```json
{
  "assignment_id": "HW-DEMO-01",
  "submission_id": "SUB-DEMO-01",
  "submission_version": 1,
  "checks": [
    {
      "requirement_id": "R1",
      "status": "met",
      "teacher_evidence": {
        "section_id": "T1",
        "quote": "Target User：需要在提交後確認作業缺漏的南大學生。"
      },
      "student_evidence": [
        {
          "section_id": "S1",
          "quote": "誰會用：剛交完報告、想知道自己有沒有漏寫內容的南大同學。"
        }
      ],
      "reason": "學生描述了目標使用者為剛交完報告、想知道自己有沒有漏寫內容的南大同學，與教師範例中需要在提交後確認作業缺漏的南大學生語意相符，符合目標使用者及使用情境的描述要求。",
      "suggestion": "無需補充，描述已符合要求。"
    },
    {
      "requirement_id": "R2",
      "status": "missing",
      "teacher_evidence": {
        "section_id": "T2",
        "quote": "Known Failure：提供一個失敗案例，包含輸入、實際結果與原因。"
      },
      "student_evidence": [],
      "reason": "學生提交內容中未提供任何失敗案例，缺少輸入、實際結果與原因的描述，未回應此要求。",
      "suggestion": "請補充一個失敗案例，包含輸入、實際結果與原因，以符合要求。"
    }
  ],
  "student_notice": {
    "needs_revision": [
      "R2"
    ],
    "needs_confirmation": []
  },
  "teacher_notice": {
    "needs_revision": [
      "R2"
    ],
    "needs_confirmation": []
  }
}
```

HTTP 200 代表檢查流程成功，**不代表作業全部完成**。實測結果為 R1=`met`、R2=`missing`，學生與老師的 `needs_revision` 都是 `["R2"]`。

### 實際驗證層

1. **Request validation**：檢查型別、必填、長度、唯一 ID 與教師引用；非法輸入回 422，provider 不執行。
2. **Provider**：合法輸入才呼叫 LLM；測試也可注入固定回覆替身。
3. **Response schema**：驗證回覆欄位、型別與 status；失敗回 502／`response_schema`。
4. **Grounding / consistency**：核對提交版本、要求集合、教師段落與學生引用是否存在；失敗回 502／`grounding`。
5. **Notice generation**：通過驗證後，以同一結果計算雙方提醒，回 HTTP 200。

錯誤只回傳 `error`，不附成功報告或補件通知。AC-B02 的實際錯誤：

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "stage": "request_validation",
    "message": "輸入未符合規格，請檢查必填欄位、型別、段落及要求的引用。"
  }
}
```

引用存在只證明引用有來源，不保證語意判斷正確。金鑰失效、額度不足或模型拒絕等 provider 錯誤，也不應被解釋為學生缺交。其他錯誤與操作細節見 [API 說明](api-usage.md)。

## 4. 三個 Given / When / Then：預期與實際結果

三案共用正常輸入。AC-B02 只改學生段落陣列；AC-B03 輸入不變，只在 provider 替身輸出的引用 ID 做單一修改。這些基準驗收編號與產品 AC-01 至 AC-09 分開。

| 案例 | Given / When | Then：預期結果與停止層 | 實際結果與證據 |
| --- | --- | --- | --- |
| AC-B01 正常比對 | 固定正常 request；提交後執行檢查 | 200；R1=`met`、R2=`missing`；通過各層，雙方提醒 R2 | 已執行一次真實 LLM，結果符合。[真實證據](execution/live-normal.json)；另有 [固定替身對照](execution/mock-normal.json) |
| AC-B02 非法輸入 | 只將 `student_submission.sections` 改成 `[]` 後提交 | Request validation 停止；422／`INVALID_REQUEST`；provider=0 次 | 已實測 422，provider_attempts=0。[證據](execution/mock-invalid.json) |
| AC-B03 事實依據失敗 | 合法輸入；替身回覆只把 R1 學生引用 S1 改為不存在的 S99 | schema 通過；grounding 停止；502／`UNGROUNDED_RESPONSE`；無通知 | 已實測 502，固定替身一次、真實 LLM 零次。[證據](execution/mock-ungrounded.json) |

AC-B03 證明驗證層會擋不存在的引用，不代表真實模型曾生成 S99。以上 HTTP 證據由 FastAPI TestClient 在程序內呼叫路由；AC-B01 的 provider 另發出真實 OpenAI HTTPS 請求。驗收測試見 [test_assignment_api.py](../tests/test_assignment_api.py)。

## 5. Baseline、模型與已知失敗

**Baseline：single LLM call + deterministic validation。** 短文字與固定要求先由一次模型呼叫完成語意對照，再由程式核對結構與引用，衍生雙方提醒。選擇理由是先建立最小可比較起點；不需要多工具 Agent 即可驗證核心價值。

| 設定 | 實際使用值 |
| --- | --- |
| 供應商／API | OpenAI Responses API |
| 模型固定版本 | `gpt-4.1-mini-2025-04-14`；本次真實呼叫成功 |
| Prompt 版本 | `assignment-check-v1.1`；完整指令見 [prompt.txt](../assignment_checker/prompt.txt) |
| SDK | `openai==2.54.0`；完整依賴見 [requirements-lock.txt](../requirements-lock.txt) |
| 輸出協定 | 本文件與 [models.py](../assignment_checker/models.py)，對應實作 commit `c5df16c` |
| 呼叫參數 | temperature=0、max_output_tokens=3000、store=False |
| 執行限制 | timeout=45 秒、max_retries=0、不啟用工具 |

指令要求逐項處理教師確認要求、依語意對應、逐字引用來源、保留提交版本，並將未取得附件的情境標示為待確認。模型只產生 checks；兩端 notice 由程式計算。實際指令檔與版本取代先前 v1.0-draft，舊稿可從 Git 歷史查閱。

### Known Failure KF-01：原文引用存在，仍可能錯判完成

固定輸入：[known-failure.request.json](../examples/assignment/known-failure.request.json)。正常輸入僅新增 S2：

```json
{"id": "S2", "text": "失敗案例的輸入、實際結果與原因請見附錄 A；附錄另檔繳交。"}
```

沒有提供附錄 A。人工預期 R1=`met`、R2=`uncertain`，雙方 `needs_confirmation=["R2"]`，提醒先確認附件內容。

**已重現的驗證層失敗：**固定替身故意引用真的存在的 S2，卻輸出 R2=`met`。schema、ID、引用核對均通過，最終 HTTP 200、提醒清單為空；與人工預期不符，`matches_expected=false`。[失敗證據](execution/mock-known-failure.json)。

這個結果證明目前 gate 無法判斷「引文是否足以支持已完成」，不是觀察到真實 LLM 犯錯。此情境的真實 LLM 表現尚未測試，不能寫成模型失敗率。它仍是後續改進可重跑的固定比較案例。

## 6. 重現步驟、證據與量測

在專案根目錄執行；macOS／Linux 使用下列路徑，Windows 換成 `.\.venv\Scripts\python.exe`。

### 安裝及離線驗收（不消耗 API）

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pytest tests/test_environment.py tests/test_assignment_api.py tests/test_assignment_provider.py -q
.venv/bin/python -m scripts.run_assignment_evidence --case normal --output tmp/assignment-evidence/mock-normal.json
.venv/bin/python -m scripts.run_assignment_evidence --case invalid --output tmp/assignment-evidence/mock-invalid.json
.venv/bin/python -m scripts.run_assignment_evidence --case ungrounded --output tmp/assignment-evidence/mock-ungrounded.json
```

已執行 pytest：**43 passed, 2 warnings in 1.22s**；為既有執行結果，本次文件更新未重新跑測試。43 項包含環境、API 與 provider 的替身測試，不是 43 份真實模型作業評測。兩項警告為依賴棄用提醒。

### 真實 API 重跑（使用一次 API 額度）

確認根目錄 `.env` 已設定 `OPENAI_API_KEY`，執行：

```sh
.venv/bin/python -m scripts.run_assignment_evidence --live --case normal --output tmp/assignment-evidence/live-normal.json
```

真實正常案例已成功一次，本次文件更新沿用現有證據，未再次消耗 API。金鑰檔不納入 Git，請勿在證據或作業文件中貼上金鑰。

### 固定已知失敗重跑（替身，不消耗 API）

```sh
.venv/bin/python -m scripts.run_assignment_evidence --case known-failure --output tmp/assignment-evidence/mock-known-failure.json
```

此案例預期顯示 HTTP 200、`matches_expected=false`，程式 exit code 1；它代表故意注入的語意錯誤仍能通過 gate。不要為了讓所有指令回 0 而刪除失敗證據。

### 本機 API 展示

```sh
.venv/bin/python -m uvicorn assignment_checker.api:app --host 127.0.0.1 --port 8000
```

開啟 `http://127.0.0.1:8000/docs`。範例請求可從 normal.request.json 複製到 Try it out，按 Execute 後會呼叫真實 API。`GET /health` 不呼叫模型，只代表服務存活。

### 證據清單與實測摘要

| 項目 | 目前證據與限制 |
| --- | --- |
| 固定 input／人工 expected | [examples/assignment](../examples/assignment)；與真實回覆分開保存 |
| command／provider output／HTTP output | 各 [execution JSON](execution/README.md) 均有實際命令、provider 類型、呼叫次數與結果 |
| 正常真實 LLM | 1 份合成樣本、1 次呼叫，R1/R2 判定符合預期；不足以推估準確率 |
| 用量 | input=858、output=305、total=1163 tokens |
| latency | provider 呼叫 5.966 秒；不含 PDF 擷取或完整使用者操作 |
| cost | 未核對實際帳務，不能將 token 數當作費用 |
| failure rate | 未進行足量樣本評估；KF-01 是替身注入的驗證層限制 |
| 尚未驗證 | 真實作業、PDF、只有範例未確認要求、主觀充分性、跨文件矛盾、長文件與服務配額情境 |

完整操作見 [API 說明](api-usage.md)，測試摘要與原始證據索引見 [執行紀錄](execution/README.md)。

## Exit ticket

**Q1：Structured Output 解決什麼問題？**

讓回覆遵循約定的結構、欄位、型別與 status，便於程式解析；不保證引用或語意判斷正確。

**Q2：為什麼 schema pass ≠ truth pass？**

AC-B03 的 S99 是合法字串，但原文沒有這個段落，因此由 grounding 擋下。KF-01 的 S2 引用真的存在，卻仍不能支持「已完成」，說明通過引用核對也不等於語意正確。

**Q3：為什麼不能只看能力排行榜選模型？**

需要用本專案資料比較 quality（語意比對、誤判／漏判與引用）、cost（每份作業費用）、latency（等待時間）、failure rate（失敗比例），以及 service constraints（模型權限、配額、上下文長度與資料處理限制）。目前只取得一份合成正常案例的回覆、用量與延遲；沒有足夠證據宣稱此模型是最佳選擇。
