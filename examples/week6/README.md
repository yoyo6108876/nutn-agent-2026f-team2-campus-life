# Week 6 固定輸入（合成資料）

原版與候選的離線案例、真實比較都使用這一組檔案。內容為教學示範用的合成作業，不含真實課程、學生、成績或個資。

| 檔案 | 內容 |
| --- | --- |
| [teacher.pdf](teacher.pdf) | 「作業二：成績統計程式」規格，2 頁：五條繳交規定在第 1 頁，合計 100% 的四項配分在第 2 頁 |
| [student.pdf](student.pdf) | 對應的學生報告，3 頁：目錄、程式說明、程式截圖、文字形式的終端機輸出、長條圖與結果分析 |
| [fixture-drafts.json](fixture-drafts.json) | 人工撰寫的三份草稿：`valid`、`invalid_refs`、`roles_mismatch`，不是模型輸出 |
| [source/](source/) | 產生 PDF 用的 HTML、SVG 與 PNG |

學生報告刻意留下幾處缺漏，讓比對有東西可找：沒有輸出標準差、終端機輸出只有文字沒有截圖、目錄列出「改進方向」但正文沒有這一節、只附截圖沒附 `stats.cpp`。程式截圖與長條圖是點陣圖，文字擷取讀不到，需要模型看頁面圖片。

`invalid_refs` 重現兩次真實 `LIVE_FAIL` 的錯誤型態：老師引用跨頁（`T1L10–T2L5`）、學生引用超過該頁行數（`S1L1–S1L13`），另加一個來源前綴錯誤（老師證據填 `S1L1`）。

## 重新產生

PDF 由 LibreOffice 7 將 `source/*.html` 轉成 PDF，字型為 PingFang TC；兩張圖由 `sharp` 將 SVG 轉成 PNG。換電腦或換字型後，擷取出的行號可能不同，`fixture-drafts.json` 的行號要一併核對。

```sh
cd examples/week6/source
soffice --headless --convert-to pdf:writer_web_pdf_Export --outdir .. teacher.html student.html
```

目前 Host 擷取的行號可用下列指令列出：

```sh
.venv/bin/python -c "import base64,pathlib;from assignment_checker.pdf_review import *;[print(l['id'],l['text']) for n,p in (('teacher','T'),('student','S')) for page in source_lines(parse_pdf(PDFInput(filename=n+'.pdf',data_base64=base64.b64encode(pathlib.Path('examples/week6/'+n+'.pdf').read_bytes()).decode())),p) for l in page['lines']]"
```
