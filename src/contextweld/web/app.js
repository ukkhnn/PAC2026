"use strict";

const $ = (selector) => document.querySelector(selector);
const state = { scenarios: [], selected: null, upload: null, run: null, busy: false, overlays: true, observation: null, history: [] };
const labels = { part_id: "부재번호", seam_id: "이음부", weld_type: "작업 종류", size_mm: "치수", position: "자세" };
const origins = { visual_candidate: "시각 후보", plan_narrowed: "작업계획으로 좁힘", operator_memory: "확인 이력으로 좁힘", operator_correction: "작업자 수정", unresolved: "확인 필요" };
const statuses = { candidate_ready: ["조건 후보 준비", "ready"], review_required: ["원본 확인 필요", "review"], blocked: ["판단 보류", "blocked"], approved: ["시연 결과 확인됨", "ready"], held: ["작업자가 보류함", "blocked"] };
let toastTimer;

function esc(value) { return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]); }
function notify(text, error = false) { const node = $("#toast"); node.textContent = text; node.className = `toast${error ? " error" : ""}`; node.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { node.hidden = true; }, 7000); }
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "요청을 완료하지 못했습니다.");
  return result;
}
function busy(value, text = "맥락과 함께 분석") {
  state.busy = value;
  document.querySelectorAll("button, #image-upload, #context-form input, #context-form select").forEach((node) => { node.disabled = value; });
  $("#analyze-button").innerHTML = `${esc(value ? text : "맥락과 함께 분석")} <span>${value ? "…" : "→"}</span>`;
}
function fillContext(context) {
  for (const [key, value] of Object.entries(context)) {
    const node = $("#context-form").elements.namedItem(key);
    if (!node) continue;
    if (node.type === "checkbox") node.checked = value === true;
    else node.value = value ?? "";
  }
}
function readContext() {
  const result = {};
  for (const node of $("#context-form").elements) {
    if (!node.name) continue;
    if (node.type === "checkbox") result[node.name] = node.checked;
    else if (node.type === "number") result[node.name] = node.value === "" ? null : Number(node.value);
    else result[node.name] = node.name === "plan_revision" ? node.value.trim() : node.value.trim().toUpperCase();
  }
  return result;
}
function renderScenarios() {
  $("#scenario-grid").innerHTML = state.scenarios.map((item, index) => `<button class="scenario${state.selected?.id === item.id && !state.upload ? " selected" : ""}" data-scenario="${esc(item.id)}" aria-pressed="${state.selected?.id === item.id && !state.upload}"><span class="number">CASE 0${index + 1}</span><strong>${esc(item.title)}</strong><small>${esc(item.tag)}</small></button>`).join("");
  document.querySelectorAll("[data-scenario]").forEach((node) => node.addEventListener("click", () => chooseScenario(node.dataset.scenario)));
}
function clearRun() {
  state.run = null;
  $("#result-status").className = "status neutral";
  $("#result-status").textContent = "분석 전";
  $("#result-body").className = "empty-result";
  $("#result-body").innerHTML = '<span class="empty-icon">⌗</span><strong>판단의 연결을 확인하세요.</strong><p>사진과 계획이 일치하는지,<br>어떤 기준이 적용되는지 확인합니다.</p>';
  for (const id of ["compare-card", "evidence-card", "review-card"]) $(`#${id}`).hidden = true;
  $("#review-note").value = "";
  $("#correction-size").value = "";
}
function chooseScenario(id) {
  if (state.busy) return;
  state.selected = state.scenarios.find((item) => item.id === id);
  state.upload = null;
  state.observation = null;
  clearRun();
  fillContext(state.selected.context);
  renderScenarios();
  renderInput(state.selected);
}
function renderInput(input) {
  $("#source-image").src = input.source?.image_url || input.image_url;
  $("#image-description").textContent = input.description || "업로드한 사진 · 실제 로컬 문자 인식";
  const actual = (input.source?.provider || input.provider) === "apple_vision_local";
  $("#source-badge").textContent = actual ? "업로드 사진 · 실제 Apple Vision OCR" : "합성 시연 이미지 · 준비된 인식 후보";
  $("#source-badge").className = `source-badge${actual ? " actual" : ""}`;
  renderObservations(input.observations);
}
function renderObservations(observations) {
  $("#observation-count").textContent = `${observations.length}개 영역`;
  $("#observations").innerHTML = observations.map((item, index) => `<div class="observation${state.observation === item.id ? " selected" : ""}" data-observation="${esc(item.id)}" tabindex="0" role="button" aria-label="${index + 1}번 표기 영역 선택"><span class="mark-number">${String(index + 1).padStart(2, "0")}</span><div class="observation-text"><strong>${esc(item.candidates[0]?.text || "인식 없음")}</strong>${item.candidates.slice(1).map((candidate) => `<span class="candidate-secondary">다른 후보 · ${esc(candidate.text)}</span>`).join("")}</div><span class="ocr-score">점수 ${Number(item.candidates[0]?.score || 0).toFixed(2)}</span></div>`).join("");
  $("#overlays").innerHTML = observations.map((item, index) => `<button class="overlay${state.observation === item.id ? " selected" : ""}" data-observation="${esc(item.id)}" aria-label="${index + 1}번 표기 영역" style="left:${item.bbox[0] * 100}%;top:${item.bbox[1] * 100}%;width:${item.bbox[2] * 100}%;height:${item.bbox[3] * 100}%"><span>${String(index + 1).padStart(2, "0")}</span></button>`).join("");
  $("#overlays").hidden = !state.overlays;
  document.querySelectorAll("[data-observation]").forEach((node) => {
    const select = () => { state.observation = node.dataset.observation; renderObservations(observations); };
    node.addEventListener("click", select);
    node.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); } });
  });
}
function valueText(field, decision) {
  const value = decision.fields[field];
  if (value !== null && value !== undefined) return `${value}${field === "size_mm" ? " mm" : ""}`;
  const values = decision.candidates[field].map((item) => item.value);
  return values.length ? `${values.join(" / ")} · 미확정` : "읽지 못함";
}
function renderRun(run) {
  state.run = run;
  const decision = run.contextual;
  const status = run.review_status === "pending" ? decision.status : run.review_status;
  const [name, css] = statuses[status];
  $("#result-status").textContent = name;
  $("#result-status").className = `status ${css}`;
  $("#result-body").className = "result-content";
  const recipe = decision.recipe;
  $("#result-body").innerHTML = `${recipe ? `<div class="recipe-card"><span class="recipe-label">DEMO PROGRAM CANDIDATE</span><strong>${esc(recipe.id)}</strong><p>${esc(recipe.title)} · 시연용 기준</p></div>` : '<p class="no-recipe">조건 후보를 확정할 근거가 부족합니다.</p>'}<div class="result-metrics"><div><small>작업 종류</small><strong>${esc(decision.fields.weld_type || "미확정")}</strong></div><div><small>치수</small><strong>${esc(valueText("size_mm", decision))}</strong></div><div><small>자세</small><strong>${esc(decision.fields.position || "미확정")}</strong></div></div>${decision.memory_used ? `<div class="memory-card">◷ 같은 작업의 확인 이력을 참조했습니다.<br>${esc(decision.memory_used.note)}<br><small>확인 기록 ${esc(decision.memory_used.review_id.slice(0, 8))}</small></div>` : ""}${decision.blockers.map((item) => `<div class="reason hard">${esc(item.text)}</div>`).join("")}${decision.reasons.map((item) => `<div class="reason">${esc(item.text)}</div>`).join("")}<p class="small-note" style="padding:12px 0 0">전류 · 전압 · 이동속도: 실제 WPS 확보 후 연결</p>`;
  $("#compare-card").hidden = false;
  $("#evidence-card").hidden = false;
  $("#review-card").hidden = false;
  $("#comparison").innerHTML = '<div class="comparison-row header"><span>해석 항목</span><span>표기만 해석</span><span>맥락과 함께 해석</span></div>' + Object.keys(labels).map((field) => `<div class="comparison-row"><span>${labels[field]}</span><div>${esc(valueText(field, run.baseline))}<small>${esc(origins[run.baseline.field_origins[field]])}</small></div><div class="${run.baseline.fields[field] !== decision.fields[field] ? "value-improved" : ""}">${esc(valueText(field, decision))}<small>${esc(origins[decision.field_origins[field]])}</small></div></div>`).join("");
  $("#evidence").innerHTML = decision.evidence.map((doc) => `<article class="evidence-item"><span class="doc-id">${esc(doc.id)} · ${esc(doc.version)}</span><h3>${esc(doc.title)}</h3><p>${esc(doc.text)}</p><small>${esc(doc.source_file)} · 시연용 가상 규칙</small></article>`).join("");
  $("#review-events").innerHTML = run.reviews.map((event) => `<div class="review-event"><strong>${event.action === "approve" ? "시연 결과 확인" : "보류 기록"}${Object.keys(event.corrections).length ? " · 표기 수정" : ""}</strong> — ${esc(event.note)}<small>${new Date(event.created_at).toLocaleString("ko-KR")} · 기록 ${esc(event.id.slice(0, 8))}</small></div>`).join("");
}
async function analyze() {
  if (state.busy) return;
  busy(true, "맥락과 기준을 대조 중");
  try {
    const run = await api("/api/analyze", { ...(state.upload ? { upload_id: state.upload.upload_id } : { scenario_id: state.selected.id }), context: readContext() });
    renderRun(run);
    await loadHistory();
    notify("분석을 기록했습니다. 판단 근거와 확인할 항목을 살펴보세요.");
  } catch (error) { notify(error.message, true); }
  finally { busy(false); }
}
async function review(action) {
  if (!state.run || state.busy) return;
  const note = $("#review-note").value.trim();
  if (!note) { notify("확인 또는 보류 이유를 입력해주세요.", true); $("#review-note").focus(); return; }
  const correction = $("#correction-size").value;
  busy(true, "확인 이력을 저장 중");
  try {
    renderRun(await api("/api/review", { run_id: state.run.id, revision: state.run.revision, action, note, corrections: correction === "" ? {} : { size_mm: Number(correction) } }));
    $("#review-note").value = "";
    $("#correction-size").value = "";
    await loadHistory();
    notify(action === "approve" ? "시연 해석을 확인했습니다. 같은 작업에서 이력을 참조할 수 있습니다." : "보류 이유를 기록했습니다.");
  } catch (error) { notify(error.message, true); }
  finally { busy(false); }
}
async function loadHistory() {
  state.history = await api("/api/history");
  $("#history-count").textContent = state.history.length;
  $("#history-list").innerHTML = state.history.length ? state.history.map((run, index) => {
    const status = run.review_status === "pending" ? run.contextual.status : run.review_status;
    const [name, css] = statuses[status];
    return `<button class="history-item" data-run="${esc(run.id)}"><span class="index">${String(index + 1).padStart(2, "0")}</span><div><strong>${esc(run.contextual.fields.part_id || "부재 미확정")} · ${esc(run.contextual.fields.seam_id || "이음부 미확정")}</strong><small>${new Date(run.created_at).toLocaleString("ko-KR")} · ${run.source.provider === "fixture_candidates" ? "시연 후보" : "실제 OCR"} · ${esc(run.id.slice(0, 8))}</small></div><span class="status ${css}">${name}</span></button>`;
  }).join("") : '<div class="history-empty">아직 분석 기록이 없습니다. 표기 분석에서 사례를 실행해보세요.</div>';
  document.querySelectorAll("[data-run]").forEach((node) => node.addEventListener("click", async () => {
    if (state.busy) return;
    try {
      const run = await api(`/api/runs/${node.dataset.run}`);
      clearRun();
      fillContext(run.context);
      state.selected = state.scenarios.find((item) => item.id === run.source.scenario_id) || null;
      state.upload = run.source.provider === "apple_vision_local" ? { upload_id: run.source.image_url.split("/").pop().split(".")[0] } : null;
      renderScenarios();
      renderInput({ source: run.source, observations: run.observations });
      renderRun(run);
      showView("workspace");
    } catch (error) { notify(error.message, true); }
  }));
}
function showView(view) {
  for (const name of ["workspace", "history", "guide"]) $(`#${name}-view`).hidden = name !== view;
  document.querySelectorAll("[data-view]").forEach((node) => node.classList.toggle("active", node.dataset.view === view));
}
async function upload(file) {
  if (!file || state.busy) return;
  if (file.size > 8 * 1024 * 1024) { notify("8 MB 이하의 PNG 또는 JPEG 사진을 선택해주세요.", true); return; }
  busy(true, "사진 문자 인식 중");
  $("#image-loading").hidden = false;
  try {
    const data = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
    const result = await api("/api/upload", { image_base64: data.split(",")[1] });
    state.upload = result;
    state.observation = null;
    clearRun();
    renderScenarios();
    renderInput(result);
    notify(result.observations.length ? "실제 OCR을 완료했습니다. 사진에 맞는 작업 맥락을 입력해주세요." : "문자를 찾지 못했습니다. 다른 사진으로 시도해주세요.");
  } catch (error) { notify(error.message, true); }
  finally { busy(false); $("#image-loading").hidden = true; $("#image-upload").value = ""; }
}
function exportRun() {
  if (!state.run) return;
  const blob = new Blob([JSON.stringify(state.run, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = `contextweld-${state.run.id.slice(0, 8)}.json`; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
document.querySelectorAll("[data-view]").forEach((node) => node.addEventListener("click", () => showView(node.dataset.view)));
$("#context-form").addEventListener("submit", (event) => { event.preventDefault(); analyze(); });
$("#context-form").addEventListener("input", () => { if (state.run) { clearRun(); notify("작업 맥락이 바뀌었습니다. 다시 분석해주세요."); } });
$("#analyze-button").addEventListener("click", analyze);
$("#approve-button").addEventListener("click", () => review("approve"));
$("#hold-button").addEventListener("click", () => review("hold"));
$("#export-button").addEventListener("click", exportRun);
$("#refresh-history").addEventListener("click", () => loadHistory().catch((error) => notify(error.message, true)));
$("#image-upload").addEventListener("change", (event) => upload(event.target.files[0]));
$("#overlay-toggle").addEventListener("click", () => { state.overlays = !state.overlays; $("#overlays").hidden = !state.overlays; $("#overlay-toggle").textContent = state.overlays ? "영역 숨기기" : "영역 보기"; });
async function init() {
  try {
    await api("/api/health");
    $("#connection").textContent = "로컬 연결됨";
    state.scenarios = await api("/api/scenarios");
    chooseScenario("normal");
    await loadHistory();
  } catch (error) { $("#connection").textContent = "연결 확인 필요"; notify(error.message, true); }
}
init();
