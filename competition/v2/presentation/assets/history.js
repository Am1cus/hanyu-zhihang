import {
  byId, createRun, downloadRun, duration, escapeHTML, operationError, recordURL, rememberRun,
  request, runPath, showNotice, simulationURL
} from "./common.js";
import {isLiveRun, missionConditions, runLabel, updateMission} from "./mission-view.js";

const records = byId("records");
const listMessage = byId("history-message");
const record = byId("record");
const recordMessage = byId("record-message");
const rows = new Set();
let cursor = null;
let listing = false;
let currentId = null;
let currentState = null;
let detailRevision = 0;
let operating = false;

function rowMarkup(item) {
  const config = item.configuration;
  const summary = item.summary;
  const title = config.scenario.label || "巡看仿真";
  return '<article class="historyitem"><div class="info"><h3>' + escapeHTML(title) +
    '</h3><p class="minor">' + escapeHTML(missionConditions(config)) +
    '</p></div><div><p class="status" data-tone="' + (summary.returned ? "good" : "") + '">' +
    escapeHTML(runLabel(item)) + '</p><p class="minor">完成 ' + summary.completed_count + " / " + summary.task_count +
    " 点 · " + escapeHTML(duration(summary.t_s)) + '</p></div><a class="ghost" data-run="' +
    escapeHTML(item.id) + '" href="' + escapeHTML(recordURL(item.id)) + '">查看详情</a></article>';
}

async function loadList(reset) {
  if (listing || (!reset && !cursor)) return;
  listing = true;
  const more = byId("more-history");
  const refresh = byId("refresh-history");
  refresh.disabled = true;
  more.disabled = true;
  showNotice(listMessage, reset ? "正在读取巡看记录…" : "正在读取更早的记录…");
  try {
    const query = new URLSearchParams({limit: "50"});
    if (!reset) query.set("cursor", cursor);
    const data = await request("/history?" + query);
    if (reset) {
      records.replaceChildren();
      rows.clear();
    }
    const next = [];
    for (const item of data.items) {
      if (rows.has(item.id)) continue;
      rows.add(item.id);
      next.push(rowMarkup(item));
    }
    records.insertAdjacentHTML("beforeend", next.join(""));
    cursor = data.next_cursor;
    byId("empty").hidden = rows.size > 0;
    byId("history-count").hidden = rows.size === 0;
    byId("history-count").textContent = "已显示 " + rows.size + " 条记录";
    more.hidden = !cursor;
    showNotice(listMessage, "");
  } catch (error) {
    showNotice(listMessage, error.message + (error.status === 422 ? "请刷新记录后重新翻页。" : ""), "bad");
  } finally {
    listing = false;
    refresh.disabled = false;
    more.disabled = false;
  }
}

function setRecordActions(state) {
  const live = isLiveRun(state);
  byId("record-actions").hidden = !state;
  byId("replay-note").hidden = !state;
  byId("resume").hidden = !live || state.status !== "PAUSED";
  byId("view-live").hidden = !live || state.status !== "RUNNING";
  if (live) byId("view-live").href = simulationURL(state.id);
  for (const id of ["replay", "export", "resume"]) byId(id).disabled = operating;
}

async function openRecord(id, moveFocus = false) {
  const token = ++detailRevision;
  currentId = id;
  currentState = null;
  record.hidden = !id;
  setRecordActions(null);
  updateMission(null);
  byId("retry-record").hidden = true;
  if (!id) {
    if (moveFocus) byId("history-title").scrollIntoView({block: "start"});
    return;
  }
  byId("record-title").textContent = "巡看详情";
  byId("record-conditions").textContent = "";
  showNotice(recordMessage, "正在读取这次巡看…");
  if (moveFocus) record.focus();
  try {
    const state = await request(runPath(id));
    if (token !== detailRevision) return;
    currentState = state;
    byId("record-title").textContent = runLabel(state);
    byId("record-conditions").textContent = state.scenario_label + " · " + missionConditions(state);
    showNotice(recordMessage, "");
    setRecordActions(state);
    updateMission(state);
  } catch (error) {
    if (token !== detailRevision) return;
    showNotice(recordMessage, error.message, "bad");
    byId("retry-record").hidden = false;
  }
}

function visitRecord(id, focus) {
  history.pushState(null, "", id ? recordURL(id) : "/history");
  openRecord(id, focus);
}

records.addEventListener("click", event => {
  const link = event.target.closest("a[data-run]");
  if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
  event.preventDefault();
  visitRecord(link.dataset.run, true);
});
byId("close-record").addEventListener("click", () => visitRecord(null, true));
byId("retry-record").addEventListener("click", () => openRecord(currentId));
byId("refresh-history").addEventListener("click", () => loadList(true));
byId("more-history").addEventListener("click", () => loadList(false));

async function recordAction(action, retrySafe = false) {
  if (operating || !currentState) return;
  const id = currentState.id;
  const token = detailRevision;
  const stillSelected = () => currentId === id && token === detailRevision;
  operating = true;
  setRecordActions(currentState);
  showNotice(recordMessage, "");
  try { await action(id, stillSelected); }
  catch (error) {
    if (stillSelected()) showNotice(recordMessage, operationError(error, retrySafe), "bad");
  } finally {
    operating = false;
    setRecordActions(currentState);
  }
}

byId("export").addEventListener("click", () => recordAction(async (id, stillSelected) => {
  await downloadRun(id);
  if (stillSelected()) showNotice(recordMessage, "已发送完整 JSON 记录到浏览器下载。", "good");
}));
byId("replay").addEventListener("click", () => recordAction(async (id, stillSelected) => {
  const next = await createRun(runPath(id) + "/replay", {});
  rememberRun(next.id);
  if (stillSelected()) location.assign(simulationURL(next.id));
}, true));
byId("resume").addEventListener("click", () => recordAction(async (id, stillSelected) => {
  const next = await request(runPath(id) + "/control", {body: {action: "resume"}});
  rememberRun(next.id);
  if (stillSelected()) location.assign(simulationURL(next.id));
}));

function openFromLocation() {
  openRecord(new URLSearchParams(location.search).get("run"));
}
window.addEventListener("popstate", openFromLocation);
window.addEventListener("pageshow", event => { if (event.persisted && currentId) openFromLocation(); });
loadList(true);
openFromLocation();
