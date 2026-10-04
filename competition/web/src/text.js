const reasons = {
  mission_started: '任务启动：核算下一巡检点与返程预算。',
  task_point_completed: '当前巡检点已完成，重新核算下一点与返程。',
  event_applied: '风或障碍发生变化，已到节点后重新规划。',
  path_finished: '当前路线结束，重新计算下一段。',
  node_reached: '已到达路线节点，重新检查任务预算。',
  next_task_budget_insufficient: '下一巡检点及返程预算不足，转为返回回收点。',
  next_task_unreachable: '下一巡检点或返程路线不可达，转为返回回收点。',
  next_task_or_return_path_unavailable: '下一巡检点或返程路线不可达，无法形成任务预算。',
  return_path_unavailable: '回收点没有可行路线，任务失败。',
  return_energy_unavailable: '剩余仿真能量不足以支持当前返程路线。',
  all_targets_visited: '三个巡检点均完成，并已返回回收点。',
  partial_task_returned: '部分巡检点完成，已返回回收点。',
  budget_or_route_rejected_at_base: '出发前预算不足或路线不可达，任务未离开回收点。',
  wind_exceeds_track_hold_model: '当前风条件超出所声明的航迹保持模型，无法执行。',
  battery_curve_cutoff: '已到参考放电曲线截止点，软件仿真结束。',
  parameters_not_loaded: '可用能量参数尚未加载，无法计算预算。',
  reference_curve_missing: '参考曲线文件缺失，请检查参数文件。',
  event_applied_waiting_for_next_grid_node_decision: '条件已变化：到下一个格节点后重算路线与预算。等待期间，旧预算不作为当前判断。',
  temperature_outside_source_nodes_no_extrapolation: '温度超出参考节点范围，本作品不进行温度外推。',
  known_current_wind_and_upper_voltage_budget_not_real_flight_safety: '按当前已知风场和保守电压估算；预算仅用于声明的仿真条件。',
  comparison_requires_both_full_success: '两种策略都完成全部巡检并返回时，才比较成对仿真耗能。',
  current_known_wind_full_remaining_task_and_final_return_upper_voltage_budget: '按当前已知风场核算完整任务，不预知后续事件。',
  all_remaining_ordered_targets_dwell_final_return_and_reference_reserve_current_wind_only: '按当前已知风场核算所有顺序巡检航段、停留、最终返程及参考储备。',
  same_nonzero_work_and_return_reserve: '同样的非零巡检工作量、均已返航且满足储备要求，允许比较成对仿真耗能。',
  different_or_zero_work_failed_return_or_reserve: '巡检工作量不同或为零、未返航或未满足储备，耗能不直接作节能对比。',
  cancelled_by_user: '操作者已取消任务。',
  operator_cancelled: '操作者已取消任务。',
  simulation_time_limit: '达到本作品仿真时长上限。',
  evaluation_time_limit: '达到预演时长上限。',
  'cannot add an obstacle on the occupied edge or base': '该格处于无人机当前航段或回收点，请选择其他格子。',
  'terminal run does not accept events': '任务已结束，不能继续添加事件。',
  terminal_run_does_not_accept_events: '任务已结束，不能继续添加事件。',
  terminal_run_control_refused: '任务已结束，不能继续暂停或恢复。',
  control_requires_running_to_pause_or_paused_to_resume: '任务状态已变化：运行中才能暂停，已暂停才能继续。页面已同步最新状态，请重试。',
  archived_run_requires_replay_not_resume: '该任务属于旧服务会话。原档案保留，请在结果复查中复演为新任务。',
  curve_fingerprint_changed_replay_refused: '参考曲线版本已变化，不能直接复演此档案。原记录保留。',
  core_or_estimator_version_changed_replay_refused: '仿真核心或估算器版本已变化，不能直接复演此档案。原记录保留。',
  scenario_no_longer_supported_replay_refused: '此档案的场景已不被当前版本支持，原记录保留。',
  scenario_version_or_content_changed_replay_refused: '场景版本或内容已变化，不能直接复演此档案。原记录保留。',
  'Failed to fetch': '无法连接本机任务服务，请检查服务是否启动。',
}

export function reasonText(value) {
  if (!value) return ''
  return reasons[value] || value
}

export const decisionLabels = {
  continue_task: '继续巡检', return: '转为返程', cannot_return: '无法返程', cannot_execute: '无法执行',
  replan: '重新规划', abort: '任务中止', unavailable: '信息不足', complete: '任务完成', planned: '完成规划', returned: '已返回',
}
