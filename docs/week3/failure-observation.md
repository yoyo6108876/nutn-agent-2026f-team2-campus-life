# Week 3 Failure Observation

完整機器紀錄：[故障注入](evidence/live/failure-observations.json)、[規則與真實 LLM 比較](evidence/live/generator-comparison.json)。以下明確區分自然執行結果與刻意注入。

## 1. 規則把關鍵字存在當成完成（實際規則執行）

Q1 的學生作業以中文描述使用者，字面規則期待 `Target User`，因此回 `uncertain`。失敗案例包含「本段沒有說明造成錯判的原因」，雖然缺原因，規則卻因找到「輸入」「實際結果」「原因」三字而回 `met`。同樣，提到「附錄 A」也被規則當成附件已提供。

預設標註是 `met / partial / uncertain`；規則結果是 `uncertain / met / met`，正確 fact coverage 0/3，unsupported claims 2，不必要 uncertain 1。單次真實 LLM 的 Q1 回覆符合三個標註。這支持在語意差異、否定與指涉判讀上使用 LLM 的動機，但不是與所有非 LLM 方法的品質比較。

## 2. top-k 過小（實際檢索執行）

Q3 與 Q1 的問題及資料完全相同，只將 k 從 6 降到 2。排名前兩段是學生使用者與失敗案例，沒有教師依據，也缺附錄段落。系統回 `coverage_failure`，不呼叫模型、不產生缺交通知。這是檢索覆蓋不足，不是學生少做了四項。調回 k=6 可恢復回答；本例不可推論 k 越大越好。

## 3. 引用未選／已撤回來源（刻意注入）

將 B1 開放時間的引用改指 `B-old`。該舊公告已於檢索前排除，故引用 gate 拒絕 `citation_not_selected`，不發布答案。即使 corpus 裡曾有此 ID，也不能繞過 evidence freeze。

## 4. 只回答兩個 fact（刻意注入）

刪除 B1 的鞋款答案。雖然其餘引用存在，fact 集合不完整，gate 拒絕 `fact_set_mismatch`。

## 5. 原文引用正確但結論錯誤（刻意注入；仍存在的限制）

保留 B-hours 正確原文「09:00–17:00」，卻將開放時間 value 改成「00:00–24:00」。這是允許的候選值、事實 ID 正確、引用也真實，因此引用 gate **通過**；離線 oracle 判定 **2/3、unsupported claims=1**。

此案例不是真實 LLM 本次發生的錯誤，而是注入錯誤以證明防線的範圍。引用正確不等於結論受引用支持；系統不宣稱通用的零幻覺。現階段交由老師確認，後續才評估語意蘊含驗證、對立證據與獨立預設標註集，不把同一 LLM 自評當成真值。

## 測試範圍

自動測試涵蓋來源有效期／權限／PII 宣告／撤回、穩定排序、no-answer、coverage failure、證據變更、引用不在所選集合、假原文、角色不足、重複與遺漏 fact、模型輸入沒有 oracle，以及 API 無效輸入在模型呼叫前被攔截。來源 PII 欄依人工宣告，未實作內容掃描；prompt 有資料／指令分離要求，但沒有完成全面 prompt injection 攻擊評估。
