# 2026-11-04 彩排時的兩次手動失敗

在本機 `/week7` 工作台手動操作，不是比較腳本產生。受測提交 `a9057cf`，其 `assignment_checker` 與 `examples/week6` 的 PDF 和候選 `327b7e2` 相同。`.env` 與伺服器環境都沒有設定 `OPENAI_PDF_MODEL`，所以模型是預設的 `gpt-5.4-2026-03-05`。兩次都沒有留下紀錄或分數（`pdf_prechecks` 仍為 0 筆）。

| 次別 | 流程 | 輸入 | 結果 | 證據 |
| --- | --- | --- | --- | --- |
| 1 | 原版（錯誤回應沒有 `workflow` 欄位） | 使用者回報為 `examples/week6`，未核對 sha256 | 502 `INVALID_SOURCE_REFERENCE`，stage `grounding`，「模型選擇的來源或頁碼不符。」 | 畫面上的錯誤回應、伺服器紀錄 |
| 2 | 未取得 | 未確認 | 502，錯誤碼未取得 | 只有伺服器紀錄 |

```text
1: POST /assistant/week7/pdf/precheck HTTP/1.1 502 Bad Gateway
2: POST /assistant/week7/pdf/precheck HTTP/1.1 502 Bad Gateway
```

**未取得：** 兩次的 response ID、tokens、耗時都沒有留下。原版失敗時不保留草稿，所以第 1 次不知道是哪一項引用出錯。第 2 次的 502 不一定是引用問題，也可能是模型回覆不完整或服務拒絕。

第 1 次以 7 項業務預期計算是 0／7（沒有產生報告）。第 2 次輸入未確認，而這 7 項是依 `examples/week6` 訂的，所以不評。兩次狀態都是 `LIVE_FAIL`。
