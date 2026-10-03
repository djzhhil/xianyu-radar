import { initCandidates, refreshCandidates } from "./candidates.js";
import { initPool, openSeller, refreshPool, refreshOpenSeller } from "./pool.js";
import { initDiscovery, refreshDiscoveryRuns } from "./discovery.js";
import { initAuth, refreshStatus } from "./auth.js";
import {
  runStatuses, scanErrors, $, $$, api, toast, setResult, setLog, withBusy, formatTime,
  addCell, addEmptyRow, safeLink, addLinkCell, showPager, addOption, pageSize,
} from "./common.js";

const eventTypes = {
  NEW_ITEM: "新增商品", REMOVED_ITEM: "商品下架", PRICE_CHANGED: "价格变化", TITLE_CHANGED: "标题变化",
};
const viewState = { eventsOffset: 0 };
const scanReview = { id: null, offset: 0 };

function activateTab(name) {
  const names = { pool: "商家池", candidates: "候选商品", scan: "扫描与变化", discover: "发现商家", auth: "登录设置" };
  if (!Object.hasOwn(names, name)) return;
  $("#pageTitle").textContent = names[name];
  document.title = `${names[name]} · 闲鱼补货工作台`;
  history.replaceState(null, "", `#${name}`);
  $$(".tab").forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  $$(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${name}`);
  });
}

window.addEventListener("hashchange", () => activateTab(location.hash.slice(1)));

async function openScanReview(scanId, offset = 0) {
  scanReview.id = scanId;
  const data = await api(`/api/scan/runs/${encodeURIComponent(scanId)}/candidate-decisions?limit=${pageSize}&offset=${offset}`);
  if (scanReview.id !== scanId) return;
  scanReview.offset = offset;
  $("#scanCandidateReview").hidden = false;
  $("#scanCandidateReviewTitle").textContent = `选品判断 · ${scanId}`;
  const body = $("#scanDecisionsBody");
  body.replaceChildren();
  if (!data.decisions.length) addEmptyRow(body, "本次扫描没有选品判断记录", 3);
  const labels = { baseline: "首次扫描基线", excluded: "自动排除", candidate: "进入候选" };
  for (const item of data.decisions) {
    const row = document.createElement("tr");
    [item.title || item.item_id, labels[item.decision] || item.decision, item.matched_patterns.join("、") || "无"].forEach(value => addCell(row, value));
    body.appendChild(row);
  }
  showPager("scanDecisions", offset, data.total);
}

async function refreshScanRuns() {
  const data = await api("/api/scan/runs?limit=10");
  const body = $("#scanRunsBody");
  body.replaceChildren();
  if (!data.runs.length) return addEmptyRow(body, "暂无扫描记录", 6);
  for (const run of data.runs) {
    const row = document.createElement("tr");
    const diagnosis = scanErrors[run.error_kind] || run.error_kind || runStatuses[run.status] || run.status;
    const detail = run.page_count ? `${diagnosis} · ${run.page_count} 页 · 预期 ${run.expected_count ?? "未知"} · ${run.finish_reason || "—"}` : diagnosis;
    [formatTime(run.started_at), run.seller_id, run.item_count, run.event_count, detail].forEach((value) => addCell(row, value));
    const cell = document.createElement("td");
    const button = document.createElement("button");
    button.className = "ghost tiny";
    button.textContent = "查看判断";
    button.addEventListener("click", () => openScanReview(run.id).catch(error => toast(error.message)));
    cell.appendChild(button);
    row.appendChild(cell);
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
    addCell(row, formatTime(event.detected_at));
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
  const labels = ["系统状态", "商家池", "候选商品", "变化事件", "发现记录", "扫描记录"];
  const results = await Promise.allSettled([
    refreshStatus(), refreshPool(), refreshCandidates(), refreshEvents(), refreshDiscoveryRuns(), refreshScanRuns(),
  ]);
  const errors = results.flatMap((result, index) => result.status === "rejected"
    ? [`${labels[index]}加载失败：${result.reason.message || result.reason}`] : []);
  try { await refreshOpenSeller(); }
  catch (error) { errors.push(`商品目录加载失败：${error.message}`); }
  if (errors.length) toast(errors.join("；"));
  return { status: results[0].status === "fulfilled" ? results[0].value : null, errors };
}

$$(".tab").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});
$("#btnRefresh").addEventListener("click", () => withBusy($("#btnRefresh"), "…", async () => {
  try {
    const result = await refreshAll();
    if (!result.errors.length) toast("数据已刷新");
  } catch (error) { toast(error.message); }
}));
$("#closeScanReview").addEventListener("click", () => {
  scanReview.id = null;
  $("#scanCandidateReview").hidden = true;
});
for (const [direction, delta] of [["Prev", -1], ["Next", 1]]) {
  $(`#scanDecisions${direction}`).addEventListener("click", () => {
    if (scanReview.id) openScanReview(scanReview.id, scanReview.offset + delta * pageSize).catch(error => toast(error.message));
  });
}

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

for (const [prefix, stateKey, refresh] of [
  ["events", "eventsOffset", refreshEvents],
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
$("#evtSince").addEventListener("change", () => {
  viewState.eventsOffset = 0;
  refreshEvents().catch((error) => toast(error.message));
});

initAuth({ activateTab });
initDiscovery({ openSeller, refreshAll });
initPool({ activateTab, refreshCandidates, refreshStatus });
initCandidates();

activateTab(location.hash.slice(1) || "pool");
refreshAll().catch((error) => toast(error.message));
const initialSeller = new URLSearchParams(location.search).get("seller");
if (initialSeller && /^[0-9]+$/.test(initialSeller) && (!location.hash || location.hash === "#pool")) {
  openSeller(initialSeller).catch((error) => toast(error.message));
}
