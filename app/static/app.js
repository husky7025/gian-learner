"use strict";
// ───────── 공통 도우미 ─────────
const $ = (s) => document.querySelector(s);
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null) el.append(c instanceof Node ? c : String(c));
  return el;
}
async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers = { "Content-Type": "application/json" }; delete o.json; }
  const r = await fetch(path, o);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r;
}
const getJSON = async (p, o) => (await api(p, o)).json();
let toastTimer;
function toast(msg, err = false) {
  const t = $("#toast"); t.textContent = msg; t.className = err ? "err" : ""; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), err ? 6000 : 2500);
}
function autoGrow(ta) { ta.style.height = "auto"; ta.style.height = Math.max(34, ta.scrollHeight + 2) + "px"; }
const clone = (o) => JSON.parse(JSON.stringify(o));

// ───────── 번호 모양 (서버와 같은 규칙) ─────────
const KOR = "가나다라마바사아자차카타파하";
const CIRC = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳";
const CIRC_K = "㉮㉯㉰㉱㉲㉳㉴㉵㉶㉷㉸㉹㉺㉻";
const TYPES = ["num_dot", "kor_dot", "num_par", "kor_par", "num_ppar", "kor_ppar", "circ", "circ_k"];
function marker(type, n) {
  const k = KOR[(n - 1) % KOR.length];
  return { num_dot: `${n}.`, kor_dot: `${k}.`, num_par: `${n})`, kor_par: `${k})`, num_ppar: `(${n})`,
    kor_ppar: `(${k})`, circ: CIRC[(n - 1) % 20], circ_k: CIRC_K[(n - 1) % 14] }[type];
}
function markers(items, styles) {
  const counters = {}; const res = [];
  for (const it of items) {
    if ((it.kind || "item") !== "item") { res.push(""); continue; }
    const d = it.depth;
    for (const k of Object.keys(counters)) if (+k > d) delete counters[k];
    counters[d] = (counters[d] || 0) + 1;
    const type = (styles[String(d)] || {}).type || TYPES[Math.min(d, TYPES.length - 1)];
    res.push(marker(type, counters[d]));
  }
  return res;
}

// ───────── 상태 ─────────
let forms = [];
let curId = null;
let CATS = { gian: "기안", pumui: "품의", gatong: "가정통신문" };
let curCat = localStorage.getItem("gian-cat") || "gian";
let T = null;       // 서버의 템플릿 응답 {form, template, samples}
let S = null;       // 작성 중 내용 {filename, fields, outline, attach}
let curTab = "write";

const draftKey = () => `gian-draft-${curId}-${T && T.template.base_sample_id}-${T && T.template.sample_count}`;
function freshState() {
  const tpl = T.template; const st = { filename: "", fields: {}, outline: [], attach: [], cells: {} };
  for (const b of tpl.blocks) {
    if (b.type === "field") st.fields[b.id] = b.default || "";
    if (b.type === "outline") st.outline = clone(b.items);
    if (b.type === "attach") st.attach = clone(b.default);
  }
  return st;
}
function saveDraft() {
  if (!S || !curId) return;
  localStorage.setItem(draftKey(), JSON.stringify(S));
  $("#draftState").textContent = "임시저장됨 " + new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}
let changeTimer;
function changed() {
  clearTimeout(changeTimer);
  changeTimer = setTimeout(() => { saveDraft(); refreshPreview(); }, 350);
}

// ───────── 양식 목록 ─────────
async function loadForms() {
  forms = await getJSON("/api/forms");
  const tabs = $("#catTabs"); tabs.replaceChildren();
  for (const [key, label] of Object.entries(CATS)) {
    const n = forms.filter((f) => f.category === key).length;
    tabs.append(h("button", { class: key === curCat ? "active" : "", onclick: () => switchCat(key) }, label, h("small", {}, `양식 ${n}`)));
  }
  $("#newFormName").placeholder = `새 ${CATS[curCat]} 양식 이름`;
  const ul = $("#formList"); ul.replaceChildren();
  for (const f of forms.filter((x) => x.category === curCat)) {
    ul.append(h("li", { class: f.id === curId ? "active" : "", onclick: () => selectForm(f.id) },
      h("span", {}, f.name), h("span", { class: "cnt" }, `샘플 ${f.sample_count}`)));
  }
  if (!ul.children.length) ul.append(h("li", { class: "cnt" }, "이 분류에 양식이 없습니다"));
  $("#empty").hidden = !!curId; $("#workspace").hidden = !curId;
}
async function switchCat(key) {
  curCat = key; localStorage.setItem("gian-cat", key);
  const last = +localStorage.getItem(`gian-last-form-${key}`);
  const list = forms.filter((f) => f.category === key);
  const pick = list.find((f) => f.id === last) || list[0];
  if (pick) await selectForm(pick.id);
  else { curId = null; await loadForms(); }
}
async function selectForm(id, tab) {
  curId = id; localStorage.setItem("gian-last-form", id);
  const f = forms.find((x) => x.id === id);
  if (f) { curCat = f.category; localStorage.setItem("gian-cat", curCat); localStorage.setItem(`gian-last-form-${curCat}`, id); }
  await loadForms();
  await loadTemplate();
  showTab(tab || (T.template.ready ? "write" : "samples"));
}
async function loadTemplate() {
  T = await getJSON(`/api/forms/${curId}/template`);
  $("#formTitle").textContent = `${CATS[T.form.category] || ""} › ${T.form.name}`;
  $("#formCat").replaceChildren(...Object.entries(CATS).map(([k, v]) => h("option", { value: k, selected: k === T.form.category }, v + " 분류")));
  const n = $("#notice");
  if (T.template.similarity_warn) {
    n.hidden = false; n.className = "notice warn";
    n.textContent = `⚠ 올린 샘플들의 항목 구성이 많이 다릅니다 (비슷한 정도 ${Math.round(T.template.similarity * 100)}%). 서로 다른 종류의 기안이라면 양식을 나눠 학습하는 것이 좋습니다.`;
  } else n.hidden = true;
  if (T.template.ready) {
    const saved = localStorage.getItem(draftKey());
    S = saved ? JSON.parse(saved) : freshState();
    S.cells = S.cells || {};
    $("#draftState").textContent = saved ? "임시저장된 내용을 불러왔습니다" : "";
  } else S = null;
  renderAll();
}
function renderAll() {
  renderWrite(); renderLearn(); renderSamples();
  if (curTab === "history") renderHistory();
}
function showTab(tab) {
  curTab = tab;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  for (const t of ["write", "learn", "samples", "history"]) $(`#tab-${t}`).hidden = t !== tab;
  $("#tabHelp").href = "/help#" + tab;
  if (tab === "history") renderHistory();
  if (tab === "write") refreshPreview();
}

// ───────── 작성 탭 ─────────
function renderWrite() {
  const ready = T && T.template.ready;
  $("#writeNotReady").hidden = !!ready; $("#writeArea").hidden = !ready;
  if (!ready) return;
  $("#fileName").value = S.filename || "";
  const box = $("#blocks"); box.replaceChildren();
  for (const b of T.template.blocks) {
    if (b.type === "fixed" && b.object && tablesAt(b.src).length) box.append(h("div", {}, tablesAt(b.src).map((t) => tableGrid(t, "write"))));
    else if (b.type === "fixed") box.append(h("div", { class: "blk-fixed", title: "고정 부분 (학습 내용 탭에서 입력칸으로 바꿀 수 있습니다)" }, b.text || " "));
    else if (b.type === "field") box.append(fieldRow(b));
    else if (b.type === "outline") box.append(outlineEditor(b));
    else if (b.type === "attach") box.append(attachEditor(b));
  }
  box.querySelectorAll("textarea").forEach(autoGrow);
}
function fieldRow(b) {
  const ta = h("textarea", { rows: 1, placeholder: b.examples && b.examples.length ? "예) " + b.examples[0] : "",
    oninput: (e) => { S.fields[b.id] = e.target.value; autoGrow(e.target); changed(); } });
  ta.value = S.fields[b.id] ?? b.default ?? "";
  return h("div", { class: "blk-field" }, h("label", {}, b.label || "내용"), ta);
}
function outlineEditor(b) {
  const wrap = h("div", { class: "outline" });
  const styles = T.template.styles;
  const draw = () => {
    wrap.replaceChildren(h("div", { class: "section-title" }, "본문 항목",
      h("span", { class: "muted small" }, "번호는 자동으로 매겨집니다 · ⇤ ⇥ 로 단계 조절")));
    const mks = markers(S.outline, styles);
    S.outline.forEach((it, i) => wrap.append(outlineRow(it, i, mks[i], draw)));
    const add = (depth) => { S.outline.push({ kind: "item", depth, label: "", value: "" }); draw(); changed(); };
    const lastDepth = [...S.outline].reverse().find((x) => (x.kind || "item") === "item")?.depth ?? 0;
    wrap.append(h("div", { class: "chips" },
      h("button", { class: "small", onclick: () => add(lastDepth) }, "＋ 항목 추가"),
      h("button", { class: "small", onclick: () => add(Math.min(lastDepth + 1, 7)) }, "＋ 하위 항목"),
      h("button", { class: "small ghost", onclick: () => { S.outline.push({ kind: "para", indent: "  ", value: "" }); draw(); changed(); } }, "＋ 번호 없는 문단")));
    const used = new Set(S.outline.map((x) => (x.label || "").replace(/\s/g, "")));
    const sugg = (b.suggestions || []).filter((s) => !used.has(s.label.replace(/\s/g, "")));
    if (sugg.length) {
      wrap.append(h("div", { class: "chips" }, h("span", { class: "muted small" }, "다른 샘플의 항목:"),
        sugg.map((s) => h("button", { class: "chip", title: "예) " + s.example,
          onclick: () => { S.outline.push({ kind: "item", depth: s.depth, label: s.label, value: "", example: s.example }); draw(); changed(); } }, "＋ " + s.label))));
    }
    wrap.querySelectorAll("textarea").forEach(autoGrow);
  };
  draw();
  return wrap;
}
function outlineRow(it, i, mk, redraw) {
  const kind = it.kind || "item";
  const move = (delta) => { const j = i + delta; if (j < 0 || j >= S.outline.length) return;
    [S.outline[i], S.outline[j]] = [S.outline[j], S.outline[i]]; redraw(); changed(); };
  const ctl = h("div", { class: "ctl" },
    kind === "item" ? h("button", { title: "상위 단계로", onclick: () => { it.depth = Math.max(0, it.depth - 1); redraw(); changed(); } }, "⇤") : null,
    kind === "item" ? h("button", { title: "하위 단계로", onclick: () => { it.depth = Math.min(7, it.depth + 1); redraw(); changed(); } }, "⇥") : null,
    h("button", { title: "위로", onclick: () => move(-1) }, "↑"),
    h("button", { title: "아래로", onclick: () => move(1) }, "↓"),
    h("button", { title: "아래에 같은 단계 항목 추가", onclick: () => {
      S.outline.splice(i + 1, 0, kind === "item" ? { kind: "item", depth: it.depth, label: "", value: "" } : { kind: "para", indent: it.indent || "  ", value: "" });
      redraw(); changed(); } }, "＋"),
    h("button", { title: "삭제", onclick: () => { S.outline.splice(i, 1); redraw(); changed(); } }, "✕"));
  const indent = h("span", { style: `width:${(it.depth || 0) * 18}px;flex-shrink:0` });
  if (kind === "blank") return h("div", { class: "ol-row" }, h("span", { class: "mk" }), h("div", { class: "tag" }, "(빈 줄)"), ctl);
  if (kind === "object") {
    const tbs = tablesAt(it.src);
    return h("div", { class: "ol-row" }, h("span", { class: "mk" }),
      tbs.length ? h("div", { class: "tblwrap" }, tbs.map((t) => tableGrid(t, "write"))) : h("div", { class: "tag" }, "[그림 — 원본 그대로 들어갑니다]"), ctl);
  }
  const val = h("textarea", { class: "val", rows: 1,
    placeholder: it.example ? "예) " + it.example : (kind === "para" ? "문단 내용" : "내용"),
    oninput: (e) => { it.value = e.target.value; autoGrow(e.target); changed(); } });
  val.value = it.value || "";
  if (kind === "para") return h("div", { class: "ol-row" }, h("span", { class: "mk" }, "¶"), val, ctl);
  const lbl = h("input", { class: "lbl", placeholder: "제목(선택)", value: it.label || "",
    oninput: (e) => { it.label = e.target.value; changed(); } });
  return h("div", { class: "ol-row" }, indent, h("span", { class: "mk" }, mk), lbl, val, ctl);
}
function tablesAt(src) { return (T.template.tables || []).filter((t) => t.src === src); }
function tableGrid(t, mode, onToggle) {
  const tb = h("table", { class: "grid" + (mode === "learn" ? " learn" : "") });
  for (const row of t.rows) {
    const tr = h("tr");
    for (const c of row) {
      const td = h("td", { class: c.locked ? "fixed locked" : c.type, colspan: c.cs > 1 ? c.cs : null, rowspan: c.rs > 1 ? c.rs : null });
      if (mode === "write" && c.type === "field") {
        const ta = h("textarea", { rows: 1, placeholder: c.examples && c.examples[0] ? "예) " + c.examples[0] : "",
          oninput: (e) => { S.cells[c.key] = e.target.value; autoGrow(e.target); changed(); } });
        ta.value = S.cells[c.key] ?? c.default ?? "";
        td.append(ta);
      } else {
        td.append(c.text || " ");
        if (mode === "learn") {
          td.title = c.locked ? "안에 표·그림이 있어 바꿀 수 없습니다" : (c.type === "fixed" ? "누르면 입력칸으로" : "누르면 고정으로");
          if (!c.locked) td.addEventListener("click", () => onToggle(c));
        }
      }
      tr.append(td);
    }
    tb.append(tr);
  }
  return tb;
}
function attachEditor(b) {
  const wrap = h("div", { class: "attach" });
  const draw = () => {
    wrap.replaceChildren(h("div", { class: "section-title" }, "붙임",
      h("span", { class: "muted small" }, T.template.uses_end ? "마지막에 「끝.」이 자동으로 붙습니다" : "")));
    S.attach.forEach((x, i) => {
      const inp = h("input", { value: x, placeholder: "예) 견적서 1부", oninput: (e) => { S.attach[i] = e.target.value; changed(); } });
      wrap.append(h("div", { class: "att-row" }, h("span", {}, S.attach.length > 1 ? `${i + 1}.` : ""), inp,
        h("button", { class: "small", onclick: () => { S.attach.splice(i, 1); draw(); changed(); } }, "✕")));
    });
    const chips = (b.examples || []).filter((x) => !S.attach.includes(x));
    wrap.append(h("div", { class: "chips" },
      h("button", { class: "small", onclick: () => { S.attach.push(""); draw(); changed(); } }, "＋ 붙임 추가"),
      chips.map((x) => h("button", { class: "chip", onclick: () => { S.attach.push(x); draw(); changed(); } }, "＋ " + x))));
  };
  draw();
  return wrap;
}
let previewSeq = 0;
async function refreshPreview() {
  if (!S || !T || !T.template.ready) return;
  const seq = ++previewSeq;
  try {
    const r = await getJSON(`/api/forms/${curId}/preview`, { method: "POST", json: payload(false) });
    if (seq === previewSeq) $("#preview").textContent = r.lines.join("\n");
  } catch (e) { $("#preview").textContent = "미리보기 오류: " + e.message; }
}
function guessName() {
  if (S.filename.trim()) return S.filename.trim();
  for (const b of T.template.blocks) if (b.type === "field" && /제목|건명/.test(b.label) && S.fields[b.id]) return S.fields[b.id];
  const it = S.outline.find((x) => /건명|제목/.test(x.label || "") && x.value);
  return it ? it.value : T.form.name;
}
function payload(save = true) {
  return { filename: guessName(), fields: S.fields, outline: S.outline, attach: S.attach, cells: S.cells || {}, save_history: save };
}
async function generate() {
  const btn = $("#generate"); btn.disabled = true;
  try {
    const r = await api(`/api/forms/${curId}/generate`, { method: "POST", json: payload(true) });
    const blob = await r.blob();
    const cd = r.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename\*=UTF-8''([^;]+)/);
    const name = m ? decodeURIComponent(m[1]) : "기안.hwpx";
    const a = h("a", { href: URL.createObjectURL(blob), download: name });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    toast(`「${name}」을(를) 만들었습니다. 다운로드 폴더를 확인하세요.`);
  } catch (e) { toast(e.message, true); }
  finally { btn.disabled = false; }
}

// ───────── 학습 내용 탭 ─────────
function renderLearn() {
  const area = $("#learnArea"); area.replaceChildren();
  const tpl = T.template;
  if (!tpl.ready) { area.append(h("div", { class: "empty small" }, "샘플을 올리면 학습 결과가 여기에 표시됩니다.")); return; }
  const ov = { lines: { ...(T.form.overrides.lines || {}) }, base_sample_id: T.form.overrides.base_sample_id ?? null };
  const save = async () => {
    try { await api(`/api/forms/${curId}/overrides`, { method: "PUT", json: ov }); await loadTemplate(); toast("학습 설정을 바꿨습니다."); }
    catch (e) { toast(e.message, true); }
  };
  const sel = h("select", { onchange: (e) => { ov.base_sample_id = e.target.value ? +e.target.value : null; save(); } },
    h("option", { value: "" }, "자동 선택"),
    T.samples.map((s) => h("option", { value: s.id, selected: ov.base_sample_id === s.id }, s.filename)));
  const base = T.samples.find((s) => s.id === tpl.base_sample_id);
  area.append(h("div", { class: "card" },
    h("h3", {}, "요약"),
    h("p", {}, `샘플 ${tpl.sample_count}개를 비교해 학습했습니다. 서식(글꼴·문단 모양·여백)은 기준 샘플 「${base ? base.filename : ""}」을 그대로 따릅니다.`),
    h("p", {}, "기준 샘플: ", sel),
    tpl.sample_count === 1 ? h("p", { class: "muted small" }, "샘플이 1개라 내용을 모두 기본값으로 채워 두었습니다. 같은 양식의 샘플을 더 올리면 바뀌는 부분이 자동으로 빈칸이 됩니다.") : null));

  const lineCard = (title, region) => {
    const blocks = tpl.blocks.filter((b) => (b.type === "fixed" || b.type === "field") && b.id[0] === region);
    if (!blocks.length) return null;
    return h("div", { class: "card" }, h("h3", {}, title),
      h("div", { class: "legend" }, h("span", { class: "lf" }, "고정 (그대로 들어감)"), h("span", { class: "li" }, "입력칸 (작성 탭에서 입력)")),
      blocks.map((b) => {
        const canToggle = !b.object && (b.text || "").trim();
        const btn = canToggle ? h("button", { onclick: () => {
          ov.lines[b.id] = b.type === "fixed" ? "field" : "fixed"; save(); } }, b.type === "fixed" ? "입력칸으로" : "고정으로") : null;
        return h("div", { class: `ln ${b.type}` }, h("span", { class: "txt" }, b.text || " "), btn);
      }));
  };
  area.append(lineCard("머리 부분", "h") || "");
  const ol = tpl.blocks.find((b) => b.type === "outline");
  if (ol) {
    const mks = markers(ol.items, tpl.styles);
    area.append(h("div", { class: "card" }, h("h3", {}, "본문 항목 (기본 구성)"),
      h("table", { class: "items" }, h("tr", {}, h("th", {}, "번호"), h("th", {}, "제목"), h("th", {}, "기본값"), h("th", {}, "샘플 예시")),
        ol.items.map((it, i) => h("tr", {},
          h("td", {}, " ".repeat((it.depth || 0) * 3) + (mks[i] || (it.kind === "para" ? "¶" : ""))),
          h("td", {}, it.label || (it.kind === "object" ? "[표·그림]" : it.kind === "blank" ? "(빈 줄)" : "")),
          h("td", {}, it.value || h("span", { class: "muted" }, "(빈칸)")),
          h("td", { class: "muted" }, (it.examples || [it.example || ""]).join(" / "))))),
      ol.suggestions.length ? h("p", { class: "muted small" }, "다른 샘플에만 있는 항목: " + ol.suggestions.map((s) => s.label).join(", ")) : null));
    const at = tpl.blocks.find((b) => b.type === "attach");
    if (at) area.append(h("div", { class: "card" }, h("h3", {}, "붙임"),
      h("p", {}, at.default.length ? "기본: " + at.default.join(", ") : "기본 붙임 없음"),
      at.examples.length ? h("p", { class: "muted small" }, "샘플에 나온 붙임: " + at.examples.join(", ")) : null));
  }
  area.append(lineCard("꼬리 부분", "f") || "");
  if ((tpl.tables || []).length) {
    area.append(h("div", { class: "card" }, h("h3", {}, "표"),
      h("div", { class: "legend" }, h("span", { class: "lf" }, "고정 칸"), h("span", { class: "li" }, "입력칸"),
        h("span", { class: "muted" }, "칸을 누르면 고정 ↔ 입력칸이 바뀝니다")),
      tpl.tables.map((t) => h("div", {}, h("p", { class: "muted small" }, `표 ${t.gti + 1}`),
        tableGrid(t, "learn", (c) => { ov.lines[c.key] = c.type === "fixed" ? "field" : "fixed"; save(); })))));
  }
}

// ───────── 샘플 탭 ─────────
function renderSamples() {
  $("#samplesStart").hidden = !(T.samples.length === 0 && !$("#packDefault").hidden);
  const ul = $("#sampleList"); ul.replaceChildren();
  if (!T.samples.length) ul.append(h("li", { class: "empty-row" }, "아직 올린 샘플이 없습니다"));
  for (const s of T.samples) {
    ul.append(h("li", {},
      h("span", { class: "grow", title: s.filename }, "📄 " + s.filename),
      s.id === T.template.base_sample_id ? h("span", { class: "badge" }, "기준 서식") : null,
      h("span", { class: "muted small" }, s.created),
      h("a", { class: "btn small", href: `/api/forms/${curId}/samples/${s.id}/download` }, "받기"),
      h("button", { class: "small", onclick: async () => {
        if (!confirm(`「${s.filename}」 샘플을 빼고 다시 학습할까요?`)) return;
        try { await api(`/api/forms/${curId}/samples/${s.id}`, { method: "DELETE" }); await loadForms(); await loadTemplate(); toast("샘플을 뺐습니다."); }
        catch (e) { toast(e.message, true); } } }, "빼기")));
  }
}
async function upload(files) {
  const packs = files.filter((f) => /\.gianpack$/i.test(f.name));
  for (const p of packs) await importPack(p);
  files = files.filter((f) => !/\.gianpack$/i.test(f.name));
  if (!files.length || !curId) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const msg = $("#uploadMsg"); msg.replaceChildren(h("p", { class: "muted" }, "분석하는 중…"));
  try {
    const r = await getJSON(`/api/forms/${curId}/samples`, { method: "POST", body: fd });
    msg.replaceChildren(
      r.added.length ? h("p", { class: "ok" }, `✔ ${r.added.length}개를 학습했습니다.`) : null,
      r.converted && r.converted.length ? h("p", { class: "muted small" }, `ℹ ${r.converted.length}개는 글자·번호 구조만 읽어 기본 서식으로 바꿨습니다: ${r.converted.join(", ")}`) : null,
      ...r.errors.map((e) => h("p", { class: "err" }, "✖ " + e)));
    await loadForms(); await loadTemplate();
  } catch (e) { msg.replaceChildren(h("p", { class: "err" }, "✖ " + e.message)); }
}

// ───────── 이력 탭 ─────────
async function renderHistory() {
  const ul = $("#historyList"); ul.replaceChildren(h("li", { class: "empty-row" }, "불러오는 중…"));
  const list = await getJSON(`/api/forms/${curId}/history`);
  ul.replaceChildren();
  if (!list.length) ul.append(h("li", { class: "empty-row" }, "아직 만든 파일이 없습니다"));
  for (const it of list) {
    ul.append(h("li", {},
      h("span", { class: "grow", title: it.filename }, "📄 " + it.filename),
      h("span", { class: "muted small" }, it.created),
      h("a", { class: "btn small", href: `/api/history/${it.id}/download` }, "다시 받기"),
      h("button", { class: "small", title: "이 내용을 작성 탭으로 불러옵니다", onclick: () => {
        if (!T.template.ready) return toast("먼저 샘플을 올려 주세요.", true);
        const p = it.payload;
        S = { filename: "", fields: { ...freshState().fields, ...p.fields }, outline: p.outline, attach: p.attach, cells: p.cells || {} };
        saveDraft(); renderWrite(); showTab("write"); toast("이전 내용을 불러왔습니다. 필요한 부분만 고쳐 쓰세요.");
      } }, "불러오기"),
      h("button", { class: "small", onclick: async () => {
        if (!confirm("이 기록을 지울까요?")) return;
        await api(`/api/history/${it.id}`, { method: "DELETE" }); renderHistory(); } }, "✕")));
  }
}

// ───────── 설정(백업·전체 초기화) ─────────
async function openSettings() {
  const info = await getJSON("/api/info");
  $("#dataDir").textContent = info.data_dir;
  getJSON("/api/system").then(showSys).catch(() => {});
  renderPackForms();
  const ul = $("#backupList"); ul.replaceChildren();
  const list = await getJSON("/api/backups");
  if (!list.length) ul.append(h("li", { class: "empty-row" }, "백업이 없습니다"));
  for (const b of list) {
    ul.append(h("li", {}, h("span", { class: "grow" }, `${b.created} · ${b.reason}`),
      h("button", { type: "button", class: "small", onclick: async () => {
        if (!confirm(`${b.created} 상태로 되돌릴까요?\n(지금 상태도 자동으로 백업됩니다)`)) return;
        try { await api(`/api/backups/${encodeURIComponent(b.name)}/restore`, { method: "POST" });
          curId = null; $("#settings").close(); await init(); toast("되돌렸습니다."); }
        catch (e) { toast(e.message, true); } } }, "이 상태로 되돌리기")));
  }
  $("#settings").showModal();
}

// ───────── 이벤트 연결 ─────────
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
$("#newForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("#newFormName").value.trim();
  if (!name) return toast("양식 이름을 입력해 주세요.", true);
  try { const r = await getJSON("/api/forms", { method: "POST", json: { name, category: curCat } }); $("#newFormName").value = ""; await selectForm(r.id, "samples"); }
  catch (err) { toast(err.message, true); }
});
$("#renameForm").addEventListener("click", async () => {
  const name = prompt("새 양식 이름", T.form.name);
  if (!name || !name.trim()) return;
  try { await api(`/api/forms/${curId}`, { method: "PATCH", json: { name } }); await loadForms(); await loadTemplate(); }
  catch (e) { toast(e.message, true); }
});
$("#formCat").addEventListener("change", async (e) => {
  try { await api(`/api/forms/${curId}/category`, { method: "PUT", json: { category: e.target.value } });
    await selectForm(curId, curTab); toast(`「${CATS[e.target.value]}」 분류로 옮겼습니다.`); }
  catch (err) { toast(err.message, true); }
});
$("#fileName").addEventListener("input", (e) => { S.filename = e.target.value; changed(); });
$("#generate").addEventListener("click", generate);
$("#resetDraft").addEventListener("click", () => {
  if (!confirm("작성 중인 내용을 지우고 학습된 처음 상태로 돌릴까요?")) return;
  S = freshState(); localStorage.removeItem(draftKey()); $("#draftState").textContent = ""; renderWrite(); refreshPreview();
});
$("#fillExamples").addEventListener("click", () => {
  for (const b of T.template.blocks) if (b.type === "field" && !S.fields[b.id] && b.examples && b.examples[0]) S.fields[b.id] = b.examples[0];
  for (const it of S.outline) if (!it.value && it.example) it.value = it.example;
  renderWrite(); changed();
});
$("#fileInput").addEventListener("change", (e) => { upload([...e.target.files]); e.target.value = ""; });
const drop = $("#drop");
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => upload([...e.dataTransfer.files]));
$("#resetForm").addEventListener("click", async () => {
  if (!confirm(`「${T.form.name}」의 학습 내용(샘플 ${T.samples.length}개, 학습 설정)을 초기화할까요?\n직전 상태는 자동 백업되어 ⚙ 메뉴에서 되돌릴 수 있습니다.`)) return;
  try { await api(`/api/forms/${curId}/reset`, { method: "POST" }); localStorage.removeItem(draftKey()); await loadForms(); await loadTemplate(); showTab("samples"); toast("초기화했습니다."); }
  catch (e) { toast(e.message, true); }
});
$("#deleteForm").addEventListener("click", async () => {
  if (!confirm(`「${T.form.name}」 양식을 삭제할까요? (샘플과 생성 이력 포함, 직전 상태는 백업됩니다)`)) return;
  try { await api(`/api/forms/${curId}`, { method: "DELETE" }); curId = null; localStorage.removeItem("gian-last-form"); await loadForms(); toast("삭제했습니다."); }
  catch (e) { toast(e.message, true); }
});
$("#openSettings").addEventListener("click", () => openSettings().catch((e) => toast(e.message, true)));
$("#resetAll").addEventListener("click", async () => {
  const ok = prompt("모든 양식·샘플·이력을 지웁니다. 계속하려면 「초기화」라고 입력하세요.");
  if (ok !== "초기화") return;
  try { await api("/api/reset-all", { method: "POST" }); curId = null; localStorage.clear(); $("#settings").close(); await init(); toast("전체 초기화했습니다. (직전 상태는 백업됨)"); }
  catch (e) { toast(e.message, true); }
});

// ───────── 양식 꾸러미 ─────────
async function importPack(file) {
  const fd = new FormData(); fd.append("file", file);
  try {
    const r = await getJSON("/api/packs/import", { method: "POST", body: fd });
    await afterImport(r.imported, `「${file.name}」`);
  } catch (e) { toast(e.message, true); }
}
async function afterImport(list, what) {
  toast(`${what}에서 양식 ${list.length}개를 가져왔습니다: ` + list.map((x) => `${CATS[x.category]}›${x.name}`).join(", "));
  if ($("#settings").open) $("#settings").close();
  if (list.length) await selectForm(list[0].id, "write"); else await loadForms();
}
async function importDefault() {
  try { const r = await getJSON("/api/packs/import-default", { method: "POST" }); await afterImport(r.imported, "기본 양식 꾸러미"); }
  catch (e) { toast(e.message, true); }
}
function renderPackForms() {
  const box = $("#packForms"); box.replaceChildren(); $("#packResult").replaceChildren();
  for (const [key, label] of Object.entries(CATS)) {
    const list = forms.filter((f) => f.category === key && f.sample_count > 0);
    if (!list.length) continue;
    box.append(h("div", { class: "cat" }, label));
    for (const f of list) box.append(h("label", {}, h("input", { type: "checkbox", value: f.id, checked: f.id === curId }), ` ${f.name} (샘플 ${f.sample_count})`));
  }
  if (!box.children.length) box.append(h("p", { class: "muted small" }, "샘플이 있는 양식이 없습니다."));
}
const packIds = () => [...document.querySelectorAll("#packForms input:checked")].map((x) => +x.value);
$("#packScan").addEventListener("click", async () => {
  const ids = packIds(); const out = $("#packResult");
  if (!ids.length) return toast("내보낼 양식을 골라 주세요.", true);
  out.replaceChildren(h("p", { class: "muted" }, "검사하는 중…"));
  try {
    const res = await getJSON("/api/packs/scan", { method: "POST", json: { form_ids: ids } });
    const total = res.reduce((n, f) => n + f.findings.length, 0);
    out.replaceChildren(total
      ? h("p", { class: "warnmsg" }, `⚠ 개인정보로 보이는 글자 ${total}건을 찾았습니다. 이 내용이 그대로 꾸러미에 들어갑니다.`)
      : h("p", { class: "okmsg" }, "✔ 개인정보로 보이는 글자를 찾지 못했습니다. (자동 검사라 완벽하지 않으니 한 번 더 확인해 주세요)"));
    for (const f of res) for (const it of f.findings)
      out.append(h("div", { class: "find" }, `[${f.category}›${f.form}] ${it.sample} · ${it.kind}: `, h("b", {}, it.value), h("span", { class: "muted" }, `  — ${it.context}`)));
    if (total) out.append(h("p", { class: "muted small" }, "지우려면 샘플을 한글에서 고쳐 저장한 뒤, 샘플 탭에서 기존 샘플을 빼고 다시 올려 주세요."));
    out.append(h("button", { type: "button", class: total ? "danger" : "primary", onclick: () => exportPack(ids) },
      total ? "확인했습니다. 그대로 내보내기" : "📤 내보내기"));
  } catch (e) { out.replaceChildren(h("p", { class: "warnmsg" }, e.message)); }
});
async function exportPack(ids) {
  try {
    const r = await api("/api/packs/export", { method: "POST", json: { form_ids: ids } });
    const blob = await r.blob();
    const m = (r.headers.get("Content-Disposition") || "").match(/filename\*=UTF-8''([^;]+)/);
    const a = h("a", { href: URL.createObjectURL(blob), download: m ? decodeURIComponent(m[1]) : "양식 꾸러미.gianpack" });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    toast("꾸러미를 만들었습니다. 다운로드 폴더를 확인하세요.");
  } catch (e) { toast(e.message, true); }
}
$("#packFile").addEventListener("change", (e) => { if (e.target.files[0]) importPack(e.target.files[0]); e.target.value = ""; });
$("#packDefault").addEventListener("click", importDefault);
$("#welcomeDefault").addEventListener("click", importDefault);
$("#samplesDefault").addEventListener("click", importDefault);

function showSys(st) {
  $("#desktopState").textContent = st.desktop ? "✔ 바탕화면에 있습니다" : "";
  $("#autostart").checked = !!st.autostart;
}
$("#mkDesktop").addEventListener("click", async () => {
  try { showSys(await getJSON("/api/system/desktop-shortcut", { method: "POST" })); toast("바탕화면에 「기안 학습기」 바로가기를 만들었습니다."); }
  catch (e) { toast(e.message, true); }
});
$("#autostart").addEventListener("change", async (e) => {
  try {
    showSys(await getJSON("/api/system/autostart", { method: "POST", json: { enable: e.target.checked } }));
    toast(e.target.checked ? "컴퓨터를 켜면 자동으로 실행됩니다." : "자동 실행을 껐습니다.");
  } catch (err) { e.target.checked = !e.target.checked; toast(err.message, true); }
});
$("#shutdown").addEventListener("click", async () => {
  if (!confirm("앱을 종료할까요? (학습 내용은 그대로 저장되어 있습니다)")) return;
  try { await api("/api/shutdown", { method: "POST" }); } catch (_) {}
  document.body.replaceChildren(h("div", { class: "empty" }, h("h1", {}, "앱을 종료했습니다"),
    h("p", {}, "다시 쓰려면 바탕화면의 「기안 학습기」 바로가기나 「기안학습기 실행.bat」을 여세요. 이 탭은 닫아도 됩니다.")));
});

// ───────── 입력 도우미 ─────────
let lastField = null;
document.addEventListener("focusin", (e) => {
  if (e.target.closest && e.target.closest("#blocks") && /^(TEXTAREA|INPUT)$/.test(e.target.tagName)) lastField = e.target;
});
function insertText(text) {
  const el = lastField;
  if (!el || !document.contains(el)) return toast("먼저 내용을 넣을 칸을 한 번 클릭하세요.", true);
  const a = el.selectionStart ?? el.value.length, b = el.selectionEnd ?? a;
  el.setRangeText(text, a, b, "end");
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.focus();
}
function fmtDate(d) { return `${d.getFullYear()}. ${d.getMonth() + 1}. ${d.getDate()}.(${"일월화수목금토"[d.getDay()]})`; }
function korMoney(n) {
  if (n === 0) return "영";
  const D = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"], SM = ["천", "백", "십", ""], BIG = ["", "만", "억", "조", "경"];
  let s = "", g = 0;
  while (n > 0) {
    const part = n % 10000; n = Math.floor(n / 10000);
    if (part) {
      const ds = String(part).padStart(4, "0");
      let t = "";
      for (let i = 0; i < 4; i++) if (ds[i] !== "0") t += D[+ds[i]] + SM[i];
      s = t + BIG[g] + s;
    }
    g++;
  }
  return s;
}
$("#insDate").addEventListener("click", () => {
  const v = $("#helpDate").value;
  if (!v) return toast("날짜를 먼저 고르세요.", true);
  const [y, m, d] = v.split("-").map(Number);
  insertText(fmtDate(new Date(y, m - 1, d)));
});
$("#insToday").addEventListener("click", () => insertText(fmtDate(new Date())));
$("#insMoney").addEventListener("click", () => {
  const n = Number(($("#helpMoney").value || "").replace(/[^0-9]/g, ""));
  if (!n) return toast("금액을 숫자로 입력하세요.", true);
  if (n > Number.MAX_SAFE_INTEGER) return toast("금액이 너무 큽니다.", true);
  insertText(`금${n.toLocaleString("ko-KR")}원(금${korMoney(n)}원)`);
});

async function init() {
  try { const info = await getJSON("/api/info"); if (info.categories) CATS = info.categories; $("#appVer").textContent = "v" + info.version; } catch (_) {}
  try {
    const d = await getJSON("/api/packs/default");
    $("#packDefault").hidden = !d.available;
    const forms0 = await getJSON("/api/forms");
    $("#welcomePack").hidden = !d.available || forms0.some((f) => f.sample_count > 0);
  } catch (_) {}
  if (!CATS[curCat]) curCat = "gian";
  await loadForms();
  const last = +localStorage.getItem("gian-last-form");
  const fresh = !forms.some((f) => f.sample_count > 0);
  if (!curId && last && forms.some((f) => f.id === last) && !fresh) await selectForm(last);
  else if (!curId && !fresh) await switchCat(curCat);
  // 처음 쓰는 경우(학습된 양식이 하나도 없음)에는 환영 화면을 보여 준다
}
init().catch((e) => toast("서버에 연결할 수 없습니다: " + e.message, true));
