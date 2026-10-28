# NUTN Agent Project

## 專案題目

**以教師範例為參考的作業規格與完成度檢查助手**

老師提供一份範例，學生提交作業後，系統先對照範例進行完整性檢查，再提供學生補件提醒與老師缺漏摘要，讓雙方知道作業少了什麼、哪些項目需要人工確認。

LLM 的核心工作是理解範例與學生作業的語意對應，辨識「換個寫法但已完成」與「只有標題、缺少內容」的差異。老師可確認範例中哪些項目必做；未確認的範例差異標示為待確認，不直接認定學生缺交。若另有作業說明，則一併納入判定依據。

預定流程：**老師提供範例 → 學生提交作業 → LLM 比對 → 學生收到補件提醒／老師查看缺漏摘要 → 老師確認疑義，學生依規定補交**。初期以手動上傳模擬提交，結果呈現在系統內；教學平台整合與外部通知留待後續。

目前已完成文字 JSON 的 single LLM call 基準 API，包含輸入驗證、引用核對及雙方提醒；一份合成範例已成功呼叫真實 OpenAI API。PDF 上傳與教學平台整合尚未實作。操作方式見 [API 執行說明](docs/api-usage.md)，證據見 [執行紀錄](docs/execution/README.md)。

依 0922 新版講義整理的 [Week 2 Baseline Declaration：實作與驗證版](docs/week2-baseline-declaration.md)，已整合本週範圍、實際 I/O、200／422／502 預期與實測結果、模型與指令版本、已知限制、重現指令及 Exit ticket，可作為本週提交入口。

**Week 3 提交入口：[Retrieval + Generator Comparison](docs/week3/README.md)。** 已依 Lecture03 PDF 的投影片 47–54 修正：normal／paraphrase／no-answer 三題、額外 coverage failure、完整 source card、top-k trace 與 Offline／Fixture 比較。執行 `.venv/bin/python -m scripts.run_studio_generator_lab --path auto` 產生 [正式比較 JSON](artifacts/week03-generator-comparison.json)，不使用 API key。

教師案例指定「學生資格、平日費率、假日例外」，PDF 沒有附三段 pricing 原文或金額，因此目前安全拒答並標記 checkpoint 未完成。先前真實 API 測試保留為歷史補充；舊開放時間 B1 案例不能替代教師費率案例。詳見 [講義核對與修正](docs/week3/requirements-audit.md)。

Week 3 新增 `/assistant/week3/queries` 與 `/assistant/week3/query`；預設 `fixture` 不呼叫 API，指定 `live` 才使用 LLM。此端點目前使用固定合成資料；任意文字作業仍使用 Week 2 的 `/assistant/check-submission`。

**Week 4 提交入口：[Tool Use 與 MCP](docs/week4/README.md)。** 沿用 OpenAI，完成 MCP 讀取缺漏、模型提出補件草稿、使用者確認後本機寫入及結果摘要；真實 API 迴圈 `LIVE_PASS`，107 項測試通過。介面位於 [本機 Week 4](http://127.0.0.1:8000/week4)，目前使用固定合成提交。講義指定 Gemini 的差異、故障注入及驗證紀錄均列於該週文件。

**Week 5 提交入口：[Frameworks & Orchestration](docs/week5/README.md)。** 以 LangGraph 局部替換等待確認與接續，原版／候選可從 [同一工作台](http://127.0.0.1:8000/week5) 切換。九個離線前後比較、兩個真實 OpenAI 前後比較與 131 項測試通過；[一頁決策](docs/week5/decision.md) 說明保留原版為預設的理由。

## 啟動 API

**階段成果報告：[簡報 PDF 與證據索引](reports/midterm/README.md)。** 第 02 組，受測程式版本 `6a5bc9b`，證據日期 2026-10-28。建議簡報與示範 14 分鐘、問答 5 分鐘，保留 1 分鐘緩衝。

**Week 7 提交入口：[Session 清除與來源更新](docs/week7/README.md)。** 新增隔離的 Session、清除控制、來源版本排除與文字比對工作台。148 項測試通過；候選主流程、同 Session 續問、清除後查詢與文字比對均有 OpenAI `LIVE_PASS`。原版／候選的真實比較包含原版 `LIVE_FAIL`，保留失敗證據，不宣稱全面通過或提升成功率。

依組員選擇繼續使用 GPT。課程要求的 **Google Cloud／ADC Gemini 為 `LIVE_NOT_RUN`，尚未符合該項規定**；Week 6 未提供教材或交付證據，未列為完成。分工為建議，實際貢獻待組員確認。

在根目錄 `.env` 填入 `OPENAI_API_KEY` 後執行：

```sh
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m uvicorn assignment_checker.api:app --host 127.0.0.1 --port 8000
```

開啟 `http://127.0.0.1:8000/docs` 查看介面規格；範例輸入見 [normal.request.json](examples/assignment/normal.request.json)。首次建立 Python 環境的步驟與 curl 呼叫指令見 [API 執行說明](docs/api-usage.md)。

本次報告開啟 [Week 7 工作台](http://127.0.0.1:8000/week7)：選示範身分、按「切換／開始」，再選補件工具流程或文字語意比對。GPT 模式會使用 API 額度；離線模式明確標示固定回覆。完整操作與備用畫面見 [示範腳本](reports/midterm/demo-runbook.md)。本機沙盒僅綁定 `127.0.0.1`，使用合成資料，尚未提供正式登入或 PDF 上傳；Windows 請使用 WSL（Session 鎖使用 POSIX `fcntl`）。

## 團隊

| 欄位 | 內容 |
| --- | --- |
| 組別 | 02 |
| 題目 | 以教師範例為參考的作業規格與完成度檢查助手 |
| GitHub 擁有者 | `yoyo6108876` |
| 目前 Repository 名稱 | `nutn-agent-2026f-team2-campus-life` |
| 課程要求命名 | 兩位組別格式為 `nutn-agent-2026f-team02-campus-life`；目前遠端使用 `team2` |
| Repository URL | https://github.com/yoyo6108876/nutn-agent-2026f-team2-campus-life |
| Week 2 Driver | 建議由陳冠友擔任，待團隊確認 |

| 姓名 | 學號 | 初步分工 |
| --- | --- | --- |
| 陳冠友 | S11259039 | 隊長；建議負責環境、程式與 Git 操作 |
| 林崇偉 | S11259031 | 隊員；建議負責需求、資料來源、測試與文件審查 |
