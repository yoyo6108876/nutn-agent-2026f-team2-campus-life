# Week 3：Retrieval Proposal 與 Generator Comparison

本版依 **Lecture03_Agentic_AI_Engineering_RAG (1).pdf** 重新對照。使用者提供的檔案共 8 頁，內容是投影片 47–54；不是整份 54 頁教材。需求對照見 [講義核對表](requirements-audit.md)。

**目前完成：** 專案 normal／paraphrase／no-answer 三題、額外 coverage failure、來源治理、top-k trace 與 Offline／Fixture 比較。**尚未完成：** 教師羽球館「學生資格／平日費率／假日例外」原始三段證據驗收；這份 PDF 沒有附原文或金額。舊 B1 開放時間案例只能當補充練習，不能代替教師指定案例。

## 提交入口

| 交付項目 | 檔案／狀態 |
| --- | --- |
| 一頁 Proposal | [使用者、單一 claim、範圍、拒答、baseline](proposal.md) |
| Source card | [owner、來源、權限、更新、撤回、衝突、PII、retention](source-card.md) |
| 3–10 stable chunks | [dataset.json](../../examples/week3/dataset.json)：專案 6 段，舊補充案例 4 段；chunk ID 不變 |
| 三個 fixed queries | Q1 normal、QP paraphrase、Q2 no-answer；問題及期望 ID 已固定 |
| Coverage failure | Q3，與 Q1 同題但 k=2；`MISSING_REQUIRED_ASPECT`，所有 generator 跳過 |
| Top-k trace | [Q1](../../artifacts/Q1-top-k-trace.json)、[QP](../../artifacts/QP-top-k-trace.json)、[Q2](../../artifacts/Q2-top-k-trace.json)、[Q3](../../artifacts/Q3-top-k-trace.json) |
| Generator comparison | [artifacts/week03-generator-comparison.json](../../artifacts/week03-generator-comparison.json) |
| Failure observation | [說明](failure-observation.md)、[JSON](../../artifacts/failure-observations.json) |
| 教師多證據案例 | [T1 安全拒答 trace](../../artifacts/T1-top-k-trace.json)、[缺件與補入方式](teacher-case.md)；尚待原始 pricing chunks |

## 固定問題、檢索與拒答

| ID | 用途與固定問題 | 預期／本次結果 |
| --- | --- | --- |
| Q1 | normal：學生作業的使用者、失敗案例與附錄證據符合老師範例嗎？哪些要補件或確認？ | k=6，`answered` |
| QP | paraphrase：同學交的報告裡，誰會用、出錯範例和附錄是否交代清楚，還缺哪些內容？ | k=6，`answered`；同一意圖、相同 gold IDs、不同排序 |
| Q2 | no-answer：截止日期？ | `no_answer`／`NO_EVIDENCE`；無日期證據 |
| Q3 | 額外 coverage failure：與 Q1 完全相同，只有 k 改為 2 | `coverage_failure`／`MISSING_REQUIRED_ASPECT`；無生成器呼叫 |
| T1 | 教師案例：持學生證的學生，週五 16:00 平日每小時場租多少？遇假日是否適用？ | 原始 pricing corpus 尚空，`NO_EVIDENCE`；不是教師驗收通過 |
| B1 | 歷史補充：週六開放時間／預約／鞋款 | 合成練習，另列，不計入三題或教師 checkpoint |

每份 trace 保存 query、k、排名 ID、scores、matched terms、selected evidence、來源版本、資料集與證據 hash，以及 **gold／acceptable IDs、should_refuse、失敗觀察、重現指令**。期望標註是 Codex 依合成文字預先撰寫、待教師覆核；執行器只在生成後將標註附到 trace，不傳給 LLM。

流程：固定 query ID 決定資料範圍 → 篩除撤回／未授權／非合成無 PII／過期來源 → 依明確來源優先順序處理已登錄衝突；同優先序衝突拒答 → 透明 lexical 檢索 → coverage gate → 固定 evidence → generators → 引用核對與系統附 citation。

Lexical baseline 將中文切雙字詞、英文切詞，用 `重疊詞數 / 查詢詞數` 計分，分數大於 0 才進排名，同分按 chunk ID 排序。沒有實作 BM25／dense／RRF：PDF 的 worked example 畫出 Hybrid 流程，但專案初始檢索要求透明 baseline；這裡如實標示採用的方法，不將 lexical 稱為 hybrid。

`fact_ids` 與 `role` 是手動建立的索引中繼資料，不是正確答案。每項作業 fact 必須同時找到 teacher／student；場館事實需 reference。證據不足時不把學生判為 missing。已知來源衝突由 `conflicts_with` 與 `precedence` 宣告處理，沒有自動語意矛盾偵測。

## Generator 比較結果

本次正式輸出為 **Offline vs Gemini Fixture** 路徑：`provider=gemini_fixture`、`llm_actually_called=false`。Fixture 是專案預先撰寫的整合回答，**不是 Gemini 錄製回覆，也沒有呼叫 Gemini API**；名稱對齊講義的 fixture contract。原有 OpenAI live 路徑保留為額外功能。

| Case | Offline 正確 fact coverage | Fixture 正確 fact coverage | same_selected_evidence | same_citations | Fixture unsupported claims／numeric |
| --- | --- | --- | --- | --- | --- |
| Q1 | 0/3 | 3/3 | true | true | 0／[] |
| QP | 0/3 | 3/3 | true | true | 0／[] |
| Q2、Q3、T1 | 未呼叫 | 未呼叫 | 不適用 | 不適用 | 不計分 |
| B1（補充） | 3/3 | 3/3 | true | true | 0／[] |

`same_selected_evidence` 比較 generator 輸入的 evidence hash；`same_citations` 比較每個 fact 所引用的 chunk IDs，原文 quote 另經 gate 驗證。`fact_coverage` 需 value 符合預設標註且必要引用齊全。錯誤的非 uncertain 結論計入 unsupported claims；錯誤數字結論另列 `unsupported_numeric_claims`，引用內的原文數字不當作新增結論。作業狀態沒有數值，numeric=[] 不能推論具備一般數字推理能力。

引用 gate 只證明來源／格式／角色一致，不能保證語意正確。Oracle 只供封閉案例離線評測，未做通用 entailment 驗證。Fixture 3/3 代表流程與規格可重現，不能算成 LLM 能力實測。`all_expected_checks_passed=true` 也**不代表整份作業驗收完畢**，JSON 另有 `teacher_checkpoint_complete=false`。

## 重現與 API

沿用既有 Python 環境即可；不需新增套件或金鑰。與講義相同的入口：

```sh
.venv/bin/python -m scripts.run_studio_generator_lab --path auto
```

產生 `artifacts/week03-generator-comparison.json`、六份 `*-top-k-trace.json` 與 `failure-observations.json`。`auto` 明確採 fixture，不讀 Gemini key、不自動消耗現有 OpenAI key；`--path fixture` 同等。要保留既有結果可指定 `--output tmp/week3-new/week03-generator-comparison.json`。

```sh
.venv/bin/python -m pytest tests/test_environment.py tests/test_assignment_api.py tests/test_assignment_provider.py tests/test_week3_retrieval.py -q
.venv/bin/python -m uvicorn assignment_checker.api:app --host 127.0.0.1 --port 8000
```

本次 **85 passed、2 warnings**（Starlette／AnyIO 既有棄用提示）；舊的未完成課表檔案不在本次範圍。Swagger 位於 `http://127.0.0.1:8000/docs`：

```sh
curl -s http://127.0.0.1:8000/assistant/week3/query \
  -H 'Content-Type: application/json' \
  -d '{"query_id":"QP","mode":"fixture"}'
```

GET `/assistant/week3/queries` 列出案例。POST 預設 fixture；只有明確指定 `mode=live` 才在 gate 通過後使用既有 OpenAI API。CLI 額外選項 `--path openai-live` 會呼叫三次 OpenAI（Q1、QP、B1），本次未執行。模型與 API 選項仍沿用 [既有說明](../api-usage.md)，未新增 Gemini live SDK，也未將 OpenAI 記為 Gemini。

## 歷史證據與範圍

[evidence/live](evidence/live/generator-comparison.json) 和 [evidence/fixture](evidence/fixture/generator-comparison.json) 保留先前依兩張截圖完成的 v1 結果；未改寫成新版測試。其 B1 是開放時間案例，不能支援教師費率驗收；Q1 舊實測仍可當語意比對補充。正式提交以根目錄 `artifacts/` v2 為準。

Week 2 任意文字 JSON API 保留；Week 3 端點目前只操作固定合成語料，PDF 上傳、自動 chunk/tag、自由查詢路由、身分驗證仍未實作。取得教師參考資料後，依 [teacher-case.md](teacher-case.md) 補 source card、三份 chunk 與期望答案，再執行教師多證據 checkpoint；不推定已完成。
