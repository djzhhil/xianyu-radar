const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let data = null;
  const text = await res.text();
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

function toast(msg) {
  const el = $("#toast");
  el.hidden = false;
  el.textContent = msg;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    el.hidden = true;
  }, 3200);
}

function setLog(id, obj) {
  $(id).textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
}

async function refreshStatus() {
  const s = await api("/api/status");
  $("#sSellers").textContent = s.counts.watching_sellers;
  $("#sItems").textContent = s.counts.items;
  $("#sCands").textContent = s.counts.candidates;
  $("#sEvents").textContent = s.counts.events_24h;
  const pill = $("#authPill");
  const cookieStatus = $("#cookieStatus");
  const envLabel = s.env || "?";
  if (s.auth.ok) {
    const modeTag = s.auth.mode === "broker" || s.auth.from_broker ? "Broker" : "本地";
    if (s.auth.looks_like_placeholder) {
      pill.textContent = `${envLabel} · 占位 Cookie（不能真扫）`;
      pill.className = "auth-pill bad";
      cookieStatus.textContent = "占位 Cookie";
      cookieStatus.className = "cookie-status bad";
    } else if (s.auth.paused) {
      pill.textContent = `${envLabel} · ${modeTag} · auth 已暂停`;
      pill.className = "auth-pill bad";
      cookieStatus.textContent = "已暂停";
      cookieStatus.className = "cookie-status warn";
    } else {
      const acct = s.auth.account_id ? ` · ${s.auth.account_id}` : "";
      pill.textContent = `${envLabel} · ${modeTag} · ${s.auth.cookie_count} cookies${acct}`;
      pill.className = "auth-pill ok";
      cookieStatus.textContent = s.auth.from_broker
        ? `Broker 租约 · ${s.auth.cookie_count} 项`
        : `已保存 · ${s.auth.cookie_count} 项`;
      cookieStatus.className = "cookie-status ok";
    }
  } else {
    const brokerHint = s.auth.mode === "broker" ? "连接 Broker / 检查 Helper" : "点此粘贴 Cookie";
    pill.textContent = `${envLabel} · 未登录（${brokerHint}）`;
    pill.className = "auth-pill bad";
    cookieStatus.textContent = "未登录";
    cookieStatus.className = "cookie-status bad";
  }
  const brokerBox = $("#brokerHealth");
  if (brokerBox) {
    if (s.broker) {
      brokerBox.hidden = false;
      brokerBox.textContent = JSON.stringify(s.broker, null, 2);
    } else {
      brokerBox.hidden = true;
      brokerBox.textContent = "";
    }
  }
  if (s.auth.hint) {
    console.info("[auth]", s.auth.hint);
  }
  $$(".env-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.env === s.env);
    b.classList.toggle("prod-active", s.env === "prod" && b.dataset.env === "prod");
  });
  return s;
}

/** Normalize pasted text into session payload for /api/auth/session */
function parseCookieInput(raw) {
  const text = String(raw || "").trim();
  if (!text) throw new Error("请先粘贴 Cookie 内容");

  if (text.startsWith("{") || text.startsWith("[")) {
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error("JSON 解析失败，请检查格式");
    }
    if (Array.isArray(parsed)) {
      return { cookies: parsed };
    }
    if (parsed && typeof parsed === "object") {
      if (parsed.cookies || parsed.cookie) return parsed;
      throw new Error('JSON 需含 "cookie" 字符串或 "cookies" 数组');
    }
    throw new Error("无法识别的 JSON 结构");
  }

  // raw header: a=1; b=2
  if (!text.includes("=")) {
    throw new Error("Cookie 字符串需形如 name=value; name2=value2");
  }
  if (!/_m_h5_tk\s*=/.test(text)) {
    throw new Error("缺少 _m_h5_tk，无法签名 MTOP");
  }
  return { cookie: text.replace(/\r?\n/g, " ").trim() };
}

function currentCookieFmt() {
  return $$(".fmt-btn.active")[0]?.dataset.fmt || "raw";
}

function setupCookiePanel() {
  $$(".fmt-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".fmt-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const input = $("#cookieInput");
      if (btn.dataset.fmt === "json") {
        input.placeholder = '{"cookie":"_m_h5_tk=xxxx_ts; cookie2=..."}';
      } else {
        input.placeholder = "_m_h5_tk=xxxx_1710000000000; _m_h5_tk_enc=...; cookie2=...";
      }
    });
  });

  $("#authPill").addEventListener("click", () => {
    $("#cookiePanel").scrollIntoView({ behavior: "smooth", block: "center" });
    $("#cookieInput").focus();
  });

  $("#btnPasteCookie").addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      $("#cookieInput").value = text.trim();
      toast("已从剪贴板粘贴");
    } catch (e) {
      toast("无法读取剪贴板，请手动 Ctrl+V");
    }
  });

  $("#btnClearCookieInput").addEventListener("click", () => {
    $("#cookieInput").value = "";
    setLog("#cookieLog", "");
  });

  $("#btnSaveCookie").addEventListener("click", async () => {
    try {
      const payload = parseCookieInput($("#cookieInput").value);
      const r = await api("/api/auth/session", {
        method: "POST",
        body: JSON.stringify({ payload, filename: "default.json" }),
      });
      setLog("#cookieLog", r);
      if (r.looks_like_placeholder) {
        toast("已保存，但是测试占位 Cookie");
      } else {
        toast("Cookie 已保存到当前环境");
      }
      await refreshStatus();
    } catch (e) {
      setLog("#cookieLog", e.message);
      toast(e.message);
    }
  });

  $("#btnCheckCookie").addEventListener("click", async () => {
    try {
      // If input has content, save first so check reflects paste
      const raw = $("#cookieInput").value.trim();
      if (raw) {
        const payload = parseCookieInput(raw);
        await api("/api/auth/session", {
          method: "POST",
          body: JSON.stringify({ payload, filename: "default.json" }),
        });
      }
      const r = await api("/api/auth/check", { method: "POST", body: "{}" });
      setLog("#cookieLog", r);
      toast(r.looks_like_placeholder ? "占位 Cookie" : "检查完成");
      await refreshStatus();
    } catch (e) {
      setLog("#cookieLog", e.message);
      toast(e.message);
    }
  });

  $("#btnClearCookiePause").addEventListener("click", async () => {
    const r = await api("/api/auth/clear-pause", { method: "POST", body: "{}" });
    setLog("#cookieLog", r);
    toast("已清除 auth 暂停");
    await refreshStatus();
  });

  const btnBroker = $("#btnBrokerRefresh");
  if (btnBroker) {
    btnBroker.addEventListener("click", async () => {
      try {
        const r = await api("/api/auth/broker/refresh", { method: "POST", body: "{}" });
        setLog("#cookieLog", r);
        toast("已从 Helper 重新租约");
        await refreshStatus();
      } catch (e) {
        setLog("#cookieLog", e.message);
        toast(e.message);
      }
    });
  }
}

function itemUrl(itemId, url) {
  if (url) return url;
  if (itemId) return `https://www.goofish.com/item?id=${encodeURIComponent(itemId)}`;
  return "";
}

function formatPrice(p) {
  if (p == null || p === "") return "—";
  const s = String(p).trim();
  if (!s) return "—";
  return /¥|￥/.test(s) ? s : `¥${s}`;
}

const SH_TZ = "Asia/Shanghai";
const shFmt = new Intl.DateTimeFormat("en-CA", {
  timeZone: SH_TZ,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

/** Format timestamps for display in Asia/Shanghai (DB may be UTC Z or +08:00). */
function shortTime(iso) {
  if (!iso) return "—";
  let s = String(iso).trim();
  // Legacy naive UTC strings → treat as UTC
  if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(s) && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(s)) {
    s = s.replace(" ", "T");
    if (!s.endsWith("Z")) s += "Z";
  }
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) {
    return String(iso).replace("T", " ").slice(0, 19);
  }
  const parts = shFmt.formatToParts(d);
  const get = (t) => parts.find((p) => p.type === t)?.value || "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}:${get("second")}`;
}

function eventTypeLabel(t) {
  const map = {
    NEW_ITEM: "上新",
    REMOVED_ITEM: "下架",
    PRICE_CHANGE: "改价",
    TITLE_CHANGE: "改标题",
  };
  return map[t] || t;
}

const pages = {
  pool: { page: 1, pageSize: 20 },
  events: { page: 1, pageSize: 50 },
  candidates: { page: 1, pageSize: 20 },
  catalog: { page: 1, pageSize: 50, sellerId: null, nickname: null },
};

function renderPager(el, meta, onPage) {
  if (!el) return;
  el.innerHTML = "";
  const total = meta?.total ?? 0;
  const page = meta?.page ?? 1;
  const pagesTotal = meta?.pages ?? 1;
  const size = meta?.page_size ?? 0;
  if (!total) {
    el.innerHTML = `<span class="pager-info">共 0 条</span>`;
    return;
  }
  const info = document.createElement("span");
  info.className = "pager-info";
  info.textContent = `共 ${total} 条 · 第 ${page}/${pagesTotal} 页 · 每页 ${size}`;
  const prev = document.createElement("button");
  prev.type = "button";
  prev.className = "ghost tiny";
  prev.textContent = "上一页";
  prev.disabled = page <= 1;
  prev.onclick = () => onPage(page - 1);
  const next = document.createElement("button");
  next.type = "button";
  next.className = "ghost tiny";
  next.textContent = "下一页";
  next.disabled = page >= pagesTotal;
  next.onclick = () => onPage(page + 1);
  el.append(prev, info, next);
}

async function openCatalog(sellerId, nickname, page = 1) {
  const panel = $("#catalogPanel");
  const title = $("#catalogTitle");
  const hint = $("#catalogHint");
  const body = $("#catalogBody");
  pages.catalog.sellerId = sellerId;
  pages.catalog.nickname = nickname;
  pages.catalog.page = Math.max(1, page);
  panel.hidden = false;
  title.textContent = `在售 · ${nickname || sellerId}`;
  hint.textContent = "加载中…";
  body.innerHTML = "";
  try {
    const data = await api(
      `/api/pool/${encodeURIComponent(sellerId)}/items?page=${pages.catalog.page}&page_size=${pages.catalog.pageSize}`,
    );
    hint.textContent = data.total
      ? `共 ${data.total} 件在售（最近扫描 ${shortTime(data.last_scan_at)}，上海时间）`
      : "暂无在售记录。对该卖家点「扫描」后会写入商品标题与价格。";
    for (const it of data.items || []) {
      const href = itemUrl(it.item_id, it.url);
      const name = it.title || it.last_title || `(无标题 ${it.item_id})`;
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="item-cell">
          <a class="item-link" href="${escapeHtml(href)}" target="_blank" rel="noopener">
            ${escapeHtml(name)}
          </a>
          <div class="item-id"><code>${escapeHtml(it.item_id)}</code></div>
        </td>
        <td class="price">${escapeHtml(formatPrice(it.price || it.last_price))}</td>
        <td><span class="badge ${escapeHtml(it.status || "")}">${escapeHtml(it.status || "—")}</span></td>
        <td>${escapeHtml(shortTime(it.last_seen_at))}</td>`;
      body.appendChild(tr);
    }
    renderPager($("#catalogPager"), data, (p) => openCatalog(sellerId, nickname, p));
  } catch (e) {
    hint.textContent = e.message;
    renderPager($("#catalogPager"), { total: 0 }, () => {});
  }
}

function closeCatalog() {
  const panel = $("#catalogPanel");
  if (panel) panel.hidden = true;
  pages.catalog.sellerId = null;
}

async function refreshPool(page) {
  if (page != null) pages.pool.page = Math.max(1, page);
  const all = $("#poolAll").checked;
  const data = await api(
    `/api/pool?all=${all ? "true" : "false"}&page=${pages.pool.page}&page_size=${pages.pool.pageSize}`,
  );
  pages.pool.page = data.page || pages.pool.page;
  const body = $("#poolBody");
  body.innerHTML = "";
  if (!data.sellers.length) {
    body.innerHTML = `<tr><td colspan="6" class="hint">商家池为空。先用关键词发现，或跑 Demo。</td></tr>`;
    renderPager($("#poolPager"), data, (p) => refreshPool(p));
    return;
  }
  for (const s of data.sellers) {
    const nick = s.nickname || "—";
    const active = s.active_item_count ?? 0;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="seller-cell">
        <div class="seller-nick">${escapeHtml(nick)}</div>
        <div class="item-id"><code>${escapeHtml(s.seller_id)}</code></div>
      </td>
      <td><span class="badge ${escapeHtml(s.status)}">${escapeHtml(s.status)}</span></td>
      <td>${active}</td>
      <td>${escapeHtml(shortTime(s.last_scan_at))}</td>
      <td>${escapeHtml(s.keywords || "—")}</td>
      <td class="ops"></td>`;
    const ops = tr.querySelector(".ops");

    const catBtn = document.createElement("button");
    catBtn.className = "tiny";
    catBtn.textContent = "在售";
    catBtn.onclick = () => openCatalog(s.seller_id, s.nickname, 1);
    ops.appendChild(catBtn);

    for (const st of ["watching", "paused", "dropped"]) {
      if (st === s.status) continue;
      const btn = document.createElement("button");
      btn.className = "ghost tiny";
      btn.textContent = st;
      btn.onclick = async () => {
        await api(`/api/pool/${encodeURIComponent(s.seller_id)}`, {
          method: "PATCH",
          body: JSON.stringify({ status: st }),
        });
        toast(`已设为 ${st}`);
        await refreshPool();
        await refreshStatus();
      };
      ops.appendChild(btn);
    }
    const scanBtn = document.createElement("button");
    scanBtn.className = "ghost tiny";
    scanBtn.textContent = "扫描";
    scanBtn.onclick = async () => {
      try {
        const r = await api(`/api/scan/seller/${encodeURIComponent(s.seller_id)}`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        toast(`扫描 ${r.status} · 事件 ${r.events?.length || 0}`);
        await refreshAll();
        await openCatalog(s.seller_id, s.nickname, 1);
      } catch (e) {
        toast(e.message);
      }
    };
    ops.appendChild(scanBtn);
    body.appendChild(tr);
  }
  renderPager($("#poolPager"), data, (p) => refreshPool(p));
}

async function refreshCandidates(page) {
  if (page != null) pages.candidates.page = Math.max(1, page);
  const since = $("#candSince").value;
  const q = new URLSearchParams({
    page: String(pages.candidates.page),
    page_size: String(pages.candidates.pageSize),
  });
  if (since) q.set("since", since);
  else q.set("since", "3650d");
  const data = await api(`/api/candidates?${q}`);
  pages.candidates.page = data.page || pages.candidates.page;
  const list = $("#candList");
  list.innerHTML = "";
  if (!data.candidates.length) {
    list.innerHTML = `<p class="hint">暂无候选。可点「跑通离线闭环 Demo」生成一条。</p>`;
    renderPager($("#candPager"), data, (p) => refreshCandidates(p));
    return;
  }
  for (const c of data.candidates) {
    const el = document.createElement("article");
    el.className = "cand";
    const title = c.sample_title || c.normalized_title || "(无标题)";
    const href = itemUrl(c.sample_item_id, null);
    const titleHtml = href
      ? `<a class="item-link" href="${escapeHtml(href)}" target="_blank" rel="noopener">${escapeHtml(title)}</a>`
      : escapeHtml(title);
    el.innerHTML = `
      <div class="title">${titleHtml}</div>
      <div class="meta price-line">${escapeHtml(formatPrice(c.sample_price))}
        · 来源卖家 ${c.seller_count} · 出现 ${c.appearance_count}
        · score ${Number(c.score).toFixed(1)}
        · <span class="badge ${escapeHtml(c.status)}">${escapeHtml(c.status)}</span>
      </div>
      <div class="meta">${escapeHtml((c.source_sellers || []).join(", ") || "—")}</div>
      <div class="ops"></div>`;
    const ops = el.querySelector(".ops");
    for (const st of ["watching", "testing", "validated", "rejected"]) {
      const btn = document.createElement("button");
      btn.className = "ghost tiny";
      btn.textContent = st;
      btn.onclick = async () => {
        await api(`/api/candidates/${c.candidate_id}`, {
          method: "PATCH",
          body: JSON.stringify({ status: st }),
        });
        toast(`候选 → ${st}`);
        await refreshCandidates();
      };
      ops.appendChild(btn);
    }
    list.appendChild(el);
  }
  renderPager($("#candPager"), data, (p) => refreshCandidates(p));
}

async function refreshEvents(page) {
  if (page != null) pages.events.page = Math.max(1, page);
  const since = $("#evtSince").value;
  const q = new URLSearchParams({
    since,
    page: String(pages.events.page),
    page_size: String(pages.events.pageSize),
  });
  const data = await api(`/api/events?${q}`);
  pages.events.page = data.page || pages.events.page;
  const body = $("#evtBody");
  body.innerHTML = "";
  if (!data.events.length) {
    body.innerHTML = `<tr><td colspan="6" class="hint">暂无事件。扫描卖家后会出现上新 / 改价等记录。</td></tr>`;
    renderPager($("#evtPager"), data, (p) => refreshEvents(p));
    return;
  }
  for (const e of data.events) {
    const href = itemUrl(e.item_id, e.url);
    const title = e.title || `(无标题 ${e.item_id})`;
    const nick = e.seller_nickname || e.seller_id;
    let priceCell = formatPrice(e.price);
    if (e.event_type === "PRICE_CHANGE" && (e.old_value || e.new_value)) {
      priceCell = `${formatPrice(e.old_value)} → ${formatPrice(e.new_value)}`;
    } else if (e.event_type === "TITLE_CHANGE" && e.new_value) {
      priceCell = formatPrice(e.price);
    }
    const flags = [];
    if (e.is_baseline) flags.push("基线");
    if (e.item_status && e.item_status !== "active") flags.push(e.item_status);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td title="Asia/Shanghai">${escapeHtml(shortTime(e.detected_at))}</td>
      <td><span class="badge evt-${escapeHtml(e.event_type)}">${escapeHtml(eventTypeLabel(e.event_type))}</span></td>
      <td class="seller-cell">
        <div class="seller-nick">${escapeHtml(nick)}</div>
        <div class="item-id"><code>${escapeHtml(e.seller_id)}</code></div>
      </td>
      <td class="item-cell">
        <a class="item-link" href="${escapeHtml(href)}" target="_blank" rel="noopener">${escapeHtml(title)}</a>
        <div class="item-id"><code>${escapeHtml(e.item_id)}</code></div>
      </td>
      <td class="price">${escapeHtml(priceCell)}</td>
      <td>${escapeHtml(flags.join(" · ") || "—")}</td>`;
    body.appendChild(tr);
  }
  renderPager($("#evtPager"), data, (p) => refreshEvents(p));
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function refreshAll() {
  await refreshStatus();
  await refreshPool();
  await refreshCandidates();
  await refreshEvents();
}

function setupTabs() {
  $$(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".tab").forEach((b) => b.classList.remove("active"));
      $$(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`#tab-${btn.dataset.tab}`).classList.add("active");
    });
  });
}

function setupForms() {
  $$(".env-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api("/api/env", {
          method: "POST",
          body: JSON.stringify({ env: btn.dataset.env }),
        });
        toast(`已切换到 ${btn.dataset.env}`);
        await refreshAll();
      } catch (e) {
        toast(e.message);
      }
    });
  });

  $("#discoverForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    const keyword = String(fd.get("keyword") || "").trim();
    const offline = !!fd.get("offline");
    try {
      const body = { keyword, no_enrich: offline };
      if (offline) body.fixture = "tests/fixtures/search_results.json";
      const r = await api("/api/discover", { method: "POST", body: JSON.stringify(body) });
      setLog("#discoverLog", r);
      toast(`发现完成 · 商品 ${r.item_count} · 新卖家 ${r.new_sellers}`);
      await refreshAll();
    } catch (e) {
      setLog("#discoverLog", e.message);
      toast(e.message);
    }
  });

  $("#btnDemoLoop").addEventListener("click", async () => {
    try {
      const r = await api("/api/demo/offline-loop", {
        method: "POST",
        body: JSON.stringify({ keyword: "Sony A7M4", seller_id: "DEMO_SELLER" }),
      });
      setLog("#discoverLog", r);
      toast("已写入 demo 库（不会污染 prod）");
      // switch UI to demo so results are visible
      await api("/api/env", { method: "POST", body: JSON.stringify({ env: "demo" }) });
      await refreshAll();
      $$(".tab").find((t) => t.dataset.tab === "candidates")?.click();
    } catch (e) {
      setLog("#discoverLog", e.message);
      toast(e.message);
    }
  });

  $("#btnScanPool").addEventListener("click", async () => {
    try {
      const r = await api("/api/scan/pool", { method: "POST", body: "{}" });
      setLog("#discoverLog", r);
      const failed = (r.results || []).filter((x) => x.status !== "ok");
      if (failed.length) {
        toast(`池扫描完成，但有 ${failed.length} 个失败/跳过`);
      } else {
        toast(`池扫描完成 · ${r.count} 个卖家`);
      }
      await refreshAll();
    } catch (e) {
      toast(e.message);
      setLog("#discoverLog", e.message);
    }
  });

  $("#poolAll").addEventListener("change", () => {
    pages.pool.page = 1;
    refreshPool(1);
  });
  const poolSize = $("#poolPageSize");
  if (poolSize) {
    poolSize.addEventListener("change", () => {
      pages.pool.pageSize = Number(poolSize.value) || 20;
      pages.pool.page = 1;
      refreshPool(1);
    });
  }
  $("#candSince").addEventListener("change", () => {
    pages.candidates.page = 1;
    refreshCandidates(1);
  });
  $("#evtSince").addEventListener("change", () => {
    pages.events.page = 1;
    refreshEvents(1);
  });
  const evtSize = $("#evtPageSize");
  if (evtSize) {
    evtSize.addEventListener("change", () => {
      pages.events.pageSize = Number(evtSize.value) || 50;
      pages.events.page = 1;
      refreshEvents(1);
    });
  }
  const closeCat = $("#btnCloseCatalog");
  if (closeCat) closeCat.addEventListener("click", () => closeCatalog());

  $("#btnSaveSession").addEventListener("click", async () => {
    try {
      const payload = JSON.parse($("#sessionJson").value);
      const r = await api("/api/auth/session", {
        method: "POST",
        body: JSON.stringify({ payload, filename: "default.json" }),
      });
      setLog("#authLog", r);
      toast(r.looks_like_placeholder ? "已保存，但是测试占位 Cookie" : "会话已保存");
      await refreshStatus();
    } catch (e) {
      setLog("#authLog", e.message);
      toast(e.message);
    }
  });

  $("#btnCheckAuth").addEventListener("click", async () => {
    try {
      const r = await api("/api/auth/status");
      setLog("#authLog", r);
    } catch (e) {
      setLog("#authLog", e.message);
    }
  });

  $("#btnClearPause").addEventListener("click", async () => {
    const r = await api("/api/auth/clear-pause", { method: "POST", body: "{}" });
    setLog("#authLog", r);
    toast("已清除 auth 暂停");
    await refreshStatus();
  });
}

setupTabs();
setupForms();
setupCookiePanel();
refreshAll().catch((e) => toast(e.message));
