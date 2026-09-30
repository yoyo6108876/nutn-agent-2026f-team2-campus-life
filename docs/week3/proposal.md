# Week 3 一頁 Proposal

**以教師範例為參考的作業規格與完成度檢查助手**

組別 02｜陳冠友 S11259039（隊長）、林崇偉 S11259031（隊員）

**使用者與情境。** 學生提交作業後想知道漏了什麼；老師需要快速看到補件與待確認摘要。先由老師確認範例中的必做項目，避免將範例寫法直接變成要求。

**單一 claim。** 「這一版提交是否足以通過教師已確認三項要求的完整性預檢？」本週限定使用者描述、失敗案例內容、可查看的附錄證據。外部依據是教師目前有效的要求與本次提交版本，不能由 LLM 常識補出。輸出附引用的 met／partial／missing／uncertain 與雙方提醒；不是自動評分或真實性保證。

**LLM 必要性。** 語意相同的不同寫法可表示已完成；「沒有說明原因」含關鍵字卻未滿足要求；「見附錄 A」不能證明附錄內容可查看。LLM 負責跨段落理解與判斷，系統控制資料、檢索、coverage、citation 與提醒。Fixture 只用於可重現比較，不宣稱有模型能力。

**資料範圍與 baseline。** 專案自製三段教師要求與三段學生文字；穩定 chunk IDs 及 fact／role 由人工整理。透明中文雙字詞／英文詞重疊檢索，再比較字面規則 Offline 與課堂契約 Gemini Fixture。固定 Q1 normal、QP paraphrase、Q2 no-answer，另外測 Q3 coverage failure。真實 PDF 匯入、自由查詢、向量索引不在此基準內。

**流程與拒答。** 來源政策與已登錄衝突優先序 → top-k → coverage gate → 固定 evidence → generator → 引用檢查。無證據、失效／撤回、同優先序來源衝突皆拒答；缺必要事實回 MISSING_REQUIRED_ASPECT，所有 generator 跳過。附件不可讀則 uncertain；不把檢索失敗算學生缺交。引用通過仍可能誤解原文，保留老師覆核。

**驗收與限制。** 保存 top-k IDs／scores、gold／acceptable IDs、是否拒答、相同 evidence／citations、fact coverage、unsupported numeric claims 與 failure observation。專案 fixture 流程已完成；教師指定的費率原始三段資料尚缺，正確拒答並標記 checkpoint 未完成。舊開放時間案例僅為補充，不能取代指定費率案例。
