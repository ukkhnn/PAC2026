/* 제조사 조건 미리보기. 패키지의 Decimal 변환 결과와 같은 필드 계약을 쓴다. */
(function (root) {
  "use strict";
  var drafts = Object.create(null);
  var labels = {current: "전류", voltage: "전압", travel_speed: "용접 이동속도", wire_feed: "와이어 송급속도"};

  function decimal(value) {
    var s = String(value).trim();
    if (s.length > 48 || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(s)) throw new Error("유한한 숫자를 입력하세요.");
    var neg = s[0] === "-"; s = s.replace(/^[+-]/, "");
    var parts = s.split("."), fraction = parts[1] || "";
    if (fraction.length > 12) throw new Error("소수점 아래 12자리까지 입력하세요.");
    return {n: BigInt((parts[0] || "0") + fraction) * (neg ? -1n : 1n), scale: fraction.length};
  }
  function stringify(d) {
    var neg = d.n < 0n, digits = String(neg ? -d.n : d.n).padStart(d.scale + 1, "0");
    if (d.scale) digits = (digits.slice(0, -d.scale) + "." + digits.slice(-d.scale)).replace(/0+$/, "").replace(/\.$/, "");
    return (neg ? "-" : "") + digits;
  }
  function compare(a, b) {
    var scale = Math.max(a.scale, b.scale);
    var left = a.n * 10n ** BigInt(scale - a.scale), right = b.n * 10n ** BigInt(scale - b.scale);
    return left < right ? -1 : left > right ? 1 : 0;
  }
  function multiply(a, b) { return {n: a.n * b.n, scale: a.scale + b.scale}; }
  function divide(a, b, precision) {
    var numerator = a.n * 10n ** BigInt(precision + b.scale), denominator = b.n * 10n ** BigInt(a.scale);
    var quotient = numerator / denominator, remainder = numerator % denominator;
    if (remainder * 2n >= denominator) quotient += 1n;
    return {n: quotient, scale: precision};
  }
  function calculate(preview, values) {
    var issues = (preview.issues || []).filter(function (i) { return i.code !== "missing_setpoint"; });
    var fields = [], targets = {}, overrides = {};
    (preview.fields || []).forEach(function (f) {
      var item = JSON.parse(JSON.stringify(f)); item.selected = null;
      try {
        if (!String(values[f.name] == null ? "" : values[f.name]).trim()) throw new Error("선택값을 입력하세요.");
        var value = decimal(values[f.name]), lo = decimal(f.source.min), hi = decimal(f.source.max);
        if (f.name === "wire_feed") {
          if (compare(value, decimal("0")) <= 0) throw new Error("송급속도는 0보다 큰 값이어야 해요.");
        } else if (compare(value, lo) < 0 || compare(value, hi) > 0) throw new Error("WPS 범위 " + f.source.min + "–" + f.source.max + " " + f.source.unit + " 안에서 입력하세요.");
        var target = multiply(value, decimal(f.factor));
        if (f.divisor) target = divide(target, decimal(f.divisor), f.precision == null ? 6 : f.precision);
        if (f.robot_field === "spd" && (compare(target, decimal("1")) < 0 || compare(target, decimal("1000")) > 0)) throw new Error("현대 spd 범위 1–1000 cm/min을 벗어났어요.");
        item.selected = {source: {value: stringify(value), unit: f.source.unit}, target: {value: stringify(target), unit: f.target.unit}};
        var changed = !f.selected || compare(value, decimal(f.selected.source.value)) !== 0;
        item.selection_origin = changed ? "user_override" : "work_order_recipe";
        if (changed) {
          overrides[f.name] = {before: f.selected ? f.selected.source : null, after: item.selected.source, source_kind: "user"};
          item.original_selection_evidence = item.selection_evidence;
          item.selection_evidence = {source_kind: "user", locator: {kind: "dashboard_input", field: f.name}};
          if (f.name === "wire_feed") item.source_range_applies_to_override = false;
        }
        if (!f.ref_only) targets[f.robot_field] = item.selected.target.value;
      } catch (e) { issues.push({field: f.name, code: "invalid_selection", message: e.message}); }
      fields.push(item);
    });
    var doosan = preview.manufacturer === "Doosan Robotics";
    var ready = !issues.length && (doosan ? ["v_target", "f_target", "vel_target"] : ["cur", "vol", "spd"]).every(function (key) { return key in targets; });
    var command = doosan ? "app_weld_set_weld_cond_analog(flag_dry_run=1, v_target=" + targets.v_target + ", f_target=" + targets.f_target + ", vel_target=" + targets.vel_target + ", vel_min=" + targets.vel_target + ", vel_max=" + targets.vel_target + ")" : "arccond D, cur=" + targets.cur + ", vol=" + targets.vol + ", spd=" + targets.spd;
    return Object.assign({}, preview, {fields: fields, issues: issues, status: ready ? "preview_ready" : "blocked", overrides: overrides,
      missing_setpoints: (preview.fields || []).filter(function (f) { return !String(values[f.name] == null ? "" : values[f.name]).trim(); }).map(function (f) { return f.name; }),
      command_preview: ready ? command : null,
      command_parameters: !ready ? null : doosan ? {flag_dry_run: 1, v_target: targets.v_target, f_target: targets.f_target, vel_target: targets.vel_target, vel_min: targets.vel_target, vel_max: targets.vel_target} : targets,
      execution_authorized: false, hardware_verified: false, delivery_requested: false,
      selection_origin: Object.keys(overrides).length ? "user_override" : "work_order_recipe", review_required: Object.keys(overrides).length > 0});
  }
  function node(tag, text, cls) {
    var n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n;
  }
  function render(block, box) {
    var bundle = block.preview, previews = bundle.previews || {hyundai: bundle};
    var key = block.id, state = drafts[key];
    if (!state || !state.values) {
      state = drafts[key] = {profile: bundle.selected_profile || "hyundai", values: {}};
      Object.keys(previews).forEach(function (profile) { (previews[profile].fields || []).forEach(function (f) { state.values[f.name] = f.selected ? f.selected.source.value : ""; }); });
    }
    box.classList.add("robot-input");
    var mount = node("div"); box.appendChild(mount);
    function draw() {
    mount.replaceChildren();
    var preview = previews[state.profile], values = state.values;
    var doosan = state.profile === "doosan";
    var toggles = node("div", null, "robot-input-toggle"); toggles.setAttribute("role", "group"); toggles.setAttribute("aria-label", "로봇 제조사 선택");
    Object.keys(previews).forEach(function (profile) {
      var toggle = node("button", profile === "doosan" ? "두산 DRL" : "현대 Hi6"); toggle.type = "button"; toggle.setAttribute("aria-pressed", String(state.profile === profile));
      toggle.addEventListener("click", function () { state.profile = profile; draw(); }); toggles.appendChild(toggle);
    }); mount.appendChild(toggles);
    var flow = node("div", null, "robot-input-flow");
    ["1 · 공통 작업 명세", "2 · 조건·누락 검사", "3 · 제조사별 변환"].forEach(function (label) { flow.appendChild(node("span", label)); }); mount.appendChild(flow);
    if (bundle.common_spec) {
      var common = bundle.common_spec;
      mount.appendChild(node("p", "부재 " + common.target.part_id + " · 접합부 " + common.target.joint_id + " · " + common.process + " · " + common.material, "robot-input-context"));
    }
    var head = node("div", null, "robot-input-head");
    head.appendChild(node("strong", doosan ? "두산로보틱스 · DRL" : "HD현대로보틱스 · Hi6"));
    head.appendChild(node("span", doosan ? "아날로그 · 전압 / 송급 / 이동속도" : "전류 A · 절대전압 V 입력 모드", "pill")); mount.appendChild(head);
    if (bundle.order_id) mount.appendChild(node("p", bundle.order_id + " · " + bundle.recipe_id + " 기본 조건", "robot-input-auto"));
    var table = node("table"), header = node("tr");
    ["항목 / 원문·작업조건", "작업조건", "제조사 입력 필드", "변환된 입력값"].forEach(function (label) { header.appendChild(node("th", label)); });
    table.appendChild(node("thead")).appendChild(header);
    var body = node("tbody"), outputs = {}, inputs = {};
    (preview.fields || []).forEach(function (f) {
      var tr = node("tr"), source = node("td"), choice = node("td");
      source.appendChild(node("strong", labels[f.name] || f.name));
      source.appendChild(node("div", f.name === "wire_feed" ? "등록조건 · " + f.source.min + " " + f.source.unit : f.source.min + "–" + f.source.max + " " + f.source.unit, "note"));
      var input = node("input"); input.type = "text"; input.inputMode = "decimal"; input.value = values[f.name]; input.autocomplete = "off";
      input.setAttribute("aria-label", (labels[f.name] || f.name) + " 작업조건");
      input.addEventListener("input", function () { values[f.name] = input.value; update(); }); inputs[f.name] = input;
      choice.appendChild(input); choice.appendChild(node("span", " " + f.source.unit, "note"));
      var field = node("td"); field.appendChild(node("code", f.ref_only ? "전류 기준" : f.robot_field)); field.appendChild(node("div", f.ref_only ? "조건 조회용" : f.target.unit, "note"));
      var out = node("td", "", "robot-input-value"); outputs[f.name] = out;
      [source, choice, field, out].forEach(function (cell) { tr.appendChild(cell); }); body.appendChild(tr);
    });
    table.appendChild(body); var scroll = node("div", null, "tw"); scroll.appendChild(table); mount.appendChild(scroll);
    mount.appendChild(node("p", doosan ? "속도: in/min × 25.4 ÷ 60 → mm/s · 송급속도는 등록된 작업조건에서 조회" : "속도: in/min × 2.54 → cm/min · WPS 2쪽, 대표층 1", "note"));
    var status = node("p", "", "robot-input-state"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite"); mount.appendChild(status);
    mount.appendChild(node("h4", "명령 미리보기"));
    var command = node("pre", "", "robot-input-command"); mount.appendChild(command);
    var actions = node("div", null, "robot-input-actions");
    var reset = node("button", "기본 조건으로"), save = node("button", "변환안 JSON 보기"); reset.type = save.type = "button";
    reset.addEventListener("click", function () { Object.keys(previews).forEach(function (profile) { previews[profile].fields.forEach(function (f) { values[f.name] = f.selected ? f.selected.source.value : ""; }); }); draw(); });
    var result;
    save.addEventListener("click", function () {
      if (!result.command_preview) return;
      var encoded = JSON.stringify(result, null, 2) + "\n";
      var blob = new Blob([encoded], {type: "application/json"}), url = URL.createObjectURL(blob);
      var modal = node("section", null, "modal robot-input-json"); modal.setAttribute("role", "dialog"); modal.setAttribute("aria-label", "변환안 JSON");
      var header = node("div", null, "mh"), close = node("button", "닫기"); close.type = "button";
      var link = node("a", "JSON 파일 내려받기"); link.href = url; link.download = (doosan ? "doosan-drl" : "hyundai-hi6") + "-input-preview.json";
      close.addEventListener("click", function () { modal.remove(); URL.revokeObjectURL(url); save.focus(); });
      header.appendChild(node("strong", doosan ? "두산 DRL 변환안" : "현대 Hi6 변환안")); header.appendChild(link); header.appendChild(close);
      modal.appendChild(header); modal.appendChild(node("pre", encoded)); document.body.appendChild(modal); close.focus();
    });
    actions.appendChild(reset); actions.appendChild(save); mount.appendChild(actions);
    function update() {
      var mapped = {}, commonIssues = [], combinedOverrides = {}, seen = {};
      Object.keys(previews).forEach(function (profile) {
        mapped[profile] = calculate(previews[profile], values);
        Object.assign(combinedOverrides, mapped[profile].overrides);
        mapped[profile].issues.forEach(function (issue) { var id = issue.field + ":" + issue.message; if (!seen[id]) { commonIssues.push(issue); seen[id] = true; } });
      });
      result = Object.assign(mapped[state.profile], {order_id: bundle.order_id, recipe_id: bundle.recipe_id, overrides: combinedOverrides,
        selection_origin: Object.keys(combinedOverrides).length ? "user_override" : "work_order_recipe", review_required: Object.keys(combinedOverrides).length > 0});
      if (commonIssues.length) { result.issues = commonIssues; result.status = "blocked"; result.command_preview = null; result.command_parameters = null; }
      if (bundle.common_spec) {
        result.common_spec = JSON.parse(JSON.stringify(bundle.common_spec));
        Object.keys(mapped).forEach(function (profile) { mapped[profile].fields.forEach(function (f) {
          var parameter = result.common_spec.parameters[f.name];
          if (!parameter || !f.selected) return;
          parameter.value = f.selected.source.value;
          if (combinedOverrides[f.name]) { parameter.origin = "user"; if (!parameter.original_evidence) parameter.original_evidence = parameter.evidence; parameter.evidence = f.selection_evidence; }
        }); });
        result.common_spec.validation.status = commonIssues.length ? "blocked" : "valid";
        result.common_spec.validation.issues = commonIssues;
      }
      result.fields.forEach(function (f) { outputs[f.name].textContent = f.selected ? f.selected.target.value + " " + f.target.unit : "—";
        inputs[f.name].setAttribute("aria-invalid", String(result.issues.some(function (i) { return i.field === f.name; }))); });
      status.textContent = result.command_preview ? (result.selection_origin === "user_override" ? "수정 조건 반영 · 필드·범위 검사 완료 · 제조사 변환 완료" : "기본 조건 적용 · 필드·범위 검사 완료 · 제조사 변환 완료") : result.issues.map(function (i) { return (labels[i.field] || i.field || "설정") + ": " + i.message; }).join(" ");
      status.className = "robot-input-state " + (result.command_preview ? "st-done" : "st-failed");
      command.textContent = result.command_preview || "입력값을 확인하면 변환 명령이 표시됩니다."; save.disabled = !result.command_preview;
    }
    update();
    }
    draw();
  }
  root.PAC_ROBOT_INPUT = {render: render, calculate: calculate};
  if (typeof module !== "undefined") module.exports = root.PAC_ROBOT_INPUT;
})(typeof window === "undefined" ? globalThis : window);
