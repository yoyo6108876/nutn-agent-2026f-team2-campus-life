# 原版與 Session 候選的三層比較

受測 SHA `6a5bc9b5c3831a40620d4d38bb659899e269561c`。原版為該版本中的 `week4.Workflow`，候選為 `week7.SessionWorkflow`；開工 SHA 為 `031d336`。原版只抽出接入點，原工具與業務規則保留，不把本次基線執行誤寫成在舊 commit 上測試。

固定條件：同 StartRequest、OpenAI `gpt-4.1-mini-2025-04-14`、temperature 0、`assignment-tools-v1`、同合成來源與空 SQLite 初始狀態。成功終點為確認後恰一份草稿、工具與摘要一致。候選多一份初始為空的 Session context。

| 層次 | 原版真實結果 | 候選真實結果 | 解讀 |
|---|---|---|---|
| 檢索 | Q1 gate=ready，來源與 evidence hash 相同 | 同左 | 都讀到固定合成報告及 T1–T3/S1–S3 |
| 回答 | 讀後直接輸出 reviewed JSON，未呼叫提案工具 | 模型提出草稿工具，確認後摘要與收據一致 | 原版未符合 draft 的工具序列 |
| 任務 | stopped、`LIVE_FAIL`、未寫入 | completed、`LIVE_PASS`、1 份草稿 | 主比較 `matches_expected=false`，完整保留 |
| 實測模型回覆數 | 2 | 3 | 原版較早失敗，不能當作成本優勢 |
| total tokens | 2,133 | 4,352 | 不同完成終點，不能推論記憶增量的淨成本 |
| 執行秒數 | 6.518 | 5.183 | 單次觀測，含工具／自動沙盒確認，不含人工閱讀時間 |

兩邊的 [離線配對](../../artifacts/week7/fixture/C01-normal-comparison.json) 均完成、結構化事實相同。[真實配對](../../artifacts/week7/live/C01-normal-comparison.json) 保留模型 output、function_call_output、參數驗證、確認前狀態、MCP trace 與 provider metadata。模型一次未提出工具是觀測結果，是否由措辭或非決定性造成尚未證明。

**本週記憶增量。** C03 同 Session 將正常 run 的成功摘要放入 context；C04 清除後 `memory:null` 且舊 run ID 不在模型初始輸入，仍完成新查詢。C02 跨使用者回傳 `RUN_NOT_FOUND`；C06 v2 使用實際檢索和 quote gate 的合成副本，舊 hash 排除。不能宣稱摘要減少查詢：每次仍查權威來源。

**總用量口徑。** 自動 live runner 的不重複工具 run 共 9 次模型回覆、11,463 tokens；文字比對另 1 次、1,240 tokens，合計 10 次、12,703 tokens。W01/W02 重送證據重複引用同 run，計數已去重。瀏覽器另有工具 3 次及文字比對 1 次，單列於 UI 證據，不混入此比較。所有成本為 token 觀測，未估算帳單。

**採用與補驗證。** 採用 Session 增量以界定資料範圍，保留原版作比較。下一步使用固定的至少 20 組自然語言措辭，分開評估工具序列可靠性、語意判斷與成本；若調整提示或路由，先重新提交程式版本，再跑同案例，保留原失敗。Gemini／ADC 必須另行驗證，目前 `LIVE_NOT_RUN`。
