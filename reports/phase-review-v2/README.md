# 階段成果檢視簡報（v2）

第 02 組，陳冠友 S11259039（隊長）、林崇瑋 S11259031（隊員）。這一版重新設計 [reports/midterm](../midterm/README.md) 的 13 張簡報，補上 10/28 晚間新增的 PDF 預檢與估分（`13b2b1e`），以及 10/30 補交的 Week 6 評估後修訂（候選 `327b7e2`）。舊版仍保留為凍結的 `report-week7-20261028` 交付物。

- [phase-review-v2.pptx](phase-review-v2.pptx)：16 張可編輯簡報，講者備註裡附逐頁講稿
- [phase-review-v2.pdf](phase-review-v2.pdf)：同內容的 PDF
- [speaker-script.md](speaker-script.md)：逐頁講稿、時間分配與問答準備（約 13.9 分鐘，另留問答 5 分鐘、緩衝 1 分鐘）

## 與舊版的差異

- 版面改為狀態標籤（已完成／需補件／待確認）貫穿全份，架構、流程、時程都改用原生圖形，測試數改用原生圖表。
- PDF 預檢三頁：處理流程與估分條件；兩次真實 `LIVE_FAIL` 與改用 gpt-5.4 後的結果；Week 6 的 Evaluator–optimizer 與真實比較。
- PDF 預檢的 gpt-5.4 結果取自 Week 6 的合成 PDF 實測（兩輪皆 `LIVE_PASS`，但 7 項業務預期只符合 6 項），只代表這組案例，不是準確率。Week 6 結論為尚未證明改善，見 [docs/week06](../../docs/week06/README.md)。

## 重新產生

`script.js` 是講稿的唯一來源，`build-deck.js` 會把它寫進講者備註並重新產生 `speaker-script.md`。需要 Node 搭配 `pptxgenjs`、`sharp`、`lucide`，以及 pptx skill 的 `apply_theme.js`：

```bash
NODE_PATH=<node_modules> node build-deck.js <path/to/apply_theme.js>
```

`assets/` 是本機實際介面截圖：前三張裁自 `reports/midterm/screenshots/`（2026-10-28，`6a5bc9b`），`pdf-upload.png` 於 2026-10-29 從本機 `/week7` 擷取，畫面為尚未上傳狀態，未呼叫模型。字型為 PingFang TC，在沒有此字型的 Windows 上 PowerPoint 會以其他字型替代，版面可能略有差異。
