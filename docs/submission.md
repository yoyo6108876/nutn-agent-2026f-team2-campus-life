# Git 操作與提交

## 本機狀態與作者

此資料夾作為獨立 Git 儲存庫，分支為 `main`。初始骨架若由 Codex 建立 commit，作者會明確標記為 Codex；這不代表學生已完成個人的 Git 實作。每位組員仍應用自己的帳號完成一次修改與提交。

先將以下示意值改為自己的真實資訊；設定僅作用於本儲存庫：

```sh
git config user.name "你的姓名"
git config user.email "你的 GitHub 提交電子郵件"
```

修改 README 的組員資料與本週分工後：

```sh
git status
git diff
git add README.md
git diff --cached
git commit -m "docs: add team members and week 2 driver"
```

## GitHub Team Repo

團隊儲存庫原名為 `nutn`，目前已改名為 `nutn-agent-2026f-team2-campus-life`；講義要求兩位組別，對應名稱應為 `nutn-agent-2026f-team02-campus-life`。網址：https://github.com/yoyo6108876/nutn-agent-2026f-team2-campus-life 。本機 origin 已更新。以下建立步驟供課程核對，無須重複建立。

### 環境與提交紀錄

- 已建立本機 `main`、環境報告、候選問題與初始 commit。
- 已執行測試：5 項通過。
- 已設定 `origin` 為 `https://github.com/yoyo6108876/nutn-agent-2026f-team2-campus-life.git`。
- 初次推送曾因缺少 GitHub 登入憑證而失敗；目前已確認 GitHub 帳號 `yoyo6108876` 可用，且遠端 `main` 已包含初始 commit 與後續 README 更新。
- 已將本次專案題目與需求定義推送到 GitHub 的 `main`。
- 尚未代為邀請教師或提交課程 URL。

後續本機 commit 可在本專案資料夾使用以下指令推送：

```sh
git push -u origin main
```

1. 使用團隊決定的擁有者帳號建立 Repository。
2. 名稱使用 `nutn-agent-2026f-teamNN-campus-life`，將 NN 改成兩位組別。若團隊決定其他主題，可修改最後一段；所有字元使用小寫 ASCII 與連字號。
3. 選擇團隊需要的可見性；不要預先產生 README，避免與本機初始歷史衝突。
4. 將以下 OWNER 與 REPO 改為剛建立的帳號及完整名稱，再執行：

```sh
git remote add origin https://github.com/OWNER/REPO.git
git push -u origin main
```

若已有 `origin`，先用 `git remote -v` 確認網址，不要直接覆蓋或強制推送。若遠端已有檔案，先協調或整合歷史。

## clone 練習

遠端建立並成功 push 後，其他組員使用新資料夾練習講義流程：

```sh
git clone https://github.com/OWNER/REPO.git
cd REPO
```

修改 README 後依序執行 `git status`、`git diff`、`git add README.md`、`git commit` 與 `git push`。本機初始化不等於已完成 clone 或 push。

## 教師權限與繳交

講義指定：Settings → Collaborators → Add people，邀請 `wcchiang0627@gmail.com`（江維鈞）。這是待由團隊執行的課程要求；本專案未自動寄出邀請。

- [ ] README 已填姓名、學號、題目與分工。
- [ ] 已指定 Week 2 Driver，並討論三個候選問題。
- [ ] `environment_check.md` 真實記錄版本、工具與登入驗證。
- [ ] GitHub 上的 `main` 可看到 README、環境紀錄與問題探索文件。
- [ ] 教師已獲得存取權限，並確認可以開啟。
- [ ] 將實際 URL 填回 README，再提交 `https://github.com/OWNER/REPO`。

目前已提供兩位組員與 GitHub 擁有者，組別為 02，目前遠端名稱使用 team2，與講義的兩位組別格式尚有差異；Week 2 Driver 確認、教師權限與課程 URL 提交仍待團隊完成。
