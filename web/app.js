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
    if (s.auth.looks_like_placeholder) {
      pill.textContent = `${envLabel} · 占位 Cookie（不能真扫）`;
      pill.className = "auth-pill bad";
      cookieStatus.textContent = "占位 Cookie";
      cookieStatus.className = "cookie-status bad";
    } else if (s.auth.paused) {
      pill.textContent = `${envLabel} · 已登录 · auth 已暂停`;
      pill.className = "auth-pill bad";
      cookieStatus.textContent = "已暂停";
      cookieStatus.className = "cookie-status warn";
    } else {
      pill.textContent = `${envLabel} · 已登录 · ${s.auth.cookie_count} cookies`;
      pill.className = "auth-pill ok";
      cookieStatus.textContent = `已保存 · ${s.auth.cookie_count} 项`;
      cookieStatus.className = "cookie-status ok";
    }
  } else {
    pill.textContent = `${envLabel} · 未登录（点此粘贴 Cookie）`;
    pill.className = "auth-pill bad";
    cookieStatus.textContent = "未登录";
    cookieStatus.className = "cookie-status bad";
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
}

async function refreshPool() {
  const all = $("#poolAll").checked;
  const data = await api(`/api/pool?all=${all ? "true" : "false"}`);
  const body = $("#poolBody");
  body.innerHTML = "";
  for (const s of data.sellers) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><code>${s.seller_id}</code></td>
      <td>${s.nickname || "—"}</td>
      <td><span class="badge ${s.status}">${s.status}</span></td>
      <td>${s.keywords || "—"}</td>
      <td class="ops"></td>`;
    const ops = tr.querySelector(".ops");
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
    scanBtn.className = "tiny";
    scanBtn.textContent = "扫描";
    scanBtn.onclick = async () => {
      try {
        const r = await api(`/api/scan/seller/${encodeURIComponent(s.seller_id)}`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        toast(`扫描 ${r.status} · 事件 ${r.events?.length || 0}`);
        await refreshAll();
      } catch (e) {
        toast(e.message);
      }
    };
    ops.appendChild(scanBtn);
    body.appendChild(tr);
  }
}

async function refreshCandidates() {
  const since = $("#candSince").value;
  const q = since ? `?since=${encodeURIComponent(since)}` : "?since=3650d";
  const data = await api(`/api/candidates${q}`);
  const list = $("#candList");
  list.innerHTML = "";
  if (!data.candidates.length) {
    list.innerHTML = `<p class="hint">暂无候选。可点「跑通离线闭环 Demo」生成一条。</p>`;
    return;
  }
  for (const c of data.candidates) {
    const el = document.createElement("article");
    el.className = "cand";
    el.innerHTML = `
      <div class="title">${escapeHtml(c.sample_title || c.normalized_title)}</div>
      <div class="meta">
        来源卖家 ${c.seller_count} · 出现 ${c.appearance_count} · score ${Number(c.score).toFixed(1)}
        · <span class="badge ${c.status}">${c.status}</span>
      </div>
      <div class="meta">${escapeHtml((c.source_sellers || []).join(", "))}</div>
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
}

async function refreshEvents() {
  const since = $("#evtSince").value;
  const data = await api(`/api/events?since=${encodeURIComponent(since)}`);
  const body = $("#evtBody");
  body.innerHTML = "";
  for (const e of data.events) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${e.detected_at}</td>
      <td>${e.event_type}</td>
      <td><code>${e.seller_id}</code></td>
      <td><code>${e.item_id}</code></td>
      <td>${e.is_baseline ? "yes" : ""}</td>`;
    body.appendChild(tr);
  }
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

  $("#poolAll").addEventListener("change", () => refreshPool());
  $("#candSince").addEventListener("change", () => refreshCandidates());
  $("#evtSince").addEventListener("change", () => refreshEvents());

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
