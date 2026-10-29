// Build the redesigned phase review deck (PPTX with speaker notes).
// Usage: NODE_PATH=<node_modules with pptxgenjs, sharp, lucide> node build-deck.js <apply_theme.js path>
// Screenshots in assets/ are real local UI captures; all case data shown is synthetic.
const path = require('path');
const fs = require('fs');
const pptxgen = require('pptxgenjs');
const sharp = require('sharp');
const lucide = require('lucide');
const JSZip = require(require.resolve('jszip', { paths: [require.resolve('pptxgenjs')] }));
const { applyTheme } = require(process.argv[2]);
const SCRIPT = require('./script.js');

const HERE = __dirname;
const OUT = path.join(HERE, 'phase-review-v2.pptx');
const ASSET = (f) => path.join(HERE, 'assets', f);
const FONT = 'PingFang TC';

const THEME = {
  name: 'Team02 Ink and Status',
  headFontFace: FONT,
  bodyFontFace: FONT,
  colors: {
    dk1: '1A2233', lt1: 'FFFFFF', dk2: '1F2D4A', lt2: 'EEF2F7',
    accent1: 'F5C542', // highlighter: new / key numbers
    accent2: '1E8A5A', // 已完成 / PASS
    accent3: 'C25E12', // 需補件 / 待驗證
    accent4: '3D6BB3', // 待確認 / GPT
    accent5: 'C73541', // 失敗
    accent6: '66768C', // muted slate
    hlink: '3D6BB3', folHlink: '66768C',
  },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; // 13.333 x 7.5 in
pres.title = '作業規格與缺漏檢查助手：階段成果檢視（v2）';
pres.author = '第 02 組';
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
const C = pres.SchemeColor;

// ---------- layouts ----------
const footer = (color) => [
  { text: { text: '第 02 組 · 作業規格與缺漏檢查助手', options: { x: 0.6, y: 7.0, w: 8, h: 0.28, fontSize: 10, color, margin: 0, lang: 'zh-TW' } } },
];
pres.defineSlideMaster({
  title: 'TITLE_DARK',
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: 'kicker', type: 'body', align: 'left', x: 0.6, y: 0.9, w: 7.4, h: 0.4, fontSize: 16, bold: true, color: C.accent1, margin: 0, valign: 'top' }, text: '' } },
    { placeholder: { options: { name: 'title', type: 'title', align: 'left', x: 0.6, y: 1.45, w: 7.6, h: 1.05, fontSize: 44, bold: true, color: C.background1, margin: 0, valign: 'top' }, text: '' } },
  ],
});
pres.defineSlideMaster({
  title: 'CONTENT',
  background: { color: C.background1 },
  objects: [
    { placeholder: { options: { name: 'kicker', type: 'body', align: 'left', x: 0.6, y: 0.4, w: 9.6, h: 0.3, fontSize: 13, bold: true, color: C.accent6, margin: 0, valign: 'top' }, text: '' } },
    { placeholder: { options: { name: 'title', type: 'title', align: 'left', x: 0.6, y: 0.72, w: 12.1, h: 0.75, fontSize: 30, bold: true, color: C.text1, margin: 0, valign: 'top' }, text: '' } },
    ...footer(C.accent6),
  ],
  slideNumber: { x: 12.13, y: 7.0, w: 0.6, h: 0.28, fontSize: 10, color: C.accent6, align: 'right' },
});
pres.defineSlideMaster({
  title: 'CLOSING_DARK',
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: 'kicker', type: 'body', align: 'left', x: 0.6, y: 0.4, w: 9.6, h: 0.3, fontSize: 13, bold: true, color: C.accent1, margin: 0, valign: 'top' }, text: '' } },
    { placeholder: { options: { name: 'title', type: 'title', align: 'left', x: 0.6, y: 0.72, w: 12.1, h: 0.75, fontSize: 30, bold: true, color: C.background1, margin: 0, valign: 'top' }, text: '' } },
    ...footer(C.background2),
  ],
  slideNumber: { x: 12.13, y: 7.0, w: 0.6, h: 0.28, fontSize: 10, color: C.background2, align: 'right' },
});

// ---------- helpers ----------
const iconCache = new Map();
async function icon(name, hex) {
  const key = name + hex;
  if (iconCache.has(key)) return iconCache.get(key);
  const node = lucide.icons[name];
  if (!node) throw new Error('missing icon ' + name);
  const body = node.map(([tag, attrs]) => `<${tag} ${Object.entries(attrs).map(([k, v]) => `${k}="${v}"`).join(' ')}/>`).join('');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#${hex}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
  const png = await sharp(Buffer.from(svg), { density: 1024 }).resize(256, 256).png().toBuffer();
  const data = 'image/png;base64,' + png.toString('base64');
  iconCache.set(key, data);
  return data;
}
let seq = 0;
const nm = (p) => `${p}-${++seq}`;

function text(s, str, x, y, w, h, o = {}) {
  s.addText(str, {
    x, y, w, h, isTextBox: true, margin: 0, fontSize: 16, color: C.text1, valign: 'top', lang: 'zh-TW',
    objectName: nm(o.name || 'text'), ...o,
  });
}
function card(s, x, y, w, h, o = {}) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: o.radius ?? 0.08,
    fill: { color: o.fill || C.background1, transparency: o.transparency || 0 },
    line: o.line === false ? { type: 'none' } : { color: o.line || C.background2, width: o.lineWidth || 1 },
    shadow: o.shadow === false ? undefined : { type: 'outer', color: HEX.dk1, opacity: 0.1, blur: 10, offset: 2, angle: 90 },
    objectName: nm(o.name || 'card'),
  });
}
async function iconCircle(s, name, x, y, d, fill, iconHex = HEX.lt1) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { type: 'none' }, objectName: nm('icon-bg') });
  const pad = d * 0.24;
  s.addImage({ data: await icon(name, iconHex), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad, altText: name, objectName: nm('icon') });
}
async function bareIcon(s, name, x, y, d, hex) {
  s.addImage({ data: await icon(name, hex), x, y, w: d, h: d, altText: name, objectName: nm('icon') });
}
// Rough text width for chips: CJK full width, Latin about 0.58 em.
function textWidth(str, pt) {
  let em = 0;
  for (const ch of str) em += /[⺀-￿]/.test(ch) ? 1 : 0.58;
  return (em * pt) / 72;
}
const STATUS = {
  met: { color: C.accent2, icon: 'CircleCheck', label: '已完成' },
  partial: { color: C.accent3, icon: 'CircleAlert', label: '需補件' },
  unsure: { color: C.accent4, icon: 'CircleHelp', label: '待確認' },
  pass: { color: C.accent2, icon: 'CircleCheck', label: 'LIVE_PASS' },
  fail: { color: C.accent5, icon: 'CircleX', label: 'LIVE_FAIL' },
  pending: { color: C.accent3, icon: 'Clock', label: '待驗證' },
  muted: { color: C.accent6, icon: 'CircleMinus', label: '未提供' },
  new: { color: C.accent1, icon: 'Sparkles', label: 'v0.8 新功能', ink: true },
};
// Status chip: the deck's recurring motif. Returns chip width.
async function chip(s, x, y, kind, label, pt = 13) {
  const st = STATUS[kind];
  const lab = label || st.label;
  const h = pt / 72 + 0.16;
  const ic = h * 0.6;
  const w = 0.12 + ic + 0.07 + textWidth(lab, pt) + 0.16;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: h / 2, fill: { color: st.color }, line: { type: 'none' }, objectName: nm('chip-' + kind) });
  s.addImage({ data: await icon(st.icon, st.ink ? HEX.dk2 : HEX.lt1), x: x + 0.12, y: y + (h - ic) / 2, w: ic, h: ic, altText: lab, objectName: nm('chip-icon') });
  text(s, lab, x + 0.12 + ic + 0.07, y, w - ic - 0.2, h, { fontSize: pt, bold: true, color: st.ink ? C.text2 : C.background1, valign: 'middle', name: 'chip-text' });
  return w;
}
// Small neutral tag (role / mode), outlined.
function tag(s, x, y, label, color, pt = 12, filled = false) {
  const h = pt / 72 + 0.12;
  const w = textWidth(label, pt) + 0.26;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: h / 2, fill: filled ? { color } : { color: C.background1 }, line: { color, width: 1 }, objectName: nm('tag') });
  text(s, label, x, y, w, h, { fontSize: pt, bold: true, color: filled ? C.background1 : color, align: 'center', valign: 'middle', name: 'tag-text' });
  return w;
}
function arrow(s, x1, y1, x2, y2, color = C.accent6, o = {}) {
  const flipH = x2 < x1, flipV = y2 < y1;
  s.addShape(pres.shapes.LINE, {
    x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1), flipH, flipV,
    line: { color, width: o.width || 1.75, endArrowType: o.end === false ? undefined : 'triangle', beginArrowType: o.both ? 'triangle' : undefined, dashType: o.dash },
    objectName: nm('arrow'),
  });
}
function screenshot(s, file, x, y, w, h, alt) {
  card(s, x - 0.06, y - 0.06, w + 0.12, h + 0.12, { radius: 0.06, name: 'shot-frame' });
  s.addImage({ path: ASSET(file), x, y, w, h, altText: alt, objectName: nm('screenshot') });
}
let slideIndex = 0;
function slide(master, section, kicker, title) {
  const s = pres.addSlide({ masterName: master, sectionTitle: section });
  if (kicker) s.addText(kicker, { placeholder: 'kicker', lang: 'zh-TW' });
  if (title) s.addText(title, { placeholder: 'title', lang: 'zh-TW' });
  s.addNotes(SCRIPT.notes(slideIndex++)); // spoken script lives in script.js
  return s;
}

async function build() {
  // ===== 1. Title =====
  pres.addSection({ title: '開場' });
  let s = slide('TITLE_DARK', '開場', '階段性成果檢視 · WEEK 01–07 ＋ PDF 預檢 v0.8', '作業規格與缺漏檢查助手');
  text(s, '以老師範例為參考，交作業前先指出哪些已完成、哪些需要補件、哪些要等老師確認。', 0.6, 2.7, 7.3, 1.0, { fontSize: 20, color: C.background2, lineSpacingMultiple: 1.15 });
  let cx = 0.6;
  for (const k of ['met', 'partial', 'unsure']) cx += (await chip(s, cx, 4.0, k, null, 16)) + 0.2;
  text(s, '第 02 組', 0.6, 5.15, 4, 0.4, { fontSize: 18, bold: true, color: C.accent1 });
  text(s, '陳冠友 S11259039（隊長）　林崇瑋 S11259031（隊員）', 0.6, 5.6, 7.4, 0.4, { fontSize: 16, color: C.background1 });
  text(s, '證據 2026-10-28／30 · W7 6a5bc9b · PDF 13b2b1e · W6 327b7e2 · 資料皆為合成', 0.6, 6.55, 7.6, 0.3, { fontSize: 12, color: C.background2 });
  // product illustration: a result card like the real UI
  card(s, 8.55, 1.2, 4.18, 4.95, { radius: 0.1, line: false, name: 'mock-card' });
  await iconCircle(s, 'FileCheck', 8.85, 1.5, 0.58, C.text2);
  text(s, '作業檢查結果', 9.6, 1.52, 3, 0.38, { fontSize: 18, bold: true });
  text(s, '提交前自我檢查 · 不是正式成績', 9.6, 1.9, 3, 0.26, { fontSize: 11, color: C.accent6 });
  const rows = [['使用者與需求', 'met', 2.3], ['失敗案例的原因', 'partial', 1.7], ['附錄測試紀錄', 'unsure', 2.0]];
  for (let i = 0; i < rows.length; i++) {
    const ry = 2.65 + i * 1.12;
    s.addShape(pres.shapes.LINE, { x: 8.85, y: ry - 0.14, w: 3.6, h: 0, line: { color: C.background2, width: 1 }, objectName: nm('rule') });
    text(s, rows[i][0], 8.85, ry, 2.3, 0.34, { fontSize: 15, bold: true });
    await chip(s, 11.3, ry + 0.02, rows[i][1], null, 11);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.85, y: ry + 0.48, w: rows[i][2], h: 0.11, rectRadius: 0.05, fill: { color: C.background2 }, line: { type: 'none' }, objectName: nm('bar') });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.85, y: ry + 0.68, w: rows[i][2] * 0.7, h: 0.11, rectRadius: 0.05, fill: { color: C.background2 }, line: { type: 'none' }, objectName: nm('bar') });
  }

  // ===== 2. Problem =====
  s = slide('CONTENT', '開場', '問題與使用情境', '學生交作業前，常常不知道少了哪一段');
  text(s, '誰會用、怎麼用', 0.6, 1.75, 5, 0.4, { fontSize: 18, bold: true });
  const who = [
    ['GraduationCap', '老師', '提供範例與已確認的必做要求'],
    ['FileSearch', '學生', '交報告前先貼上或上傳，自我檢查'],
    ['ListChecks', '老師與學生', '學生看補件建議，老師看有引用的待確認項'],
  ];
  for (let i = 0; i < who.length; i++) {
    const y = 2.35 + i * 1.3;
    if (i < who.length - 1) s.addShape(pres.shapes.LINE, { x: 0.95, y: y + 0.7, w: 0, h: 0.6, line: { color: C.background2, width: 2 }, objectName: nm('rule') });
    await iconCircle(s, who[i][0], 0.6, y, 0.7, i === 1 ? C.accent4 : C.text2);
    text(s, who[i][1], 1.55, y + 0.02, 4.4, 0.36, { fontSize: 18, bold: true });
    text(s, who[i][2], 1.55, y + 0.4, 4.4, 0.7, { fontSize: 15, color: C.accent6 });
  }
  text(s, '同樣「有寫」，判斷可能不同', 6.6, 1.75, 6, 0.4, { fontSize: 18, bold: true });
  const ex = [
    ['「誰會用」寫成：擔心漏寫的南大同學', '語意符合，標題不同不算缺交', 'met'],
    ['失敗案例只有「輸入」與「實際結果」', '缺少失敗原因，提醒補上', 'partial'],
    ['寫「測試紀錄見附錄 A」，但讀不到附錄', '無法確認，交由老師核對', 'unsure'],
  ];
  for (let i = 0; i < ex.length; i++) {
    const y = 2.3 + i * 1.38;
    card(s, 6.6, y, 6.13, 1.18);
    text(s, ex[i][0], 6.85, y + 0.18, 4.3, 0.5, { fontSize: 15, bold: true });
    text(s, ex[i][1], 6.85, y + 0.72, 4.3, 0.3, { fontSize: 13, color: C.accent6 });
    await chip(s, 11.45, y + 0.2, ex[i][2], null, 13);
  }
  await bareIcon(s, 'Lightbulb', 0.6, 6.4, 0.34, HEX.accent4);
  text(s, '標題與用字都會變，關鍵字規則判不準，所以需要 LLM 判讀語意。', 1.05, 6.4, 11.5, 0.36, { fontSize: 16, bold: true, color: C.accent4, valign: 'middle' });

  // ===== 3. Progress timeline =====
  s = slide('CONTENT', '開場', 'WEEK 01–07 ＋ v0.8 進度', '七週累積：三條路徑都能運作，但還沒接在一起');
  const tl = [
    ['W1–2', '題目、文字比對\n與引用核對', '', 'done'],
    ['W3', '來源檢索\n與拒答 gate', '缺教師費率原文', 'done'],
    ['W4', 'MCP 讀取\n確認後才寫入', 'Gemini／ADC\n未驗證', 'done'],
    ['W5', 'LangGraph\n候選與比較', '原版仍為預設', 'done'],
    ['W6', '評估後修訂\n（10/30 補交）', 'live 未證明改善', 'done'],
    ['W7', 'Session\n清除與隔離', '正式登入待做', 'done'],
    ['v0.8', 'PDF 預檢\n與估分', '語意仍有誤判', 'new'],
  ];
  const tx0 = 1.25, tstep = (12.1 - 1.25) / 6;
  s.addShape(pres.shapes.LINE, { x: tx0, y: 2.38, w: tstep * 6, h: 0, line: { color: C.background2, width: 3 }, objectName: nm('timeline') });
  for (let i = 0; i < tl.length; i++) {
    const [wk, done, gap, st] = tl[i];
    const xc = tx0 + i * tstep;
    const d = st === 'new' ? 0.46 : 0.34;
    s.addShape(pres.shapes.OVAL, { x: xc - d / 2, y: 2.38 - d / 2, w: d, h: d, fill: { color: st === 'done' ? C.accent2 : st === 'new' ? C.accent1 : C.background1 }, line: { color: st === 'none' ? C.accent6 : st === 'new' ? C.text2 : C.accent2, width: st === 'new' ? 2 : 1.5 }, objectName: nm('node') });
    text(s, wk, xc - 0.85, 1.7, 1.7, 0.34, { fontSize: 15, bold: true, align: 'center', color: st === 'none' ? C.accent6 : C.text1 });
    text(s, done, xc - 0.85, 2.72, 1.7, 0.62, { fontSize: 13, bold: st === 'new', align: 'center', color: st === 'none' ? C.accent6 : C.text1 });
    if (gap) text(s, gap, xc - 0.85, 3.38, 1.7, 0.5, { fontSize: 12, align: 'center', color: st === 'none' ? C.accent6 : C.accent3 });
  }
  const paths = [
    ['MessageSquareText', 'A　文字語意比對', '老師規格＋學生文字 → GPT 判讀是否符合，系統核對原文引用', 'pass', null],
    ['Wrench', 'B　補件工具流程', 'GPT 提出工具呼叫 → Host 驗證 → 使用者確認後寫入草稿', 'pass', null],
    ['FileText', 'C　PDF 預檢與估分', '老師與學生 PDF 圖文比對，確認配分後才顯示估分；實測用合成 PDF', 'pass', 'LIVE_PASS · 預期 6／7'],
  ];
  for (let i = 0; i < paths.length; i++) {
    const x = 0.6 + i * 4.15;
    card(s, x, 4.15, 3.85, 2.05, i === 2 ? { line: C.accent1, lineWidth: 2 } : {});
    await iconCircle(s, paths[i][0], x + 0.25, 4.38, 0.56, C.text2);
    text(s, paths[i][1], x + 0.95, 4.47, 2.8, 0.4, { fontSize: 17, bold: true });
    text(s, paths[i][2], x + 0.25, 5.07, 3.4, 0.6, { fontSize: 13, color: C.accent6 });
    await chip(s, x + 0.25, 5.72, paths[i][3], paths[i][4], 12);
  }
  await bareIcon(s, 'Unlink', 0.6, 6.4, 0.32, HEX.accent3);
  text(s, '最大缺口：A、C 的判讀結果尚未接入 B 的草稿工具，B 目前讀的是預先撰寫的合成評閱快照。', 1.02, 6.4, 11.7, 0.34, { fontSize: 15, bold: true, color: C.accent3, valign: 'middle' });

  // ===== 4. LLM vs program =====
  pres.addSection({ title: '系統設計' });
  s = slide('CONTENT', '系統設計', '設計理由與責任邊界', 'LLM 判讀語意，程式負責把關');
  const cols = [
    ['Brain', C.accent4, '交給模型', '需要理解語意的判斷', ['理解換句話說：標題不同，內容是否仍符合', '判斷充分性：有寫，但是否寫完整', '讀 PDF 文字與圖片，選出證據行號', '提出工具呼叫與修改建議']],
    ['ShieldCheck', C.text2, '交給程式', '可以明確驗證的規則', ['欄位、版本、要求覆蓋與大小限制', '原文引用、頁碼與來源 hash 核對', '權限、人工確認與 Session 隔離', 'SQLite 交易、同 ID 冪等、配分加總']],
  ];
  for (let i = 0; i < 2; i++) {
    const x = 0.6 + i * 6.23;
    const [ic, col, h, sub, items] = cols[i];
    card(s, x, 1.75, 5.9, 3.8);
    await iconCircle(s, ic, x + 0.35, 2.05, 0.7, col);
    text(s, h, x + 1.25, 2.06, 4, 0.42, { fontSize: 21, bold: true, color: col });
    text(s, sub, x + 1.25, 2.48, 4, 0.3, { fontSize: 13, color: C.accent6 });
    s.addText(items.map((t, j) => ({ text: t, options: { bullet: { indent: 18 }, breakLine: j < items.length - 1 } })), {
      x: x + 0.35, y: 3.1, w: 5.3, h: 2.3, isTextBox: true, margin: 0, fontSize: 17, color: C.text1, valign: 'top', paraSpaceAfter: 16, lang: 'zh-TW', objectName: nm('bullets'),
    });
  }
  card(s, 0.6, 5.85, 12.13, 0.9, { fill: C.background2, line: false, shadow: false });
  await bareIcon(s, 'Quote', 0.9, 6.08, 0.44, HEX.dk2);
  text(s, '單次比對不需要 Agent；「查詢後提案、確認後執行、再回填結果」才需要受控的工具流程。', 1.55, 5.85, 10.9, 0.9, { fontSize: 17, bold: true, color: C.text2, valign: 'middle' });

  // ===== 5. Architecture =====
  s = slide('CONTENT', '系統設計', '系統架構', '模型只提出動作，Host 決定能不能執行');
  card(s, 0.6, 1.95, 2.75, 1.6);
  await iconCircle(s, 'Monitor', 0.85, 2.15, 0.5, C.accent6);
  text(s, '瀏覽器 /week7', 0.85, 2.75, 2.4, 0.34, { fontSize: 16, bold: true });
  text(s, 'PDF 預檢 · 補件工具\n文字語意比對', 0.85, 3.07, 2.4, 0.42, { fontSize: 11, color: C.accent6 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 4.3, y: 1.8, w: 4.6, h: 1.95, rectRadius: 0.1, fill: { color: C.text2 }, line: { type: 'none' }, shadow: { type: 'outer', color: HEX.dk1, opacity: 0.15, blur: 10, offset: 2, angle: 90 }, objectName: 'host-box' });
  await bareIcon(s, 'ShieldCheck', 4.6, 2.05, 0.42, HEX.accent1);
  text(s, 'FastAPI ＋ Host 守門', 5.15, 2.05, 3.6, 0.42, { fontSize: 19, bold: true, color: C.background1, valign: 'middle' });
  s.addText([
    { text: 'Cookie／Session 身分驗證', options: { breakLine: true } },
    { text: '工具參數與允許序列驗證', options: { breakLine: true } },
    { text: '引用、頁碼、配分與摘要核對' },
  ], { x: 4.6, y: 2.62, w: 4.1, h: 1.0, isTextBox: true, margin: 0, fontSize: 14, color: C.background2, paraSpaceAfter: 4, lang: 'zh-TW', objectName: 'host-items' });
  card(s, 9.85, 1.95, 2.88, 1.6);
  await iconCircle(s, 'Bot', 10.1, 2.15, 0.5, C.accent4);
  text(s, 'OpenAI GPT', 10.1, 2.75, 2.5, 0.34, { fontSize: 16, bold: true });
  text(s, '工具／文字：gpt-4.1-mini\nPDF 圖文：gpt-5.4', 10.1, 3.07, 2.6, 0.45, { fontSize: 11, color: C.accent6 });
  arrow(s, 3.4, 2.75, 4.25, 2.75, C.accent6, { both: true });
  arrow(s, 8.95, 2.45, 9.8, 2.45, C.accent4);
  arrow(s, 9.8, 3.1, 8.95, 3.1, C.accent4);
  text(s, 'context', 8.95, 2.1, 0.85, 0.28, { fontSize: 11, color: C.accent4, align: 'center' });
  text(s, '提出 call', 8.95, 3.18, 0.85, 0.28, { fontSize: 11, color: C.accent4, align: 'center' });
  const stores = [
    ['FileSearch', '來源與 RAG gate', 'T1–T3／S1–S3 版本與 hash'],
    ['Server', 'MCP stdio 唯讀', '既有合成評閱快照'],
    ['Database', 'SQLite', '草稿、收據、稽核（確認後寫）'],
    ['History', 'Session 記憶', '只留最近一筆成功摘要'],
  ];
  const sw = 2.85, sg = (12.13 - 4 * sw) / 3;
  s.addShape(pres.shapes.LINE, { x: 6.6, y: 3.75, w: 0, h: 0.4, line: { color: C.accent6, width: 1.75 }, objectName: 'bus-stem' });
  s.addShape(pres.shapes.LINE, { x: 0.6 + sw / 2, y: 4.15, w: 3 * (sw + sg), h: 0, line: { color: C.accent6, width: 1.75 }, objectName: 'bus' });
  for (let i = 0; i < stores.length; i++) {
    const x = 0.6 + i * (sw + sg);
    arrow(s, x + sw / 2, 4.15, x + sw / 2, 4.5, C.accent6);
    card(s, x, 4.55, sw, 1.35, { fill: C.background2, line: false, shadow: false });
    await bareIcon(s, stores[i][0], x + 0.25, 4.75, 0.36, HEX.dk2);
    text(s, stores[i][1], x + 0.75, 4.75, 2.0, 0.36, { fontSize: 15, bold: true, valign: 'middle' });
    text(s, stores[i][2], x + 0.25, 5.25, sw - 0.4, 0.5, { fontSize: 12, color: C.accent6 });
  }
  await bareIcon(s, 'RotateCcw', 0.6, 6.25, 0.3, HEX.dk2);
  text(s, '工具結果回填模型後，Host 再核對摘要才回傳 UI。', 1.0, 6.22, 5.6, 0.36, { fontSize: 14, valign: 'middle' });
  await bareIcon(s, 'Lock', 6.83, 6.25, 0.3, HEX.dk2);
  text(s, 'Session 記憶只提供背景，不能授權寫入。', 7.23, 6.22, 5.5, 0.36, { fontSize: 14, valign: 'middle' });

  // ===== 6. Tools =====
  s = slide('CONTENT', '系統設計', '工具介面與停止條件', '兩個工具都有可驗證的輸入、輸出與停止點');
  const tools = [
    ['FileSearch', 'get_submission_review', '唯讀 · MCP', C.accent4, [['輸入', '作業 ID、提交 ID、版本'], ['輸出', '缺漏、待確認項、引用與 hash'], ['驗證', '目標一致、來源有效、完整覆蓋'], ['傳輸', 'MCP stdio，只能讀']]],
    ['FilePen', 'create_revision_draft', '寫入 · 需確認', C.accent3, [['輸入', '相同目標＋requirement_ids'], ['輸出', 'draft_id、request_id、收據'], ['驗證', '項目一致、來源未變、使用者確認'], ['寫入', '本機 SQLite，同 run ID 只寫一次']]],
  ];
  for (let i = 0; i < 2; i++) {
    const x = 0.6 + i * 6.23;
    const [ic, name, tg, col, rowsT] = tools[i];
    card(s, x, 1.75, 5.9, 3.05);
    await iconCircle(s, ic, x + 0.3, 1.98, 0.56, col);
    text(s, name, x + 1.02, 2.0, 3.2, 0.5, { fontSize: 18, bold: true, valign: 'middle' });
    tag(s, x + 5.9 - 0.3 - (textWidth(tg, 12) + 0.26), 2.1, tg, col, 12);
    for (let j = 0; j < rowsT.length; j++) {
      const ry = 2.85 + j * 0.46;
      text(s, rowsT[j][0], x + 0.3, ry, 0.7, 0.36, { fontSize: 14, bold: true, color: col, valign: 'middle' });
      text(s, rowsT[j][1], x + 1.02, ry, 4.6, 0.36, { fontSize: 14, valign: 'middle' });
    }
  }
  const stats = [['3', '輪', '模型呼叫上限'], ['2', '次', '可重試錯誤上限'], ['10', '分鐘', '提案確認期限']];
  for (let i = 0; i < 3; i++) {
    const x = 0.6 + i * 4.14;
    card(s, x, 5.1, 3.85, 1.1, { fill: C.background2, line: false, shadow: false });
    s.addText([
      { text: stats[i][0], options: { fontSize: 40, bold: true, color: C.text2 } },
      { text: ' ' + stats[i][1], options: { fontSize: 18, bold: true, color: C.text2 } },
    ], { x: x + 0.3, y: 5.1, w: 1.9, h: 1.1, isTextBox: true, margin: 0, valign: 'middle', lang: 'zh-TW', objectName: nm('stat') });
    text(s, stats[i][2], x + 2.15, 5.1, 1.6, 1.1, { fontSize: 15, color: C.accent6, valign: 'middle' });
  }
  await bareIcon(s, 'OctagonX', 0.6, 6.44, 0.32, HEX.accent5);
  text(s, '非法參數、工具順序不符、引用不足或無權限 → 立即停止、不寫入，疑義交給老師。', 1.02, 6.42, 11.7, 0.36, { fontSize: 15, bold: true, valign: 'middle' });

  // ===== 7. Session memory =====
  s = slide('CONTENT', '系統設計', 'WEEK 07 · 路線 C：Session 記憶', '清除對話後，舊摘要不再進入模型');
  const flow = [['成功報告', '摘要通過 Host 核對', false], ['本 Session 最近一筆摘要', '≤ 4,096 bytes，不含原文與先前同意', true], ['下次模型 context', '先核對 owner 與來源版本', false]];
  for (let i = 0; i < 3; i++) {
    const x = 0.6 + i * 4.24;
    if (flow[i][2]) s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.75, w: 3.65, h: 1.0, rectRadius: 0.08, fill: { color: C.text2 }, line: { type: 'none' }, objectName: 'memory-box' });
    else card(s, x, 1.75, 3.65, 1.0);
    text(s, flow[i][0], x + 0.25, 1.85, 3.2, 0.38, { fontSize: 16, bold: true, color: flow[i][2] ? C.background1 : C.text1 });
    text(s, flow[i][1], x + 0.25, 2.25, 3.25, 0.4, { fontSize: 12, color: flow[i][2] ? C.background2 : C.accent6 });
    if (i < 2) arrow(s, x + 3.7, 2.25, x + 4.19, 2.25, C.accent6);
  }
  text(s, '三種情況會切斷記憶', 0.6, 3.1, 5.8, 0.38, { fontSize: 17, bold: true });
  const cuts = [['Eraser', '清除對話，開始新 Session'], ['UserX', '換成另一位使用者'], ['RefreshCw', '來源更新為 v2（hash 改變）']];
  for (let i = 0; i < 3; i++) {
    const y = 3.62 + i * 0.6;
    await iconCircle(s, cuts[i][0], 0.6, y, 0.44, C.accent5);
    text(s, cuts[i][1], 1.2, y, 5.1, 0.44, { fontSize: 15, valign: 'middle' });
  }
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 5.5, w: 5.9, h: 0.52, rectRadius: 0.26, fill: { color: C.text2 }, line: { type: 'none' }, objectName: 'memory-null' });
  text(s, '→ context 回填 memory: null，舊提案失效', 0.85, 5.5, 5.5, 0.52, { fontSize: 15, bold: true, color: C.background1, valign: 'middle' });
  text(s, '清除 ≠ 刪除：既有草稿、交易與稽核紀錄仍保留在本機。', 0.6, 6.2, 5.9, 0.36, { fontSize: 13, color: C.accent6 });
  screenshot(s, 's04-memory.png', 6.98, 3.2, 5.7, 5.7 * 320 / 583, '2026-10-28 清除對話後新 Session 的記憶範圍，memory 為 null');
  text(s, '實際畫面：清除後的新 Session（2026-10-28）', 6.98, 6.4, 5.7, 0.3, { fontSize: 12, color: C.accent6 });

  // ===== 8. Demo A =====
  pres.addSection({ title: '實際示範' });
  s = slide('CONTENT', '實際示範', '真實介面 · OPENAI · 2026-10-28', '示範：使用者按下確認後，才寫入一份草稿');
  const steps = [
    ['使用者', C.accent2, '提出補件需求'],
    ['GPT', C.accent4, '呼叫查詢工具 get_submission_review'],
    ['Host', C.text2, '驗證參數、查來源並回填結果'],
    ['GPT', C.accent4, '提出草稿工具（此時尚未寫入）'],
    ['使用者', C.accent2, '按下確認，Host 才寫入 SQLite'],
    ['Host', C.text2, '收據回填 GPT，核對摘要後回傳'],
  ];
  for (let i = 0; i < steps.length; i++) {
    const y = 1.8 + i * 0.68;
    if (i === 4) s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.45, y: y - 0.1, w: 6.9, h: 0.66, rectRadius: 0.1, fill: { color: C.accent1, transparency: 65 }, line: { type: 'none' }, objectName: 'highlight-step' });
    s.addShape(pres.shapes.OVAL, { x: 0.6, y, w: 0.46, h: 0.46, fill: { color: steps[i][1] }, line: { type: 'none' }, objectName: nm('step-dot') });
    text(s, String(i + 1), 0.6, y, 0.46, 0.46, { fontSize: 15, bold: true, color: C.background1, align: 'center', valign: 'middle' });
    text(s, steps[i][2], 1.25, y, 4.75, 0.46, { fontSize: 16, bold: i === 4, valign: 'middle' });
    tag(s, 6.1, y + 0.08, steps[i][0], steps[i][1], 12);
  }
  card(s, 0.6, 5.95, 6.6, 0.8, { fill: C.background2, line: false, shadow: false });
  const cw = await chip(s, 0.85, 6.17, 'pass', null, 13);
  text(s, '草稿 1 份；同一請求重送仍是 1 份', 0.85 + cw + 0.2, 5.95, 4.9, 0.8, { fontSize: 16, bold: true, valign: 'middle' });
  screenshot(s, 's02-result.png', 8.35, 1.72, 4.95 * 583 / 730, 4.95, '2026-10-28 真實 GPT 工作台：三個檢查項目與已建立的補件草稿');

  // ===== 9. Demo B =====
  s = slide('CONTENT', '實際示範', '真實介面 · OPENAI · 2026-10-28', '語意比對分得出「有寫」和「寫完整」');
  text(s, '老師要求：說明使用者與情境，並提供含輸入、結果與原因的失敗案例。', 0.6, 1.75, 6.3, 0.5, { fontSize: 14, color: C.accent6 });
  const rr = [['met', 'R1　使用者與情境', '標題寫「誰會用」，仍清楚描述對象與情境 → 符合'], ['partial', 'R2　完整的失敗案例', '有輸入、有實際結果，但沒寫失敗原因 → 部分完成']];
  for (let i = 0; i < 2; i++) {
    const y = 2.4 + i * 1.6;
    card(s, 0.6, y, 6.3, 1.4);
    await chip(s, 0.85, y + 0.22, rr[i][0], null, 13);
    text(s, rr[i][1], 2.15, y + 0.17, 4.6, 0.42, { fontSize: 18, bold: true, valign: 'middle' });
    text(s, rr[i][2], 0.85, y + 0.75, 5.85, 0.5, { fontSize: 15 });
  }
  await bareIcon(s, 'TriangleAlert', 0.6, 5.72, 0.36, HEX.accent3);
  text(s, '系統只確認引用確實存在於原文，不保證語意判斷正確；模型建議的失敗原因也需學生自行查證。', 1.1, 5.68, 5.8, 0.9, { fontSize: 15, bold: true, color: C.accent3 });
  screenshot(s, 's03-result.png', 7.45, 1.78, 5.25, 5.25 * 528 / 583, '2026-10-28 真實 GPT 文字比對：R1 已完成、R2 需補件');

  // ===== 10. PDF pipeline =====
  pres.addSection({ title: 'PDF 預檢' });
  s = slide('CONTENT', 'PDF 預檢', 'PDF 提交前預檢與估分 · 2026-10-28 晚間新增', 'PDF 預檢：模型挑證據行號，Host 複製原文');
  await chip(s, 10.9, 0.36, 'new', null, 12);
  const pipe = [
    ['使用者', C.accent2, '上傳兩份 PDF', '老師規格／範例＋學生報告'],
    ['Host', C.text2, '驗證並標上行號', '檢查大小與頁數，擷取文字並逐行編號'],
    ['GPT', C.accent4, '圖文一起判讀', '讀文字與頁面圖片，比對語意，選出證據行號'],
    ['Host', C.text2, '複製原文核對', '依行號取引文，驗證頁碼、配分與分數範圍'],
    ['使用者', C.accent2, '確認老師配分', '勾選核對後，才看得到估分'],
    ['Host', C.text2, '加總估分區間', '產生本機報告，可下載 JSON'],
  ];
  const pw = 2.4, pg = 0.4;
  for (let i = 0; i < 6; i++) {
    const r = Math.floor(i / 3), c = i % 3;
    const x = 0.6 + c * (pw + pg), y = 1.75 + r * 1.85;
    card(s, x, y, pw, 1.5);
    s.addShape(pres.shapes.OVAL, { x: x + 0.2, y: y + 0.18, w: 0.36, h: 0.36, fill: { color: pipe[i][1] }, line: { type: 'none' }, objectName: nm('pipe-dot') });
    text(s, String(i + 1), x + 0.2, y + 0.18, 0.36, 0.36, { fontSize: 13, bold: true, color: C.background1, align: 'center', valign: 'middle' });
    tag(s, x + pw - 0.2 - (textWidth(pipe[i][0], 11) + 0.26), y + 0.21, pipe[i][0], pipe[i][1], 11);
    text(s, pipe[i][2], x + 0.2, y + 0.62, pw - 0.35, 0.34, { fontSize: 15, bold: true });
    text(s, pipe[i][3], x + 0.2, y + 0.96, pw - 0.3, 0.5, { fontSize: 12, color: C.accent6 });
    if (c < 2) arrow(s, x + pw + 0.04, y + 0.75, x + pw + pg - 0.04, y + 0.75, C.accent6);
  }
  // elbow from step 3 down to step 4
  const x3 = 0.6 + 2 * (pw + pg) + pw / 2, x4 = 0.6 + pw / 2;
  s.addShape(pres.shapes.LINE, { x: x3, y: 3.25, w: 0, h: 0.175, line: { color: C.accent6, width: 1.75 }, objectName: 'elbow-1' });
  s.addShape(pres.shapes.LINE, { x: x4, y: 3.425, w: x3 - x4, h: 0, line: { color: C.accent6, width: 1.75 }, objectName: 'elbow-2' });
  arrow(s, x4, 3.425, x4, 3.58, C.accent6);
  text(s, '估分只在三個條件都成立時才顯示', 0.6, 5.42, 8, 0.36, { fontSize: 15, bold: true });
  let gx = 0.6;
  const gates = ['老師原文明列配分', '總和 = 100', '使用者已確認'];
  for (const g of gates) {
    gx += tag(s, gx, 5.9, g, C.text2, 13) + 0.08;
    arrow(s, gx, 6.06, gx + 0.3, 6.06, C.accent6);
    gx += 0.38;
  }
  tag(s, gx, 5.9, '顯示估分區間', C.accent2, 13, true);
  text(s, '否則只列缺漏與待確認項，不產生分數。', 0.6, 6.42, 8, 0.3, { fontSize: 13, color: C.accent6 });
  screenshot(s, 'pdf-upload.png', 9.3, 1.75, 3.4, 3.4 * 1086 / 745, '本機 /week7 PDF 預檢與估分的上傳畫面，尚未上傳檔案');

  // ===== 11. PDF failures =====
  s = slide('CONTENT', 'PDF 預檢', 'PDF 預檢 · 真實呼叫紀錄', '兩次失敗被 Host 擋下；換模型後通過，判斷仍會錯');
  await chip(s, 10.9, 0.36, 'new', null, 12);
  const fails = [
    ['ae1a441', 'fail', null, 'gpt-4.1-mini 直接寫引文', '模型把摘要當成逐字引文，還混用頁碼。', 'UNGROUNDED_PDF_REPORT', 'Host 拒絕輸出成績'],
    ['a9010bf', 'fail', null, '改成模型選行號、Host 複製', '模型選了跨頁、過長的範圍；人工抽查也發現目錄被當成正文。', 'INVALID_SOURCE_REFERENCE', '引用被擋下，未給分'],
    ['13b2b1e', 'pass', null, 'PDF 改用 gpt-5.4', 'Week 6（c0403a3、327b7e2）以合成 PDF 實測兩輪都通過核對；但 7 項業務預期只中 6 項。', 'gpt-5.4-2026-03-05', '引用過關，語意仍會錯'],
  ];
  for (let i = 0; i < 3; i++) {
    const x = 0.6 + i * 4.14;
    const f = fails[i];
    card(s, x, 1.75, 3.85, 3.6, i === 2 ? { line: C.accent1, lineWidth: 2 } : {});
    text(s, f[0], x + 0.28, 1.98, 1.5, 0.32, { fontSize: 13, bold: true, color: C.accent6, valign: 'middle' });
    await chip(s, x + 3.85 - 0.28 - (0.12 + 0.2 + 0.07 + textWidth(f[2] || STATUS[f[1]].label, 12) + 0.16), 1.98, f[1], f[2], 12);
    text(s, f[3], x + 0.28, 2.5, 3.35, 0.4, { fontSize: 17, bold: true });
    text(s, f[4], x + 0.28, 2.98, 3.35, 0.95, { fontSize: 14 });
    card(s, x + 0.28, 4.0, 3.29, 0.42, { fill: C.background2, line: false, shadow: false, radius: 0.05 });
    text(s, f[5], x + 0.4, 4.0, 3.1, 0.42, { fontSize: 12, bold: true, color: f[1] === 'fail' ? C.accent5 : C.text2, valign: 'middle', fontFace: 'Courier New' });
    await bareIcon(s, f[1] === 'fail' ? 'ShieldCheck' : 'TriangleAlert', x + 0.28, 4.66, 0.3, f[1] === 'fail' ? HEX.accent2 : HEX.accent3);
    text(s, f[6], x + 0.68, 4.62, 3.0, 0.38, { fontSize: 14, bold: true, valign: 'middle' });
    if (i < 2) arrow(s, x + 3.88, 3.55, x + 4.11, 3.55, C.accent6);
  }
  text(s, '學到的事：三層要分開驗證', 0.6, 5.62, 6, 0.36, { fontSize: 16, bold: true });
  let lx = 0.6;
  const layers = ['格式通過', '引用正確', '語意判斷正確'];
  for (let i = 0; i < 3; i++) {
    lx += tag(s, lx, 6.12, layers[i], C.text2, 14, i === 2) + 0.12;
    if (i < 2) { text(s, '≠', lx, 6.08, 0.35, 0.42, { fontSize: 20, bold: true, color: C.accent6, align: 'center', valign: 'middle' }); lx += 0.47; }
  }
  text(s, '實測：模型說學生第 2 頁有終端機截圖，實際沒有，Host 核對仍放行。', 6.9, 6.12, 5.8, 0.38, { fontSize: 13, color: C.accent6, valign: 'middle' });

  // ===== 12. Week 6 evaluator–optimizer =====
  s = slide('CONTENT', 'PDF 預檢', 'WEEK 06 · EVALUATOR–OPTIMIZER（10/30 補交）', 'Week 6：系統指出錯處，再請 GPT 修訂一次');
  const loop = [
    ['GPT', C.accent4, '草稿 A', '讀兩份 PDF，選證據行號'],
    ['Host', C.text2, '逐項評估', '最終關卡同一套規則，列出問題與位置'],
    ['GPT', C.accent4, '修訂得到 B', '帶著 A 與問題清單，只改被指出處'],
    ['Host', C.text2, '同規則重評', '並禁止把推測改成明確要求'],
    ['結果', C.accent2, '通過才採用', '仍未通過：第 2 份即停，不給分'],
  ];
  const lw = 2.2, lg = 0.28;
  for (let i = 0; i < loop.length; i++) {
    const x = 0.6 + i * (lw + lg);
    card(s, x, 1.75, lw, 1.45, i === 4 ? { line: C.accent2, lineWidth: 1.5 } : {});
    s.addShape(pres.shapes.OVAL, { x: x + 0.18, y: 1.92, w: 0.34, h: 0.34, fill: { color: loop[i][1] }, line: { type: 'none' }, objectName: nm('loop-dot') });
    text(s, String(i + 1), x + 0.18, 1.92, 0.34, 0.34, { fontSize: 13, bold: true, color: C.background1, align: 'center', valign: 'middle' });
    tag(s, x + lw - 0.18 - (textWidth(loop[i][0], 11) + 0.26), 1.95, loop[i][0], loop[i][1], 11);
    text(s, loop[i][2], x + 0.18, 2.36, lw - 0.3, 0.34, { fontSize: 15, bold: true });
    text(s, loop[i][3], x + 0.18, 2.7, lw - 0.3, 0.45, { fontSize: 11, color: C.accent6 });
    if (i < loop.length - 1) arrow(s, x + lw + 0.03, 2.47, x + lw + lg - 0.03, 2.47, C.accent6);
  }
  text(s, '草稿 A 通過就直接採用，呼叫次數與原版相同；判斷檔案放反不修訂；模型服務錯誤不重試。', 0.6, 3.36, 12.1, 0.32, { fontSize: 13, color: C.accent6 });
  text(s, '真實比較：同一組合成 PDF，每版每輪各跑一次', 0.6, 3.82, 8, 0.36, { fontSize: 15, bold: true });
  const res = [
    ['gpt-5.4 · 兩輪', [['pass', '原版 LIVE_PASS'], ['pass', '候選 LIVE_PASS']], '草稿 A 都直接通過，候選沒有多呼叫；但 7 項預期都只中 6 項。'],
    ['gpt-4.1-mini · 兩輪', [['fail', '原版 LIVE_FAIL'], ['fail', '候選 LIVE_FAIL']], '候選的修訂稿兩次都與 A 逐字相同，到上限停止；tokens 約 2.3 倍。'],
    ['離線 15 個案例', [['met', '15／15 符合預期']], '修訂後通過、到上限停止、檔案放反不修訂、改標推測被拒。'],
  ];
  for (let i = 0; i < res.length; i++) {
    const x = 0.6 + i * 4.14;
    card(s, x, 4.28, 3.85, 1.8);
    text(s, res[i][0], x + 0.28, 4.43, 3.3, 0.36, { fontSize: 16, bold: true, valign: 'middle' });
    let rx = x + 0.28;
    for (const [kind, label] of res[i][1]) rx += (await chip(s, rx, 4.9, kind, label, 10)) + 0.12;
    text(s, res[i][2], x + 0.28, 5.33, 3.35, 0.65, { fontSize: 13 });
  }
  const pw6 = await chip(s, 0.6, 6.3, 'pending', '尚未證明改善', 13);
  text(s, '預設維持原版，候選可在工作台切換。下一步：把草稿 A 改放在 user 訊息再重測。', 0.6 + pw6 + 0.2, 6.27, 12.13 - pw6 - 0.2, 0.4, { fontSize: 14, bold: true, valign: 'middle' });

  // ===== 13. Tests =====
  pres.addSection({ title: '驗證與限制' });
  s = slide('CONTENT', '驗證與限制', '驗證', '回歸測試從 107 項成長到 213 項');
  s.addChart(pres.charts.BAR, [{ name: '通過測試', labels: ['W4', 'W5', 'W7', 'v0.8', 'W6'], values: [107, 131, 148, 178, 213] }], {
    x: 0.6, y: 1.7, w: 5.6, h: 4.35, barDir: 'col', barGapWidthPct: 55,
    chartColors: [HEX.accent6, HEX.accent6, HEX.dk2, HEX.accent1, HEX.accent4],
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 16, dataLabelFontBold: true, dataLabelColor: HEX.dk1, dataLabelFontFace: '+mn-lt',
    catAxisLabelFontSize: 14, catAxisLabelColor: HEX.accent6, catAxisLabelFontFace: '+mn-lt', catAxisLineShow: false,
    valAxisHidden: true, valAxisMinVal: 0, valAxisMaxVal: 240, valGridLine: { style: 'none' }, catGridLine: { style: 'none' },
    showLegend: false, showTitle: false, objectName: 'tests-chart',
  });
  text(s, 'v0.8 新增 30 項 PDF 測試，W6（10/30 補交）再加 35 項。\n全部是離線與故障注入，不等於真實模型準確率。', 0.6, 6.1, 5.6, 0.6, { fontSize: 13, color: C.accent6 });
  text(s, '關鍵案例：預期與實際一致', 6.75, 1.75, 6, 0.38, { fontSize: 17, bold: true });
  const cases = [
    ['同 Session 續問', '帶入該 Session 的摘要', 'GPT', C.accent4],
    ['清除後新查詢', 'memory:null，任務仍完成', 'GPT', C.accent4],
    ['跨使用者讀取', 'RUN_NOT_FOUND', 'HTTP', C.text2],
    ['同 ID 重送', '確認後與重送都是 1 份', 'GPT', C.accent4],
    ['非法參數、429', '有限停止，不新增草稿', '故障注入', C.accent3],
    ['PDF 錯誤引用、到上限', '不估分，第 2 份即停', '離線', C.accent6],
  ];
  for (let i = 0; i < cases.length; i++) {
    const y = 2.3 + i * 0.64;
    if (i % 2 === 0) s.addShape(pres.shapes.RECTANGLE, { x: 6.75, y: y - 0.06, w: 5.98, h: 0.6, fill: { color: C.background2 }, line: { type: 'none' }, objectName: nm('row-bg') });
    await bareIcon(s, 'CircleCheck', 6.88, y + 0.1, 0.28, HEX.accent2);
    text(s, cases[i][0], 7.3, y, 2.45, 0.48, { fontSize: 14, bold: true, valign: 'middle' });
    text(s, cases[i][1], 9.75, y, 2.0, 0.48, { fontSize: 12, color: C.text1, valign: 'middle' });
    const tw = textWidth(cases[i][2], 11) + 0.26;
    tag(s, 12.63 - tw, y + 0.1, cases[i][2], cases[i][3], 11);
  }
  text(s, '真實呼叫用量（不是帳單）：Week 7 共 14 次模型回覆、18,296 tokens；Week 6 共 10 次回覆、86,451 tokens。', 6.75, 6.18, 5.98, 0.55, { fontSize: 12, color: C.accent6, valign: 'middle' });

  // ===== 14. C01 failure =====
  s = slide('CONTENT', '驗證與限制', '原版 vs Session 候選 · 同輸入、同模型、同來源', '保留一個真實失敗：模型略過了草稿提案');
  text(s, '兩者的檢索與引用 gate 都是 ready，且使用同一個 evidence hash。', 0.6, 1.7, 12, 0.34, { fontSize: 14, color: C.accent6 });
  const cmp = [
    ['原版', 'fail', '讀取後直接回答，跳過提案工具；Host 以 UNEXPECTED_TOOL_SEQUENCE 擋下，未寫入。', [['2', '次模型回覆'], ['2,133', 'tokens'], ['6.518 s', '觀測時間']]],
    ['Session 候選', 'pass', '依序提案、等待確認，使用者確認後完成草稿。', [['3', '次模型回覆'], ['4,352', 'tokens'], ['5.183 s', '觀測時間']]],
  ];
  for (let i = 0; i < 2; i++) {
    const x = 0.6 + i * 6.23;
    card(s, x, 2.2, 5.9, 3.15);
    text(s, cmp[i][0], x + 0.35, 2.42, 3, 0.44, { fontSize: 21, bold: true, valign: 'middle' });
    const label = STATUS[cmp[i][1]].label;
    await chip(s, x + 5.9 - 0.35 - (0.12 + 0.2 + 0.07 + textWidth(label, 13) + 0.16), 2.47, cmp[i][1], null, 13);
    text(s, cmp[i][2], x + 0.35, 3.0, 5.2, 0.9, { fontSize: 15 });
    for (let j = 0; j < 3; j++) {
      const sx = x + 0.35 + j * 1.75;
      text(s, cmp[i][3][j][0], sx, 3.95, 1.7, 0.6, { fontSize: 28, bold: true, color: i === 0 ? C.accent5 : C.accent2, valign: 'bottom' });
      text(s, cmp[i][3][j][1], sx, 4.6, 1.7, 0.3, { fontSize: 12, color: C.accent6 });
    }
  }
  await bareIcon(s, 'TriangleAlert', 0.6, 5.72, 0.36, HEX.accent3);
  text(s, '只有一組樣本，而且兩者完成的終點不同：不能宣稱記憶提升了品質或降低成本。', 1.1, 5.7, 11.6, 0.4, { fontSize: 16, bold: true, color: C.accent3, valign: 'middle' });
  text(s, '課程指定的 Google Cloud／ADC Gemini：LIVE_NOT_RUN（依組員選擇使用 OpenAI，不能拿來替代）。', 1.1, 6.18, 11.6, 0.36, { fontSize: 14, color: C.accent6, valign: 'middle' });

  // ===== 15. Next steps =====
  s = slide('CONTENT', '驗證與限制', '已完成、待證明與規劃', '下一步：把判讀結果接進草稿工具');
  const board = [
    ['CircleCheck', C.accent2, '已完成且已驗證', ['文字語意比對：LIVE_PASS', '補件工具流程：LIVE_PASS', 'Session 清除與跨人隔離']],
    ['Clock', C.accent3, '已實作，效果待證明', ['W6 評估後修訂：未證明改善', 'PDF 預檢：通過，業務預期 6／7', '來源 v2 僅離線；估分未校準']],
    ['Map', C.accent4, '規劃中（期末前）', ['P0　判讀結果接入草稿工具', 'P0　20 組教師標註案例', 'P1　掃描 PDF OCR、正式登入']],
  ];
  for (let i = 0; i < 3; i++) {
    const x = 0.6 + i * 4.14;
    card(s, x, 1.75, 3.85, 4.3, { fill: C.background2, line: false, shadow: false });
    await iconCircle(s, board[i][0], x + 0.25, 1.97, 0.5, board[i][1]);
    text(s, board[i][2], x + 0.88, 1.97, 2.9, 0.5, { fontSize: 17, bold: true, color: board[i][1], valign: 'middle' });
    for (let j = 0; j < 3; j++) {
      const y = 2.72 + j * 1.07;
      card(s, x + 0.22, y, 3.41, 0.9, { shadow: false, line: false });
      text(s, board[i][3][j], x + 0.4, y, 3.1, 0.9, { fontSize: 14, valign: 'middle' });
    }
  }
  await bareIcon(s, 'Target', 0.6, 6.3, 0.34, HEX.dk2);
  text(s, '驗收：20 組標註案例 · 跨人隔離 · 來源變更拒寫 · 可重現 trace，並分開報告正確率與拒答率。', 1.08, 6.28, 11.6, 0.4, { fontSize: 15, bold: true, valign: 'middle' });

  // ===== 16. Team & Q&A =====
  pres.addSection({ title: '結尾' });
  s = slide('CLOSING_DARK', '結尾', '團隊與後續', '分工與問答');
  const team = [['陳冠友', 'S11259039 · 隊長', '後端、工具確認、Session 記憶與 PDF 預檢示範'], ['林崇瑋', 'S11259031 · 隊員', '使用情境、來源引用、測試與失敗分析']];
  for (let i = 0; i < 2; i++) {
    const x = 0.6 + i * 6.23;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.8, w: 5.9, h: 2.25, rectRadius: 0.1, fill: { color: C.background1, transparency: 90 }, line: { color: C.background1, width: 1, transparency: 70 }, objectName: nm('member-card') });
    await iconCircle(s, 'User', x + 0.35, 2.1, 0.66, C.accent1, HEX.dk2);
    text(s, team[i][0], x + 1.25, 2.08, 3, 0.44, { fontSize: 24, bold: true, color: C.background1, valign: 'middle' });
    text(s, team[i][1], x + 1.25, 2.52, 3, 0.3, { fontSize: 13, color: C.background2 });
    text(s, '建議主講', x + 0.35, 3.05, 2, 0.3, { fontSize: 13, bold: true, color: C.accent1 });
    text(s, team[i][2], x + 0.35, 3.36, 5.3, 0.5, { fontSize: 16, color: C.background1 });
  }
  text(s, '以上是建議分工，實際貢獻待兩位確認；開發、測試與簡報製作有使用 AI 工具（Codex、Claude）協助。', 0.6, 4.3, 12.1, 0.36, { fontSize: 14, color: C.accent1 });
  const total = 12.13, segs = [[14, '簡報＋示範 14 分鐘', C.accent1, C.text2], [5, '問答 5 分鐘', C.background1, C.text2], [1, '緩衝', C.accent6, C.background1]];
  let bx = 0.6;
  for (const [min, lab, fill, ink] of segs) {
    const w = (total - 0.1) * min / 20;
    s.addShape(pres.shapes.RECTANGLE, { x: bx, y: 5.05, w, h: 0.62, fill: { color: fill }, line: { type: 'none' }, objectName: nm('time-seg') });
    if (min === 1) text(s, lab, bx, 5.05, w, 0.62, { fontSize: 12, bold: true, color: ink, align: 'center', valign: 'middle' });
    else text(s, lab, bx + 0.15, 5.05, w - 0.2, 0.62, { fontSize: 15, bold: true, color: ink, valign: 'middle' });
    bx += w + 0.05;
  }
  text(s, '共 20 分鐘', 10.73, 5.75, 2.0, 0.3, { fontSize: 12, color: C.background2, align: 'right' });
  text(s, '謝謝，歡迎提問', 0.6, 5.95, 8, 0.6, { fontSize: 26, bold: true, color: C.background1, valign: 'middle' });

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  // CJK text uses the theme's East Asian font slots, which pptxgenjs leaves empty / 新細明體.
  const zip = await JSZip.loadAsync(fs.readFileSync(OUT));
  for (const f of Object.keys(zip.files).filter((n) => /^ppt\/theme\/theme\d+\.xml$/.test(n))) {
    let xml = await zip.file(f).async('string');
    xml = xml.replace(/<a:ea typeface="[^"]*"\/>/g, `<a:ea typeface="${FONT}"/>`).replace(/(<a:font script="Hant" typeface=")[^"]*("\/>)/g, `$1${FONT}$2`);
    zip.file(f, xml);
  }
  fs.writeFileSync(OUT, await zip.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' }));
  if (slideIndex !== SCRIPT.SLIDES.length) throw new Error(`script has ${SCRIPT.SLIDES.length} entries for ${slideIndex} slides`);
  fs.writeFileSync(path.join(HERE, 'speaker-script.md'), SCRIPT.markdown());
  console.log('wrote', OUT, 'and speaker-script.md');
}

build().catch((e) => { console.error(e); process.exit(1); });
