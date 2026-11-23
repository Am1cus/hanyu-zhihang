const canvasColors = {
  paper: "#f3f7fa", grid: "#c8d5df", calm: "#d5e9f8", block: "#c5cdd3",
  hatch: "#768793", newBlock: "#ffead1", newHatch: "#996026",
  go: "#0069b4", returning: "#7755a7", flown: "#477284",
  base: "#253a4a", target: "#075994", done: "#246f53", point: "#506574"
};

export function samePath(first, second) {
  return first.length === second.length &&
    first.every(([x, y], index) => x === second[index][0] && y === second[index][1]);
}

function mapPlot(canvas, {width, height, blocked}, marked = new Set(), shaded = []) {
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (w < 30 || h < 30) return null;
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  const context = canvas.getContext("2d");
  context.scale(scale, scale);
  const cell = Math.min((w - 34) / width, (h - 24) / height);
  const left = (w - cell * width) / 2;
  const top = (h - cell * height) / 2;
  const point = ([x, y]) => [left + (x + .5) * cell, top + (y + .5) * cell];
  context.fillStyle = canvasColors.paper;
  context.fillRect(0, 0, w, h);
  for (const area of shaded) {
    const xMin = Math.max(0, Math.ceil(area.x_min));
    const yMin = Math.max(0, Math.ceil(area.y_min));
    const xMax = Math.min(width - 1, Math.floor(area.x_max));
    const yMax = Math.min(height - 1, Math.floor(area.y_max));
    if (xMin > xMax || yMin > yMax) continue;
    context.fillStyle = canvasColors.calm;
    context.fillRect(left + xMin * cell, top + yMin * cell, (xMax - xMin + 1) * cell, (yMax - yMin + 1) * cell);
  }
  context.strokeStyle = canvasColors.grid;
  context.lineWidth = .55;
  context.beginPath();
  for (let col = 0; col <= width; col++) {
    const x = left + col * cell;
    context.moveTo(x, top);
    context.lineTo(x, top + height * cell);
  }
  for (let row = 0; row <= height; row++) {
    const y = top + row * cell;
    context.moveTo(left, y);
    context.lineTo(left + width * cell, y);
  }
  context.stroke();
  for (const position of blocked) {
    const [x, y] = point(position);
    const fresh = marked.has(position.join(","));
    const half = cell / 2 - .9;
    context.fillStyle = fresh ? canvasColors.newBlock : canvasColors.block;
    context.fillRect(x - half, y - half, half * 2, half * 2);
    context.strokeStyle = fresh ? canvasColors.newHatch : canvasColors.hatch;
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(x - half, y + half);
    context.lineTo(x + half, y - half);
    if (fresh) {
      context.moveTo(x - half, y - half);
      context.lineTo(x + half, y + half);
    }
    context.stroke();
  }
  function line(path, color, thickness, dash = []) {
    if (path.length < 2) return;
    context.save();
    context.beginPath();
    context.strokeStyle = color;
    context.lineWidth = thickness;
    context.lineJoin = "round";
    context.setLineDash(dash);
    path.forEach((position, index) => {
      const [x, y] = point(position);
      if (index) context.lineTo(x, y);
      else context.moveTo(x, y);
    });
    context.stroke();
    context.restore();
  }
  function arrow(path, index, color, fraction = .5) {
    if (!path[index + 1]) return;
    const [ax, ay] = point(path[index]);
    const [bx, by] = point(path[index + 1]);
    context.save();
    context.translate(ax + (bx - ax) * fraction, ay + (by - ay) * fraction);
    context.rotate(Math.atan2(by - ay, bx - ax));
    context.beginPath();
    context.moveTo(-4, -3);
    context.lineTo(1, 0);
    context.lineTo(-4, 3);
    context.strokeStyle = color;
    context.lineWidth = 2;
    context.stroke();
    context.restore();
  }
  function label(x, y, text, color, size) {
    context.font = '600 ' + size + 'px -apple-system, "PingFang SC", sans-serif';
    context.textAlign = "center";
    context.strokeStyle = canvasColors.paper;
    context.lineWidth = 3;
    context.strokeText(text, x, y);
    context.fillStyle = color;
    context.fillText(text, x, y);
  }
  function marker(position, {color, text, below = false, size = 5}) {
    if (!position) return;
    const [x, y] = point(position);
    context.beginPath();
    context.arc(x, y, size, 0, Math.PI * 2);
    context.fillStyle = color;
    context.fill();
    context.strokeStyle = canvasColors.paper;
    context.lineWidth = 1.6;
    context.stroke();
    if (text) label(x, below ? y + 18 : y - 9, text, color, 11);
  }
  return {line, arrow, marker};
}

export function calmAreas(grid) {
  const [base, ...areas] = grid.wind_regions;
  if (!base) return [];
  const magnitude = area => Math.hypot(...area.vector);
  return areas.filter(area => magnitude(area) < magnitude(base));
}

export function drawRoundTrip(canvas, data, route, turnaround) {
  const plot = mapPlot(canvas, data.grid, new Set(), calmAreas(data.grid));
  if (!plot) return;
  const outward = route.outbound.path || [];
  const inward = route.inbound.path || [];
  const retraces = outward.length > 1 && samePath(outward, inward.slice().reverse());
  plot.line(outward, canvasColors.go, 3);
  if (!retraces) plot.line(inward, canvasColors.returning, 2.6, [5, 3]);
  plot.arrow(outward, Math.floor((outward.length - 1) * .34), canvasColors.go);
  plot.arrow(inward, Math.floor((inward.length - 1) * (retraces ? .34 : .5)),
    retraces ? canvasColors.go : canvasColors.returning);
  if (!retraces) markSharedDirections(plot, outward, inward);
  plot.marker(data.start, {color: canvasColors.base, text: "基地", below: true});
  plot.marker(data.goal, {color: canvasColors.target, text: "目标点", below: true});
  if (turnaround) plot.marker(turnaround, {color: canvasColors.newHatch, text: "折返点"});
}

function markSharedDirections(plot, outward, inward) {
  const key = (start, end) => start.join(",") + ">" + end.join(",");
  const returnEdges = new Set(inward.slice(1).map((end, i) => key(end, inward[i])));
  const shared = outward.slice(1).map((end, i) => returnEdges.has(key(outward[i], end)));
  let start = 0;
  while (start < shared.length) {
    if (!shared[start]) { start++; continue; }
    let end = start + 1;
    while (shared[end]) end++;
    const middle = Math.floor((start + end - 1) / 2);
    plot.arrow(outward, middle, canvasColors.go, .8);
    plot.arrow([outward[middle + 1], outward[middle]], 0, canvasColors.returning, .8);
    start = end;
  }
}

export function drawMission(canvas, state) {
  const marked = new Set(state.events.filter(event => event.applied && event.payload.type === "obstacle")
    .flatMap(event => event.payload.cells.map(point => point.join(","))));
  const plot = mapPlot(canvas, state.grid, marked);
  if (!plot) return;
  const decision = state.current_decision;
  const returning = decision?.planned_legs?.at(-1);
  const live = state.is_preview || (state.runtime_available && ["RUNNING", "PAUSED"].includes(state.status));
  const completed = new Set(state.completed_ids);
  const next = live && state.stage !== "RETURN" ? decision?.record?.ordered_task_ids?.[0] : null;
  plot.line(state.executed_path, canvasColors.flown, 2.5);
  if (live && returning?.to_id === "BASE") plot.line(returning.path, canvasColors.returning, 2.2, [5, 3]);
  if (live && state.path.length > 1) {
    const ahead = [state.position, ...state.path.slice(1)];
    const home = state.stage === "RETURN";
    plot.line(ahead, home ? canvasColors.returning : canvasColors.go, 3, home ? [5, 3] : []);
  }
  plot.marker(state.base, {color: canvasColors.base, text: "管理站", below: true});
  for (const task of state.tasks) {
    const color = completed.has(task.id) ? canvasColors.done : next === task.id ? canvasColors.go : canvasColors.point;
    plot.marker(task.position, {color, text: task.id, size: next === task.id ? 5.5 : 4});
  }
  if (!state.is_preview) plot.marker(state.position, {color: canvasColors.base, size: 6.5});
}
