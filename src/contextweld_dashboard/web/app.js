/* ContextWeld 관리자 대시보드 — 저장 기록 읽기 전용 재생기.
   네트워크 API·innerHTML·eval을 쓰지 않는다. 데이터는 패키지 안 data/*.js 를 <script>로만 읽는다. */
(function () {
  "use strict";
  var D = window.PAC_DASHBOARD_DATA = window.PAC_DASHBOARD_DATA || { runs: {}, raw: {} };
  var KEY_RE = /^[a-z0-9][a-z0-9-]{0,63}$/, RAW_RE = /^[a-z0-9][a-z0-9-]{0,63}\/[0-9]{4}$/;
  var TABS = [["summary", "실행 요약"], ["capture", "촬영 전후 비교"], ["timeline", "단계 타임라인"], ["recapture", "재촬영 설명"],
    ["evidence", "해석·문서 근거"], ["delivery", "전달 내역"], ["corrections", "수정·재검토 이력"]];
  var AV = { available: "● 있음", partial: "◐ 일부", absent: "○ 없음" };
  var ORIGIN = { model: "원본 · model", user: "수정 · user", demo_fixture: "수정 · demo_fixture (사람 검수 아님)", fixture: "시연 fixture",
    rule: "재판단 · rule", document: "문서 · document", system: "system", simulator: "시뮬레이터 · 평가/설계 정보 (모델 관측 아님)",
    dataset: "공개 데이터셋 출처 정보 (모델 관측 아님)", dashboard: "대시보드 계산 (원문 아님)" };
  var OUTCOME = { succeeded: ["성공", "good"], needs_review: ["검토 보류", "warning"], failed: ["기술 실패", "critical"], aborted: ["중단", "critical"], running: ["실행 중 기록", "serious"] };
  var EXPORT = { complete: ["묶음 완전", "good"], incomplete: ["묶음 불완전", "critical"], in_progress: ["기록 중", "serious"] };
  var DELIV = { received: ["모의 수신 확인 (용접 완료 아님)", "good"], blocked: ["전달 차단", "serious"], not_requested: ["전달 미요청", "neutral"], failed: ["전달 실패", "critical"] };
  var INTEG = { verified: ["✓ 묶음 검증 통과", "good"], failed: ["✕ 묶음 검증 실패", "critical"], partial: ["◐ 부분 검증", "warning"], unverifiable: ["? 검증 불가", "serious"] };
  var STEP = { success: ["✓ 성공", "good"], undetermined: ["! 미확정·보류", "warning"], failure: ["✕ 기술 실패", "critical"], recorded: ["• 기록됨 (판정 필드 없음)", "neutral"] };
  var NOTICE = { info: "ℹ 안내", warning: "! 주의", serious: "■ 경고", critical: "✕ 오류" };
  var STAGE_ST = { done: "✓", not_done: "○", failed: "✕", absent: "—", unknown: "?" };
  var S = { key: null, tab: "summary", cur: -1, mode: "replay", playing: false, timer: null, speed: 1, galSel: {} };
  var app = document.getElementById("app"), tip = null;

  function el(tag, cls, kids) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    (kids || []).forEach(function (k) { if (k !== null && k !== undefined) n.appendChild(typeof k === "string" ? document.createTextNode(k) : k); });
    return n;
  }
  function txt(tag, cls, s) { var n = el(tag, cls); n.textContent = s == null ? "" : String(s); return n; }
  function btn(label, fn, cls) { var b = txt("button", cls, label); b.type = "button"; b.addEventListener("click", fn); return b; }
  function load(src, ok, bad) {
    var s = document.createElement("script"); s.src = src;
    s.onload = ok; s.onerror = bad; document.head.appendChild(s);
  }
  function chip(label, tone) { return txt("span", "chip tone-" + (tone || "neutral"), label); }
  function enumChip(v, table) {
    if (!v || v.absent) return chip("기록 없음", "neutral");
    if (v.v === null) return chip("null (미기록)", "neutral");
    var t = table[v.v]; return chip((t ? t[0] + " · " : "") + v.v, t ? t[1] : "neutral");
  }
  function run() { return S.key ? D.runs[S.key] : null; }
  function curSeq() { var r = run(); if (!r || S.mode === "full" || S.cur < 0 || !r.steps.length) return null; return r.steps[S.cur].seq; }
  function visible(seq) { var c = curSeq(); return S.mode === "full" || c === null || seq === null || seq === undefined || seq <= c; }
  function maskNode(seq) { var n = txt("span", "masked", "아직 기록 전 — seq " + seq + "에서 기록 (현재 seq " + curSeq() + ")"); n.setAttribute("data-masked-seq", String(seq)); return n; }
  function short(s, n) { s = String(s); return s.length > n ? s.slice(0, n) + "…" : s; }

  function renderValue(V, mono) {
    var wrap = el("span", "vwrap");
    if (!V || typeof V !== "object" || !("v" in V)) { wrap.appendChild(txt("span", "absent", "값 없음")); return wrap; }
    var n;
    if (V.absent) n = txt("span", "val absent", "기록 없음 (키 없음)");
    else if (V.v === null) n = txt("span", "val nullv", "null (미기록)");
    else if (typeof V.v === "object") { n = txt("span", "val mono", JSON.stringify(V.v)); if (n.textContent.length > 400) { n = el("details", "val", [txt("summary", null, short(JSON.stringify(V.v), 120)), txt("pre", null, JSON.stringify(V.v, null, 2))]); } }
    else n = txt("span", "val" + (mono ? " mono" : ""), String(V.v));
    n.setAttribute("data-src", V.src || "dashboard");
    wrap.appendChild(n);
    if (V.o) wrap.appendChild(txt("span", "origin", ORIGIN[V.o] || V.o));
    var b = btn("ⓘ", function (e) { e.stopPropagation(); showSource(V); }, "src");
    b.setAttribute("aria-label", "출처 보기"); b.title = V.src ? "출처: " + V.src : "대시보드 계산: " + (V.n || "");
    wrap.appendChild(b);
    return wrap;
  }
  function showSource(V) {
    if (!V.src) { alert("대시보드 계산 값 (원문 아님)\n" + (V.n || "")); return; }
    var p = V.src.split("::"), root = p[0], rest = p[1].split("#");
    openRaw(root, rest[0], "출처 " + V.src + (V.o ? "\n출처 구분: " + (ORIGIN[V.o] || V.o) : ""));
  }

  function block(b) {
    var box = el("section", b.type === "notice" ? "" : "blk");
    if (b.type !== "notice" && b.title) { var h = txt("h3", null, b.title); if (b.seq != null) h.appendChild(txt("span", "seqb", "seq " + b.seq)); box.appendChild(h); }
    if (b.seq != null && !visible(b.seq)) { box.appendChild(maskNode(b.seq)); return box; }
    var f = R[b.type]; if (f) f(b, box); else box.appendChild(txt("p", "absent", "표시할 수 없는 블록: " + b.type));
    if (b.note) box.appendChild(txt("p", "note", b.note));
    return box;
  }
  function rowLine(r) {
    var tr = el("tr");
    tr.appendChild(txt("th", null, r.label));
    var td = el("td");
    if (r.seq != null && !visible(r.seq)) td.appendChild(maskNode(r.seq));
    else {
      td.appendChild(renderValue(r.value));
      if (r.unit) { td.appendChild(document.createTextNode(" ")); td.appendChild(renderValue(r.unit)); }
      if (r.tone) td.appendChild(chip(r.help || "", r.tone)); else if (r.help) td.appendChild(txt("span", "seqb", r.help));
      if (r.origin) td.appendChild(txt("span", "origin", ORIGIN[r.origin] || r.origin));
      if (r.seq != null) td.appendChild(txt("span", "seqb", "seq " + r.seq));
    }
    tr.appendChild(td); return tr;
  }
  var R = {
    notice: function (b, box) { box.className = "notice " + b.level; box.appendChild(txt("span", "lv", NOTICE[b.level] || b.level)); box.appendChild(document.createTextNode(b.text)); },
    fields: function (b, box) { var t = el("table"); (b.rows || []).forEach(function (r) { t.appendChild(rowLine(r)); }); box.appendChild(t); },
    table: function (b, box) {
      var rows = b.rows || [];
      if (!rows.length) { box.appendChild(txt("p", "absent", b.empty_text || "기록 없음")); return; }
      var t = el("table"), hr = el("tr"); (b.columns || []).forEach(function (c) { hr.appendChild(txt("th", null, c.label)); });
      t.appendChild(el("thead", null, [hr])); var tb = el("tbody");
      rows.forEach(function (r) {
        var tr = el("tr");
        if (r.seq != null && !visible(r.seq)) { var td = el("td"); td.colSpan = (b.columns || []).length; td.appendChild(maskNode(r.seq)); tr.appendChild(td); tb.appendChild(tr); return; }
        (b.columns || []).forEach(function (c, i) { var td = el("td"); var v = r.cells[c.key]; td.appendChild(v ? renderValue(v) : txt("span", "absent", "—")); if (i === 0 && r.origin) td.appendChild(txt("span", "origin", ORIGIN[r.origin] || r.origin)); tr.appendChild(td); });
        if (r.highlight) { tr.addEventListener("mouseenter", function () { highlight(r.highlight, true); tr.classList.add("hl"); }); tr.addEventListener("mouseleave", function () { highlight(r.highlight, false); tr.classList.remove("hl"); }); }
        tb.appendChild(tr);
      });
      t.appendChild(tb); box.appendChild(el("div", "tw", [t]));
    },
    image: function (b, box) { box.appendChild(figure(b.image, b.overlays || [], b.legend || [], b.caption)); },
    image_pair: function (b, box) {
      box.appendChild(txt("p", "note", "서로 다른 시점의 저장 이미지입니다. 각 이미지 아래 촬영 시각을 확인하세요."));
      var g = el("div", "pair");
      (b.items || []).forEach(function (it) { var c = el("div"); c.appendChild(txt("b", null, it.label)); c.appendChild(figure(it.image, [], [], null)); var t = el("table"); (it.rows || []).forEach(function (r) { t.appendChild(rowLine(r)); }); c.appendChild(t); g.appendChild(c); });
      box.appendChild(g);
    },
    cards: function (b, box) { (b.cards || []).forEach(function (c) { var t = el("table"); (c.rows || []).forEach(function (r) { t.appendChild(rowLine(r)); }); box.appendChild(el("div", "blk", [txt("b", null, c.title), t])); }); },
    stages: function (b, box) {
      var g = el("div", "stages");
      (b.stages || []).forEach(function (s) {
        var c = el("div", "stage");
        if (s.seq != null && !visible(s.seq)) { c.appendChild(txt("div", "st st-unknown", "… " + s.label)); c.appendChild(maskNode(s.seq)); g.appendChild(c); return; }
        c.appendChild(txt("div", "st st-" + s.state, (STAGE_ST[s.state] || "?") + " " + s.label));
        c.appendChild(txt("div", "note", s.state_label)); var t = el("table"); (s.rows || []).forEach(function (r) { t.appendChild(rowLine(r)); }); c.appendChild(t); g.appendChild(c);
      });
      box.appendChild(g);
    },
    diff: function (b, box) {
      (b.items || []).forEach(function (it) {
        var t = el("table");
        t.appendChild(el("tr", null, [txt("th", null, "수정 전 (" + (ORIGIN[it.origin_before] || it.origin_before) + ")"), el("td", null, [renderValue(it.before)])]));
        t.appendChild(el("tr", null, [txt("th", null, "수정 후 (" + (ORIGIN[it.origin_after] || it.origin_after) + ")"), el("td", null, [renderValue(it.after)])]));
        (it.rows || []).forEach(function (r) { t.appendChild(rowLine(r)); });
        box.appendChild(t);
      });
    },
    lineage: function (b, box) {
      var g = el("div", "lin");
      (b.nodes || []).forEach(function (nd, i) {
        if (i) g.appendChild(txt("span", "arrow", "→"));
        var c = el("div", "node", [txt("div", "note", nd.label + " · " + (nd.kind_label || "")), renderValue(nd.run_id)]);
        (nd.rows || []).forEach(function (r) { c.appendChild(el("table", null, [rowLine(r)])); });
        if (nd.run_key && D.index && hasRun(nd.run_key)) c.appendChild(btn("이 실행 열기", function () { select(nd.run_key); }));
        else if (nd.role !== "self") c.appendChild(txt("div", "note", "패키지 안 동일 묶음(manifest 해시 일치) 확인 불가 또는 미포함"));
        g.appendChild(c);
      });
      box.appendChild(g);
    },
    text: function (b, box) { var d = el("details"); d.open = !b.collapsed; d.appendChild(txt("summary", null, "펼치기/접기")); d.appendChild(txt("pre", null, b.value && b.value.v)); box.appendChild(d); },
    json: function (b, box) {
      var d = el("details"); d.open = !b.collapsed; d.appendChild(txt("summary", null, "구조화 원문 (JSON)" + (b.value && b.value.src ? " · " + b.value.src.split("::")[1] : "")));
      var pre = txt("pre", null, b.value && b.value.absent ? "기록 없음 (키 없음)" : JSON.stringify(b.value ? b.value.v : null, null, 2));
      pre.setAttribute("data-src", (b.value && b.value.src) || "dashboard"); d.appendChild(pre); box.appendChild(d);
    },
    raw_files: function (b, box) { var w = el("div", "chips"); (b.files || []).forEach(function (f) { w.appendChild(btn("원문: " + f.path, function () { openRaw(f.root, f.path); })); }); box.appendChild(w); },
    flow: function (b, box) {
      var g = el("div", "flow");
      (b.items || []).forEach(function (it) { var c = el("div", "it", [txt("b", null, it.label), txt("div", "st st-" + it.state, (STAGE_ST[it.state] || "?") + " " + ({ done: "기록 있음", not_done: "수행 안 됨", failed: "실패 기록", absent: "기록 없음", unknown: "알 수 없음" }[it.state] || it.state)), txt("p", null, it.summary)]); c.appendChild(btn("보기 →", function () { setTab(it.tab); })); g.appendChild(c); });
      box.appendChild(g);
    },
    group: function (b, box) {
      var items = b.items || []; var sel = S.galSel[b.id] || (items[0] && items[0].id);
      var strip = el("div", "gal");
      items.forEach(function (it) { var x = btn("", function () { S.galSel[b.id] = it.id; render(); }); x.setAttribute("aria-pressed", String(it.id === sel)); if (it.thumb) { var im = el("img"); im.src = it.thumb.path; im.alt = it.label; x.appendChild(im); } x.appendChild(txt("span", null, it.label)); strip.appendChild(x); });
      box.appendChild(strip);
      items.forEach(function (it) { if (it.id === sel) (it.blocks || []).forEach(function (c) { box.appendChild(block(c)); }); });
    },
    video: function (b, box) { var v = el("video"); v.controls = true; v.src = b.path; box.appendChild(v); }
  };

  function figure(img, overlays, legend, caption) {
    var f = el("figure", "fig"); var wrap = el("div");
    if (!img) { wrap.appendChild(txt("p", "err", "이미지 기록 없음")); return wrap; }
    var im = el("img"); im.src = img.path; im.alt = img.label || "원본 이미지";
    im.onerror = function () { f.replaceWith(txt("p", "err", "이미지 파일을 불러오지 못했습니다(패키지 누락·손상 가능): " + img.path)); };
    f.appendChild(im);
    var hidden = {};
    var NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg");
    if (img.width && img.height) { svg.setAttribute("viewBox", "0 0 " + img.width + " " + img.height); svg.setAttribute("preserveAspectRatio", "none"); }
    function draw() {
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      overlays.forEach(function (o) {
        if (hidden[o.kind] || (o.seq != null && !visible(o.seq))) return;
        var color = getComputedStyle(document.documentElement).getPropertyValue("--k-" + o.kind) || "#e34948";
        [true, false].forEach(function (halo) {
          var s;
          if (o.shape.type === "polygon") { s = document.createElementNS(NS, "polygon"); s.setAttribute("points", o.shape.points.map(function (p) { return Number(p[0]) + "," + Number(p[1]); }).join(" ")); }
          else { var q = o.shape.xyxy.map(Number); s = document.createElementNS(NS, "rect"); s.setAttribute("x", q[0]); s.setAttribute("y", q[1]); s.setAttribute("width", Math.max(0, q[2] - q[0])); s.setAttribute("height", Math.max(0, q[3] - q[1])); }
          s.setAttribute("class", halo ? "halo" : "ov" + (o.kind.indexOf("vlm") === 0 ? " dash" : ""));
          if (!halo) { s.setAttribute("stroke", color.trim()); s.setAttribute("data-ov", o.id); s.setAttribute("data-src", o.src); s.setAttribute("tabindex", "0");
            s.addEventListener("mouseenter", function (e) { showTip(e, (o.label || o.id) + "\n" + (o.value && o.value.v != null ? String(o.value.v) + "\n" : "") + (ORIGIN[o.origin] || o.origin) + "\n" + o.src); });
            s.addEventListener("mouseleave", hideTip); }
          svg.appendChild(s);
        });
      });
    }
    draw(); f.appendChild(svg); wrap.appendChild(f);
    if (overlays.length) {
      var kinds = []; overlays.forEach(function (o) { if (kinds.indexOf(o.kind) < 0) kinds.push(o.kind); });
      var lg = el("div", "legend");
      kinds.forEach(function (k) {
        var cb = el("input"); cb.type = "checkbox"; cb.checked = true; cb.addEventListener("change", function () { hidden[k] = !cb.checked; draw(); });
        var lab = (legend.filter(function (x) { return x.kind === k; })[0] || {}).label || k;
        var sw = el("span", "sw"); sw.style.background = "var(--k-" + k + ")";
        var count = overlays.filter(function (o) { return o.kind === k; }).length;
        lg.appendChild(el("label", null, [cb, sw, lab + " (" + count + ")" + (k.indexOf("vlm") === 0 ? " 점선" : " 실선")]));
      });
      wrap.appendChild(lg);
    }
    wrap.appendChild(txt("p", "note", "원본 이미지(픽셀 미변경) · " + img.width + "×" + img.height + " · SHA-256 " + String(img.sha256 || "").slice(0, 12) + " · 오버레이는 저장 좌표로 그린 별도 표시층" + (caption ? " · " + caption : "")));
    return wrap;
  }
  function highlight(ids, on) { ids.forEach(function (id) { document.querySelectorAll('[data-ov="' + String(id).replace(/["\\]/g, "") + '"]').forEach(function (n) { n.classList.toggle("on", on); }); }); }
  function showTip(e, s) { hideTip(); tip = txt("div", "tip", s); tip.style.whiteSpace = "pre-wrap"; tip.style.left = (e.clientX + 12) + "px"; tip.style.top = (e.clientY + 12) + "px"; document.body.appendChild(tip); }
  function hideTip() { if (tip) { tip.remove(); tip = null; } }

  function openRaw(root, path, extra) {
    var r = D.runs[root] || run(); var f = null;
    if (r) (r.files || []).forEach(function (x) { if (x.path === path) f = x; });
    var m = el("div", "modal"); m.setAttribute("role", "dialog");
    var close = btn("닫기 (Esc)", function () { m.remove(); });
    m.appendChild(el("div", "mh", [txt("b", null, root + " :: " + path), close]));
    if (extra) m.appendChild(txt("pre", null, extra));
    if (!f) { m.appendChild(txt("p", "err", "이 파일은 원문 목록에 없습니다(다른 실행의 파일이거나 패키지에서 제외).")); document.body.appendChild(m); close.focus(); return; }
    m.appendChild(txt("div", "note", "크기 " + f.size + " B · 내보내기 SHA-256 " + f.sha256 + " · 원본 기록 SHA-256 " + (f.recorded_sha256 || "기록 없음") + " · 상태 " + f.state));
    var body = el("div"); m.appendChild(body); document.body.appendChild(m); close.focus();
    if (!f.raw_id || !RAW_RE.test(f.raw_id)) { body.appendChild(txt("p", "note", "텍스트 원문 사본 없음(이미지·이진 파일). 패키지의 bundles/" + root + "/" + path + " 파일을 직접 여세요.")); return; }
    function show() {
      var raw = D.raw[f.raw_id]; var st = txt("p", "note", "브라우저 SHA-256 계산 중…"); body.appendChild(st);
      body.appendChild(txt("pre", "mono", raw.text));
      if (window.crypto && crypto.subtle && window.TextEncoder) crypto.subtle.digest("SHA-256", new TextEncoder().encode(raw.text)).then(function (h) {
        var hex = Array.prototype.map.call(new Uint8Array(h), function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
        var ok = hex === f.sha256 && (!f.recorded_sha256 || hex === f.recorded_sha256);
        st.textContent = (ok ? "✓ 브라우저에서 계산한 SHA-256이 원본 기록과 일치" : "✕ SHA-256 불일치 — 패키지 손상 가능") + " (" + hex.slice(0, 16) + "…)";
      }); else st.textContent = "이 브라우저에서는 SHA-256을 계산할 수 없습니다.";
    }
    if (D.raw[f.raw_id]) show(); else load("data/raw/" + f.raw_id + ".js", show, function () { body.appendChild(txt("p", "err", "원문 데이터 파일 누락: data/raw/" + f.raw_id + ".js")); });
  }

  function hasRun(k) { return D.index.runs.some(function (r) { return r.key === k; }); }
  function select(k) { if (!KEY_RE.test(k) || !hasRun(k)) return; stop(); S.key = k; S.cur = -1; S.galSel = {};
    if (D.runs[k]) { initRun(); render(); return; }
    render(); load("data/runs/" + k + ".js", function () { initRun(); render(); }, function () { S.loadErr = k; render(); }); }
  function initRun() { var r = run(); if (!r) return; S.loadErr = null; var en = r.summary.replay && r.summary.replay.enabled && r.steps.length;
    S.mode = en ? S.mode : "full"; if (S.pendingSeq != null && r.steps.length) { r.steps.forEach(function (s, i) { if (s.seq === S.pendingSeq) S.cur = i; }); S.pendingSeq = null; } if (S.cur < 0 && r.steps.length) S.cur = 0; }
  function setTab(t) { S.tab = t; render(); }
  function stop() { S.playing = false; if (S.timer) clearInterval(S.timer); S.timer = null; }
  function step(d) { var r = run(); if (!r || !r.steps.length) return; S.cur = Math.max(0, Math.min(r.steps.length - 1, S.cur + d)); render(); }
  function play() { var r = run(); if (!r || !r.steps.length) return; if (S.playing) { stop(); render(); return; }
    if (S.cur >= r.steps.length - 1) S.cur = 0; S.mode = "replay"; S.playing = true;
    S.timer = setInterval(function () { if (S.cur >= run().steps.length - 1) { stop(); render(); return; } S.cur += 1; render(); }, 900 / S.speed); render(); }

  function header() {
    var info = D.exportInfo || {};
    var top = el("header", "top", [txt("h1", null, "ContextWeld 관리자 대시보드"), txt("span", "sub", "저장 기록 오프라인 재생 · 읽기 전용"),
      txt("span", "pill", "네트워크 연결 차단(CSP)"), txt("span", "pill", "실행 기능 없음 · 추론·재검색·카메라·전송·재검토 호출 0"), el("span", "grow"),
      txt("span", "pill", info.source_repo_head ? "원본 커밋 " + String(info.source_repo_head).slice(0, 9) + (info.source_repo_dirty ? " (미커밋 변경 있음)" : "") : "내보내기 정보 없음"),
      btn("테마 전환", function () { var c = document.documentElement.getAttribute("data-theme"); document.documentElement.setAttribute("data-theme", c === "dark" ? "light" : "dark"); })]);
    return top;
  }
  function sidebar() {
    var side = el("nav", "side"); side.setAttribute("aria-label", "실행 목록");
    var q = el("input"); q.placeholder = "실행 검색 (ID·시나리오)"; q.value = S.q || ""; q.addEventListener("input", function () { S.q = q.value; render(); setTimeout(function () { var n = document.querySelector(".side input"); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }, 0); });
    side.appendChild(q);
    D.index.groups.forEach(function (g) {
      var runs = D.index.runs.filter(function (r) { return r.group === g.key && (!S.q || (r.key + " " + JSON.stringify(r.summary.run_id) + JSON.stringify(r.summary.scenario_id) + r.summary.title).toLowerCase().indexOf(S.q.toLowerCase()) >= 0); });
      if (!runs.length) return;
      side.appendChild(txt("div", "grp", g.label + " · " + runs.length));
      runs.forEach(function (r) {
        var s = r.summary, c = btn("", function () { select(r.key); }, "runcard"); c.setAttribute("data-run", r.key); c.setAttribute("aria-current", String(r.key === S.key));
        c.appendChild(txt("div", "t", s.title)); c.appendChild(txt("div", "s", r.kind_label + (s.scenario_id && s.scenario_id.v ? " · " + s.scenario_id.v : "") + (s.note ? " · " + s.note : "")));
        var ch = el("div", "chips");
        if (r.group !== "scene" && r.group !== "reference") { ch.appendChild(enumChip(s.run_outcome, OUTCOME)); ch.appendChild(enumChip(s.export_status, EXPORT)); if (s.delivery_status && !s.delivery_status.absent) ch.appendChild(enumChip(s.delivery_status, DELIV)); }
        var ig = INTEG[r.integrity.state] || ["? " + r.integrity.state, "neutral"]; ch.appendChild(chip(ig[0], ig[1]));
        c.appendChild(ch); side.appendChild(c);
      });
    });
    return side;
  }
  function runView() {
    var main = el("main", "main");
    var nt = el("div", "notices"), d = el("details"); d.appendChild(txt("summary", null, "전역 안내 · 제외 자료 (" + (D.index.notices.length + D.index.exclusions.length) + ")"));
    D.index.notices.forEach(function (n) { d.appendChild(block({ type: "notice", level: n.level, text: n.text })); });
    D.index.exclusions.forEach(function (x) { d.appendChild(block({ type: "notice", level: "info", text: "제외: " + x.item + " — " + x.reason })); });
    nt.appendChild(d); main.appendChild(nt);
    if (!S.key) { main.appendChild(txt("div", "empty", "왼쪽 목록에서 실행을 선택하세요. 종류(인식·문서 검토·재검토·장면·참조)는 서로 다른 자료입니다.")); return main; }
    if (S.loadErr === S.key) { main.appendChild(txt("div", "empty err", "실행 데이터 파일(data/runs/" + S.key + ".js)을 불러오지 못했습니다. 패키지 누락·손상 가능 — tools/verify_package.py로 확인하세요.")); return main; }
    var r = run(); if (!r) { main.appendChild(txt("p", "loading", "불러오는 중…")); return main; }
    var s = r.summary, entry = D.index.runs.filter(function (x) { return x.key === S.key; })[0];
    var head = el("div", "runhead", [txt("h2", null, s.title), txt("div", "sub", s.kind_label + " · " + s.group_label + " · 원본 위치 " + s.display_path)]);
    var ch = el("div", "chips");
    var fin = s.final_seq != null && S.mode === "replay" && curSeq() !== null && curSeq() < s.final_seq;
    ["run_id", "scenario_id", "run_kind", "capture_mode"].forEach(function (k) { ch.appendChild(el("span", "chip", [k + ": ", renderValue(s[k])])); });
    var lab = fin ? "최종 기록 (실행 종료 시 확정 · seq " + s.final_seq + ") " : "최종 기록 ";
    if (s.run_outcome) { var c1 = enumChip(s.run_outcome, OUTCOME); c1.prepend(lab + "run_outcome: "); if (fin) c1.style.opacity = ".5"; ch.appendChild(c1); }
    if (s.export_status) { var c2 = enumChip(s.export_status, EXPORT); c2.prepend("export_status: "); ch.appendChild(c2); }
    if (s.delivery_status && !s.delivery_status.absent) { var c3 = enumChip(s.delivery_status, DELIV); c3.prepend(lab + "delivery_status: "); if (fin) c3.style.opacity = ".5"; ch.appendChild(c3); }
    var ig = INTEG[r.integrity.state] || ["? " + r.integrity.state, "neutral"];
    var ib = btn(ig[0] + " — 상세", function () { var lines = [r.integrity.label || "", r.integrity.message ? "메시지: " + r.integrity.message : "", "원본과 사본 검증 결과 일치: " + r.integrity.copy_matches_original].concat((r.integrity.checks || []).map(function (c) { return (c.state === "pass" ? "✓ " : c.state === "fail" ? "✕ " : "• ") + c.name + " — " + c.detail + (c.items ? " [" + c.items.slice(0, 8).join(", ") + (c.item_count > 8 ? " …" : "") + "]" : ""); })).concat((r.integrity.excluded || []).map(function (x) { return "패키지 제외: " + x.item + " — " + x.reason; }));
      var m = el("div", "modal", [el("div", "mh", [txt("b", null, "무결성 검사 · " + S.key), btn("닫기 (Esc)", function () { m.remove(); })]), txt("pre", null, lines.filter(Boolean).join("\n"))]); document.body.appendChild(m); }, "chip tone-" + ig[1]);
    ch.appendChild(ib);
    head.appendChild(ch);
    var fl = el("div", "chips"); (s.flags || []).forEach(function (f) { fl.appendChild(el("span", "chip", [f.label + ": ", renderValue(f.value)])); }); head.appendChild(fl);
    if (entry && entry.viewer_html) { var a = el("a"); a.href = entry.viewer_html; a.target = "_blank"; a.rel = "noopener"; a.textContent = "기존 단건 HTML 조회기로 보기(기존 exporter 화면, 새 탭)"; head.appendChild(a); }
    main.appendChild(head); main.appendChild(bar(r));
    var tabs = el("div", "tabs"); tabs.setAttribute("role", "tablist");
    TABS.forEach(function (t, i) { var tb = r.tabs[t[0]]; var b = btn("", function () { setTab(t[0]); }); b.setAttribute("role", "tab"); b.setAttribute("data-tab", t[0]); b.setAttribute("aria-selected", String(S.tab === t[0])); b.appendChild(document.createTextNode((i + 1) + ". " + t[1])); b.appendChild(txt("span", "av", AV[tb.availability])); tabs.appendChild(b); });
    main.appendChild(tabs);
    if (S.mode === "full" && r.steps.length) main.appendChild(txt("div", "full-banner", "최종 기록 전체 보기 — 서로 다른 시점(seq)의 기록이 함께 보입니다. 각 항목의 seq 표시를 확인하세요."));
    var tb = r.tabs[S.tab];
    if (tb.availability !== "available") main.appendChild(txt("div", "empty", (tb.availability === "absent" ? "○ 이 실행에는 해당 기록이 없습니다 — " : "◐ 일부만 있음 — ") + tb.absent_reason));
    if (S.tab === "timeline") main.appendChild(timeline(r));
    tb.blocks.forEach(function (b) { main.appendChild(block(b)); });
    return main;
  }
  function bar(r) {
    var en = r.summary.replay && r.summary.replay.enabled && r.steps.length;
    var b = el("div", "bar"); b.setAttribute("aria-label", "재생 조작");
    if (!en) { b.appendChild(txt("b", null, "재생 불가")); b.appendChild(txt("span", "cur", (r.summary.replay && r.summary.replay.reason) || "사건 기록 없음")); return b; }
    function A(label, act, fn) { var x = btn(label, fn); x.setAttribute("data-action", act); return x; }
    b.appendChild(A("⏮ 처음", "first", function () { stop(); S.cur = 0; S.mode = "replay"; render(); }));
    b.appendChild(A("◀ 이전", "prev", function () { stop(); step(-1); }));
    b.appendChild(A(S.playing ? "⏸ 일시정지" : "▶ 재생", "play", play));
    b.appendChild(A("다음 ▶", "next", function () { stop(); step(1); }));
    b.appendChild(A("끝 ⏭", "last", function () { stop(); S.cur = r.steps.length - 1; render(); }));
    var rg = el("input"); rg.type = "range"; rg.min = "0"; rg.max = String(r.steps.length - 1); rg.value = String(Math.max(0, S.cur)); rg.setAttribute("aria-label", "단계 위치");
    rg.addEventListener("input", function () { stop(); S.cur = Number(rg.value); render(); }); b.appendChild(rg);
    var st = r.steps[Math.max(0, S.cur)], sc = STEP[st.status.class] || ["?", "neutral"];
    b.appendChild(txt("span", "cur", "seq " + st.seq + " / " + r.steps[r.steps.length - 1].seq + " · " + st.label));
    b.appendChild(chip(sc[0], sc[1]));
    b.appendChild(txt("span", "cur", (st.recorded_at_utc.v || "") + (st.elapsed_ms.v != null ? " · +" + (st.elapsed_ms.v / 1000).toFixed(1) + "s" : "")));
    var sp = el("select"); [0.5, 1, 2, 4].forEach(function (v) { var o = txt("option", null, v + "×"); o.value = String(v); o.selected = v === S.speed; sp.appendChild(o); });
    sp.setAttribute("aria-label", "재생 속도"); sp.addEventListener("change", function () { S.speed = Number(sp.value); if (S.playing) { stop(); play(); } }); b.appendChild(sp);
    b.appendChild(A(S.mode === "replay" ? "최종 기록 전체 보기로" : "재생 시점 보기로", "mode", function () { stop(); S.mode = S.mode === "replay" ? "full" : "replay"; render(); }));
    return b;
  }
  function timeline(r) {
    var g = el("div", "steps"), list = el("div", "steplist blk"), c = curSeq();
    r.steps.forEach(function (s, i) {
      var fut = c !== null && s.seq > c;
      var row = btn("", function () { stop(); S.mode = "replay"; S.cur = i; render(); }, "steprow" + (i === S.cur && S.mode === "replay" ? " cur" : "") + (fut ? " future" : ""));
      row.setAttribute("data-seq", String(s.seq));
      row.appendChild(txt("span", "mono", "seq " + s.seq));
      if (fut) { row.appendChild(txt("span", null, "아직 진행 전")); row.appendChild(txt("span", null, "")); }
      else { row.appendChild(txt("span", null, s.label + " · " + (s.stage.v || "") + (s.type.absent ? "" : " / " + s.type.v))); var sc = STEP[s.status.class]; row.appendChild(chip(sc[0], sc[1])); }
      list.appendChild(row);
    });
    g.appendChild(list);
    var s = r.steps[Math.max(0, S.cur)], det = el("div", "blk");
    if (!s) { det.appendChild(txt("p", null, "단계 없음")); g.appendChild(det); return g; }
    det.appendChild(txt("h3", null, "선택 단계 seq " + s.seq + " · " + s.label));
    var t = el("table");
    [["상태", null], ["판단 근거", s.status.basis], ["event_id", s.event_id], ["type", s.type], ["stage", s.stage], ["producer", s.producer], ["recorded_at_utc", s.recorded_at_utc], ["elapsed_ms", s.elapsed_ms],
      ["parent_event_ids", s.parent_event_ids], ["input_frame_ids", s.input_frame_ids], ["input_result_ids", s.input_result_ids], ["request_id", s.request_id], ["command_id", s.command_id], ["payload_ref", s.payload_ref]].forEach(function (p) {
      var tr = el("tr"); tr.appendChild(txt("th", null, p[0])); var td = el("td");
      if (p[0] === "상태") { var sc = STEP[s.status.class]; td.appendChild(chip(sc[0] + " · " + s.status.label, sc[1])); if (s.status.note) td.appendChild(txt("span", "seqb", s.status.note)); }
      else if (p[1]) td.appendChild(renderValue(p[1], true)); else td.appendChild(txt("span", "absent", "판단 근거 필드 없음"));
      tr.appendChild(td); t.appendChild(tr);
    });
    det.appendChild(t);
    if (s.payload) det.appendChild(btn("출력 원문 열기: " + s.payload.path, function () { openRaw(s.payload.root, s.payload.path); }));
    (s.frames || []).forEach(function (f) { det.appendChild(txt("div", "note", "입력 프레임 " + (f.label || ""))); det.appendChild(figure(f, [], [], null)); });
    g.appendChild(det);
    return g;
  }
  function render() {
    var keep = window.scrollY;
    while (app.firstChild) app.removeChild(app.firstChild);
    app.appendChild(header()); app.appendChild(sidebar()); app.appendChild(runView());
    window.scrollTo(0, keep);
    var r = run(); document.body.dataset.run = r ? S.key : ""; document.body.dataset.tab = S.tab; document.body.dataset.mode = S.mode;
    document.body.dataset.cursor = curSeq() === null ? "" : String(curSeq());
    var h = S.key ? "#run=" + S.key + "&tab=" + S.tab + "&mode=" + S.mode + (curSeq() !== null ? "&seq=" + curSeq() : "") : "";
    if (h && location.hash !== h) history.replaceState(null, "", h);
  }
  document.addEventListener("keydown", function (e) {
    if (e.target && /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
    if (e.key === "Escape") { document.querySelectorAll(".modal").forEach(function (m) { m.remove(); }); return; }
    if (!run()) return;
    if (e.key === " ") { e.preventDefault(); play(); } else if (e.key === "ArrowRight") { stop(); step(1); } else if (e.key === "ArrowLeft") { stop(); step(-1); }
    else if (e.key === "Home") { stop(); S.cur = 0; render(); } else if (e.key === "End") { stop(); S.cur = run().steps.length - 1; render(); }
    else if (/^[1-7]$/.test(e.key)) setTab(TABS[Number(e.key) - 1][0]);
  });
  function start() {
    if (!D.index || !D.index.runs) { app.textContent = ""; app.appendChild(txt("p", "err", "화면 데이터(data/index.js)를 불러오지 못했습니다. 패키지 파일이 빠졌거나 손상됐을 수 있습니다. tools/verify_package.py로 확인하세요.")); return; }
    var p = {}; location.hash.replace(/^#/, "").split("&").forEach(function (kv) { var a = kv.split("="); if (a[0]) p[a[0]] = decodeURIComponent(a[1] || ""); });
    if (p.tab && TABS.some(function (t) { return t[0] === p.tab; })) S.tab = p.tab;
    if (p.mode === "full" || p.mode === "replay") S.mode = p.mode;
    if (p.seq && /^[0-9]+$/.test(p.seq)) S.pendingSeq = Number(p.seq);
    document.body.dataset.ready = "1";
    if (p.run && KEY_RE.test(p.run) && hasRun(p.run)) select(p.run); else { if (!D.index.runs.length) { app.textContent = ""; app.appendChild(txt("div", "empty", "표시할 실행이 없습니다.")); return; } render(); }
  }
  load("data/index.js", function () { load("data/export-info.js", start, start); }, function () { D.index = null; start(); });
})();
