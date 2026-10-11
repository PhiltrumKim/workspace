// GHOST 시나리오 편집기 — 프레임워크 없는 단일 스크립트
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const h = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "html") e.innerHTML = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
};

async function api(method, path, body) {
  const r = await fetch(path, { method, headers: { "Content-Type": "application/json" },
                                body: body === undefined ? undefined : JSON.stringify(body) });
  const data = r.headers.get("Content-Type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error(data?.error || `HTTP ${r.status}`);
  return data;
}

// ---------------------------------------------------------------- 상태
const S = {
  state: null, targets: [], scenarios: [],
  scen: { name: "", description: "", steps: [] }, extra: {},   // extra: watch, on_abort 등 폼 밖의 키
  live: true, mode: "view", img: new Image(), imgW: 1920, imgH: 1080,
  overlay: [], drag: null, pick: null, logSeq: 0,
  editPath: null, stepResults: {}, runPoll: null, dirty: false, runningIdx: null,
  paramRows: [],                                              // [{name, default, description}]
};

// ---------------------------------------------------------------- 동작 정의 (스텝 폼)
const ACTIONS = {
  click:       { label: "클릭", fields: ["target", "timeout", "expect", "retry", "label"] },
  double:      { label: "더블클릭", fields: ["target", "timeout", "expect", "retry", "label"] },
  right_click: { label: "우클릭", fields: ["target", "timeout", "expect", "retry", "label"] },
  move:        { label: "커서 이동", fields: ["target", "timeout", "label"] },
  type:        { label: "글자 입력", fields: ["text", "expect", "label"] },
  key:         { label: "키 누르기", fields: ["key", "expect", "retry", "label"] },
  hotkey:      { label: "조합키", fields: ["keys", "expect", "retry", "label"] },
  wait:        { label: "대기", fields: ["sec", "label"] },
  wait_for:    { label: "나타날 때까지 대기", fields: ["target_only", "timeout", "label"] },
  wait_gone:   { label: "사라질 때까지 대기", fields: ["target_only", "timeout", "label"] },
  expect:      { label: "화면 확인", fields: ["target_only", "timeout", "label"] },
  read:        { label: "글자·수치 읽기", fields: ["name", "region", "pattern", "range", "vote", "label"] },
  screenshot:  { label: "화면 저장", fields: ["label"] },
  call:        { label: "다른 시나리오 실행", fields: ["scenario", "args", "label"] },
  home:        { label: "커서 원점 재설정", fields: ["label"] },
  set:         { label: "변수 설정", fields: ["setv", "label"] },
  if:          { label: "조건 분기 (만약)", fields: ["cond", "label"] },
  repeat:      { label: "N번 반복", fields: ["times", "var", "label"] },
  for_each:    { label: "목록 항목마다 반복", fields: ["items", "var", "label"] },
  while:       { label: "조건이 맞는 동안 반복", fields: ["cond", "max", "var", "label"] },
  break:       { label: "반복 빠져나가기", fields: ["label"] },
  continue:    { label: "다음 회차로 건너뛰기", fields: ["label"] },
  fail:        { label: "실패로 처리", fields: ["message", "label"] },
};
const ACTION_GROUPS = [
  ["조작", ["click", "double", "right_click", "move", "type", "key", "hotkey"]],
  ["대기·확인", ["wait", "wait_for", "wait_gone", "expect"]],
  ["읽기·기록", ["read", "screenshot"]],
  ["흐름 제어", ["if", "for_each", "repeat", "while", "set", "break", "continue", "fail", "call"]],
  ["기타", ["home"]],
];
const CHILD_KEYS = {
  if: [["then", "그러면 (조건이 맞을 때)"], ["else", "아니면 (조건이 안 맞을 때)"]],
  repeat: [["steps", "반복할 스텝"]], for_each: [["steps", "항목마다 실행할 스텝"]], while: [["steps", "조건이 맞는 동안 실행할 스텝"]],
};
const VAR_DEFAULT = { repeat: "i", while: "i", for_each: "item" };
const POINTER = ["click", "double", "right_click", "move"];

function tname(t) { return typeof t === "string" ? t : t && t.text !== undefined ? `"${t.text}"` : "?"; }

function condText(c) {
  if (!c || typeof c !== "object") return "?";
  if ("expr" in c) return c.expr;
  if ("visible" in c) return `${tname(c.visible)} 보이면${c.timeout ? ` (${c.timeout}초까지)` : ""}`;
  if ("gone" in c) return `${tname(c.gone)} 없으면`;
  if ("not" in c) return `아님(${condText(c.not)})`;
  if ("all" in c) return c.all.map(condText).join(" 그리고 ");
  if ("any" in c) return c.any.map(condText).join(" 또는 ");
  return "?";
}

function summary(st) {
  const a = st.action;
  const bits = [];
  if (POINTER.includes(a)) bits.push(st.target !== undefined ? tname(st.target) : `(${st.x}, ${st.y})`);
  if (["wait_for", "wait_gone", "expect"].includes(a)) bits.push(tname(st.target));
  if (a === "type") bits.push(`"${st.text}"`);
  if (a === "key") bits.push(st.key);
  if (a === "hotkey") bits.push((st.keys || []).join("+"));
  if (a === "wait") bits.push(`${st.sec}초`);
  if (a === "read") bits.push(`${st.name || "value"} ← ${st.region ? "[" + st.region.join(",") + "]" : st.anchor ? tname(st.anchor) + " 기준" : ""}${st.vote ? " · 다수결" : ""}`);
  if (a === "call") bits.push(st.scenario + (st.args && Object.keys(st.args).length ? ` (${Object.entries(st.args).map(([k, v]) => `${k}=${v}`).join(", ")})` : ""));
  if (a === "set") bits.push(`${st.name} = ${st.expr !== undefined ? st.expr : JSON.stringify(st.value)}`);
  if (a === "if" || a === "while") bits.push(condText(st.cond));
  if (a === "repeat") bits.push(`${st.times}번 (변수 ${st.var || "i"})`);
  if (a === "for_each") bits.push(`${st.var || "item"} ← ${Array.isArray(st.items) ? st.items.join(", ") : st.items}`);
  if (a === "while" && st.max) bits.push(`최대 ${st.max}회`);
  if (a === "fail" && st.message) bits.push(st.message);
  if (st.timeout !== undefined && a !== "wait") bits.push(`최대 ${st.timeout}초`);
  if (st.expect) bits.push(`확인: ${tname(st.expect.visible ?? st.expect.gone)} ${"gone" in st.expect ? "사라짐" : "표시"}`);
  if (st.retry) bits.push(`재시도 ${st.retry}`);
  return bits.join(" · ");
}

// ---------------------------------------------------------------- 화면
const canvas = $("#screen");
const ctx = canvas.getContext("2d");

function fitCanvas() {
  const wrap = $("#canvas-wrap");
  const ratio = S.imgW / S.imgH;
  let w = wrap.clientWidth, hgt = w / ratio;
  if (hgt > wrap.clientHeight) { hgt = wrap.clientHeight; w = hgt * ratio; }
  canvas.style.width = `${Math.floor(w)}px`;
  canvas.style.height = `${Math.floor(hgt)}px`;
}

function draw() {
  if (!S.img.complete || !S.img.naturalWidth) return;
  if (canvas.width !== S.imgW || canvas.height !== S.imgH) { canvas.width = S.imgW; canvas.height = S.imgH; fitCanvas(); }
  ctx.drawImage(S.img, 0, 0, S.imgW, S.imgH);
  const lw = Math.max(2, S.imgW / 640);
  ctx.font = `${Math.max(14, S.imgW / 90)}px sans-serif`;
  for (const o of S.overlay) {
    const [x, y, w, hh] = o.box;
    ctx.lineWidth = lw; ctx.strokeStyle = o.color; ctx.strokeRect(x, y, w, hh);
    if (o.label) {
      const tw = ctx.measureText(o.label).width + 10;
      ctx.fillStyle = o.color; ctx.fillRect(x, Math.max(0, y - 24), tw, 22);
      ctx.fillStyle = "#fff"; ctx.fillText(o.label, x + 5, Math.max(16, y - 7));
    }
  }
  if (S.drag && S.drag.w) {
    ctx.setLineDash([8, 5]); ctx.lineWidth = lw; ctx.strokeStyle = "#ffb020";
    ctx.strokeRect(S.drag.x, S.drag.y, S.drag.w, S.drag.h); ctx.setLineDash([]);
  }
  if (S.state) {                                  // 엔진이 알고 있는 커서 위치
    const [cx, cy] = S.state.cursor;
    ctx.strokeStyle = "#ff3d7f"; ctx.lineWidth = lw;
    ctx.beginPath(); ctx.arc(cx, cy, 10, 0, Math.PI * 2); ctx.stroke();
  }
}

function loadFrame() {
  if (!S.live) return;
  const im = new Image();
  im.onload = () => { S.img = im; S.imgW = S.state?.width || im.naturalWidth * 2; S.imgH = S.state?.height || im.naturalHeight * 2; draw(); setTimeout(loadFrame, 350); };
  im.onerror = () => setTimeout(loadFrame, 1500);
  im.src = `/api/frame.jpg?scale=0.5&t=${Date.now()}`;
}

function setLive(on) {
  S.live = on;
  $("#btn-live").classList.toggle("on", on);
  $("#btn-snap").classList.toggle("on", !on);
  if (on) loadFrame();
}

async function snapshot() {
  await api("POST", "/api/snapshot");
  setLive(false);
  await new Promise((res) => {
    const im = new Image();
    im.onload = () => { S.img = im; S.imgW = im.naturalWidth; S.imgH = im.naturalHeight; draw(); res(); };
    im.src = `/api/snapshot.jpg?t=${Date.now()}`;
  });
}

const MODE_HINT = {
  view: "화면을 보기만 합니다.",
  select: "등록할 버튼이나 글자 영역을 드래그하세요. (화면이 고정됩니다)",
  control: "클릭이 장비에 실제로 들어갑니다. 원하는 화면으로 이동할 때 쓰세요.",
};
function setMode(m) {
  S.mode = m;
  $$(".toolbar [data-mode]").forEach((b) => b.classList.toggle("on", b.dataset.mode === m));
  canvas.className = m;
  $("#mode-hint").textContent = MODE_HINT[m];
  $("#control-bar").hidden = m !== "control";
  if (m === "select" && S.live) snapshot();
}

function toFrame(e) {
  const r = canvas.getBoundingClientRect();
  return { x: Math.round((e.clientX - r.left) / r.width * S.imgW), y: Math.round((e.clientY - r.top) / r.height * S.imgH) };
}

// 다른 폼이 화면 좌표/영역을 요청할 때
function requestPick(kind, prompt) {
  return new Promise((resolve) => {
    S.pick = { kind, resolve };
    const b = $("#pick-banner"); b.textContent = prompt + "  (Esc: 취소)"; b.hidden = false;
    canvas.className = kind === "point" ? "point" : "select";
    if (kind === "region" && S.live) snapshot();
    canvas.focus();
  });
}
function endPick(value) {
  if (!S.pick) return;
  const p = S.pick; S.pick = null;
  $("#pick-banner").hidden = true; canvas.className = S.mode;
  p.resolve(value);
}

canvas.addEventListener("mousedown", (e) => {
  const p = toFrame(e);
  const wantsRegion = S.pick?.kind === "region" || (!S.pick && S.mode === "select");
  if (wantsRegion) { S.drag = { x0: p.x, y0: p.y, x: p.x, y: p.y, w: 0, h: 0 }; e.preventDefault(); }
});
canvas.addEventListener("mousemove", (e) => {
  if (!S.drag) return;
  const p = toFrame(e);
  Object.assign(S.drag, { x: Math.min(p.x, S.drag.x0), y: Math.min(p.y, S.drag.y0), w: Math.abs(p.x - S.drag.x0), h: Math.abs(p.y - S.drag.y0) });
  draw();
});
canvas.addEventListener("mouseup", async (e) => {
  if (S.drag) {
    const d = S.drag; S.drag = null;
    if (d.w < 4 || d.h < 4) { draw(); return; }
    const box = [d.x, d.y, d.w, d.h];
    S.overlay = [{ box, color: "#ffb020", label: "선택" }]; draw();
    if (S.pick?.kind === "region") return endPick(box);
    return openTargetForm(box);
  }
  const p = toFrame(e);
  if (S.pick?.kind === "point") return endPick([p.x, p.y]);
  if (S.mode === "control" && e.button === 0) control({ kind: e.shiftKey ? "double" : "click", x: p.x, y: p.y });
});
canvas.addEventListener("contextmenu", (e) => {
  if (S.mode !== "control") return;
  e.preventDefault();
  const p = toFrame(e);
  control({ kind: "right_click", x: p.x, y: p.y });
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && S.pick) endPick(null); });
window.addEventListener("resize", fitCanvas);

async function control(cmd) {
  try {
    const r = await api("POST", "/api/control", cmd);
    if (S.state) S.state.cursor = r.cursor;
  } catch (err) { log(`직접 조작 실패: ${err.message}`); }
}

// ---------------------------------------------------------------- 메시지·로그
function msg(el, text, kind = "info") { el.textContent = text; el.className = `msg ${kind}`; el.hidden = !text; }
function log(text) { const pre = $("#logs"); pre.textContent += text + "\n"; pre.scrollTop = pre.scrollHeight; }
async function pollLogs() {
  try {
    const r = await api("GET", `/api/logs?after=${S.logSeq}`);
    for (const l of r.lines) log(`${new Date(l.t * 1000).toLocaleTimeString()}  ${l.msg}`);
    S.logSeq = r.seq;
  } catch { /* 서버 재시작 중 */ }
  setTimeout(pollLogs, 1000);
}
async function pollState() {
  try {
    S.state = await api("GET", "/api/state");
    $("#conn").textContent = S.state.mode === "sim" ? "시뮬레이터" : `실장비 · ${S.state.port} · ${S.state.width}×${S.state.height}`;
    const st = $("#status");
    const opJob = S.state.ops_job;
    st.className = "status" + (S.state.running || opJob ? " running" : S.state.busy ? " busy" : "");
    $("#status-text").textContent = S.state.running ? "시나리오 실행 중" : opJob ? `운영 작업 #${opJob} 실행 중`
      : S.state.busy ? "조작 중" : S.state.ops === "halted" ? "운영 장치 정지" : S.state.ops === "running" ? "운영 중 · 대기" : "대기";
  } catch { $("#conn").textContent = "서버 연결 끊김"; }
  setTimeout(pollState, 1500);
}

// ---------------------------------------------------------------- 탭
$$(".tabs button").forEach((b) => b.addEventListener("click", () => {
  $$(".tabs button").forEach((x) => x.classList.toggle("on", x === b));
  $$(".tab").forEach((t) => { t.hidden = t.id !== `tab-${b.dataset.tab}`; });
  if (b.dataset.tab === "runs") loadRuns();
  if (b.dataset.tab === "ops") opsOpen();
}));

// ---------------------------------------------------------------- 대상(target)
let tfKind = "template", tfBox = null, tfOcrText = "";

async function loadTargets() {
  S.targets = await api("GET", "/api/targets");
  renderTargets();
}

function renderTargets() {
  const q = $("#target-filter").value.trim().toLowerCase();
  const ul = $("#targets"); ul.replaceChildren();
  for (const t of S.targets.filter((t) => !q || t.name.toLowerCase().includes(q))) {
    const thumb = t.kind === "template"
      ? h("img", { class: "thumb", src: `/api/targets/${encodeURIComponent(t.name)}.png`, alt: t.name })
      : h("div", { class: "thumb" }, `"${t.text}"`);
    const meta = t.kind === "text"
      ? `글자 "${t.text}" · ${t.match || "contains"}${t.region ? " · 영역 지정" : t.anchor ? " · 기준 " + t.anchor : " · 전체 화면(느림)"}`
      : `그림 ${t.w}×${t.h}${t.threshold ? " · 기준 " + t.threshold : ""}${t.color_tol ? " · 색 " + t.color_tol : ""}`;
    ul.append(h("li", { class: "target" }, thumb,
      h("div", {}, h("div", { class: "nm" }, t.name, " ", h("span", { class: `badge ${t.kind === "text" ? "txt" : ""}` }, t.kind === "text" ? "글자" : "그림")),
        h("div", { class: "meta" }, meta)),
      h("div", { class: "row" },
        h("button", { onclick: () => testLocate(t.name), title: "지금 화면에서 찾아 표시" }, "찾기"),
        h("button", { class: "ghost", onclick: (e) => deleteTarget(t.name, e.currentTarget), title: "삭제" }, "✕"))));
  }
  if (!ul.children.length) ul.append(h("li", { class: "hint" }, q ? "일치하는 대상이 없습니다." : "등록된 대상이 없습니다."));
}

async function testLocate(target, useSnapshot = false) {
  try {
    const r = await api("POST", "/api/locate", { target, snapshot: useSnapshot });
    const name = tname(target);
    if (r.found) {
      S.overlay = [{ box: r.box, color: "#1fbf6a", label: `${name} ${r.score} (${r.ms}ms)` }];
      log(`찾기 ${name}: 위치 ${r.center} 점수 ${r.score} (${r.ms}ms)`);
    } else {
      S.overlay = [];
      log(`찾기 ${name}: 화면에 없음 (${r.ms}ms)`);
    }
    draw();
    return r;
  } catch (err) { log(`찾기 실패: ${err.message}`); return null; }
}

async function deleteTarget(name, btn) {
  const used = S.scen.steps.some((s) => JSON.stringify(s).includes(`"${name}"`));
  if (btn && btn.dataset.confirm !== "1") {          // 브라우저 confirm 대신 두 번 누르기
    btn.dataset.confirm = "1"; btn.textContent = used ? "사용 중! 삭제?" : "삭제?"; btn.classList.add("danger");
    setTimeout(() => { if (btn.isConnected) { btn.dataset.confirm = ""; btn.textContent = "✕"; btn.classList.remove("danger"); } }, 3000);
    return;
  }
  await api("DELETE", `/api/targets/${encodeURIComponent(name)}`);
  await loadTargets(); renderStepForm();
}

function setTfKind(k) {
  tfKind = k;
  $$("#target-form [data-kind]").forEach((b) => b.classList.toggle("on", b.dataset.kind === k));
  $("#tf-text-fields").hidden = k !== "text";
  $("#tf-tmpl-fields").hidden = k !== "template";
  $("#tf-kind-hint").textContent = k === "text"
    ? "글자를 읽어 찾습니다. 창 위치·테마가 바뀌어도 덜 깨집니다. 지정한 영역 안에서만 찾습니다."
    : "잘라낸 그림과 같은 모양을 찾습니다. 빠르고(수 ms) 아이콘·그림에 적합합니다."
      + (tfOcrText ? ` 이 영역에서 읽힌 글자: "${tfOcrText}" — 글자로 찾기도 가능합니다.` : "");
}

async function openTargetForm(box) {
  tfBox = box;
  $$(".tabs button").find((b) => b.dataset.tab === "targets").click();
  const f = $("#target-form"); f.hidden = false; msg($("#tf-msg"), "");
  $("#tf-box").textContent = `영역 [${box.join(", ")}]`;
  const tc = $("#tf-canvas"); tc.width = box[2]; tc.height = box[3];
  tc.getContext("2d").drawImage(S.img, box[0], box[1], box[2], box[3], 0, 0, box[2], box[3]);
  $("#tf-name").value = ""; $("#tf-name").focus();
  tfOcrText = ""; setTfKind(tfKind);
  $("#tf-ocr").replaceChildren(h("span", { class: "hint" }, "글자 읽는 중…"));
  try {
    const r = await api("POST", "/api/ocr", { box });
    const chips = $("#tf-ocr"); chips.replaceChildren();
    const texts = r.hits.map((x) => x.text);
    if (texts.length > 1) texts.unshift(texts.join(" "));
    for (const t of [...new Set(texts)]) chips.append(h("button", { type: "button", class: "chip", onclick: () => { $("#tf-text").value = t; } }, t));
    if (!texts.length) chips.append(h("span", { class: "hint" }, "읽힌 글자 없음"));
    $("#tf-text").value = texts[0] || "";
    tfOcrText = texts[0] || ""; setTfKind(tfKind);
    if (!$("#tf-name").value && texts[0]) $("#tf-name").value = texts[0].toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40);
  } catch (err) { $("#tf-ocr").replaceChildren(h("span", { class: "hint" }, `OCR 실패: ${err.message}`)); }
}

$$("#target-form [data-kind]").forEach((b) => b.addEventListener("click", () => setTfKind(b.dataset.kind)));
$("#tf-cancel").addEventListener("click", () => { $("#target-form").hidden = true; S.overlay = []; draw(); });
$("#target-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = { name: $("#tf-name").value.trim(), kind: tfKind, box: tfBox };
  if (tfKind === "text") {
    Object.assign(body, { text: $("#tf-text").value, match: $("#tf-match").value });
    const [x, y, w, hh] = tfBox, pad = 8;                 // 글자 영역은 약간 넉넉하게
    body.box = [Math.max(0, x - pad), Math.max(0, y - pad), w + 2 * pad, hh + 2 * pad];
  } else {
    body.threshold = $("#tf-threshold").value; body.color_tol = $("#tf-color").value;
  }
  try {
    await api("POST", "/api/targets", body);
    msg($("#tf-msg"), `'${body.name}' 등록했습니다.`, "ok");
    await loadTargets(); renderStepForm();
    const r = await testLocate(body.name, true);
    if (r && !r.found) msg($("#tf-msg"), `'${body.name}' 등록했지만 고정 화면에서 찾지 못했습니다. 비교 방식이나 영역을 바꿔 보세요.`, "bad");
  } catch (err) { msg($("#tf-msg"), err.message, "bad"); }
});
$("#tf-test").addEventListener("click", async () => {
  const name = $("#tf-name").value.trim();
  if (!S.targets.some((t) => t.name === name)) return msg($("#tf-msg"), "먼저 등록하세요.", "bad");
  testLocate(name);
});
$("#target-filter").addEventListener("input", renderTargets);

// ---------------------------------------------------------------- 시나리오
// 스텝 위치 = 목록 경로 lp ([[부모번호, "then"|"else"|"steps"], ...], 최상위 = []) + 목록 안 번호 i
function listAt(lp, root = S.scen.steps) {
  let arr = root;
  for (const [i, k] of lp) { const st = arr[i]; if (!Array.isArray(st[k])) st[k] = []; arr = st[k]; }
  return arr;
}
// 실행기 스텝 번호 ("3", "3.then.0", "4[*].1") — 결과 표시용
function runIndex(lp, i) {
  let base = "";
  for (const [pi, k] of lp) base = k === "steps" ? `${base}${pi}[*].` : `${base}${pi}.${k}.`;
  return base + i;
}
// 검증기 스텝 경로 ("3", "3.then.0", "4.1")
function validIndex(lp, i) {
  let base = "";
  for (const [pi, k] of lp) base += k === "steps" ? `${pi}.` : `${pi}.${k}.`;
  return base + i;
}
function resultFor(ri) {
  if (!ri.includes("*")) return S.stepResults[ri];
  const re = new RegExp("^" + ri.replace(/[.]/g, "\\.").replace(/\[\*\]/g, "\\[\\d+\\]") + "$");
  let last;
  for (const [k, v] of Object.entries(S.stepResults)) if (re.test(k)) last = v;   // 마지막 회차
  return last;
}
const samePath = (a, lp, i) => a && a.i === i && JSON.stringify(a.lp) === JSON.stringify(lp);

async function loadScenarioList(select) {
  S.scenarios = (await api("GET", "/api/scenarios")).filter((s) => s.kind === "scenario");
  const sel = $("#scen-select"); sel.replaceChildren(h("option", { value: "" }, "— 시나리오 선택 —"));
  for (const s of S.scenarios) sel.append(h("option", { value: s.name }, `${s.name} (${s.steps})`));
  sel.value = select ?? S.scen.name ?? "";
}

function setScenario(sc) {
  const { name = "", description = "", steps = [], params = {}, ghost, ...extra } = sc;
  S.scen = { name, description, steps: JSON.parse(JSON.stringify(steps)) };
  S.paramRows = Object.entries(params || {}).map(([k, v]) => ({
    name: k, default: v && typeof v === "object" ? (v.default ?? "") : (v ?? ""), description: v && typeof v === "object" ? (v.description ?? "") : "" }));
  S.extra = extra; S.stepResults = {}; S.editPath = null; S.dirty = false;
  $("#scen-name").value = name; $("#scen-desc").value = description;
  $("#step-form").hidden = true; $("#run-form").hidden = true;
  $("#params-box").open = S.paramRows.length > 0;
  msg($("#scen-msg"), Object.keys(extra).length ? `이 시나리오에는 폼에 없는 설정(${Object.keys(extra).join(", ")})이 있습니다. JSON 보기에서 확인할 수 있고 저장 시 유지됩니다.` : "");
  renderParams(); renderSteps(); syncJson();
}

function paramsObject() {
  const out = {};
  for (const r of S.paramRows) if (r.name.trim()) out[r.name.trim()] = { default: r.default, ...(r.description ? { description: r.description } : {}) };
  return out;
}
function paramDefaults() {
  const out = {};
  for (const r of S.paramRows) if (r.name.trim() && r.default !== "") out[r.name.trim()] = r.default;
  return out;
}
function currentScenario() {
  const sc = { ...S.extra, name: $("#scen-name").value.trim(), description: $("#scen-desc").value.trim() };
  const p = paramsObject();
  if (Object.keys(p).length) sc.params = p;
  sc.steps = S.scen.steps;
  return sc;
}
function markDirty() { S.dirty = true; syncJson(); }
function syncJson() {
  if (!$("#scen-json").hidden) $("#scen-json").value = JSON.stringify({ ghost: 1, ...currentScenario() }, null, 2);
}

// ---- 파라미터 표
function renderParams() {
  const tb = $("#params-rows"); tb.replaceChildren();
  S.paramRows.forEach((r, i) => {
    const inp = (key, ph) => h("input", { value: r[key] ?? "", placeholder: ph, "aria-label": key,
      oninput: (e) => { r[key] = e.target.value; markDirty(); renderVarsHint(); } });
    tb.append(h("tr", {}, h("td", {}, inp("name", "lots")), h("td", {}, inp("default", "LOT-A,LOT-B")),
      h("td", {}, inp("description", "설명")),
      h("td", {}, h("button", { class: "ghost", title: "삭제", onclick: () => { S.paramRows.splice(i, 1); renderParams(); markDirty(); } }, "✕"))));
  });
  $("#params-count").textContent = S.paramRows.length ? `(${S.paramRows.length})` : "";
}
$("#param-add").addEventListener("click", () => { S.paramRows.push({ name: "", default: "", description: "" }); renderParams(); $("#params-rows tr:last-child input").focus(); });

// ---- 스텝 목록 (트리)
function renderSteps() {
  const ol = $("#steps"); ol.replaceChildren();
  renderList(S.scen.steps, [], ol);
  if (!S.scen.steps.length) ol.append(h("li", { class: "hint" }, "스텝이 없습니다. 아래 '+ 스텝 추가'로 시작하세요."));
}
function renderList(arr, lp, ol) { arr.forEach((st, i) => ol.append(renderStep(st, lp, i))); }

function renderStep(st, lp, i) {
  const ri = runIndex(lp, i), r = resultFor(ri), kids = CHILD_KEYS[st.action];
  const arr = listAt(lp);
  const cls = ["step", kids && "container", samePath(S.editPath, lp, i) && "editing", S.runningIdx === ri && "running",
               r && (r.ok ? "passed" : "failed")].filter(Boolean).join(" ");
  const body = h("div", { class: "body" },
    h("div", { class: "act" }, ACTIONS[st.action]?.label || st.action, st.label ? h("span", { class: "sum" }, `  ${st.label}`) : null),
    h("div", { class: "sum" }, summary(st)),
    r ? h("div", { class: `res ${r.ok ? "ok" : "bad"}` }, `${r.ok ? "✓" : "✗"} ${r.message} (${r.elapsed}s)`) : null);
  if (kids) {
    for (const [k, label] of kids) {
      const childLp = [...lp, [i, k]];
      const sub = h("div", { class: "substeps" }, h("div", { class: "blk" }, label));
      const ol = h("ol", { class: "steps" });
      renderList(st[k] || [], childLp, ol);
      sub.append(ol, h("button", { class: "add small", onclick: () => openStepForm(null, childLp, null) }, "+ 여기에 스텝 추가"));
      body.append(sub);
    }
  }
  return h("li", { class: cls },
    h("span", { class: `n ${lp.length ? "nested" : ""}` }, i),
    body,
    h("div", { class: "tools" },
      h("button", { class: "go", title: "이 스텝만 실행", onclick: () => tryStep(st, lp, i) }, "▶"),
      h("button", { title: "편집", onclick: () => openStepForm(st, lp, i) }, "✎"),
      h("button", { title: "복제", onclick: () => { arr.splice(i + 1, 0, JSON.parse(JSON.stringify(st))); S.stepResults = {}; renderSteps(); markDirty(); } }, "⧉"),
      h("button", { title: "위로", disabled: i === 0, onclick: () => moveStep(lp, i, -1) }, "↑"),
      h("button", { title: "아래로", disabled: i === arr.length - 1, onclick: () => moveStep(lp, i, 1) }, "↓"),
      h("button", { class: "ghost", title: "삭제", onclick: () => { arr.splice(i, 1); S.stepResults = {}; renderSteps(); markDirty(); } }, "✕")));
}

function moveStep(lp, i, d) {
  const s = listAt(lp); [s[i], s[i + d]] = [s[i + d], s[i]];
  S.stepResults = {}; renderSteps(); markDirty();
}

async function tryStep(st, lp = null, i = null) {
  const ri = lp ? runIndex(lp, i) : null;
  try {
    if (ri) { S.runningIdx = ri; renderSteps(); }
    const r = await api("POST", "/api/step", { step: st, vars: paramDefaults() });
    if (ri) S.stepResults[ri.replace(/\[\*\]/g, "[1]")] = r;
    if (S.state) S.state.cursor = r.cursor;
    S.runningIdx = null; renderSteps();
    if (Object.keys(r.values || {}).length) log(`읽은 값: ${JSON.stringify(r.values)}`);
    return r;
  } catch (err) { log(`스텝 실행 실패: ${err.message}`); S.runningIdx = null; renderSteps(); return null; }
}

// ---- 사용 가능한 변수
function definedVars() {
  const out = new Set(S.paramRows.map((r) => r.name.trim()).filter(Boolean));
  const walk = (steps) => (steps || []).forEach((st) => {
    if (st.action === "read") out.add(st.name || "value");
    if (st.action === "set" && st.name) out.add(st.name);
    if (st.action === "repeat" || st.action === "while") out.add(st.var || "i");
    if (st.action === "for_each") { const v = st.var || "item"; out.add(v); out.add(`${v}_index`); }
    for (const k of ["steps", "then", "else"]) walk(st[k]);
  });
  walk(S.scen.steps);
  return [...out];
}
let lastTextInput = null;
function renderVarsHint() {
  const el = $("#sf-vars"); if (!el) return;
  const vars = definedVars();
  el.replaceChildren(...(vars.length ? ["사용 가능한 변수 (눌러서 넣기): ", ...vars.map((v) => h("span", { class: "mono", title: "커서 위치에 넣기",
    onclick: () => { if (lastTextInput) { const t = lastTextInput; const pos = t.selectionStart ?? t.value.length;
      t.value = t.value.slice(0, pos) + "${" + v + "}" + t.value.slice(pos); t.focus(); } } }, "${" + v + "}"))]
    : ["파라미터나 읽기·변수 설정 스텝을 만들면 ${이름} 으로 쓸 수 있습니다."]));
}
document.addEventListener("focusin", (e) => { if (e.target.matches?.("#sf-fields input[type=text], #sf-fields input:not([type]), #sf-fields textarea")) lastTextInput = e.target; });

// ---------------------------------------------------------------- 스텝 폼
const sf = { action: "click", step: {} };

function targetOptions(sel, allowXY) {
  const opts = [h("option", { value: "" }, "— 대상 선택 —")];
  if (allowXY) opts.push(h("option", { value: "@xy" }, "(화면 좌표 직접 지정)"));
  for (const t of S.targets) opts.push(h("option", { value: t.name }, `${t.name} · ${t.kind === "text" ? "글자" : "그림"}`));
  if (typeof sel === "object" && sel !== null) opts.push(h("option", { value: "@inline" }, `글자 ${tname(sel)} (인라인)`));
  if (typeof sel === "string" && sel.includes("${")) opts.push(h("option", { value: sel }, `${sel} (변수)`));
  return opts;
}

function numInput(id, val, attrs = {}) { return h("input", { id, type: "number", value: val ?? "", ...attrs }); }
function textInput(id, val, attrs = {}) { return h("input", { id, type: "text", value: val ?? "", ...attrs }); }

function fieldTarget(st, allowXY) {
  const cur = st.target === undefined ? (st.x !== undefined ? "@xy" : "") : typeof st.target === "string" ? st.target : "@inline";
  const sel = h("select", { id: "f-target" }, targetOptions(st.target, allowXY));
  sel.value = cur;
  const xy = h("div", { class: "inline", id: "f-xy", hidden: cur !== "@xy" },
    "x", numInput("f-x", st.x), "y", numInput("f-y", st.y),
    h("button", { type: "button", onclick: async () => {
      const p = await requestPick("point", "클릭할 위치를 화면에서 누르세요");
      if (p) { $("#f-x").value = p[0]; $("#f-y").value = p[1]; S.overlay = [{ box: [p[0] - 6, p[1] - 6, 12, 12], color: "#ff3d7f" }]; draw(); }
    } }, "화면에서 찍기"));
  sel.addEventListener("change", () => { xy.hidden = sel.value !== "@xy"; });
  sf.inlineTarget = typeof st.target === "object" ? st.target : null;
  return h("div", { class: "fld" }, h("label", { for: "f-target" }, "대상"),
    h("div", { class: "inline" }, sel, h("button", { type: "button", onclick: () => { const v = sel.value; if (v && !v.startsWith("@") && !v.includes("${")) testLocate(v); } }, "찾기")), xy);
}

function fieldExpect(st) {
  const e = st.expect || {};
  const kind = "gone" in e ? "gone" : "visible" in e ? "visible" : "";
  const tgt = e.gone ?? e.visible;
  const sel = h("select", { id: "f-exp-kind" }, h("option", { value: "" }, "확인 안 함"), h("option", { value: "visible" }, "이 대상이 나타나야 함"), h("option", { value: "gone" }, "이 대상이 사라져야 함"));
  sel.value = kind;
  const ts = h("select", { id: "f-exp-target" }, targetOptions(tgt, false));
  ts.value = typeof tgt === "string" ? tgt : tgt ? "@inline" : "";
  sf.inlineExpect = typeof tgt === "object" ? tgt : null;
  const wrap = h("div", { class: "inline", hidden: !kind }, ts, "최대", numInput("f-exp-timeout", e.timeout ?? 3, { step: "0.5", min: "0" }), "초");
  sel.addEventListener("change", () => { wrap.hidden = !sel.value; });
  return h("div", { class: "fld" }, h("label", { for: "f-exp-kind" }, "실행 후 확인 (결과가 중요하면 꼭 지정)"), sel, wrap);
}

function fieldCond(st) {
  const c = st.cond || {};
  const simple = "visible" in c || "gone" in c || "expr" in c || !Object.keys(c).length;
  const kind = "expr" in c ? "expr" : "gone" in c ? "gone" : simple ? "visible" : "json";
  const sel = h("select", { id: "f-cond-kind" },
    h("option", { value: "visible" }, "이 대상이 화면에 보이면"), h("option", { value: "gone" }, "이 대상이 화면에 없으면"),
    h("option", { value: "expr" }, "계산식이 참이면"), !simple ? h("option", { value: "json" }, "복합 조건 (JSON 으로 편집)") : null);
  sel.value = kind;
  const tgt = c.visible ?? c.gone;
  const ts = h("select", { id: "f-cond-target" }, targetOptions(tgt, false));
  ts.value = typeof tgt === "string" ? tgt : "";
  const tWrap = h("div", { class: "inline" }, ts, "최대", numInput("f-cond-timeout", c.timeout ?? 0, { step: "0.5", min: "0" }), "초 기다림");
  const eWrap = h("div", { class: "inline" }, textInput("f-cond-expr", c.expr ?? "", { class: "wide mono", placeholder: "예) lot_read != lot   done >= 3   recipe == 'RCP_B'" }));
  const show = () => { tWrap.hidden = !["visible", "gone"].includes(sel.value); eWrap.hidden = sel.value !== "expr"; };
  sel.addEventListener("change", show); show();
  sf.complexCond = simple ? null : c;
  return h("div", { class: "fld" }, h("label", { for: "f-cond-kind" }, "조건"), sel, tWrap, eWrap,
    h("p", { class: "hint" }, "계산식에서는 변수 이름을 ${} 없이 그대로 씁니다. 숫자처럼 보이는 판독값은 숫자로 비교됩니다."));
}

function fieldRegion(st) {
  const r = st.region || [];
  const wrap = h("div", { class: "inline" }, ...["x", "y", "w", "h"].map((k, i) => [k, numInput(`f-r${i}`, r[i])]).flat(),
    h("button", { type: "button", onclick: async () => {
      const box = await requestPick("region", "읽을 영역을 화면에서 드래그하세요");
      if (box) box.forEach((v, i) => { $(`#f-r${i}`).value = v; });
    } }, "화면에서 그리기"));
  return h("div", { class: "fld" }, h("label", {}, "읽을 영역"), wrap);
}

function renderStepForm() {
  if ($("#step-form").hidden) return;
  const st = sf.step, a = sf.action, box = $("#sf-fields");
  box.replaceChildren();
  for (const f of ACTIONS[a].fields) {
    if (f === "target") box.append(fieldTarget(st, true));
    else if (f === "target_only") box.append(fieldTarget(st, false));
    else if (f === "expect") box.append(fieldExpect(st));
    else if (f === "region") box.append(fieldRegion(st));
    else if (f === "cond") box.append(fieldCond(st));
    else if (f === "timeout") box.append(h("label", {}, "대상 찾기 최대 대기(초)", numInput("f-timeout", st.timeout, { step: "0.5", min: "0", placeholder: a === "wait_for" || a === "wait_gone" ? "10" : "3" })));
    else if (f === "retry") box.append(h("label", {}, "실패 시 재시도 횟수", numInput("f-retry", st.retry, { min: "0", max: "5", placeholder: "0" })));
    else if (f === "label") box.append(h("label", {}, "메모 (화면에 표시될 설명)", textInput("f-label", st.label)));
    else if (f === "text") box.append(h("label", {}, "입력할 글자 (영문·숫자·기호, ${변수} 가능)", textInput("f-text", st.text)));
    else if (f === "key") box.append(h("label", {}, "키", h("input", { id: "f-key", list: "key-list", value: st.key ?? "", placeholder: "enter, esc, f5…" })));
    else if (f === "keys") box.append(h("label", {}, "조합키 (+로 연결)", textInput("f-keys", (st.keys || []).join("+"), { placeholder: "ctrl+s, alt+f4…" })));
    else if (f === "sec") box.append(h("label", {}, "대기 시간(초)", numInput("f-sec", st.sec ?? 1, { step: "0.1", min: "0" })));
    else if (f === "name") box.append(h("label", {}, "값 이름 (이후 ${이름} 으로 사용)", textInput("f-name", st.name, { placeholder: "elapsed_s" })));
    else if (f === "pattern") box.append(h("label", {}, "값 추출 정규식 (선택, 괄호 부분이 값)", textInput("f-pattern", st.pattern, { class: "mono", placeholder: "^00:00:(\\d\\d\\.\\d\\d)$" })));
    else if (f === "range") box.append(h("div", { class: "fld" }, h("label", {}, "허용 범위 (선택 — 벗어나면 실패)"),
      h("div", { class: "inline" }, "최소", numInput("f-min", st.min, { step: "any" }), "최대", numInput("f-max", st.max, { step: "any" }))));
    else if (f === "vote") box.append(h("label", { class: "inline" }, h("input", { id: "f-vote", type: "checkbox", checked: !!st.vote }), "다수결 판독 (숫자 표시창처럼 오인식이 잦을 때)"));
    else if (f === "scenario") {
      const sel = h("select", { id: "f-scenario" }, S.scenarios.map((s) => h("option", { value: s.name }, s.name)));
      sel.value = st.scenario ?? ""; box.append(h("label", {}, "실행할 시나리오", sel));
    } else if (f === "args") {
      box.append(h("label", {}, "넘길 값 (한 줄에 이름=값, 선택)",
        h("textarea", { id: "f-args", rows: 2, class: "mono" }, Object.entries(st.args || {}).map(([k, v]) => `${k}=${v}`).join("\n"))));
    } else if (f === "setv") {
      const mode = st.expr !== undefined ? "expr" : "value";
      const msel = h("select", { id: "f-set-mode" }, h("option", { value: "value" }, "값 그대로"), h("option", { value: "expr" }, "계산식 결과"));
      msel.value = mode;
      box.append(h("label", {}, "변수 이름", textInput("f-set-name", st.name, { placeholder: "done" })),
        h("div", { class: "fld" }, h("label", {}, "넣을 값"), h("div", { class: "inline" }, msel,
          textInput("f-set-val", mode === "expr" ? st.expr : (st.value ?? ""), { class: "wide mono", placeholder: "0  /  done + 1" }))));
    } else if (f === "times") box.append(h("label", {}, "반복 횟수 (숫자 또는 ${변수})", textInput("f-times", st.times ?? 3)));
    else if (f === "items") box.append(h("label", {}, "항목 목록 (쉼표로 구분, 또는 ${파라미터})", textInput("f-items", Array.isArray(st.items) ? st.items.join(",") : st.items, { placeholder: "LOT-A,LOT-B  또는  ${lots}" })));
    else if (f === "var") box.append(h("label", {}, `반복 변수 이름 (기본 ${VAR_DEFAULT[a]}${a === "for_each" ? ", 몇 번째인지는 이름_index" : ", 1부터"})`, textInput("f-var", st.var, { placeholder: VAR_DEFAULT[a] })));
    else if (f === "max") box.append(h("label", {}, "최대 반복 횟수 (무한 반복 방지)", numInput("f-maxiter", st.max ?? 100, { min: "1" })));
    else if (f === "message") box.append(h("label", {}, "실패 메시지 (${변수} 가능)", textInput("f-message", st.message)));
  }
  $("#sf-json").value = JSON.stringify(st, null, 2);
  renderVarsHint();
}

function readStepForm() {
  if ($("#sf-adv").open) {                            // JSON 편집 모드
    try { return JSON.parse($("#sf-json").value); } catch (e) { throw new Error(`JSON 오류: ${e.message}`); }
  }
  const a = sf.action, st = { action: a };
  const v = (id) => { const el = $(`#${id}`); return el ? el.value.trim() : ""; };
  const num = (id) => (v(id) === "" ? undefined : Number(v(id)));
  const numOrVar = (id) => { const x = v(id); return x === "" ? undefined : (/^-?\d+(\.\d+)?$/.test(x) ? Number(x) : x); };
  for (const f of ACTIONS[a].fields) {
    if (f === "target" || f === "target_only") {
      const t = v("f-target");
      if (t === "@xy") { st.x = num("f-x"); st.y = num("f-y"); if (st.x === undefined || st.y === undefined) throw new Error("좌표를 지정하세요"); }
      else if (t === "@inline") st.target = sf.inlineTarget;
      else if (t) st.target = t;
      else throw new Error("대상을 선택하세요");
    } else if (f === "expect") {
      const k = v("f-exp-kind");
      if (k) {
        const t = v("f-exp-target");
        if (!t) throw new Error("확인할 대상을 선택하세요");
        st.expect = { [k]: t === "@inline" ? sf.inlineExpect : t, timeout: num("f-exp-timeout") ?? 3 };
      }
    } else if (f === "cond") {
      const k = v("f-cond-kind");
      if (k === "json") st.cond = sf.complexCond;
      else if (k === "expr") { if (!v("f-cond-expr")) throw new Error("계산식을 입력하세요"); st.cond = { expr: v("f-cond-expr") }; }
      else {
        const t = v("f-cond-target");
        if (!t) throw new Error("조건 대상을 선택하세요");
        st.cond = { [k]: t };
        if (num("f-cond-timeout")) st.cond.timeout = num("f-cond-timeout");
      }
    } else if (f === "region") {
      const r = [0, 1, 2, 3].map((i) => num(`f-r${i}`));
      if (r.some((x) => x === undefined)) throw new Error("읽을 영역을 지정하세요");
      st.region = r;
    } else if (f === "timeout") { if (num("f-timeout") !== undefined) st.timeout = num("f-timeout"); }
    else if (f === "retry") { if (num("f-retry")) st.retry = num("f-retry"); }
    else if (f === "label") { if (v("f-label")) st.label = v("f-label"); }
    else if (f === "text") st.text = $("#f-text").value;
    else if (f === "key") st.key = v("f-key");
    else if (f === "keys") st.keys = v("f-keys").split("+").map((x) => x.trim()).filter(Boolean);
    else if (f === "sec") st.sec = num("f-sec") ?? 1;
    else if (f === "name") { if (v("f-name")) st.name = v("f-name"); }
    else if (f === "pattern") { if (v("f-pattern")) st.pattern = v("f-pattern"); }
    else if (f === "range") { if (num("f-min") !== undefined) st.min = num("f-min"); if (num("f-max") !== undefined) st.max = num("f-max"); }
    else if (f === "vote") { if ($("#f-vote").checked) st.vote = true; }
    else if (f === "scenario") st.scenario = v("f-scenario");
    else if (f === "args") {
      const args = {};
      for (const line of $("#f-args").value.split("\n")) {
        if (!line.trim()) continue;
        const at = line.indexOf("=");
        if (at < 1) throw new Error(`넘길 값 형식은 이름=값: ${line}`);
        args[line.slice(0, at).trim()] = line.slice(at + 1).trim();
      }
      if (Object.keys(args).length) st.args = args;
    } else if (f === "setv") {
      st.name = v("f-set-name");
      if (!st.name) throw new Error("변수 이름을 입력하세요");
      if (v("f-set-mode") === "expr") st.expr = v("f-set-val");
      else st.value = numOrVar("f-set-val") ?? "";
    } else if (f === "times") st.times = numOrVar("f-times") ?? 1;
    else if (f === "items") st.items = v("f-items");
    else if (f === "var") { if (v("f-var")) st.var = v("f-var"); }
    else if (f === "max") st.max = num("f-maxiter") ?? 100;
    else if (f === "message") { if (v("f-message")) st.message = v("f-message"); }
  }
  for (const [k] of CHILD_KEYS[a] || []) st[k] = Array.isArray(sf.step[k]) ? sf.step[k] : [];   // 안쪽 스텝 유지
  return st;
}
function readStepFormSafe() { const open = $("#sf-adv").open; $("#sf-adv").open = false; try { return readStepForm(); } finally { $("#sf-adv").open = open; } }

function openStepForm(step = null, lp = [], index = null) {
  S.editPath = { lp, i: index };
  sf.step = step ? JSON.parse(JSON.stringify(step)) : {};
  sf.action = step?.action || (ACTIONS[sf.action] ? sf.action : "click");
  $("#sf-action").value = sf.action;
  const where = lp.length ? ` (${lp.map(([i, k]) => `${i}번 ${k === "then" ? "그러면" : k === "else" ? "아니면" : "반복"}`).join(" › ")} 안)` : "";
  $("#step-form-title").textContent = index === null ? `스텝 추가${where}` : `스텝 ${index} 편집${where}`;
  $("#sf-save").textContent = index === null ? "추가" : "수정";
  $("#sf-adv").open = false;
  msg($("#sf-msg"), "");
  $("#step-form").hidden = false;
  renderStepForm(); renderSteps();
  $("#step-form").scrollIntoView({ block: "nearest" });
}

for (const [g, acts] of ACTION_GROUPS) $("#sf-action").append(h("optgroup", { label: g }, acts.map((k) => h("option", { value: k }, ACTIONS[k].label))));
$("#sf-action").addEventListener("change", (e) => {
  let keep = {};
  try { keep = readStepFormSafe(); } catch { /* 입력 중 */ }
  sf.action = e.target.value; sf.step = { ...keep, action: sf.action }; renderStepForm();
});
$("#step-add").addEventListener("click", () => openStepForm(null, [], null));
$("#step-cancel").addEventListener("click", () => { $("#step-form").hidden = true; S.editPath = null; renderSteps(); });
$("#sf-adv").addEventListener("toggle", () => { if ($("#sf-adv").open) { try { $("#sf-json").value = JSON.stringify(readStepFormSafe(), null, 2); } catch { /* 유지 */ } } });

$("#step-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  let st;
  try { st = readStepForm(); } catch (err) { return msg($("#sf-msg"), err.message, "bad"); }
  const { lp, i } = S.editPath;
  // 시나리오 전체 맥락에서 검증 (반복 변수·파라미터를 알아야 하므로) → 이 스텝 관련 오류만 표시
  const steps = JSON.parse(JSON.stringify(S.scen.steps));
  const arr = listAt(lp, steps);
  const pos = i === null ? arr.length : i;
  if (i === null) arr.push(st); else arr[i] = st;
  const vp = validIndex(lp, pos);
  const r = await api("POST", "/api/validate", { ...currentScenario(), steps });
  const mine = r.errors.filter((x) => (x.startsWith(`step[${vp}]`) || x.startsWith(`step[${vp} `))
                                     && !/비어 있음|then 또는 else/.test(x));
  if (mine.length) return msg($("#sf-msg"), mine.join("\n"), "bad");
  const target = listAt(lp);
  if (i === null) target.push(st); else target[i] = st;
  S.stepResults = {};
  $("#step-form").hidden = true; S.editPath = null;
  renderSteps(); markDirty();
});
$("#sf-try").addEventListener("click", async () => {
  let st;
  try { st = readStepForm(); } catch (err) { return msg($("#sf-msg"), err.message, "bad"); }
  msg($("#sf-msg"), "실행 중…", "info");
  const { lp, i } = S.editPath || { lp: [], i: null };
  const r = await tryStep(st, i === null ? null : lp, i);
  if (r) msg($("#sf-msg"), `${r.ok ? "✓ 성공" : "✗ 실패"}: ${r.message} (${r.elapsed}s)`, r.ok ? "ok" : "bad");
  else msg($("#sf-msg"), "실행하지 못했습니다. 로그를 확인하세요.", "bad");
});

// ---------------------------------------------------------------- 시나리오 버튼
$("#scen-select").addEventListener("change", async (e) => {
  if (!e.target.value) return;
  setScenario(await api("GET", `/api/scenarios/${encodeURIComponent(e.target.value)}`));
});
$("#scen-new").addEventListener("click", () => { setScenario({ name: "", description: "", steps: [] }); $("#scen-select").value = ""; $("#scen-name").focus(); });
$("#scen-name").addEventListener("input", markDirty);
$("#scen-desc").addEventListener("input", markDirty);
$("#scen-validate").addEventListener("click", async () => {
  const r = await api("POST", "/api/validate", currentScenario());
  msg($("#scen-msg"), r.errors.length ? r.errors.join("\n") : "문제 없음", r.errors.length ? "bad" : "ok");
});
$("#scen-save").addEventListener("click", async () => {
  const sc = currentScenario();
  if (!/^[A-Za-z0-9_-]{1,60}$/.test(sc.name)) return msg($("#scen-msg"), "이름은 영문·숫자·_·- 로 입력하세요.", "bad");
  try {
    const r = await api("PUT", `/api/scenarios/${encodeURIComponent(sc.name)}`, sc);
    if (!r.saved) return msg($("#scen-msg"), "저장하지 않았습니다:\n" + r.errors.join("\n"), "bad");
    S.dirty = false; S.scen.name = sc.name;
    msg($("#scen-msg"), `'${sc.name}' 저장했습니다.`, "ok");
    await loadScenarioList(sc.name);
  } catch (err) { msg($("#scen-msg"), err.message, "bad"); }
});
$("#scen-json-toggle").addEventListener("click", () => {
  const ta = $("#scen-json");
  if (ta.hidden) { ta.hidden = false; syncJson(); $("#scen-json-toggle").textContent = "JSON 적용"; return; }
  try {
    const sc = JSON.parse(ta.value);
    setScenario(sc); ta.hidden = true; $("#scen-json-toggle").textContent = "JSON"; markDirty();
  } catch (err) { msg($("#scen-msg"), `JSON 오류: ${err.message}`, "bad"); }
});

// ---- 실행 (파라미터가 있으면 값 입력 후)
$("#scen-run").addEventListener("click", () => {
  const rows = S.paramRows.filter((r) => r.name.trim());
  if (!rows.length) return startRun({});
  const f = $("#run-fields"); f.replaceChildren();
  for (const r of rows) f.append(h("label", {}, `${r.name}${r.description ? ` — ${r.description}` : ""}`, textInput(`run-p-${r.name}`, r.default, { "data-param": r.name })));
  $("#run-form").hidden = false;
  f.querySelector("input")?.focus();
});
$("#run-cancel").addEventListener("click", () => { $("#run-form").hidden = true; });
$("#run-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const params = {};
  $$("#run-fields input").forEach((i) => { params[i.dataset.param] = i.value; });
  $("#run-form").hidden = true;
  startRun(params);
});

async function startRun(params) {
  try {
    S.stepResults = {};
    await api("POST", "/api/run", { scenario: currentScenario(), params });
    $("#scen-run").disabled = true; $("#scen-stop").disabled = false;
    msg($("#scen-msg"), `실행 중…${Object.keys(params).length ? ` ${JSON.stringify(params)}` : ""}`, "info");
    S.runPoll = setInterval(pollRun, 600);
  } catch (err) { msg($("#scen-msg"), err.message, "bad"); }
}
$("#scen-stop").addEventListener("click", () => api("POST", "/api/run/stop"));

async function pollRun() {
  const r = await api("GET", "/api/run");
  for (const sr of r.steps) S.stepResults[sr.index] = sr;
  const top = Object.keys(S.stepResults).filter((k) => /^\d+$/.test(k)).map(Number);
  S.runningIdx = r.running ? String(top.length ? Math.max(...top) + 1 : 0) : null;
  renderSteps();
  if (!r.running) {
    clearInterval(S.runPoll); S.runPoll = null;
    $("#scen-run").disabled = false; $("#scen-stop").disabled = true;
    const vals = Object.keys(r.values || {}).length ? `\n읽은 값: ${JSON.stringify(r.values)}` : "";
    const why = r.stopped ? " (중지됨)" : r.aborted_by ? ` (감시 '${r.aborted_by}'로 중단)` : "";
    msg($("#scen-msg"), `${r.ok ? "✓ 성공" : "✗ 실패"}${why} · 기록 ${r.run_dir}${vals}`, r.ok ? "ok" : "bad");
  }
}

// ---------------------------------------------------------------- 실행 기록
async function loadRuns() {
  const runs = await api("GET", "/api/runs");
  const ul = $("#runs"); ul.replaceChildren();
  for (const r of runs) {
    const clips = r.files.filter((f) => /\.(mp4|avi)$/.test(f)).length;
    ul.append(h("li", { class: "run", onclick: () => showRun(r.dir) },
      h("span", {}, r.dir.replace(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})_/, "$2/$3 $4:$5 · ")),
      h("span", { class: r.ok ? "ok" : "bad" }, r.ok === undefined || r.ok === null ? "?" : r.ok ? "성공" : "실패", clips ? ` · 영상 ${clips}` : "")));
  }
  if (!runs.length) ul.append(h("li", { class: "hint" }, "실행 기록이 없습니다."));
}

async function showRun(dir) {
  const d = await api("GET", `/api/runs/${encodeURIComponent(dir)}`);
  const box = $("#run-detail"); box.replaceChildren(h("h4", {}, dir));
  const steps = h("div", { class: "detail-steps" });
  for (const e of d.events) {
    if (e.kind === "step") steps.append(h("div", { class: e.ok ? "" : "bad" }, `${e.ok ? "✓" : "✗"} [${e.index}] ${e.desc} → ${e.message}`));
    if (e.kind === "watch") steps.append(h("div", {}, `⚠ 감시 ${e.event.rule} ${e.event.kind}`));
    if (e.kind === "read") steps.append(h("div", {}, `📏 ${e.name} = ${e.value}`));
  }
  box.append(steps);
  const files = h("div", { class: "files" });
  for (const f of d.files) {
    const url = `/api/runs/${encodeURIComponent(dir)}/${encodeURIComponent(f)}`;
    if (f.endsWith(".png")) files.append(h("a", { href: url, target: "_blank" }, h("img", { src: url, alt: f, loading: "lazy" }), f));
    else files.append(h("a", { href: url, download: f }, `🎞 ${f} (받기)`));
  }
  box.append(files);
}
$("#runs-refresh").addEventListener("click", loadRuns);

// ---------------------------------------------------------------- 운영 (대기열·예약·보고서)
const OPS_STATE = { running: ["운영 중", "go"], paused: ["일시정지", "warn"], stopped: ["정지됨", ""], halted: ["장치 정지", "bad"] };
const JOB_ST = { queued: "대기", running: "실행 중", ok: "성공", failed: "실패", error: "장치 오류", stopped: "중지",
                 cancelled: "취소", interrupted: "중단" };
const DAY_NAMES = "월화수목금토일";
const O = { timer: null, scen: [], params: {}, skind: "interval", editId: null };
const fmtT = (t) => { if (!t) return "-"; const d = new Date(t * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`; };

async function opsOpen() {
  O.scen = (await api("GET", "/api/scenarios")).filter((s) => s.kind === "scenario").map((s) => s.name);
  for (const sel of [$("#ops-scen"), $("#sc-scen")]) {
    const cur = sel.value;
    sel.replaceChildren(...O.scen.map((n) => h("option", { value: n }, n)));
    if (O.scen.includes(cur)) sel.value = cur;
  }
  if (!$("#sc-days").children.length)
    $("#sc-days").append(...[...DAY_NAMES].map((d, i) => h("label", { class: "day" }, h("input", { type: "checkbox", value: i }), d)));
  await opsParams("#ops-scen", "#ops-params");
  await opsParams("#sc-scen", "#sc-params");
  O.counts = null;
  opsRefresh();
}

async function opsParams(selId, boxId, values = {}) {
  const name = $(selId).value, box = $(boxId);
  box.replaceChildren();
  if (!name) return;
  const sc = await api("GET", `/api/scenarios/${encodeURIComponent(name)}`);
  for (const [k, p] of Object.entries(sc.params || {})) {
    const spec = typeof p === "object" && p !== null ? p : { default: p };
    box.append(h("label", { title: spec.description || "" }, `${k}${spec.description ? " — " + spec.description : ""}`,
      h("input", { "data-param": k, value: values[k] ?? spec.default ?? "", placeholder: spec.default === undefined ? "필수" : "" })));
  }
}
const paramValues = (boxId) => Object.fromEntries($$(`${boxId} [data-param]`).map((i) => [i.dataset.param, i.value]));

async function opsRefresh() {
  clearTimeout(O.timer);
  if ($("#tab-ops").hidden) return;
  try {
    const [st, jobs, scheds, evs] = await Promise.all([api("GET", "/api/ops/status"),
      api("GET", `/api/ops/jobs?limit=60&status=${$("#ops-filter").value}`), api("GET", "/api/ops/schedules"),
      api("GET", "/api/ops/events?limit=30")]);
    renderOpsState(st); renderJobs(jobs); renderScheds(scheds);
    const ck = JSON.stringify(st.counts);
    if (ck !== O.counts) { O.counts = ck; setRepLinks(); }      // 작업이 끝나면 보고서 요약도 갱신
    $("#ops-events").replaceChildren(...evs.map((e) => h("li", {}, h("span", { class: "mono" }, fmtT(e.t)), ` ${e.kind} `, h("span", { class: "hint" }, e.detail || ""))));
  } catch (e) { msg($("#ops-msg"), e.message, "bad"); }
  clearTimeout(O.timer);
  O.timer = setTimeout(opsRefresh, 2000);             // 탭이 열려 있는 동안 2초마다 갱신
}

function renderOpsState(st) {
  const [label, cls] = OPS_STATE[st.state] || [st.state, ""];
  const b = $("#ops-badge"); b.textContent = label; b.className = `opbadge ${cls}`;
  $("#ops-halt").hidden = !st.halt_reason; $("#ops-halt").textContent = st.halt_reason || "";
  $("#ops-current").textContent = st.current
    ? `실행 중: 작업 ${st.current.id} · ${st.current.scenario} · ${st.current.elapsed}s · ${st.current.attempts}회째 (${st.current.source})`
    : "진행 중인 작업 없음";
  const c = st.counts || {};
  $("#ops-counts").replaceChildren(...["queued", "ok", "failed", "error"].map((k) =>
    h("span", { class: `cnt ${k}` }, h("b", {}, c[k] || 0), JOB_ST[k])),
    h("span", { class: "cnt" }, h("b", {}, st.device?.reconnects || 0), "재연결"));
  $("#ops-mem").textContent = st.memory_mb ? `메모리 ${st.memory_mb} MB` : "";
  $("#ops-start").hidden = st.state !== "stopped";
  $("#ops-pause").hidden = st.state !== "running";
  $("#ops-resume").hidden = !["paused", "halted"].includes(st.state);
  $("#ops-stop").hidden = st.state === "stopped";
  $("#ops-stop-cur").hidden = !st.current;
}

function renderJobs(jobs) {
  const ul = $("#ops-jobs");
  ul.replaceChildren(...jobs.map((j) => {
    const vals = j.vals && typeof j.vals === "object" ? Object.entries(j.vals).map(([k, v]) => `${k}=${v}`).join(" ") : "";
    const params = j.params && Object.keys(j.params).length ? JSON.stringify(j.params) : "";
    return h("li", { class: `job ${j.status}` },
      h("span", { class: `st ${j.status}` }, JOB_ST[j.status] || j.status),
      h("div", { class: "body" },
        h("div", {}, h("b", {}, `#${j.id} ${j.scenario}`), params ? h("span", { class: "hint" }, ` ${params}`) : null),
        h("div", { class: "hint" }, `${fmtT(j.started || j.created)} · ${j.source || ""}${j.duration != null ? ` · ${j.duration}s` : ""}${j.attempts > 1 ? ` · ${j.attempts}회째` : ""}`),
        vals ? h("div", { class: "vals" }, vals) : null,
        j.error && j.status !== "ok" ? h("div", { class: "err" }, j.error) : null),
      h("div", { class: "tools" },
        j.status === "queued" ? h("button", { class: "ghost", title: "취소", onclick: async () => { await api("DELETE", `/api/ops/jobs/${j.id}`); opsRefresh(); } }, "취소") : null,
        j.run_dir ? h("button", { class: "ghost", title: "실행 기록 보기", onclick: () => { $$(".tabs button").find((b) => b.dataset.tab === "runs").click(); showRun(j.run_dir); } }, "기록") : null));
  }));
  if (!jobs.length) ul.append(h("li", { class: "hint" }, "작업이 없습니다."));
}

function renderScheds(list) {
  $("#ops-sched-count").textContent = list.length ? `${list.filter((s) => s.enabled).length}/${list.length}개 켜짐` : "";
  $("#ops-scheds").replaceChildren(...list.map((s) => h("li", { class: `sched ${s.enabled ? "" : "off"}` },
    h("label", { class: "inl", title: "켜기/끄기" }, h("input", { type: "checkbox", checked: !!s.enabled,
      onchange: async (e) => { await api("PUT", `/api/ops/schedules/${s.id}`, { enabled: e.target.checked }); opsRefresh(); } })),
    h("div", { class: "body" }, h("b", {}, s.name), h("span", { class: "hint" }, ` ${s.scenario} · ${s.describe}`),
      h("div", { class: "hint" }, s.enabled ? `다음: ${fmtT(s.next_run)} · 마지막: ${fmtT(s.last_run)}` : "꺼짐")),
    h("div", { class: "tools" },
      h("button", { class: "ghost", onclick: () => editSched(s) }, "수정"),
      h("button", { class: "ghost", onclick: async () => { if (confirm(`예약 '${s.name}'을 삭제할까요?`)) { await api("DELETE", `/api/ops/schedules/${s.id}`); opsRefresh(); } } }, "삭제")))));
}

function setSkind(k) {
  O.skind = k;
  $$("[data-skind]").forEach((b) => b.classList.toggle("on", b.dataset.skind === k));
  $("#sc-every-l").hidden = k !== "interval"; $("#sc-daily").hidden = k !== "daily";
}
async function editSched(s) {
  O.editId = s?.id ?? null;
  $("#sc-name").value = s?.name || "";
  if (s) $("#sc-scen").value = s.scenario;
  setSkind(s?.kind || "interval");
  $("#sc-every").value = s?.every_min || 60;
  $("#sc-times").value = (s?.times || []).join(", ");
  $$("#sc-days input").forEach((i) => { i.checked = (s?.days || []).includes(+i.value); });
  await opsParams("#sc-scen", "#sc-params", s?.params || {});
  $("#sc-save").textContent = s ? "예약 저장" : "예약 추가";
  $("#sc-reset").hidden = !s;
  $("#ops-sched-box").open = true;
  msg($("#sc-msg"), "");
}

function setRepLinks() {
  const d = $("#rep-days").value;
  $("#rep-html").href = `/api/ops/report.html?days=${d}`;
  $("#rep-csv").href = `/api/ops/jobs.csv?days=${d}`;
  api("GET", `/api/ops/report?days=${d}`).then((r) => {
    const rows = r.scenarios.map((s) => h("tr", {}, h("td", {}, s.scenario), h("td", { class: "num" }, s.runs),
      h("td", { class: "num" }, `${s.success_rate}%`), h("td", { class: "num" }, s.duration ? `${s.duration.mean}s` : "-")));
    $("#rep-table").replaceChildren(h("tr", {}, h("th", {}, "시나리오"), h("th", {}, "실행"), h("th", {}, "성공률"), h("th", {}, "평균")),
      ...rows, h("tr", {}, h("td", { class: "hint" }, `합계 (재연결 ${r.events.reconnect_ok || 0})`), h("td", { class: "num" }, r.total),
        h("td", { class: "num" }, `${r.success_rate}%`), h("td", {}, "")));
  }).catch(() => {});
}

async function opsControl(action) {
  try { renderOpsState(await api("POST", "/api/ops/control", { action })); opsRefresh(); }
  catch (e) { msg($("#ops-msg"), e.message, "bad"); }
}
$("#ops-start").addEventListener("click", () => opsControl("start"));
$("#ops-pause").addEventListener("click", () => opsControl("pause"));
$("#ops-resume").addEventListener("click", () => opsControl("resume"));
$("#ops-stop").addEventListener("click", () => { if (confirm("운영을 중지할까요? 진행 중 작업도 중지됩니다.")) opsControl("stop"); });
$("#ops-stop-cur").addEventListener("click", () => opsControl("stop_current"));
$("#ops-scen").addEventListener("change", () => opsParams("#ops-scen", "#ops-params"));
$("#sc-scen").addEventListener("change", () => opsParams("#sc-scen", "#sc-params"));
$("#ops-filter").addEventListener("change", () => opsRefresh());
$("#rep-days").addEventListener("change", setRepLinks);
$$("[data-skind]").forEach((b) => b.addEventListener("click", () => setSkind(b.dataset.skind)));
$("#sc-reset").addEventListener("click", () => editSched(null));
$("#ops-submit").addEventListener("click", async () => {
  try {
    const r = await api("POST", "/api/ops/jobs", { scenario: $("#ops-scen").value, params: paramValues("#ops-params"),
                                                  count: +$("#ops-count").value || 1 });
    msg($("#ops-msg"), `대기열에 추가: 작업 ${r.ids.join(", ")}`, "ok");
    opsRefresh();
  } catch (e) { msg($("#ops-msg"), e.message, "bad"); }
});
$("#sched-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = { name: $("#sc-name").value.trim(), scenario: $("#sc-scen").value, kind: O.skind,
                 every_min: +$("#sc-every").value, params: paramValues("#sc-params"),
                 times: $("#sc-times").value.split(/[,\s]+/).filter(Boolean),
                 days: $$("#sc-days input").filter((i) => i.checked).map((i) => +i.value) };
  try {
    await api(O.editId ? "PUT" : "POST", O.editId ? `/api/ops/schedules/${O.editId}` : "/api/ops/schedules", body);
    msg($("#sc-msg"), O.editId ? "저장했습니다." : "예약을 추가했습니다.", "ok");
    if (!O.editId) $("#sc-name").value = "";
    opsRefresh();
  } catch (err) { msg($("#sc-msg"), err.message, "bad"); }
});

// ---------------------------------------------------------------- 직접 조작 막대
$("#ctl-type").addEventListener("click", () => { const t = $("#ctl-text").value; if (t) control({ kind: "type", text: t }); });
$("#ctl-key-btn").addEventListener("click", () => {
  const k = $("#ctl-key").value.trim(); if (!k) return;
  control(k.includes("+") ? { kind: "hotkey", keys: k.split("+").map((x) => x.trim()) } : { kind: "key", key: k });
});
$("#ctl-home").addEventListener("click", () => control({ kind: "home" }));
$("#logs-clear").addEventListener("click", () => { $("#logs").textContent = ""; });

// ---------------------------------------------------------------- 시작
$("#btn-live").addEventListener("click", () => setLive(true));
$("#btn-snap").addEventListener("click", snapshot);
$$(".toolbar [data-mode]").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
window.addEventListener("beforeunload", (e) => { if (S.dirty) { e.preventDefault(); e.returnValue = ""; } });

(async function init() {
  setTfKind("template");
  await pollState();
  $("#key-list").append(...(S.state?.keys || []).map((k) => h("option", { value: k })));
  await loadTargets();
  await loadScenarioList("");
  setScenario({ name: "", description: "", steps: [] });
  loadFrame();
  pollLogs();
  if (location.hash === "#ops") $$(".tabs button").find((b) => b.dataset.tab === "ops").click();
})();
