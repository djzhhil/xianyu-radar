const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const poolStatuses = {
  watching: "监控中",
  paused: "已暂停",
  dropped: "已移除",
};
const candidateStatuses = {
  new: "新候选",
  watching: "观察中",
  testing: "测试中",
  validated: "已验证",
  rejected: "已排除",
};

async function api(path, options = {}) {
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
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function toast(message) {
  const el = $("#toast");
  el.hidden = false;
  el.textContent = message;
  clearTimeout(toast.timeout);
  toast.timeout = setTimeout(() => { el.hidden = true; }, 3200);
}

function setResult(selector, message, isError = false) {
  const el = $(selector);
  el.textContent = message;
  el.classList.toggle("error", isError);
}

function setLog(selector, value) {
  $(selector).textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

async function withBusy(button, busyText, action) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = busyText;
  try {
    await action();
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function activateTab(name) {
  $$(".tab").forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  $$(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${name}`);
  });
}

async function refreshStatus() {
  const status = await api("/api/status");
  $("#sSellers").textContent = status.counts.watching_sellers;
  $("#sItems").textContent = status.counts.items;
  $("#sCands").textContent = status.counts.candidates;

  const pill = $("#authPill");
  if (!status.auth.ok) {
    pill.textContent = "未登录 · 设置 Cookie";
    pill.className = "auth-pill bad";
  } else if (status.auth.looks_like_placeholder) {
    pill.textContent = "测试 Cookie · 不能在线请求";
    pill.className = "auth-pill bad";
  } else if (status.auth.paused) {
    pill.textContent = "登录态已暂停 · 请更新 Cookie";
    pill.className = "auth-pill bad";
  } else {
    pill.textContent = "登录态已保存";
    pill.className = "auth-pill ok";
  }
  return status;
}

function parseCookieInput(raw) {
  const text = String(raw || "").trim();
  if (!text) throw new Error("请先粘贴 Cookie 或会话 JSON");
  if (text.startsWith("{") || text.startsWith("[")) {
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error("JSON 解析失败，请检查格式");
    }
    if (Array.isArray(parsed)) return { cookies: parsed };
    if (parsed && typeof parsed === "object" && (parsed.cookies || parsed.cookie)) {
      return parsed;
    }
    throw new Error('JSON 需含 "cookie" 字符串或 "cookies" 数组');
  }
  if (!/_m_h5_tk\s*=/.test(text)) {
    throw new Error("Cookie 缺少 _m_h5_tk，无法签名闲鱼请求");
  }
  return { cookie: text.replace(/\r?\n/g, " ").trim() };
}

function addCell(row, value, asCode = false) {
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

function addOption(select, value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  select.appendChild(option);
}

async function refreshPool() {
  const data = await api("/api/pool?all=true");
  const body = $("#poolBody");
  const scanTarget = $("#scanTarget");
  const selected = scanTarget.value;
  body.replaceChildren();
  scanTarget.replaceChildren();
  addOption(scanTarget, "", "全部监控商家");

  if (!data.sellers.length) {
    const row = document.createElement("tr");
    const cell = addCell(row, "暂无商家，请先到“发现商家”输入关键词");
    cell.colSpan = 4;
    body.appendChild(row);
  }

  for (const seller of data.sellers) {
    const row = document.createElement("tr");
    addCell(row, seller.seller_id, true);
    addCell(row, seller.nickname || "—");
    addCell(row, seller.keywords || "—");

    const statusCell = document.createElement("td");
    const select = document.createElement("select");
    select.setAttribute("aria-label", `商家 ${seller.seller_id} 的状态`);
    for (const [value, label] of Object.entries(poolStatuses)) {
      addOption(select, value, label);
    }
    select.value = seller.status;
    select.addEventListener("change", async () => {
      const oldStatus = seller.status;
      select.disabled = true;
      try {
        await api(`/api/pool/${encodeURIComponent(seller.seller_id)}`, {
          method: "PATCH",
          body: JSON.stringify({ status: select.value }),
        });
        toast("商家状态已更新");
        await Promise.all([refreshPool(), refreshStatus()]);
      } catch (error) {
        select.value = oldStatus;
        toast(error.message);
      } finally {
        select.disabled = false;
      }
    });
    statusCell.appendChild(select);
    row.appendChild(statusCell);
    body.appendChild(row);
    addOption(scanTarget, seller.seller_id, `${seller.nickname || seller.seller_id} · ${poolStatuses[seller.status] || seller.status}`);
  }
  if ([...scanTarget.options].some((option) => option.value === selected)) {
    scanTarget.value = selected;
  }
}

async function refreshCandidates() {
  const since = $("#candSince").value;
  const query = since ? `?since=${encodeURIComponent(since)}` : "?since=3650d";
  const data = await api(`/api/candidates${query}`);
  const list = $("#candList");
  list.replaceChildren();
  if (!data.candidates.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "暂无候选。先发现商家，再扫描商家商品。";
    list.appendChild(empty);
    return;
  }

  for (const candidate of data.candidates) {
    const card = document.createElement("article");
    card.className = "cand";
    const title = document.createElement("div");
    title.className = "title";
    title.textContent = candidate.sample_title || candidate.normalized_title || "未命名商品";
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `来源商家 ${candidate.seller_count} · 出现 ${candidate.appearance_count} 次 · 评分 ${Number(candidate.score || 0).toFixed(1)}`;
    const sources = document.createElement("div");
    sources.className = "meta";
    sources.textContent = (candidate.source_sellers || []).join("、");
    const status = document.createElement("select");
    status.setAttribute("aria-label", `候选商品 ${title.textContent} 的状态`);
    for (const [value, label] of Object.entries(candidateStatuses)) {
      addOption(status, value, label);
    }
    status.value = candidate.status;
    status.addEventListener("change", async () => {
      const oldStatus = candidate.status;
      status.disabled = true;
      try {
        await api(`/api/candidates/${candidate.candidate_id}`, {
          method: "PATCH",
          body: JSON.stringify({ status: status.value }),
        });
        toast("候选状态已更新");
        await refreshCandidates();
      } catch (error) {
        status.value = oldStatus;
        toast(error.message);
      } finally {
        status.disabled = false;
      }
    });
    card.append(title, meta, sources, status);
    list.appendChild(card);
  }
}

async function refreshEvents() {
  const since = $("#evtSince").value;
  const data = await api(`/api/events?since=${encodeURIComponent(since)}`);
  const body = $("#evtBody");
  body.replaceChildren();
  if (!data.events.length) {
    const row = document.createElement("tr");
    const cell = addCell(row, "暂无扫描事件");
    cell.colSpan = 5;
    body.appendChild(row);
    return;
  }
  for (const event of data.events) {
    const row = document.createElement("tr");
    addCell(row, event.detected_at);
    addCell(row, event.event_type);
    addCell(row, event.seller_id, true);
    addCell(row, event.item_id, true);
    addCell(row, event.is_baseline ? "是" : "否");
    body.appendChild(row);
  }
}

async function refreshAll() {
  const [status] = await Promise.all([
    refreshStatus(), refreshPool(), refreshCandidates(), refreshEvents(),
  ]);
  return status;
}

$$(".tab").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});
$("#authPill").addEventListener("click", () => {
  activateTab("auth");
  $("#cookieInput").focus();
});

$("#btnSaveCookie").addEventListener("click", () => withBusy($("#btnSaveCookie"), "保存中…", async () => {
  try {
    const payload = parseCookieInput($("#cookieInput").value);
    const result = await api("/api/auth/session", {
      method: "POST",
      body: JSON.stringify({ payload, filename: "default.json" }),
    });
    setLog("#cookieLog", result);
    $("#cookieInput").value = "";
    const message = result.looks_like_placeholder
      ? "已保存测试 Cookie，无法用于在线发现和扫描。"
      : "登录态已保存。实际可用性会在发现或扫描时检查。";
    setResult("#authResult", message);
    toast(message);
    await refreshStatus();
  } catch (error) {
    setLog("#cookieLog", error.message);
    setResult("#authResult", error.message, true);
    toast(error.message);
  }
}));

$("#discoverForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  withBusy(button, "发现中…", async () => {
    const keyword = String(new FormData(event.currentTarget).get("keyword") || "").trim();
    try {
      const result = await api("/api/discover", {
        method: "POST",
        body: JSON.stringify({ keyword }),
      });
      setLog("#discoverLog", result);
      const extra = result.validation_required ? "；闲鱼要求人机验证，已保留识别成功的商家" : "";
      const message = `搜索商品 ${result.item_count} 条，新增商家 ${result.new_sellers} 个，未识别卖家 ${result.skipped_no_seller} 条${extra}。`;
      setResult("#discoverResult", message);
      toast("发现完成，商家可在“商家池”查看");
      await refreshAll();
    } catch (error) {
      setLog("#discoverLog", error.message);
      setResult("#discoverResult", error.message, true);
      toast(error.message);
    }
  });
});

$("#btnScan").addEventListener("click", () => withBusy($("#btnScan"), "扫描中…", async () => {
  const sellerId = $("#scanTarget").value;
  const path = sellerId ? `/api/scan/seller/${encodeURIComponent(sellerId)}` : "/api/scan/pool";
  try {
    const result = await api(path, { method: "POST", body: "{}" });
    setLog("#scanLog", result);
    let message;
    if (sellerId) {
      message = result.status === "ok"
        ? `商家 ${sellerId} 扫描完成：商品 ${result.item_count} 条，事件 ${result.events?.length || 0} 条。`
        : `商家 ${sellerId} 扫描失败：${result.error_kind || "未知原因"}。`;
    } else {
      const failed = (result.results || []).filter((item) => item.status !== "ok").length;
      message = `商家池扫描完成：共 ${result.count} 个商家${failed ? `，其中 ${failed} 个失败` : ""}。`;
    }
    setResult("#scanResult", message, sellerId && result.status !== "ok");
    toast(message);
    await refreshAll();
  } catch (error) {
    setLog("#scanLog", error.message);
    setResult("#scanResult", error.message, true);
    toast(error.message);
  }
}));

$("#candSince").addEventListener("change", () => refreshCandidates().catch((error) => toast(error.message)));
$("#evtSince").addEventListener("change", () => refreshEvents().catch((error) => toast(error.message)));

refreshAll()
  .then((status) => { if (status.auth.ok) activateTab("discover"); })
  .catch((error) => toast(error.message));
