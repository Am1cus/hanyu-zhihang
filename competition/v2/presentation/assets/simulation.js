import {
  byId, createRun, decimal, operationError, readSession, recordURL, rememberRun, rememberedRun,
  request, runPath, saveSession, showNotice, simulationURL
} from "./common.js";
import {isLiveRun, missionConditions, runLabel, updateMission} from "./mission-view.js";

const draftKey = "hyzh.simulation-settings";
const form = byId("mission-form");
const temperature = byId("sim-temperature");
const charge = byId("sim-charge");
const notice = byId("simulation-notice");
const presets = {
  obstacle: "第 32 仿真秒，北侧通道成为禁入区。",
  normal: "无预设扰动，适合观察完整巡看和返回。",
  gust: "第 32 仿真秒，东区逆风增强，影响用时和预算。",
  low_budget: "固定起始电量为 10%，用于观察起飞判断。",
  unavailable: "固定为 −30 ℃，超出参考曲线范围。",
  blocked_return: "第 180 仿真秒出现强突风，用于观察执行失败。"
};
let state = null;
let draft = true;
let loading = true;
let writing = false;
let offline = false;
let previewSignature = "";
let revision = 0;
let pollTimer;
let recentLive = null;

const saved = readSession(draftKey) || {};
let editableTemperature = saved.temperature_c ?? 0;
let editableCharge = saved.charge_percent ?? 85;
byId("preset").value = saved.preset || "obstacle";
byId("selector").value = saved.selector_id || "value_per_cost";
byId("budget-mode").value = saved.budget_mode || "bounded";
byId("speedup").value = saved.speedup ?? 20;
displayPreset();

function displayPreset() {
  const preset = byId("preset").value;
  temperature.readOnly = preset === "unavailable";
  charge.readOnly = preset === "low_budget";
  temperature.value = temperature.readOnly ? -30 : editableTemperature;
  charge.value = charge.readOnly ? 10 : editableCharge;
  byId("preset-hint").textContent = presets[preset];
}

function settings() {
  return {
    preset: byId("preset").value,
    selector_id: byId("selector").value,
    temperature_c: temperature.valueAsNumber,
    initial_soc: charge.valueAsNumber / 100,
    budget_mode: byId("budget-mode").value,
    speedup: byId("speedup").valueAsNumber
  };
}

function rememberSettings() {
  const value = settings();
  saveSession(draftKey, {
    preset: value.preset, selector_id: value.selector_id, budget_mode: value.budget_mode,
    temperature_c: editableTemperature, charge_percent: editableCharge, speedup: value.speedup
  });
}

function showCurrentLink() {
  const link = byId("open-current");
  link.hidden = !recentLive;
  if (recentLive) link.href = simulationURL(recentLive);
}

function update() {
  byId("mission-config").hidden = !draft;
  byId("live-bar").hidden = draft || !state;
  const phase = byId("phase");
  phase.hidden = !draft && !!state && !offline;
  const phaseText = offline ? "连接中断" : state ? runLabel(state) :
    loading ? (draft ? "核算起飞预览" : "正在读取") : "准备巡看";
  if (phase.textContent !== phaseText) phase.textContent = phaseText;
  phase.dataset.tone = offline || ["FAILED", "UNAVAILABLE"].includes(state?.status) ? "bad" :
    state?.summary.returned ? "good" : state?.status === "PAUSED" ? "mid" : "";
  const start = byId("start");
  start.disabled = loading || writing || !previewSignature || offline;
  start.textContent = writing && draft ? "正在开始…" : loading ? "等待起飞预览" : "开始巡看";
  byId("retry").hidden = !offline || writing;
  showCurrentLink();
  const active = !draft && isLiveRun(state);
  const blocked = offline || writing;
  byId("pause").hidden = !active;
  byId("pause").disabled = blocked;
  byId("pause").textContent = state?.status === "PAUSED" ? "继续巡看" : "暂停";
  byId("resume-note").hidden = !active || state.status !== "PAUSED";
  byId("open-record").hidden = draft || !state || active;
  byId("new-run").hidden = draft || !state || active;
  byId("control-details").hidden = !active;
  byId("obstacle").disabled = blocked || !active || state.stage === "DWELL";
  byId("gust").disabled = blocked || !active;
  byId("cancel").disabled = blocked;
  if (!draft && state) {
    byId("live-heading").textContent = runLabel(state);
    byId("live-conditions").textContent = missionConditions(state);
    byId("open-record").href = recordURL(state.id);
    byId("live-record").href = recordURL(state.id);
    const queued = state.queued_manual_events;
    byId("event-note").textContent = queued
      ? "已排队 " + queued + " 项变化，在下一仿真步生效。"
      : "成功排队的变化在下一仿真步生效。";
  }
  updateMission(state);
}

function tell(message, tone = "") {
  showNotice(notice, message, tone);
}

function endPoll() {
  clearTimeout(pollTimer);
}

function schedulePoll() {
  endPoll();
  if (draft || !state || writing) return;
  if (!isLiveRun(state) && !offline) return;
  pollTimer = setTimeout(syncRun, offline ? 1500 : state.status === "PAUSED" ? 900 : 300);
}

function takeRun(next, markLast = false) {
  state = next;
  draft = false;
  loading = false;
  offline = false;
  if (isLiveRun(next)) recentLive = next.id;
  else if (recentLive === next.id) recentLive = null;
  if (markLast || isLiveRun(next)) rememberRun(next.id);
}

async function syncRun() {
  if (!state || writing || draft) return;
  endPoll();
  const token = ++revision;
  const id = state.id;
  try {
    const next = await request(runPath(id));
    if (token !== revision) return;
    const wasOffline = offline;
    takeRun(next);
    if (wasOffline) tell("连接已恢复，显示后端保存的最新状态。");
  } catch (error) {
    if (token !== revision) return;
    if (error.status === 404) {
      state = null;
      if (rememberedRun() === id) rememberRun(null);
      if (recentLive === id) recentLive = null;
      loading = false;
      offline = false;
      tell("当前数据库找不到这条记录，可以准备新巡看。", "bad");
      byId("mission-config").hidden = false;
      draft = true;
      previewSignature = "";
      await preview({keepMessage: true});
      return;
    }
    offline = true;
    tell("连接中断，当前保留最后一次收到的画面。", "bad");
  } finally {
    if (token === revision) {
      update();
      schedulePoll();
    }
  }
}

async function preview({keepMessage = false} = {}) {
  if (!draft || writing) return;
  const token = ++revision;
  const value = settings();
  const valid = form.checkValidity();
  loading = valid;
  offline = false;
  previewSignature = "";
  state = null;
  if (!keepMessage) tell(valid ? "" : "请检查气温、电量和播放速度。", valid ? "" : "bad");
  if (valid) rememberSettings();
  update();
  if (!valid) return;
  try {
    const result = await request("/preview", {body: value});
    if (token !== revision) return;
    state = result;
    previewSignature = JSON.stringify(value);
  } catch (error) {
    if (token !== revision) return;
    offline = true;
    tell(error.message, "bad");
  } finally {
    if (token === revision) {
      loading = false;
      update();
    }
  }
}

let previewTimer;
form.addEventListener("input", event => {
  if (event.target === temperature && !temperature.readOnly) editableTemperature = temperature.value;
  if (event.target === charge && !charge.readOnly) editableCharge = charge.value;
  if (event.target === byId("preset")) displayPreset();
  clearTimeout(previewTimer);
  previewSignature = "";
  ++revision;
  loading = true;
  update();
  previewTimer = setTimeout(preview, 140);
});

async function withAction(action, {retrySafe = false} = {}) {
  if (writing || offline) return;
  ++revision;
  endPoll();
  writing = true;
  tell("");
  update();
  try { await action(); }
  catch (error) {
    tell(operationError(error, retrySafe), "bad");
    if (!draft && (error.network || error.status >= 500)) offline = true;
  } finally {
    writing = false;
    update();
    schedulePoll();
  }
}

function prepareAgain() {
  if (writing) return;
  ++revision;
  endPoll();
  clearTimeout(previewTimer);
  draft = true;
  previewSignature = "";
  state = null;
  history.replaceState(null, "", "/simulation?new=1#mission-config");
  preview();
  byId("prepare-title").scrollIntoView({block: "center"});
}

form.addEventListener("submit", event => {
  event.preventDefault();
  const value = settings();
  if (JSON.stringify(value) !== previewSignature || !form.reportValidity()) return;
  withAction(async () => {
    const next = await createRun("/runs", value);
    takeRun(next, true);
    history.replaceState(null, "", simulationURL(next.id));
    tell("");
  }, {retrySafe: true});
});
byId("pause").addEventListener("click", () => withAction(async () => {
  const action = state.status === "PAUSED" ? "resume" : "pause";
  takeRun(await request(runPath(state.id) + "/control", {body: {action}}));
}));
byId("cancel").addEventListener("click", () => withAction(async () => {
  takeRun(await request(runPath(state.id) + "/control", {body: {action: "cancel"}}));
  tell("本次巡看已结束，记录已保存。");
}));
for (const [id, kind] of [["obstacle", "obstacle_ahead"], ["gust", "gust"]]) {
  byId(id).addEventListener("click", () => withAction(async () => {
    const event = await request(runPath(state.id) + "/events", {body: {kind}});
    tell("变化已排队，将在第 " + decimal(event.scheduled_at_s, 1) + " 仿真秒生效。");
    takeRun(await request(runPath(state.id)));
  }));
}
for (const id of ["new-run", "prepare-again"]) byId(id).addEventListener("click", prepareAgain);
byId("retry").addEventListener("click", () => {
  if (state && !draft) syncRun();
  else if (draft) preview();
  else openPage();
});

async function findLive() {
  const rows = await request("/runs");
  return rows.find(row => row.runtime_available && row.summary.status === "RUNNING")?.id ||
    rows.find(row => row.runtime_available && row.summary.status === "PAUSED")?.id || null;
}

async function openPage() {
  const url = new URL(location.href);
  const id = url.searchParams.get("run");
  const newRun = url.searchParams.has("new") || location.hash === "#mission-config";
  const token = ++revision;
  loading = true;
  offline = false;
  draft = !id;
  update();
  if (newRun && !id) {
    preview();
    try { recentLive = await findLive(); showCurrentLink(); } catch { /* The preview reports connection errors. */ }
    return;
  }
  try {
    let selected = id ? await request(runPath(id)) : null;
    const saved = rememberedRun();
    if (!selected && saved) {
      try {
        const prior = await request(runPath(saved));
        if (isLiveRun(prior)) selected = prior;
      } catch (error) {
        if (error.status !== 404) throw error;
        rememberRun(null);
      }
    }
    if (!selected) {
      const live = await findLive();
      if (live) selected = await request(runPath(live));
    }
    if (token !== revision) return;
    if (selected) {
      takeRun(selected);
      update();
      schedulePoll();
    } else await preview();
  } catch (error) {
    if (token !== revision) return;
    loading = false;
    if (error.status === 404 && id) {
      history.replaceState(null, "", "/simulation?new=1");
      draft = true;
      tell("这条巡看已不在当前数据库，已打开起飞预览。", "bad");
      await preview({keepMessage: true});
    } else {
      offline = true;
      tell(error.message, "bad");
      update();
    }
  }
}

function openModelNotes() {
  if (location.hash === "#model-notes") byId("model-notes").open = true;
}
window.addEventListener("hashchange", openModelNotes);
window.addEventListener("pageshow", event => {
  if (event.persisted && state && !draft) syncRun();
});
openModelNotes();
openPage();
