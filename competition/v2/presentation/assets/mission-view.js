import {byId, decimal, duration, escapeHTML} from "./common.js";
import {drawMission} from "./map.js";

export const statusNames = {
  RUNNING: "运行中", PAUSED: "已暂停", COMPLETED_RETURNED: "全部完成并返回",
  PARTIAL_RETURNED: "部分完成并返回", REFUSED: "拒绝起飞", FAILED: "执行失败",
  UNAVAILABLE: "信息不足", CANCELLED: "用户取消"
};
const methods = {
  value_per_cost: "优先选择划算的点", subset_dp: "一次安排整趟",
  nearest_feasible: "优先去近处", fixed_order: "按原清单顺序"
};
const reasons = {
  PLAN_SELECTED: "已将返程和储备计入预算",
  ALL_TASKS_VISITED: "计划内的巡看已结束",
  NO_FEASIBLE_TASK: "当前预算和路线下没有可行任务",
  RETURN_UNREACHABLE: "返程路线不可达",
  RETURN_BUDGET_INSUFFICIENT: "返程预算不足",
  DATA_UNAVAILABLE: "参考参数不足",
  wind_exceeds_track_hold_model: "风速超出了当前航迹保持能力",
  occupied_edge_became_excluded: "正在执行的航段受新禁入区域影响",
  temperature_outside_source_nodes_no_extrapolation: "气温超出参考曲线范围",
  battery_curve_cutoff: "参考电池达到截止状态",
  operator_cancelled: "用户结束了本次巡看",
  all_tasks_completed: "已完成全部巡看点",
  returned_to_base: "已返回管理站"
};
const deferred = {
  BUDGET: "单点往返也超出当前预算", UNREACHABLE: "当前路线不可达",
  LOWER_VALUE_PLAN: "当前策略未安排在这趟", DATA_UNAVAILABLE: "适用参数不足"
};
const auditActions = {
  create: "创建运行", pause: "暂停", resume: "继续", cancel: "结束本次",
  event_queued: "环境变化已排队", replay_origin: "关联原运行"
};

export const isLiveRun = state => !!state?.runtime_available && ["RUNNING", "PAUSED"].includes(state.status);

export function missionConditions(state) {
  return state.temperature_c + " ℃ · 起始电量 " + decimal(state.initial_soc * 100, 0) + "% · " +
    (methods[state.selector_id] || state.selector_id) + " · " + (state.budget_mode === "bounded" ? "计入估算误差" : "按当前估计值");
}

export function runLabel(state) {
  const status = state.summary?.status || state.status;
  if (state.is_preview) return "起飞预览";
  return (state.runtime_available ? "" : "已归档 · ") + (statusNames[status] || status);
}

const canvas = byId("mission-canvas");
let visibleState = null;

function setText(id, value) {
  const target = byId(id);
  if (target.textContent !== value) target.textContent = value;
}

function nextTask(state) {
  const id = state.current_decision?.record.ordered_task_ids[0];
  return state.tasks.find(task => task.id === id);
}

function reasonText(code) {
  return reasons[code] || code || "本次结束，详细操作见运行记录。";
}

function explain(state) {
  const decision = state.current_decision;
  const next = nextTask(state);
  if (state.is_preview) {
    if (["REFUSED", "UNAVAILABLE"].includes(state.status)) {
      return ["起飞判断", statusNames[state.status], reasonText(state.summary.ended_reason)];
    }
    return ["预览下一站", next?.label || "准备巡看",
      "已按当前条件安排任务并计入返程和储备。开始后可观察实际执行。"];
  }
  if (!isLiveRun(state)) {
    if (["RUNNING", "PAUSED"].includes(state.status)) {
      return ["保存时的状态", statusNames[state.status], "已记录到最后一次保存的检查点，可从头复演。"];
    }
    const message = state.summary.returned
      ? "执行器已记录到达管理站。已完成 " + state.summary.completed_count + " 个巡看点。"
      : reasonText(state.summary.ended_reason);
    return ["运行结果", statusNames[state.status], message];
  }
  if (state.stage === "RETURN") return ["下一步", "返回管理站", "系统按当前条件执行返程，抵达后会更新返回结果。"];
  const title = state.stage === "DWELL" ? "在 " + (next?.label || "任务点") + " 停留" : next?.label || "核算下一步";
  if (state.pending_replan) {
    return ["当前安排", title, state.stage === "DWELL"
      ? "当前停留完成后，将依据新环境重新核算。" : "到达下一网格节点后，将从实际位置重新核算。"];
  }
  if (decision?.responding_to?.length) {
    const seen = state.events.find(event => event.event_id === decision.responding_to[0]);
    const change = seen?.payload.type === "wind" ? "风场变化" : "禁入区域变化";
    const comparison = state.response_metrics.find(row => row.decision_index === state.decisions.length - 1);
    const previous = comparison?.same_state_counterfactual?.record.ordered_task_ids[0];
    const earlier = state.tasks.find(task => task.id === previous);
    const summary = earlier && next && earlier.id !== next.id
      ? "同一位置，原条件会先去" + earlier.label + "，调整后改去" + next.label + "。"
      : decision.plan_changed ? "任务顺序已按当前信息重新安排。"
        : decision.budget_changed ? "任务顺序保持，预算已更新。" : "当前路线与安排仍可执行。";
    return ["下一站", title, change + "已生效。" + summary];
  }
  if (decision?.trigger === "task_completed") return ["下一站", title, "上一站停留完成，系统已按剩余能量重新安排。"];
  return ["下一站", title, "系统依据当前地图、任务优先级和往返预算安排。"];
}

function renderBudget(state) {
  const sum = state.summary;
  const record = state.current_decision?.record;
  const values = [
    ["已耗能量", sum.consumed_wh], ["扣除储备后可用", sum.reserve_margin_wh],
    ["固定储备", sum.reserve_wh], ["最近计划返程耗能", record?.budget.return_wh],
    ["最近决策的预算余量", record?.budget.margin_wh]
  ];
  byId("budget-values").innerHTML = values.map(([label, value]) =>
    "<div><dt>" + label + "</dt><dd>" + (value == null ? "—" : decimal(value) + " Wh") + "</dd></div>").join("");
  const names = (record?.ordered_task_ids || []).map(id => state.tasks.find(task => task.id === id)?.label || id);
  if (names.length) names.push("管理站");
  setText("plan-order", names.length ? "最近计划 · " + names.join(" → ") : "最近计划没有新增巡看点。");
}

function renderTasks(state) {
  const completed = new Set(state.completed_ids);
  const record = state.current_decision?.record;
  const order = new Set(state.is_preview || isLiveRun(state) ? record?.ordered_task_ids : []);
  const deferrals = new Map((record?.deferred_tasks || []).map(task => [task.id, task.reason]));
  byId("task-list").innerHTML = state.tasks.map(task => {
    const done = completed.has(task.id);
    const planned = order.has(task.id);
    const label = done ? "已完成" : planned ? "计划中" : "未完成";
    const detail = done ? "已完成仿真停留。" : planned ? "在当前计划中。" :
      deferred[deferrals.get(task.id)] || "本次尚未完成。";
    return '<li><span class="task-letter">' + escapeHTML(task.id) + '</span><div><strong>' + escapeHTML(task.label) +
      '</strong><p class="minor">' + escapeHTML(detail) + '</p></div><span class="status" data-tone="' +
      (done ? "good" : "") + '">' + label + '</span></li>';
  }).join("");
}

function renderTimeline(state) {
  const entries = [];
  for (const row of state.events) {
    const kind = row.payload.type === "wind" ? "风场变化" : "禁入区域变化";
    const detail = row.intersects_occupied_edge ? "变化影响正在执行的航段。" : row.applied ? "已纳入当前环境。" : "已记录变化。";
    entries.push([row.t_s, kind, detail]);
  }
  for (const row of state.decisions) {
    const record = row.record;
    const next = state.tasks.find(task => task.id === record.ordered_task_ids[0]);
    const title = row.trigger === "mission_started" ? "生成起始计划" :
      row.trigger === "task_completed" ? "完成一个点，重新核算" : row.plan_changed ? "更新巡看计划" : "核对路线与预算";
    const detail = record.action === "CONTINUE" && next ? "下一站 " + next.label + "，预算余量 " +
      decimal(record.budget.margin_wh) + " Wh。" : reasonText(record.reason_code);
    entries.push([row.t_s, title, detail]);
  }
  for (const row of state.execution_audit?.records || []) {
    const detail = row.source_run_id ? "来源运行 " + row.source_run_id :
      row.event ? "将在第 " + decimal(row.event.scheduled_at_s, 1) + " 仿真秒生效。" : "";
    entries.push([row.t_s, auditActions[row.action] || row.action, detail]);
  }
  if (!state.is_preview && !["RUNNING", "PAUSED"].includes(state.status)) {
    entries.push([state.t_s, statusNames[state.status], reasonText(state.summary.ended_reason)]);
  }
  byId("timeline").innerHTML = entries.sort((a, b) => b[0] - a[0]).map(([time, title, detail]) =>
    '<li><time>' + escapeHTML(duration(time)) + '</time><div><strong>' + escapeHTML(title) +
    '</strong><p class="minor">' + escapeHTML(detail) + '</p></div></li>').join("");
  setText("run-identifier", state.is_preview ? "起飞预览" : "记录编号 " + state.id + " · " + state.runtime_version);
}

const details = [["budget-info", renderBudget], ["task-info", renderTasks], ["timeline-info", renderTimeline]];
for (const [id, render] of details) {
  byId(id).addEventListener("toggle", event => {
    if (event.target.open && visibleState) render(visibleState);
  });
}

function redraw() {
  if (visibleState) drawMission(canvas, visibleState);
}
new ResizeObserver(redraw).observe(canvas);

export function updateMission(state) {
  visibleState = state;
  byId("mission-detail").hidden = !state;
  if (!state) return;
  const [label, title, reason] = explain(state);
  const next = nextTask(state);
  const live = isLiveRun(state);
  setText("map-title", state.is_preview ? "起飞前地图" : live ? "当前位置与路线" : "最后保存的巡看画面");
  const caption = [];
  if (!state.is_preview) caption.push("实心圆为当前位置");
  if (state.is_preview || live) caption.push("蓝线为下一段，紫色虚线为返程");
  if (!state.is_preview) caption.push("灰蓝线为已执行轨迹");
  caption.push("斜纹为禁入区", "每格 " + state.grid.cell_size_m + " 米");
  setText("mission-caption", caption.join(" · "));
  const nextLabel = (live || state.is_preview) && next && state.stage !== "RETURN" ? "，下一站 " + next.label : "";
  canvas.setAttribute("aria-label", (state.is_preview ? "起飞前地图" : "仿真巡看地图") + nextLabel);
  setText("decision-label", label);
  setText("decision-title", title);
  setText("decision-text", reason);
  setText("completed", state.summary.completed_count + " / " + state.summary.task_count + " 点");
  setText("remaining", state.summary.remaining_wh == null ? "—" : decimal(state.summary.remaining_wh) + " Wh");
  setText("sim-time", duration(state.t_s));
  for (const [id, render] of details) if (byId(id).open) render(state);
  redraw();
}
