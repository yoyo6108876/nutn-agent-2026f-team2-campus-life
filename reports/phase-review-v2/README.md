# 階段成果檢視簡報（v2）

第 02 組。這一版重新設計 [reports/midterm](../midterm/README.md) 的 13 張簡報，並補上 10/28 晚間新增的 PDF 預檢與估分（`13b2b1e`）。舊版仍保留為凍結的 `report-week7-20261028` 交付物。

- [phase-review-v2.pptx](phase-review-v2.pptx)：15 張可編輯簡報，講者備註裡附逐頁講稿
- [phase-review-v2.pdf](phase-review-v2.pdf)：同內容的 PDF
- [speaker-script.md](speaker-script.md)：逐頁講稿、時間分配與問答準備

## 與舊版的差異

- 版面改為狀態標籤（已完成／需補件／待確認）貫穿全份，架構、流程、時程都改用原生圖形，測試數改用原生圖表。
- 新增 PDF 預檢兩頁：處理流程與估分條件、兩次真實 `LIVE_FAIL` 與修正過程。
- PDF 改用 gpt-5.4 之後的最終結果沒有公開的 `verification.json`，簡報標為「待記錄」。上台前若已有紀錄，再改第 3、11、14 頁與講稿。

## 重新產生

`script.js` 是講稿的唯一來源，`build-deck.js` 會把它寫進講者備註並重新產生 `speaker-script.md`。需要 Node 搭配 `pptxgenjs`、`sharp`、`lucide`，以及 pptx skill 的 `apply_theme.js`：

```bash
NODE_PATH=<node_modules> node build-deck.js <path/to/apply_theme.js>
```

`assets/` 是本機實際介面截圖：前三張裁自 `reports/midterm/screenshots/`（2026-10-28，`6a5bc9b`），`pdf-upload.png` 於 2026-10-29 從本機 `/week7` 擷取，畫面為尚未上傳狀態，未呼叫模型。字型為 PingFang TC，在沒有此字型的 Windows 上 PowerPoint 會以其他字型替代，版面可能略有差異。
