# NUTN Agent Project

## 專案題目

**以教師範例為參考的作業規格與完成度檢查助手**

老師提供一份範例，學生提交作業後，系統先對照範例進行完整性檢查，再提供學生補件提醒與老師缺漏摘要，讓雙方知道作業少了什麼、哪些項目需要人工確認。

LLM 的核心工作是理解範例與學生作業的語意對應，辨識「換個寫法但已完成」與「只有標題、缺少內容」的差異。老師可確認範例中哪些項目必做；未確認的範例差異標示為待確認，不直接認定學生缺交。若另有作業說明，則一併納入判定依據。

預定流程：**老師提供範例 → 學生提交作業 → LLM 比對 → 學生收到補件提醒／老師查看缺漏摘要 → 老師確認疑義，學生依規定補交**。初期以手動上傳模擬提交，結果呈現在系統內；教學平台整合與外部通知留待後續。

目前已完成文字 JSON 的 single LLM call 基準 API，包含輸入驗證、引用核對及雙方提醒；一份合成範例已成功呼叫真實 OpenAI API。PDF 上傳與教學平台整合尚未實作。操作方式見 [API 執行說明](docs/api-usage.md)，證據見 [執行紀錄](docs/execution/README.md)。

依 0922 新版講義的 [Week 2 Baseline Declaration 初稿](docs/week2-baseline-declaration.md) 保留原始預期規格；後續實作與 200／422／502 的執行結果另記於執行紀錄，區分真實 LLM 與固定替身，不將它們混為同一種證據。

## 啟動 API

在根目錄 `.env` 填入 `OPENAI_API_KEY` 後執行：

```sh
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m uvicorn assignment_checker.api:app --host 127.0.0.1 --port 8000
```

開啟 `http://127.0.0.1:8000/docs` 查看介面規格；範例輸入見 [normal.request.json](examples/assignment/normal.request.json)。首次建立 Python 環境的步驟與 curl 呼叫指令見 [API 執行說明](docs/api-usage.md)。

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

姓名、學號與隊長／隊員身分由團隊提供；具體工作分配為草案，待兩位確認。

投影片流程頁寫 3–4 人，專題說明及本週清單寫 2–3 人；本草稿依後兩者安排，實際人數以授課教師確認為準。

## 專案文件與既有工具

- [API 執行說明](docs/api-usage.md)：安裝、啟動、錯誤處理與證據產生。
- [執行紀錄](docs/execution/README.md)：合成資料上的真實 API 及替身測試結果。
- [Week 2 Baseline Declaration 初稿](docs/week2-baseline-declaration.md)：對應新版講義六項提交清單。
- [專案題目與範圍定義](docs/week2-proposal.md)：問題、使用者、LLM 必要性、輸入輸出、驗收條件與後續基準驗證規劃。
- [環境驗證紀錄](environment_check.md)：實際偵測結果及待人工確認項目。
- [三個候選問題](docs/candidate_problems.md)：對象、痛點、資料工具及 Agent Necessity Test。
- [Git 操作與繳交步驟](docs/submission.md)：本機 commit、GitHub 建立、推送與教師權限確認。
- `scripts/check_environment.py`：可重複執行的環境檢查工具。
- `tests/test_environment.py`：檢查工具的失敗處理與報告格式測試。

## 執行環境驗證

使用 Python 3.10 以上（這是本骨架的需求；講義未指定版本）。目前電腦是 macOS；講義的示範環境為 Windows，以下也提供 PowerShell 操作。

macOS / Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/check_environment.py
.venv/bin/python -m pytest
```

Windows PowerShell：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/check_environment.py
.\.venv\Scripts\python.exe -m pytest
```

檢查指令預設更新根目錄的 `environment_check.md`；也可使用 `--output 路徑` 保存各組員的紀錄。指令成功只代表報告已產生；請閱讀表格中的缺少工具與待確認項目。

VS Code 的 Codex 擴充套件登入、GitHub 存取與教師權限須人工確認，程式不讀取憑證。Cursor 或 Codex 桌面版的存在不代表已完成 VS Code + Codex IDE 要求。

## 完成交付前

- [ ] 填妥組別、組員姓名、學號與分工，指定 Week 2 Driver。
- [ ] 每位組員完成環境驗證及 Codex 擴充套件登入。
- [ ] 團隊討論並修改候選問題草稿。
- [ ] 建立符合命名規則的 GitHub Team Repo，將本機 main 推送上去。
- [ ] 依講義邀請教師並確認存取權限，再提交 Repository URL。

專案已收斂為教師範例與學生作業的對照檢查。目前只完成合成案例的基準測試，尚未進行學生訪談、真實作業評測或大規模品質比較；需求假設與預期效果仍需驗證。
