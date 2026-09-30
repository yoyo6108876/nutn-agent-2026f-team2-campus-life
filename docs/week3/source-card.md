# Week 3 Data Source Card

資料集 **week3-studio-v2**，檢閱日 **2026-09-30**。[機器可讀來源卡與 chunks](../../examples/week3/dataset.json)。以下是專案自製合成來源的治理規格；教師 pricing 來源尚未取得，不推定有授權或正確版本。

| 欄位 | 本專案設定 |
| --- | --- |
| Owner | 本專案團隊負責合成資料維護；具體分工待團隊確認。文字與期望標註由 Codex 協助整理，未經老師覆核。 |
| 原始 URL／檔案 | 自製語料原檔為 `examples/week3/dataset.json`，由 source ID 和 chunk ID 定位；無外部 URL。講義是規格來源，沒有當成可報價的 pricing 原文。 |
| Authority | teacher-demo 在模擬作業內定義要求；student-demo 只表示提交內容，不可覆蓋教師要求。court-*-demo 只在舊合成練習內有效，不是校方公告。 |
| License／Permission | 專案自製教學測試文字，准許本專案測試及公開展示。`permission=true` 只適用這些合成資料，不代表真實教材／學生作業已獲授權。 |
| Update cadence | 教師要求或案例變更時檢閱，最遲 valid_until 前複核。沒有自動抓取排程。 |
| Freshness／Validity | 各來源 `version=synthetic-v1`，2026-09-30 至 2026-12-31 有效；資料集因規格欄位增補升為 studio-v2，原文不變。過期來源於新請求中排除，trace 保存 policy_date／來源版本／hash。 |
| 衝突 precedence | 權威在自己的角色範圍內生效；學生不得定義教師規則。已知衝突用 `conflicts_with` 明確登錄，較高 precedence 勝出、同優先序拒答 SOURCE_CONFLICT。程式不自動偵測語意矛盾；新增資料須人工檢閱。 |
| PII | 固定語料不含真實師生姓名、學號、帳號；標記 synthetic_no_pii，其他標記先排除。團隊名單不送 LLM。此為人工宣告，沒有自動 PII 掃描。 |
| Retention | 合成來源與去識別化執行紀錄保留供課程稽核，2027-01-31 檢閱刪除需求；沒有自動刪除程式。真實資料尚未接收，保留條件須另獲授權。 |
| 撤回／Delete／Reindex | withdrawn=true 後下一次請求重新讀檔並排除；本系統無持久向量索引，因此無 index re-build。來源檔、衍生 trace、artifact、Git 歷史另行清理；不能承諾已公開副本自動消失。 |
| Provider handling | 本次 fixture 不傳送任何資料到模型。選用額外 OpenAI live 時只傳選定合成段落，store=false、無工具及自動重試；不代表供應商所有日誌零留存。key 不寫入 trace／Git。 |

| source_id | Chunks | Authority／狀態 |
| --- | --- | --- |
| teacher-demo | T1、T2、T3 | 合成教師要求，可用 |
| student-demo | S1、S2、S3 | 合成學生提交，可用 |
| court-hours-demo | B-hours | 舊補充開放時間練習，可用 |
| court-booking-demo | B-booking | 舊補充預約練習，可用 |
| court-shoes-demo | B-shoes | 舊補充鞋款練習，可用 |
| court-old-demo | B-old | 已撤回，不可引用 |
| mock-pricing-2026-fall | 講義指定 price-student-* 三段 | 原始內容、owner／license／版本資訊未提供，**尚未匯入可用來源** |

每段穩定 ID 回到資料集原文。來源權限欄不是使用者身分驗證；現行服務限本機與合成資料。教師原始資料匯入前需補 [待確認項目](teacher-case.md)。
