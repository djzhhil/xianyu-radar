import { initScan, refreshScanRuns, refreshEvents } from "./scan.js";
import { initCandidates, refreshCandidates } from "./candidates.js";
import { initPool, openSeller, refreshPool, refreshOpenSeller } from "./pool.js";
import { initDiscovery, refreshDiscoveryRuns } from "./discovery.js";
import { initAuth, refreshStatus } from "./auth.js";
import { $, $$, toast, withBusy } from "./common.js";

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
initAuth({ activateTab });
initDiscovery({ openSeller, refreshAll });
initPool({ activateTab, refreshCandidates, refreshStatus });
initCandidates();
initScan({ refreshAll });

activateTab(location.hash.slice(1) || "pool");
refreshAll().catch((error) => toast(error.message));
const initialSeller = new URLSearchParams(location.search).get("seller");
if (initialSeller && /^[0-9]+$/.test(initialSeller) && (!location.hash || location.hash === "#pool")) {
  openSeller(initialSeller).catch((error) => toast(error.message));
}
