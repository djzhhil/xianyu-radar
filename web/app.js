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
const eventTypes = {
  NEW_ITEM: "新增商品", REMOVED_ITEM: "商品下架", PRICE_CHANGED: "价格变化", TITLE_CHANGED: "标题变化",
};
const itemStatuses = { active: "在售", removed: "已下架", unknown: "未知" };
const itemSources = { discovery: "关键词发现", seller_scan: "商家扫描" };
const runStatuses = { running: "进行中", ok: "成功", failed: "失败", suspect: "待复核", partial: "部分完成", parse_failed: "解析失败", rate_limit: "已限流", verification_required: "需要验证", auth: "登录态失效" };
const scanErrors = { incomplete: "分页不完整", count_drop: "商品数骤降，等待复扫" };
const pageSize = 20;
const viewState = { sellerId: null, sellerOffset: 0, eventsOffset: 0, candidatesOffset: 0 };

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

function addEmptyRow(body, message, columns) {
  const row = document.createElement("tr");
  addCell(row, message).colSpan = columns;
  body.appendChild(row);
}

function safeLink(url, label = "查看商品") {
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

function addLinkCell(row, url, label = "查看商品") {
  const cell = document.createElement("td");
  cell.appendChild(safeLink(url, label));
  row.appendChild(cell);
}

function showPager(prefix, offset, total) {
  const page = Math.floor(offset / pageSize) + 1;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  $(`#${prefix}Page`).textContent = `第 ${page} / ${pages} 页 · 共 ${total} 条`;
  $(`#${prefix}Prev`).disabled = offset === 0;
  $(`#${prefix}Next`).disabled = offset + pageSize >= total;
}

function renderDiscoverItems(items) {
  const body = $("#discoverBody");
  body.replaceChildren();
  if (!items.length) return addEmptyRow(body, "本次搜索没有可展示的商品", 4);
  for (const item of items) {
    const row = document.createElement("tr");
    addCell(row, item.title || item.item_id || "—");
    addCell(row, item.price);
    const sellerCell = document.createElement("td");
    if (item.seller_id) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ghost tiny text-button";
      button.textContent = item.seller_nick || item.seller_id;
      button.addEventListener("click", () => openSeller(item.seller_id).catch((error) => toast(error.message)));
      sellerCell.appendChild(button);
    } else {
      sellerCell.textContent = "未识别";
    }
    row.appendChild(sellerCell);
    addLinkCell(row, item.url);
    body.appendChild(row);
  }
}

async function refreshDiscoveryRuns() {
  const data = await api("/api/discover/runs?limit=10");
  const body = $("#discoveryRunsBody");
  body.replaceChildren();
  if (!data.runs.length) return addEmptyRow(body, "暂无发现记录", 7);
  for (const run of data.runs) {
    const row = document.createElement("tr");
    const counts = `${run.page_count} / ${run.raw_result_count} / ${run.unique_item_count || run.item_count}`;
    const state = `${runStatuses[run.status] || run.status}${run.error_kind ? ` · ${run.error_kind}` : ""}${run.unresolved_count ? ` · 未识别 ${run.unresolved_count}` : ""}${run.unparsed_count ? ` · 未解析 ${run.unparsed_count}` : ""}`;
    [run.started_at, run.keyword, counts, run.unique_seller_count, run.seller_count, state].forEach((value) => addCell(row, value));
    const actions = document.createElement("td");
    const detail = document.createElement("button");
    detail.type = "button";
    detail.className = "ghost tiny";
    detail.textContent = "查看诊断";
    detail.addEventListener("click", async () => {
      try { setLog("#discoverLog", await api(`/api/discover/runs/${encodeURIComponent(run.id)}`)); }
      catch (error) { toast(error.message); }
    });
    actions.appendChild(detail);
    if (run.status !== "ok" && run.status !== "running" && run.next_page <= 50) {
      const resume = document.createElement("button");
      resume.type = "button";
      resume.className = "ghost tiny";
      resume.textContent = "继续";
      resume.addEventListener("click", () => withBusy(resume, "继续中…", async () => {
        try {
          const max_pages = Math.max(Number($("#discoverForm [name=max_pages]").value) || 3, run.next_page || 1);
          const result = await api("/api/discover", { method: "POST", body: JSON.stringify({ keyword: run.keyword, max_pages, resume_run_id: run.id }) });
          setLog("#discoverLog", result);
          renderDiscoverItems(result.items || []);
          setResult("#discoverResult", `已继续处理：${result.page_count} 页，识别商家 ${result.unique_seller_count} 个，未识别商品 ${result.skipped_no_seller} 条。`);
          await refreshAll();
        } catch (error) { setLog("#discoverLog", error.message); toast(error.message); await refreshDiscoveryRuns(); }
      }));
      actions.appendChild(resume);
    }
    row.appendChild(actions);
    body.appendChild(row);
  }
}

async function openSeller(sellerId, offset = 0, activate = true) {
  const data = await api(`/api/pool/${encodeURIComponent(sellerId)}?limit=${pageSize}&offset=${offset}`);
  viewState.sellerId = sellerId;
  viewState.sellerOffset = offset;
  const seller = data.seller;
  $("#sellerTags").value = (seller.tags || []).join(", ");
  $("#sellerNotes").value = seller.notes || "";
  setResult("#sellerMetadataResult", "");
  $("#sellerDetail").hidden = false;
  $("#sellerDetailTitle").textContent = `${seller.nickname || seller.seller_id} · ${seller.seller_id}`;
  $("#sellerDetailMeta").textContent = `状态：${poolStatuses[seller.status] || seller.status} · 最近扫描：${seller.last_scan_at || "暂无"} · 连续失败：${seller.consecutive_failures || 0} · 已存商品：${data.total_items}`;
  const entriesBody = $("#sellerEntriesBody");
  entriesBody.replaceChildren();
  if (!data.entries.length) addEmptyRow(entriesBody, "暂无入池记录", 4);
  for (const entry of data.entries) {
    const row = document.createElement("tr");
    [entry.source_keyword, entry.source_item_id, entry.reason === "manual" ? "手动添加" : entry.reason, entry.joined_at].forEach((value) => addCell(row, value));
    entriesBody.appendChild(row);
  }
  const itemsBody = $("#sellerItemsBody");
  itemsBody.replaceChildren();
  if (!data.items.length) addEmptyRow(itemsBody, "暂无已存商品。请先扫描该商家。", 6);
  for (const item of data.items) {
    const row = document.createElement("tr");
    [item.title || item.item_id, item.price, itemStatuses[item.status] || item.status, itemSources[item.source] || item.source, item.last_seen_at].forEach((value) => addCell(row, value));
    addLinkCell(row, item.url);
    itemsBody.appendChild(row);
  }
  showPager("sellerItems", offset, data.total_items);
  if (activate) activateTab("pool");
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
    addEmptyRow(body, "暂无商家，请先到“发现商家”输入关键词", 5);
  }

  for (const seller of data.sellers) {
    const row = document.createElement("tr");
    const sellerCell = document.createElement("td");
    const detailButton = document.createElement("button");
    detailButton.type = "button";
    detailButton.className = "ghost tiny text-button";
    detailButton.textContent = seller.seller_id;
    detailButton.addEventListener("click", () => openSeller(seller.seller_id).catch((error) => toast(error.message)));
    sellerCell.appendChild(detailButton);
    row.appendChild(sellerCell);
    addCell(row, [seller.nickname || "—", ...(seller.tags || [])].join(" · "));
    addCell(row, seller.keywords || "—");
    addCell(row, seller.last_scan_at);

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
        if (viewState.sellerId === seller.seller_id) await openSeller(seller.seller_id, viewState.sellerOffset);
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
  if (viewState.sellerId && !data.sellers.some((seller) => seller.seller_id === viewState.sellerId)) {
    viewState.sellerId = null;
    $("#sellerDetail").hidden = true;
  }
}

async function refreshCandidates() {
  const since = $("#candSince").value;
  const quality = $("#candQuality").value;
  const status = $("#candStatus").value;
  const query = `?since=${encodeURIComponent(since)}&quality=${encodeURIComponent(quality)}&status=${encodeURIComponent(status)}&limit=${pageSize}&offset=${viewState.candidatesOffset}`;
  const data = await api(`/api/candidates${query}`);
  $("#candTotal").textContent = data.summary.total;
  $("#candNew").textContent = data.summary.by_status.new || 0;
  $("#candMulti").textContent = data.summary.multi_seller;
  $("#candValidated").textContent = data.summary.by_status.validated || 0;
  const list = $("#candList");
  list.replaceChildren();
  showPager("candidates", viewState.candidatesOffset, data.total);
  if (!data.candidates.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = data.total
      ? "这一页没有候选，请返回上一页。"
      : data.summary.total
        ? "当前状态下没有候选，请调整状态筛选。"
        : "暂无候选。先发现商家，再扫描商家商品。";
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
    const qualityLabel = candidate.quality_flag === "legacy_unverified" ? "历史待核实" : "新扫描候选";
    meta.textContent = `${qualityLabel} · 参考价格 ${candidate.sample_price || "—"} · 来源商家 ${candidate.seller_count} · 出现 ${candidate.appearance_count} 次 · 评分 ${Number(candidate.score || 0).toFixed(1)}`;
    const sources = document.createElement("div");
    sources.className = "meta";
    sources.textContent = `商家：${(candidate.source_sellers || []).join("、") || "—"}`;
    const dates = document.createElement("div");
    dates.className = "meta";
    dates.textContent = `首次发现 ${candidate.first_seen_at || "—"} · 最近发现 ${candidate.last_seen_at || "—"}`;
    const actions = document.createElement("div");
    actions.className = "cand-actions";
    actions.appendChild(safeLink(candidate.sample_url));
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
    actions.appendChild(status);
    card.append(title, meta, sources, dates, actions);
    list.appendChild(card);
  }
}

async function refreshScanRuns() {
  const data = await api("/api/scan/runs?limit=10");
  const body = $("#scanRunsBody");
  body.replaceChildren();
  if (!data.runs.length) return addEmptyRow(body, "暂无扫描记录", 5);
  for (const run of data.runs) {
    const row = document.createElement("tr");
    const diagnosis = scanErrors[run.error_kind] || run.error_kind || runStatuses[run.status] || run.status;
    const detail = run.page_count ? `${diagnosis} · ${run.page_count} 页 · 预期 ${run.expected_count ?? "未知"} · ${run.finish_reason || "—"}` : diagnosis;
    [run.started_at, run.seller_id, run.item_count, run.event_count, detail].forEach((value) => addCell(row, value));
    body.appendChild(row);
  }
}

async function refreshEvents() {
  const since = $("#evtSince").value;
  const data = await api(`/api/events?since=${encodeURIComponent(since)}&limit=${pageSize}&offset=${viewState.eventsOffset}`);
  const body = $("#evtBody");
  body.replaceChildren();
  showPager("events", viewState.eventsOffset, data.total);
  if (!data.events.length) {
    return addEmptyRow(body, data.total ? "这一页没有事件，请返回上一页。" : "暂无扫描事件", 7);
  }
  for (const event of data.events) {
    const row = document.createElement("tr");
    addCell(row, event.detected_at);
    addCell(row, eventTypes[event.event_type] || event.event_type);
    addCell(row, event.seller_id, true);
    addCell(row, event.item_id, true);
    addCell(row, event.old_value);
    addCell(row, event.new_value);
    addCell(row, event.is_baseline ? "是" : "否");
    body.appendChild(row);
  }
}

async function refreshAll() {
  const [status] = await Promise.all([
    refreshStatus(), refreshPool(), refreshCandidates(), refreshEvents(), refreshDiscoveryRuns(), refreshScanRuns(),
  ]);
  if (viewState.sellerId) await openSeller(viewState.sellerId, viewState.sellerOffset, false);
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
    const max_pages = Number(new FormData(event.currentTarget).get("max_pages")) || 3;
    try {
      const result = await api("/api/discover", {
        method: "POST",
        body: JSON.stringify({ keyword, max_pages }),
      });
      setLog("#discoverLog", result);
      renderDiscoverItems(result.items || []);
      const extra = result.status !== "ok" ? `；${runStatuses[result.status] || result.status}（${result.error_kind || "未识别"}）` : "";
      const message = `搜索 ${result.page_count} 页，原始结果 ${result.raw_result_count} 条，去重商品 ${result.item_count} 条，识别商家 ${result.unique_seller_count} 个，新增商家 ${result.new_sellers} 个，未识别卖家 ${result.skipped_no_seller} 条，未解析 ${result.unparsed_count} 条${extra}。`;
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

$("#addSellerForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form));
  withBusy(form.querySelector('button[type="submit"]'), "添加中…", async () => {
    try {
      const result = await api("/api/pool", { method: "POST", body: JSON.stringify(payload) });
      form.reset();
      setResult("#addSellerResult", `${result.added ? "已添加" : "已在商家池"}：${result.seller_id} · ${poolStatuses[result.status] || result.status}`);
      await Promise.all([refreshPool(), refreshStatus()]);
      await openSeller(result.seller_id);
    } catch (error) {
      setResult("#addSellerResult", error.message, true);
    }
  });
});

$("#sellerMetadataForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const sellerId = viewState.sellerId;
  if (!sellerId) return;
  const payload = { notes: $("#sellerNotes").value, tags: $("#sellerTags").value.split(/[,，]/).map(tag => tag.trim()).filter(Boolean) };
  withBusy(event.currentTarget.querySelector('button[type="submit"]'), "保存中…", async () => {
    try {
      await api(`/api/pool/${encodeURIComponent(sellerId)}/metadata`, { method: "PATCH", body: JSON.stringify(payload) });
      await refreshPool();
      if (viewState.sellerId === sellerId) setResult("#sellerMetadataResult", "备注与标签已保存");
    } catch (error) {
      if (viewState.sellerId === sellerId) setResult("#sellerMetadataResult", error.message, true);
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
        : `商家 ${sellerId} 扫描未提交：${scanErrors[result.error_kind] || result.error_kind || "未知原因"}；已读 ${result.item_count || 0} 条，预期 ${result.expected_count ?? "未知"} 条。`;
    } else {
      const uncommitted = (result.results || []).filter((item) => item.status !== "ok").length;
      message = `商家池扫描完成：共 ${result.count} 个商家${uncommitted ? `，其中 ${uncommitted} 个未提交` : ""}。`;
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

$("#closeSellerDetail").addEventListener("click", () => {
  viewState.sellerId = null;
  $("#sellerDetail").hidden = true;
});
for (const [id, delta] of [["sellerItemsPrev", -1], ["sellerItemsNext", 1]]) {
  $(`#${id}`).addEventListener("click", () => openSeller(viewState.sellerId, viewState.sellerOffset + delta * pageSize).catch((error) => toast(error.message)));
}
for (const [prefix, stateKey, refresh] of [
  ["events", "eventsOffset", refreshEvents],
  ["candidates", "candidatesOffset", refreshCandidates],
]) {
  for (const [direction, delta] of [["Prev", -1], ["Next", 1]]) {
    $(`#${prefix}${direction}`).addEventListener("click", () => {
      viewState[stateKey] += delta * pageSize;
      refresh().catch((error) => {
        viewState[stateKey] -= delta * pageSize;
        toast(error.message);
      });
    });
  }
}
$("#candSince").addEventListener("change", () => {
  viewState.candidatesOffset = 0;
  refreshCandidates().catch((error) => toast(error.message));
});
$("#candQuality").addEventListener("change", () => {
  viewState.candidatesOffset = 0;
  refreshCandidates().catch((error) => toast(error.message));
});
$("#candStatus").addEventListener("change", () => {
  viewState.candidatesOffset = 0;
  refreshCandidates().catch((error) => toast(error.message));
});
$("#evtSince").addEventListener("change", () => {
  viewState.eventsOffset = 0;
  refreshEvents().catch((error) => toast(error.message));
});

refreshAll()
  .then((status) => { if (status.auth.ok) activateTab("discover"); })
  .catch((error) => toast(error.message));
