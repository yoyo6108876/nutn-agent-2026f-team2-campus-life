# Memory ADR 007：只保存本 Session 最近成功摘要

日期：2026-10-28。狀態：採用於本機合成示範，正式校園部署未核准。路線 C：Session 清除。

**問題。** 原流程無對話範圍。直接沿用過往報告可能把其他人或舊版規格的判斷帶入後續回答；先前確認也不能成為下一次寫入權限。

**決定。** 在 `Workflow.build_history` 增加受控 context。在 SQLite 綁定 owner、session、run，僅保存最近一筆經摘要核對的成功報告。模型只能讀到小於 4096 bytes 的型別化摘要、來源版本、證據 hash 與 run ID。清除會停用舊 Session、刪除摘要並建立 successor；同清除 ID 重送取得現有 successor。新來源版本不符時，回填 `memory:null`，仍重新檢索權威來源。

**保留。** OpenAI、MCP 唯讀工具、引用 gate、工具參數驗證、確認後交易寫入、同 run ID 冪等與有限重試。課程 Gemini／ADC 要求尚未執行，供應商差異由組員選擇，不能視為課程驗收完成。

**權限與保留範圍。** HttpOnly cookie 對應伺服器 owner/session，讀寫 run 重新驗證歸屬。清除與決策使用同 Session 檔案鎖，模型呼叫後再驗證 Session。舊同意與草稿 ID 不存成記憶。交易、稽核與備份另存，清除對話不代表實體刪除全部紀錄。示範登入可選合成 A/B，尚非正式認證。

**替代方案與代價。** 無記憶最簡單但無法展示清除邊界；永久偏好／向量記憶尚無明確需求，增加來源與權限成本；TTL 需要可測時鐘與到期策略，本週選清除。新增 SQLite 表與 POSIX 鎖，Windows 需 WSL。多個平行唯讀完成時保存最後寫入的成功摘要，不提供多分支對話排序保證。

**證據與採用。** 148 項回歸測試通過（本週 17 項）；8 個離線案例符合預期。候選 OpenAI 主流程、續問與清除後查詢 `LIVE_PASS`；同輸入基線出現 `UNEXPECTED_TOOL_SEQUENCE / LIVE_FAIL`，不將一次差異解讀為記憶改善品質。來源 v2 僅離線驗證。採用原因是範圍可驗證且可清除，非成本或成功率優勢。詳見 [比較](comparison.md) 及 [索引](../../reports/midterm/evidence-index.md)。
