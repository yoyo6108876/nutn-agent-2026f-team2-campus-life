# 第 02 組：階段性成果檢視

**題目：以教師範例為參考的作業規格與完成度檢查助手。**

陳冠友 S11259039（隊長）、林崇瑋 S11259031（隊員）。證據日期：2026-10-28。安排：13 張簡報與操作共 14 分鐘、問答 5 分鐘、緩衝 1 分鐘。

> 2026-10-30 更正：組員姓名原誤植為「林崇偉」，已在本資料夾的 README、示範腳本、分工表、簡報產生程式、PPTX、PDF 與 overview.png 改為「林崇瑋」，其他內容未變。PDF 以原本的 `pdf-fonts.conf` 重新輸出。`manifest.json` 的雜湊仍對應 tag `report-week7-20261028` 的原始版本。更新後的簡報（含 PDF 預檢與 Week 6）見 [phase-review-v2](../phase-review-v2/README.md)。

## 交付入口

- [報告簡報 PDF](phase-review.pdf)
- [可編輯 PPTX（含講者備註）](phase-review.pptx)
- [示範操作與備援](demo-runbook.md)
- [證據索引：正常、失敗、測試、畫面與 trace](evidence-index.md)
- [建議分工、實際貢獻待確認及後續驗收](team-progress.md)
- [口頭講解與問答準備](speaker-notes.md)
- [Week 7 路線 C](../../docs/week7/README.md)、[Memory ADR](../../docs/week7/memory-adr.md)、[比較表](../../docs/week7/comparison.md)

## 版本與可重現性

原專題 Repository：https://github.com/yoyo6108876/nutn-agent-2026f-team2-campus-life

開工基線 commit：`031d336922622056c619e41871b9c5cb9425aae0`。本週全部執行證據對應的**程式 commit**：`6a5bc9b5c3831a40620d4d38bb659899e269561c`。後續報告提交只增補文件與證據，沒有把文件 commit 誤寫成受測程式版本。報告交付版本使用 Git tag `report-week7-20261028`，可執行 `git rev-parse report-week7-20261028` 取得報告 commit。

完整環境設定與啟動在 [根目錄 README](../../README.md)，真實測試使用本機 `.env` 的 `OPENAI_API_KEY`。模型 `gpt-4.1-mini-2025-04-14`，工具提示 `assignment-tools-v1`，語意提示 `assignment-check-v1.1`。合成資料來源與引用在 [Week 3 source card](../../docs/week3/source-card.md)。資料效期可能影響日後重現，不能自行延長後再把結果當成原版證據。

## 報告主張的範圍

已驗證：文字語意比對、固定合成評閱快照的工具迴圈、確認與同 ID 冪等、Session 清除與隔離、引用 gate。148 項回歸測試通過，保留一組真實比較中的原版 `LIVE_FAIL`。

已實作但未完成真實服務驗證：來源 v2 更新排除僅離線通過。規劃中：將新語意結果接入草稿工具、PDF 上傳解析、正式身分認證、教師授權與教學平台整合。現有工具讀取的是**預先撰寫的合成評閱快照**，不宣稱已能對任意上傳作業完成整條工具流程。

依組員明確選擇繼續使用 OpenAI。課程 Google Cloud／ADC Gemini 要求為 **`LIVE_NOT_RUN`，尚未符合**。Week 6 未提供可核對材料；Week 3 教師費率案例缺原文；這些缺口未列為完成。

## 備援畫面與資料安全

提供 4 張實際介面截圖，含等待確認、成功、語意比對、清除後空記憶。詳見索引與 [截圖目錄](screenshots/)。本次未錄製影片，備援採截圖序列；使用備援時須說明執行日期與版本，不宣稱為當場呼叫。

測試及畫面均使用合成資料。JSON 不含 key、cookie 或 ADC；資料庫與 `.env` 不提交。UI 的 A/B 身分只適合本機展示，不能視為正式校園認證。

## 製作與引用

本報告與程式由 Codex 協助開發、測試、排版；組員必須自行核對與試講，不能把建議分工寫成既成貢獻。課程規格來源為使用者提供的 Week 1、Week 2、Lecture03、Lecture4、Lecture05、Lecture07 PDF 及本次階段報告文字。Week 7 特別對照投影片 77–90。授課 PDF 未重新散布到公開 repo。

簡報以 Artifact Session 建立，來源為 [build-slides.mjs](build-slides.mjs)，使用本專案真實畫面與原生可編輯架構圖／表格。重建時在 Artifact Session 匯入該模組，呼叫 `build(presentation, 本資料夾絕對路徑)`，逐頁 render 後匯出 PPTX；PDF 匯出方式與檔案雜湊記於 [交付 manifest](manifest.json)。
