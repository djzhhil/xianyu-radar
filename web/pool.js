import {
  $, $$, api, toast, setResult, withBusy, formatTime, addCell, addEmptyRow,
  addLinkCell, addOption, showPager, pageSize, runStatuses, scanErrors,
} from "./common.js";

let workbench;
const viewState = { sellerId: null, sellerOffset: 0 };
let catalogSelectionScan = null;
let rulesNextOffset = 0;

const poolStatuses = {
  watching: "监控中",
  paused: "已暂停",
  dropped: "已移除",
};
const itemStatuses = { active: "在售", removed: "已下架", unknown: "未知" };
const itemSources = { discovery: "关键词发现", seller_scan: "商家扫描" };
function updateCatalogSelection() {
  const boxes = $$(".catalog-select:not(:disabled)");
  const count = boxes.filter(box => box.checked).length;
  $("#addCatalogCandidates").disabled = count === 0;
  $("#addCatalogCandidates").textContent = `加入候选（${count}）`;
  $("#catalogSelectAll").checked = boxes.length > 0 && count === boxes.length;
  $("#catalogSelectAll").indeterminate = count > 0 && count < boxes.length;
  $("#catalogSelectAll").disabled = boxes.length === 0;
}

function selectSellerView(name) {
  $$("[data-seller-view]").forEach(button => {
    const active = button.dataset.sellerView === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  $$(".seller-pane").forEach(pane => { pane.hidden = pane.id !== `seller-pane-${name}`; });
}

export async function openSeller(sellerId, offset = 0, activate = true) {
  if (viewState.sellerId !== sellerId) {
    $("#sellerItemQuery").value = "";
    $("#sellerItemStatus").value = "";
    selectSellerView("catalog");
    $("#catalogSelectionResult").textContent = "";
  }
  const query = new URLSearchParams({ limit: pageSize, offset, query: $("#sellerItemQuery").value, item_status: $("#sellerItemStatus").value });
  const data = await api(`/api/pool/${encodeURIComponent(sellerId)}?${query}`);
  viewState.sellerId = sellerId;
  viewState.sellerOffset = offset;
  const seller = data.seller;
  catalogSelectionScan = data.selection_scan_id;
  $("#sellerTags").value = (seller.tags || []).join(", ");
  $("#sellerNotes").value = seller.notes || "";
  $("#candidateExcludePatterns").value = (seller.candidate_exclude_patterns || []).join("\n");
  $("#sellerDiscoveryKeywords").textContent = `发现来源关键词：${seller.keywords || "无"}`;
  setResult("#candidateRulesResult", "");
  setResult("#sellerMetadataResult", "");
  $("#sellerDetail").hidden = false;
  $("#sellerRoster").hidden = true;
  $("#sellerDetailTitle").textContent = seller.nickname ? `${seller.nickname} · ${seller.seller_id}` : `商家 ${seller.seller_id}`;
  $("#sellerDetailMeta").textContent = `${poolStatuses[seller.status] || seller.status} · 最近成功扫描：${formatTime(seller.last_scan_at)} · 连续失败 ${seller.consecutive_failures || 0} 次`;
  const complete = data.latest_complete_scan;
  const latest = data.latest_scan;
  $("#sellerCatalogQuality").textContent = complete
    ? `最近完整扫描：${formatTime(complete.finished_at || complete.started_at)} · ${complete.item_count} 件 · 当前筛选 ${data.total_items} 件`
    : "尚无完整扫描记录";
  if (latest && latest.status !== "ok") {
    $("#sellerCatalogQuality").textContent += `；最近扫描：${scanErrors[latest.error_kind] || runStatuses[latest.status] || latest.status} · ${formatTime(latest.finished_at || latest.started_at)}`;
  }
  const entriesBody = $("#sellerEntriesBody");
  entriesBody.replaceChildren();
  if (!data.entries.length) addEmptyRow(entriesBody, "暂无入池记录", 4);
  for (const entry of data.entries) {
    const row = document.createElement("tr");
    [entry.source_keyword, entry.source_item_id, entry.reason === "manual" ? "手动添加" : entry.reason, formatTime(entry.joined_at)].forEach((value) => addCell(row, value));
    entriesBody.appendChild(row);
  }
  const itemsBody = $("#sellerItemsBody");
  itemsBody.replaceChildren();
  if (!data.items.length) addEmptyRow(itemsBody, "当前范围暂无商品", 9);
  for (const item of data.items) {
    const row = document.createElement("tr");
    const selectCell = document.createElement("td");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "catalog-select";
    checkbox.value = item.item_id;
    checkbox.disabled = !item.selectable;
    checkbox.setAttribute("aria-label", `选择 ${item.title || item.item_id}`);
    checkbox.title = item.selectable ? "加入研究候选" : "不在最近可信目录中，需完成扫描后复核";
    checkbox.addEventListener("change", updateCatalogSelection);
    selectCell.appendChild(checkbox);
    row.appendChild(selectCell);
    const imageCell = document.createElement("td");
    const preview = document.createElement("div");
    preview.className = "catalog-image";
    preview.textContent = "暂无图片";
    try {
      const url = new URL(item.image);
      if (!["http:", "https:"].includes(url.protocol)) throw new Error("unsupported image URL");
      const image = document.createElement("img");
      image.src = url.href;
      image.alt = item.title || item.item_id;
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => { preview.textContent = "图片失效"; });
      preview.replaceChildren(image);
    } catch { /* Missing or unsupported image URLs retain the placeholder. */ }
    imageCell.appendChild(preview);
    row.appendChild(imageCell);
    [item.title || item.item_id, item.price, itemStatuses[item.status] || item.status, itemSources[item.source] || item.source, formatTime(item.last_seen_at)].forEach((value) => addCell(row, value));
    const detailCell = document.createElement("td");
    const detailLink = document.createElement("a");
    detailLink.href = `/items/${encodeURIComponent(item.item_id)}?seller=${encodeURIComponent(sellerId)}`;
    detailLink.textContent = "商品详情";
    detailCell.appendChild(detailLink);
    row.appendChild(detailCell);
    addLinkCell(row, item.url);
    itemsBody.appendChild(row);
  }
  showPager("sellerItems", offset, data.total_items);
  updateCatalogSelection();
  if (!$("#seller-pane-rules").hidden) await loadRulePreview(sellerId);
  if (activate) workbench.activateTab("pool");
}

async function loadRulePreview(sellerId, offset = 0) {
  const data = await api(`/api/pool/${encodeURIComponent(sellerId)}/candidate-rules?limit=${pageSize}&offset=${offset}`);
  if (viewState.sellerId !== sellerId) return;
  const list = $("#candidateRulesMatches");
  if (!offset) list.replaceChildren();
  for (const match of data.matches) {
    const row = document.createElement("div");
    row.className = "rule-match";
    row.textContent = `${match.title || match.item_id} · 命中：${match.matched_patterns.join("、")}`;
    list.appendChild(row);
  }
  rulesNextOffset = offset + data.matches.length;
  $("#candidateRulesSummary").textContent = `当前已存目录：命中 ${data.total} 件，已显示 ${rulesNextOffset} 件`;
  $("#candidateRulesMore").hidden = rulesNextOffset >= data.total;
  return data;
}

export async function refreshPool() {
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
    addCell(row, formatTime(seller.last_scan_at));

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
        await Promise.all([refreshPool(), workbench.refreshStatus()]);
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
    $("#sellerRoster").hidden = false;
  }
}

export async function refreshOpenSeller() {
  if (viewState.sellerId) await openSeller(viewState.sellerId, viewState.sellerOffset, false);
}

export function initPool(callbacks) {
  workbench = callbacks;
  $$("[data-seller-view]").forEach(button => {
    button.addEventListener("click", () => {
      selectSellerView(button.dataset.sellerView);
      if (button.dataset.sellerView === "rules" && viewState.sellerId) loadRulePreview(viewState.sellerId).catch(error => toast(error.message));
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
        await Promise.all([refreshPool(), workbench.refreshStatus()]);
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

  $("#sellerItemFilters").addEventListener("submit", (event) => {
    event.preventDefault();
    if (viewState.sellerId) openSeller(viewState.sellerId).catch(error => toast(error.message));
  });

  $("#candidateRulesForm").addEventListener("submit", event => {
    event.preventDefault();
    const sellerId = viewState.sellerId;
    if (!sellerId) return;
    const exclude_patterns = $("#candidateExcludePatterns").value.split(/\r?\n/).map(value => value.trim()).filter(Boolean);
    withBusy(event.currentTarget.querySelector('button[type="submit"]'), "保存中…", async () => {
      try {
        await api(`/api/pool/${encodeURIComponent(sellerId)}/candidate-rules`, { method: "PATCH", body: JSON.stringify({ exclude_patterns }) });
        const data = await loadRulePreview(sellerId);
        if (viewState.sellerId !== sellerId) return;
        $("#candidateExcludePatterns").value = data.exclude_patterns.join("\n");
        setResult("#candidateRulesResult", "排除规则已保存");
      } catch (error) {
        if (viewState.sellerId === sellerId) setResult("#candidateRulesResult", error.message, true);
      }
    });
  });
  $("#candidateRulesMore").addEventListener("click", () => withBusy($("#candidateRulesMore"), "加载中…", async () => {
    try { await loadRulePreview(viewState.sellerId, rulesNextOffset); } catch (error) { toast(error.message); }
  }));
  $("#catalogSelectAll").addEventListener("change", event => {
    $$(".catalog-select:not(:disabled)").forEach(box => { box.checked = event.target.checked; });
    updateCatalogSelection();
  });
  $("#addCatalogCandidates").addEventListener("click", () => {
    const body = { seller_id: viewState.sellerId, scan_id: catalogSelectionScan, item_ids: $$(".catalog-select:checked").map(box => box.value) };
    withBusy($("#addCatalogCandidates"), "保存中…", async () => {
      try {
        const result = await api("/api/candidates/from-catalog", { method: "POST", body: JSON.stringify(body) });
        if (viewState.sellerId === body.seller_id) {
          $("#catalogSelectionResult").textContent = `新增 ${result.added} 件来源，已存在 ${result.existing} 件`;
          $$(".catalog-select").forEach(box => { box.checked = false; });
        }
        await Promise.all([workbench.refreshCandidates(), workbench.refreshStatus()]);
      } catch (error) { if (viewState.sellerId === body.seller_id) $("#catalogSelectionResult").textContent = error.message; }
    }).finally(updateCatalogSelection);
  });

  $("#closeSellerDetail").addEventListener("click", () => {
    viewState.sellerId = null;
    $("#sellerDetail").hidden = true;
    $("#sellerRoster").hidden = false;
  });
  for (const [id, delta] of [["sellerItemsPrev", -1], ["sellerItemsNext", 1]]) {
    $(`#${id}`).addEventListener("click", () => openSeller(viewState.sellerId, viewState.sellerOffset + delta * pageSize).catch((error) => toast(error.message)));
  }
}
