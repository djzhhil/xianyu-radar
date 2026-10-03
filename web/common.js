export const scanErrors = {
  incomplete: "分页不完整", count_drop: "商品数骤降，等待复扫",
  auth: "登录态失效", auth_paused: "在线工作已暂停", token: "签名凭证需在 Helper 恢复",
  verification_required: "需要在 Helper 完成人机验证", rate_limit: "闲鱼限流，请稍后重试",
  helper_config: "Helper 未配置", helper_auth: "Helper 登录配置有误",
  helper_permission: "Helper 用户无权访问目标账号", helper_account: "Helper 账号或接口不存在",
  helper_unavailable: "Helper 不可达", cookie_snapshot_unavailable: "请先在 Helper 登录",
  helper_contract: "Helper 响应不符合接入要求", credential_conflict: "Helper 凭证已变化，请重新继续操作",
  cookie_update_unknown: "Cookie 回写结果未知，已停止", cookie_update_rejected: "Helper 拒绝更新，已停止",
  cookie_update_limit: "Cookie 更新超过接入限制，已停止",
};

export const runStatuses = { running: "进行中", ok: "成功", failed: "失败", suspect: "待复核", partial: "部分完成", parse_failed: "解析失败", ...scanErrors };


export const pageSize = 20;

export const $ = (selector) => document.querySelector(selector);
export const $$ = (selector) => [...document.querySelectorAll(selector)];

export async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const detail = data?.detail || data?.error || res.statusText;
    throw new Error(typeof detail === "string" ? detail : detail?.message || JSON.stringify(detail));
  }
  return data;
}

export function toast(message) {
  const el = $("#toast");
  el.hidden = false;
  el.textContent = message;
  clearTimeout(toast.timeout);
  toast.timeout = setTimeout(() => { el.hidden = true; }, 3200);
}

export function setResult(selector, message, isError = false) {
  const el = $(selector);
  el.textContent = message;
  el.classList.toggle("error", isError);
}

export function setLog(selector, value) {
  $(selector).textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

export async function withBusy(button, busyText, action) {
  const content = [...button.childNodes];
  button.disabled = true;
  button.textContent = busyText;
  try {
    await action();
  } finally {
    button.disabled = false;
    button.replaceChildren(...content);
  }
}

export function formatTime(value) {
  if (!value) return "暂无";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(date);
}

export function addCell(row, value, asCode = false) {
  const cell = document.createElement("td");
  if (asCode) {
    const code = document.createElement("code");
    code.textContent = String(value ?? "—");
    cell.appendChild(code);
  } else {
    cell.textContent = String(value ?? "—");
  }
  row.appendChild(cell);
  return cell;
}

export function addEmptyRow(body, message, columns) {
  const row = document.createElement("tr");
  addCell(row, message).colSpan = columns;
  body.appendChild(row);
}

export function safeLink(url, label = "查看商品") {
  try {
    const target = new URL(url);
    if (!["http:", "https:"].includes(target.protocol)) throw new Error("unsupported URL");
    const link = document.createElement("a");
    link.href = target.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = label;
    return link;
  } catch {
    return document.createTextNode("—");
  }
}

export function addLinkCell(row, url, label = "查看商品") {
  const cell = document.createElement("td");
  cell.appendChild(safeLink(url, label));
  row.appendChild(cell);
}

export function showPager(prefix, offset, total) {
  const page = Math.floor(offset / pageSize) + 1;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  $(`#${prefix}Page`).textContent = `第 ${page} / ${pages} 页 · 共 ${total} 条`;
  $(`#${prefix}Prev`).disabled = offset === 0;
  $(`#${prefix}Next`).disabled = offset + pageSize >= total;
}

export function addOption(select, value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  select.appendChild(option);
}
