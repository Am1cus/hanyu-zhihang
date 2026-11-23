import {byId, decimal, duration, readSession, rememberRun, rememberedRun, request, runPath, saveSession, showNotice, simulationURL} from "./common.js";
import {calmAreas, drawRoundTrip, samePath} from "./map.js";

const storageKey = "hyzh.endurance";
const fields = {
  temperature_c: "temperature", battery_percent: "battery", wind_speed_ms: "wind",
  ground_speed_ms: "speed", reserve_percent: "reserve", nominal_capacity_ah: "capacity"
};
const fieldLabels = {
  temperature_c: "气温", battery_percent: "当前电量", wind_speed_ms: "风速", ground_speed_ms: "平飞地速"
};
const presets = {
  normal: {temperature_c: -20, battery_percent: 80, wind_speed_ms: 5},
  gust: {temperature_c: -20, battery_percent: 90, wind_speed_ms: 10},
  low: {temperature_c: -20, battery_percent: 10, wind_speed_ms: 5}
};
const defaults = {...presets.normal, ground_speed_ms: 2, reserve_percent: 20, nominal_capacity_ah: null};
const labels = {energy: "省电路线", distance: "最短路线"};
const apiRoutes = {energy: "energy_route", distance: "distance_route"};
const chargeTolerance = 1e-10;
const form = byId("conditions-form");
const sample = byId("sample");
const routeCanvas = byId("route-map");
const routeButtons = Array.from(document.querySelectorAll("[data-route]"));
let current;
let selectedRoute = "energy";
let metadata;

function draftValues() {
  return Object.fromEntries(Object.entries(fields).map(([key, id]) => [key, byId(id).value]));
}

function submittedValues() {
  return Object.fromEntries(Object.entries(fields).map(([key, id]) => {
    const field = byId(id);
    return [key, field.value === "" ? null : field.valueAsNumber];
  }));
}

function fill(values) {
  for (const [key, id] of Object.entries(fields)) byId(id).value = values[key] ?? "";
}

function formChanged() {
  const values = submittedValues();
  const pending = Object.keys(fields).some(key => values[key] !== current.inputs[key]);
  sample.value = Object.keys(presets).find(name => Object.entries(presets[name])
    .every(([key, value]) => values[key] === value)) || "";
  const speed = values.ground_speed_ms ?? "—";
  const reserve = values.reserve_percent ?? "—";
  const capacity = values.nominal_capacity_ah == null ? "约 1.8 Ah" : values.nominal_capacity_ah + " Ah";
  byId("condition-summary").textContent = "储备 " + reserve + "% · " + speed + " m/s · " + capacity;
  const notice = byId("edit-state");
  notice.hidden = !pending;
  notice.textContent = pending ? "条件已改，待计算。当前结果对应上次提交的条件。" : "";
  saveSession(storageKey, {draft: draftValues(), applied: current.inputs});
}

function applySample(name) {
  if (!presets[name]) return;
  for (const [key, value] of Object.entries(presets[name])) byId(fields[key]).value = value;
  if (form.reportValidity()) calculate(submittedValues());
  else formChanged();
}

function describeInputs(inputs) {
  return inputs.temperature_c + " ℃ / " + inputs.battery_percent + "% / " + inputs.wind_speed_ms +
    " m/s · 地速 " + inputs.ground_speed_ms + " m/s";
}

function showTime(minutes) {
  const target = byId("usable");
  const seconds = Math.round(minutes * 60);
  const wholeMinutes = Math.floor(seconds / 60);
  target.replaceChildren();
  function appendPart(value, unit) {
    const label = document.createElement("small");
    label.textContent = unit;
    target.append(String(value), label);
  }
  if (wholeMinutes) appendPart(wholeMinutes, "分");
  appendPart(wholeMinutes ? String(seconds % 60).padStart(2, "0") : seconds, "秒");
}

function renderPrediction(batch) {
  const result = batch.prediction;
  byId("usable-title").textContent = batch.inputs.reserve_percent > 0
    ? "保留 " + batch.inputs.reserve_percent + "% 后预计可飞" : "预计可飞";
  byId("used-conditions").textContent = "均匀风 · " + describeInputs(batch.inputs);
  byId("retry-prediction").hidden = !batch.predictError;
  const outside = byId("outside");
  outside.hidden = !result?.extrapolated_fields.length;
  outside.textContent = outside.hidden ? "" :
    result.extrapolated_fields.map(key => fieldLabels[key] || key).join("、") + "超出模型标定范围。";
  if (result) {
    showTime(result.usable_minutes);
    byId("to-zero").textContent = "预计至 0% 共 " + duration(result.remaining_minutes * 60);
  } else {
    byId("usable").textContent = "—";
    byId("to-zero").textContent = batch.predictError || "正在计算续航…";
  }
  byId("model-values").textContent = result ?
    result.profile_name + " · 平均 " + decimal(result.estimated_current_a, 1) + " A / " +
    decimal(result.estimated_power_w, 1) + " W · 当前温度满电 " + decimal(result.full_capacity_ah) +
    " Ah · 模型 " + result.model_version : "";
  const assumptions = byId("model-assumptions");
  assumptions.hidden = !result?.assumptions.length;
  assumptions.replaceChildren(...(result?.assumptions || []).map(text => {
    const item = document.createElement("li");
    item.textContent = text;
    return item;
  }));
}

function selectedPlan(data) {
  return data[apiRoutes[selectedRoute]];
}

function routeChargeInsufficient(route, data) {
  return route.estimated_consumption_ah > data.prediction.available_capacity_ah + chargeTolerance;
}

function outcome(tone, sign, title, message) {
  byId("outcome").dataset.tone = tone;
  byId("symbol").textContent = sign;
  byId("verdict").textContent = title;
  byId("arrival").textContent = message;
}

function renderRouteVerdict(data, route) {
  const label = labels[selectedRoute] + " · ";
  if (route.status !== "planned") {
    const legs = [["去程", route.outbound], ["返程", route.inbound]]
      .filter(([, leg]) => leg.status !== "planned").map(([name]) => name).join("和");
    outcome("bad", "!", "无可行往返路线", label + legs + "在当前障碍和风场下不可达。");
  } else if (routeChargeInsufficient(route, data)) {
    outcome("bad", "×", "预计电量不足以完成往返", label + "预计需 " +
      decimal(route.estimated_consumption_ah * 1000, 1) + " mAh，当前约有 " +
      decimal(data.prediction.available_capacity_ah * 1000, 1) + " mAh。");
  } else {
    const enough = route.feasible_with_reserve;
    const arrival = decimal(route.remaining_battery_percent, 1);
    outcome(enough ? "good" : "mid", enough ? "✓" : "!",
      enough ? "预计能返回并留足储备" : "预计能返回，到站电量低于储备",
      label + "往返 " + duration(route.duration_s) + "，到站预计剩 " + arrival +
      "%，设定储备 " + data.prediction.inputs.reserve_percent + "%。");
  }
}

function redrawRoute() {
  if (current?.route) drawRoundTrip(routeCanvas, current.route, selectedPlan(current.route), turnaroundPoint(current.route));
}

function turnaroundPoint(data) {
  const limit = data.return_limit;
  if (selectedRoute === "energy" && limit?.status === "turn_back" && limit.last_feasible.distance_m > 0) {
    return limit.last_feasible.position;
  }
  return null;
}

function showReturnLimit(data) {
  const notice = byId("return-limit");
  const limit = data.return_limit;
  if (selectedRoute !== "energy" || !limit || limit.status === "outbound_unreachable") {
    showNotice(notice, "");
    return;
  }
  const reserve = data.prediction.inputs.reserve_percent;
  if (limit.status === "start_below_reserve") {
    showNotice(notice, "起始电量低于 " + reserve + "% 储备，可留足储备的航程为 0 米。", "mid");
    return;
  }
  const point = limit.last_feasible;
  const distance = decimal(point.distance_m, 0) + " 米";
  const arrival = decimal(point.remaining_battery_percent, 1) + "%";
  if (limit.status === "goal_with_reserve") {
    showNotice(notice, "可沿省电路线飞到目标点（去程 " + distance + "），预计返航后剩 " + arrival + " 电量。", "good");
    return;
  }
  const nextReason = limit.reason === "return_unreachable" ? "下一格起无可行返程。" : "飞到下一格再返航会低于储备。";
  const range = point.distance_m > 0
    ? "留足 " + reserve + "% 储备时，预计最晚在去程 " + distance + "处转返（" +
      duration(point.duration_s) + "），回到基地约剩 " + arrival + "。"
    : "当前条件下，可留足储备的航程为 0 米。";
  showNotice(notice, range + nextReason, "mid");
}

function comparisonText(data) {
  const energy = data.energy_route;
  const distance = data.distance_route;
  if (energy.status !== "planned" || distance.status !== "planned") return "";
  const same = samePath(energy.outbound.path, distance.outbound.path) && samePath(energy.inbound.path, distance.inbound.path);
  if (same) return "两种方案走同一路线，预计耗电相同。";
  const saving = (distance.estimated_consumption_ah - energy.estimated_consumption_ah) * 1000;
  if (Math.abs(saving) < .05) return "两种方案的预计耗电持平。";
  const extraDistance = energy.distance_m - distance.distance_m;
  const extraTime = energy.duration_s - distance.duration_s;
  const changes = [];
  if (Math.abs(extraDistance) >= .05) changes.push((extraDistance > 0 ? "多走 " : "少走 ") + decimal(Math.abs(extraDistance), 0) + " 米");
  if (Math.abs(extraTime) >= .5) changes.push((extraTime > 0 ? "多用 " : "少用 ") + duration(Math.abs(extraTime)));
  const percent = saving > 0 && Number.isFinite(data.saving_percent) ? "（" + decimal(data.saving_percent, 1) + "%）" : "";
  changes.push((saving > 0 ? "少用约 " : "多用约 ") + decimal(Math.abs(saving), 1) + " mAh" + percent);
  return "与最短路线比，省电方案" + changes.join("，") + "。";
}

function compareRoutes(data) {
  const rows = [
    ["路程", route => decimal(route.distance_m, 0) + " 米"],
    ["用时", route => duration(route.duration_s)],
    ["耗电", route => decimal(route.estimated_consumption_ah * 1000, 1) + " mAh"],
    ["到站电量", route => routeChargeInsufficient(route, data)
      ? "预计无法到站" : decimal(route.remaining_battery_percent, 1) + "%"]
  ];
  const target = byId("compare");
  target.replaceChildren();
  for (const [name, format] of rows) {
    const row = document.createElement("tr");
    const title = document.createElement("th");
    title.scope = "row";
    title.textContent = name;
    row.append(title);
    for (const route of [data.energy_route, data.distance_route]) {
      const cell = document.createElement("td");
      cell.textContent = route.status === "planned" ? format(route) : "—";
      row.append(cell);
    }
    target.append(row);
  }
  byId("difference").textContent = comparisonText(data);
}

function renderRoute(batch) {
  byId("retry-route").hidden = !batch.routeError;
  const data = batch.route;
  byId("route-data").hidden = !data;
  const message = byId("route-message");
  message.hidden = !!data;
  if (!data) {
    message.textContent = batch.routeError || batch.routeNote || "正在核算去程和返程…";
    if (batch.routeError) outcome("bad", "!", "路线暂未算出", batch.routeError);
    else if (batch.routeNote) outcome("mid", "!", "当前速度无法规划往返", batch.routeNote);
    else outcome("", "↔", "正在计算往返路线", "");
    return;
  }
  const route = selectedPlan(data);
  for (const button of routeButtons) button.setAttribute("aria-pressed", String(button.dataset.route === selectedRoute));
  renderRouteVerdict(data, route);
  compareRoutes(data);
  showReturnLimit(data);
  const retraces = route.status === "planned" && samePath(route.outbound.path, route.inbound.path.slice().reverse());
  const captions = ["每格 " + data.grid.cell_size_m + " 米"];
  if (retraces) captions.push("双箭头表示去返重合");
  else captions.push("实线为去程，虚线为返程");
  captions.push("斜纹为障碍");
  if (calmAreas(data.grid).length) captions.push("浅蓝带为低风速通道");
  if (turnaroundPoint(data)) captions.push("橙色点为预计折返点");
  byId("route-caption").textContent = captions.join(" · ");
  redrawRoute();
}

async function getPrediction(batch) {
  batch.predictError = "";
  batch.prediction = null;
  renderPrediction(batch);
  try {
    batch.prediction = await request("/endurance/predict", {body: batch.inputs});
  } catch (error) { batch.predictError = error.message; }
  if (batch === current) renderPrediction(batch);
}

async function getRoute(batch) {
  batch.routeError = "";
  batch.route = null;
  renderRoute(batch);
  if (batch.routeNote) return;
  try {
    batch.route = await request("/endurance/route", {body: batch.inputs});
  } catch (error) { batch.routeError = error.message; }
  if (batch === current) renderRoute(batch);
}

function calculate(inputs) {
  current = {
    inputs,
    routeNote: inputs.ground_speed_ms < .25 ? "往返规划需至少 0.25 m/s 地速。续航按当前输入估计。" : ""
  };
  selectedRoute = "energy";
  formChanged();
  getPrediction(current);
  getRoute(current);
}

async function readMetadata() {
  const note = byId("model-evidence");
  byId("retry-metadata").hidden = true;
  note.textContent = "正在读取模型依据…";
  try {
    metadata ||= await request("/endurance/model");
    const training = metadata.training;
    const error = training.holdout_current_flight_mean_metrics.mape_percent;
    note.textContent = "拟合使用 " + training.training_flights.length + " 个 AirSim 架次，留出 " +
      training.holdout_flights.length + " 个架次的平均电流相对误差为 " + decimal(error, 2) +
      "%。可飞时间由耗电率推算，目前没有全航程分钟误差。";
  } catch (error) {
    note.textContent = error.message;
    byId("retry-metadata").hidden = false;
  }
}

async function showRunningLink() {
  const link = byId("return-current");
  const remembered = rememberedRun();
  if (remembered) {
    try {
      const state = await request(runPath(remembered));
      if (state.runtime_available && ["RUNNING", "PAUSED"].includes(state.status)) {
        link.href = simulationURL(state.id);
        link.hidden = false;
        return;
      }
    } catch (error) {
      if (error.status === 404) rememberRun(null);
    }
  }
  try {
    const runs = await request("/runs");
    const currentRun = runs.find(run => run.runtime_available && run.summary.status === "RUNNING");
    link.hidden = !currentRun;
    if (currentRun) link.href = simulationURL(currentRun.id);
  } catch { link.hidden = true; }
}

function redirectLegacy() {
  if (location.pathname !== "/") return false;
  const anchors = {
    "#main": "/simulation", "#mission-config": "/simulation#mission-config",
    "#mission-map": "/simulation#mission-map", "#model-notes": "/simulation#model-notes", "#review": "/history"
  };
  const target = anchors[location.hash];
  if (target) location.replace(target);
  return !!target;
}

if (!redirectLegacy()) {
  const saved = readSession(storageKey);
  const applied = saved?.applied || defaults;
  fill(saved?.draft || applied);
  byId("capacity").addEventListener("input", () => {
    const field = byId("capacity");
    field.setCustomValidity(field.value !== "" && field.valueAsNumber <= 0 ? "标称容量应大于 0 Ah。" : "");
  });
  form.addEventListener("invalid", event => {
    if (event.target.closest("#advanced")) byId("advanced").open = true;
  }, true);
  form.addEventListener("input", formChanged);
  form.addEventListener("submit", event => {
    event.preventDefault();
    calculate(submittedValues());
  });
  sample.addEventListener("change", () => applySample(sample.value));
  for (const button of routeButtons) button.addEventListener("click", () => {
    selectedRoute = button.dataset.route;
    renderRoute(current);
  });
  byId("retry-prediction").addEventListener("click", () => getPrediction(current));
  byId("retry-route").addEventListener("click", () => getRoute(current));
  byId("model-notes").addEventListener("toggle", event => {
    if (event.target.open && !metadata) readMetadata();
  });
  byId("retry-metadata").addEventListener("click", readMetadata);
  new ResizeObserver(redrawRoute).observe(routeCanvas);
  calculate(applied);
  showRunningLink();
  window.addEventListener("hashchange", redirectLegacy);
  window.addEventListener("pageshow", event => { if (event.persisted) showRunningLink(); });
}
