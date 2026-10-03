import { $, api, toast, setResult, setLog, withBusy, formatTime, addCell, addEmptyRow, addLinkCell, runStatuses } from "./common.js";

let workbench;

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
      button.addEventListener("click", () => workbench.openSeller(item.seller_id).catch((error) => toast(error.message)));
      sellerCell.appendChild(button);
    } else {
      sellerCell.textContent = "未识别";
    }
    row.appendChild(sellerCell);
    addLinkCell(row, item.url);
    body.appendChild(row);
  }
}

export async function refreshDiscoveryRuns() {
  const data = await api("/api/discover/runs?limit=10");
  const body = $("#discoveryRunsBody");
  body.replaceChildren();
  if (!data.runs.length) return addEmptyRow(body, "暂无发现记录", 7);
  for (const run of data.runs) {
    const row = document.createElement("tr");
    const counts = `${run.page_count} / ${run.raw_result_count} / ${run.unique_item_count || run.item_count}`;
    const state = `${runStatuses[run.status] || run.status}${run.error_kind ? ` · ${run.error_kind}` : ""}${run.unresolved_count ? ` · 未识别 ${run.unresolved_count}` : ""}${run.unparsed_count ? ` · 未解析 ${run.unparsed_count}` : ""}`;
    [formatTime(run.started_at), run.keyword, counts, run.unique_seller_count, run.seller_count, state].forEach((value) => addCell(row, value));
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
          await workbench.refreshAll();
        } catch (error) { setLog("#discoverLog", error.message); toast(error.message); await refreshDiscoveryRuns(); }
      }));
      actions.appendChild(resume);
    }
    row.appendChild(actions);
    body.appendChild(row);
  }
}

export function initDiscovery(callbacks) {
  workbench = callbacks;
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
        await workbench.refreshAll();
      } catch (error) {
        setLog("#discoverLog", error.message);
        setResult("#discoverResult", error.message, true);
        toast(error.message);
      }
    });
  });
}
