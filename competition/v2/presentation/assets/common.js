const API = "/api/v2";
const lastRunKey = "hyzh-v2-last-run";

export const byId = id => document.getElementById(id);

export const decimal = (value, digits = 2) => Number.isFinite(value) ? value.toFixed(digits) : "—";

export function duration(seconds) {
  if (!Number.isFinite(seconds)) return "—";
  const total = Math.round(seconds);
  if (total < 60) return total + " 秒";
  return Math.floor(total / 60) + " 分 " + String(total % 60).padStart(2, "0") + " 秒";
}

export function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);
}

export function readSession(key) {
  try { return JSON.parse(sessionStorage.getItem(key)); }
  catch { return null; }
}

export function saveSession(key, value) {
  try { sessionStorage.setItem(key, JSON.stringify(value)); }
  catch { /* Navigation still works when browser storage is disabled. */ }
}

export function rememberedRun() {
  try { return JSON.parse(localStorage.getItem(lastRunKey))?.id || null; }
  catch { return null; }
}

export function rememberRun(id) {
  try {
    if (id) localStorage.setItem(lastRunKey, JSON.stringify({id}));
    else localStorage.removeItem(lastRunKey);
  } catch { /* The run is still reachable by its URL and in history. */ }
}

export function showNotice(element, message, tone = "") {
  element.hidden = !message;
  element.dataset.tone = tone;
  if (element.textContent !== message) element.textContent = message;
}

export async function request(path, {body, key, format = "json"} = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (key) headers["Idempotency-Key"] = key;
  try {
    const response = await fetch(API + path, {
      method: body === undefined ? "GET" : "POST",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      cache: "no-store"
    });
    if (!response.ok) {
      const value = await response.json().catch(() => null);
      const detail = value?.detail;
      const error = new Error(typeof detail === "string" ? detail :
        response.status === 422 ? "参数未通过校验，请检查输入。" : "服务暂时无法处理这次请求。");
      error.status = response.status;
      error.detail = detail;
      throw error;
    }
    return format === "blob" ? await response.blob() : await response.json();
  } catch (error) {
    if (error.status) throw error;
    const failure = new Error("本机服务暂时无法连接，请确认启动窗口保持打开。", {cause: error});
    failure.network = true;
    throw failure;
  } finally {
    clearTimeout(timeout);
  }
}

export const runPath = id => "/runs/" + encodeURIComponent(id);
export const simulationURL = id => "/simulation?run=" + encodeURIComponent(id);
export const recordURL = id => "/history?run=" + encodeURIComponent(id);

const pendingInMemory = new Map();

export async function createRun(path, body) {
  const slot = "hyzh.pending." + path;
  const signature = JSON.stringify(body);
  const previous = pendingInMemory.get(slot) || readSession(slot);
  const key = previous?.signature === signature ? previous.key : crypto.randomUUID();
  const pending = {signature, key};
  pendingInMemory.set(slot, pending);
  saveSession(slot, pending);
  const clear = () => {
    pendingInMemory.delete(slot);
    saveSession(slot, null);
  };
  try {
    const state = await request(path, {body, key});
    clear();
    return state;
  } catch (error) {
    if (error.status >= 400 && error.status < 500 && error.status !== 408) clear();
    throw error;
  }
}

export function operationError(error, retrySafe = false) {
  if (retrySafe && (error.network || error.status >= 500 || error.status === 408)) {
    return "尚未确认这次操作。保持相同条件重试，服务会找回已保存的结果。";
  }
  return error.message;
}

export async function downloadRun(id) {
  const blob = await request(runPath(id) + "/export", {format: "blob"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "寒域智航-运行-" + id.slice(0, 8) + ".json";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
