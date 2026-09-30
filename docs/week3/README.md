# Week 3：Retrieval + Generator Comparison

本週沿用「作業規格與缺漏檢查助手」，完成可執行的檢索／證據固定／生成比較／引用檢查流程。**程式、fixture 與兩次真實 API 測試已完成；教師原始多證據案例尚未取得，仍待教師 checkpoint 驗收。** 不將合成羽球館規則當成南大真實規則。

## Gate 對照

| 截圖要求 | 本專案交付 | 狀態 |
| --- | --- | --- |
| 一頁 proposal：使用者、claim、資料範圍、拒答 | [Proposal](proposal.md) | 完成 |
| source card：authority、permission、freshness、PII、撤回 | [Source card](source-card.md)及 [機器可讀來源](../../examples/week3/dataset.json) | 完成 |
| 三個 fixed queries，包含 no-answer 與 coverage failure | Q1、Q2、Q3，見下表 | 完成 |
| 教師多證據案例，羽球館 3/3 與 0 unsupported | B1 合成替代案例已跑 fixture／live；未提供原始案例 | 待原案例驗收 |
| Team repo + top-k trace + generator comparison JSON | [實測比較 JSON](evidence/live/generator-comparison.json)及四份 trace | 完成 |
| failure observation | [觀察說明](failure-observation.md)、[故障注入 JSON](evidence/live/failure-observations.json) | 完成 |

## 固定查詢與結果

| ID | 查詢／設定 | 預期與實測 | 證據 |
| --- | --- | --- | --- |
| Q1 | 學生作業的使用者、失敗案例與附錄證據符合老師範例嗎？哪些要補件或確認？`top_k=6` | `answered`；使用者 met、失敗案例 partial、附錄 uncertain | [top-k trace](evidence/live/Q1-top-k-trace.json) |
| Q2 | 截止日期？`top_k=6` | `no_answer`；沒有日期資料、零模型呼叫 | [top-k trace](evidence/live/Q2-top-k-trace.json) |
| Q3 | 與 Q1 完全相同問題，唯一更改為 `top_k=2` | `coverage_failure`；缺教師要求與附錄段落、零模型呼叫 | [top-k trace](evidence/live/Q3-top-k-trace.json) |
| B1 | 羽球館週六開放時間、預約方式與入場鞋款限制？`top_k=3` | `answered`；三份合成來源、3/3、unsupported=0；舊公告撤回排除 | [top-k trace](evidence/live/B1-top-k-trace.json) |

Q3 說明「搜到兩段」不等於「可以判定作業完整」。將 Q3 的 top-k 改回 6 可恢復回答。`uncertain` 是對已找到資料中的資訊缺口作判斷；`coverage_failure` 則在生成前拒答，兩者不同。

## 檢索、固定證據與生成

1. 伺服器依固定 query ID 選資料範圍；只用具權限、有效期內、合成無 PII、未撤回的來源。
2. 以英文詞及連續中文字的雙字詞集合計分：`交集詞數 / 查詢詞數`，分數需大於 0；分數相同依 chunk ID 排序。此為透明的小型 lexical baseline，沒有實作 embeddings、vector store、hybrid 或 reranker。
3. 依 top-k 選段，檢查每個必要 fact 的角色覆蓋。作業判斷需要 teacher 與 student，場館事實需要 reference。人工索引標籤是這個小資料集的前提，尚未自動建索引。
4. 固定所選原文、來源版本、角色與 ID，計算 SHA-256。規則基準與 LLM 使用完全相同證據；比較 JSON 記錄相同 evidence hash。LLM 不接觸未選段落、oracle 或規則基準答案。
5. 回覆結構固定為每個 fact 的 `value` 與逐字引用。系統核對 fact 集合、可選值、引用是否屬於所選段落、原文是否存在與角色是否齊全，再附 source ID／version 與教師／學生提醒。來源中的命令視為內容，不執行。

LLM 以既有 OpenAI Responses adapter 產生結構化結果。結構化輸出只能約束格式，仍需應用程式檢查內容；實作依 [OpenAI Structured Outputs 文件](https://developers.openai.com/api/docs/guides/structured-outputs)。`gpt-4.1-mini-2025-04-14`、temperature 0、最多 3000 output tokens、45 秒 timeout、無重試、`store=false`，prompt 版本 `retrieval-generator-v1`：[完整 prompt](../../assignment_checker/retrieval_prompt.txt)。

## 比較實測（2026-09-30）

| 案例 | Generator | 正確且有證據的 fact coverage | Unsupported claims | 不必要的 uncertain | 結果 |
| --- | --- | --- | --- | --- | --- |
| Q1 | 字面關鍵字規則 | 0/3 | 2 | 1 | 換句話說、否定句、附件引用皆有問題 |
| Q1 | 真實 LLM | 3/3 | 0 | 0 | 本次符合預設標註 |
| B1 | 字面關鍵字規則 | 3/3 | 0 | 0 | 明載簡單事實可用規則抽取 |
| B1 | 真實 LLM | 3/3 | 0 | 0 | 本次多證據整合符合標註 |

Q1：7.062 秒，input 1,028／output 331／total 1,359 tokens。B1：3.233 秒，input 804／output 195／total 999 tokens。合計兩次 API 呼叫、2,358 tokens；未查帳單金額。沒有多次抽樣、負載或實際學生資料評測，不能用此表推估普遍正確率或穩定性。

**評測定義：** [oracle.json](../../examples/week3/oracle.json) 是分開保存的預設期望標註，由 Codex 依合成原文整理、尚未經老師覆核，只供離線 evaluator 使用。正確 fact 需 value 相符、必要 chunk 齊全且引用有效；錯誤的非 uncertain 結論算 unsupported claim；不必要 uncertain 另計。引用 gate 檢查 provenance 與結構，不檢查語意蘊含。故「unsupported=0」只表示此封閉標註案例的結果，並非通用真實性保證。B1 回覆逐項引用 B-hours、B-booking、B-shoes，與所選三份證據一致。

Fixture 回覆為預先撰寫測試替身，證明流程可重現，不能算成 LLM 能力測量；[fixture 比較檔](evidence/fixture/generator-comparison.json)明確記錄此區別。

## 本機操作

沿用根目錄 `.env`，不要把 key 貼進 API 請求或提交到 Git。先依 [API 安裝說明](../api-usage.md)建立環境，再啟動：

```sh
.venv/bin/python -m uvicorn assignment_checker.api:app --host 127.0.0.1 --port 8000
```

開啟 `http://127.0.0.1:8000/docs`。GET `/assistant/week3/queries` 列出查詢；POST `/assistant/week3/query` 預設 fixture，以下範例不會呼叫付費 API：

```sh
curl -s http://127.0.0.1:8000/assistant/week3/query \
  -H 'Content-Type: application/json' \
  -d '{"query_id":"Q1","mode":"fixture"}'
```

將 mode 改成 `live` 會在通過檢索 gate 後呼叫一次 OpenAI。Q2／Q3 被 gate 擋下，即使 live 也不呼叫模型。可選 `top_k` 1–10；非法參數 422，引用／模型錯誤 502，逾時 504，缺金鑰 503。正常拒答使用 200 並以 `status` 區分。此為本機示範，沒有使用者登入與多租戶隔離，請使用 localhost。

產生可提交的比較與 trace（預設不花 API 費用）：

```sh
.venv/bin/python -m scripts.run_week3_evidence --output-dir tmp/week3-fixture
.venv/bin/python -m pytest tests/test_environment.py tests/test_assignment_api.py tests/test_assignment_provider.py tests/test_week3_retrieval.py -q
```

需要重新實測時，以下會呼叫 API **兩次**：

```sh
.venv/bin/python -m scripts.run_week3_evidence --live Q1 B1 --output-dir tmp/week3-live
```

本次測試：**76 passed、2 warnings**（既有 Starlette／AnyIO 棄用提示），包含 Week 2 回歸及 Week 3 新增測試；未將未完成的舊課表測試納入本次範圍。

每次產生四份 `*-top-k-trace.json`、一份 `generator-comparison.json`、一份 `failure-observations.json`。預設輸出 `tmp/` 已被 Git 忽略；本次審查過的合成資料證據存入本目錄。保留舊結果，新實驗另存目錄。來源超過有效期時會拒答；不要為重現而關閉來源政策。

## 檔案與後續驗收

- [檢索與 gate](../../assignment_checker/retrieval.py)、[API](../../assignment_checker/api.py)、[比較執行器](../../scripts/run_week3_evidence.py)、[測試](../../tests/test_week3_retrieval.py)。
- [合成資料／固定查詢](../../examples/week3/dataset.json)、[人工 generator 替身](../../examples/week3/generator-fixtures.json)、[獨立 oracle](../../examples/week3/oracle.json)。
- [Week 2 實作紀錄](../week2-baseline-declaration.md)維持歷史基準，Week 2 API 可處理既有文字 JSON；本週端點目前只跑固定合成資料。

下一個課堂 checkpoint：取得教師原始多證據案例與可用授權，補來源卡、固定查詢與教師確認的 oracle，再跑同樣比較；保留本次合成資料紀錄，另增教師案例紀錄。教師原始案例、真實文件匯入、未知問題路由及一般化語意把關仍未完成。
