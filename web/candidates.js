import { $, api, toast, formatTime, showPager, safeLink, addOption, pageSize } from "./common.js";

const viewState = { candidatesOffset: 0 };

const candidateStatuses = {
  new: "新候选",
  watching: "观察中",
  testing: "测试中",
  validated: "已验证",
  rejected: "已排除",
};
export async function refreshCandidates() {
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
    const qualityLabel = candidate.quality_flag === "legacy_unverified" ? "历史待核实" : "已记录候选";
    meta.textContent = `${qualityLabel} · 参考价格 ${candidate.sample_price || "—"} · 来源商家 ${candidate.seller_count} · 出现 ${candidate.appearance_count} 次 · 评分 ${Number(candidate.score || 0).toFixed(1)}`;
    const sources = document.createElement("div");
    sources.className = "meta";
    sources.textContent = `商家：${(candidate.source_sellers || []).join("、") || "—"}`;
    const dates = document.createElement("div");
    dates.className = "meta";
    dates.textContent = `首次发现 ${formatTime(candidate.first_seen_at)} · 最近发现 ${formatTime(candidate.last_seen_at)}`;
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
    const evidence = document.createElement("details");
    evidence.className = "candidate-evidence";
    const summary = document.createElement("summary");
    const types = candidate.source_types || {};
    summary.textContent = `商品来源 · 存量 ${types.baseline_catalog || 0} · 上新 ${types.new_item || 0}`;
    const sourceList = document.createElement("div");
    evidence.append(summary, sourceList);
    let offset = 0;
    async function loadSources() {
      const result = await api(`/api/candidates/${candidate.candidate_id}/sources?limit=20&offset=${offset}`);
      if (!result.total) sourceList.textContent = "未保存逐商品来源，需人工核对历史记录。";
      for (const source of result.sources) {
        const row = document.createElement("div");
        row.className = "source-row";
        row.append(document.createTextNode(`${source.source_type === "baseline_catalog" ? "存量选品" : "监控上新"} · ${source.title} · ${source.price || "—"} · 商家 ${source.nickname || source.seller_id} · 观察于 ${formatTime(source.observed_at)} · `), safeLink(source.url));
        sourceList.appendChild(row);
      }
      offset += result.sources.length;
      if (offset < result.total) {
        const more = document.createElement("button");
        more.className = "ghost tiny";
        more.type = "button";
        more.textContent = "更多来源";
        more.addEventListener("click", async () => {
          more.disabled = true;
          try { await loadSources(); more.remove(); } catch (error) { more.disabled = false; toast(error.message); }
        });
        sourceList.appendChild(more);
      }
    }
    evidence.addEventListener("toggle", async () => {
      if (!evidence.open || evidence.dataset.loaded) return;
      evidence.dataset.loaded = "loading";
      if (offset === 0) sourceList.replaceChildren();
      try { await loadSources(); evidence.dataset.loaded = "yes"; }
      catch (error) { delete evidence.dataset.loaded; sourceList.textContent = "来源读取失败，请重新展开重试"; toast(error.message); }
    });
    card.appendChild(evidence);
    list.appendChild(card);
  }
}

export function initCandidates() {
  for (const [direction, delta] of [["Prev", -1], ["Next", 1]]) {
    $(`#candidates${direction}`).addEventListener("click", () => {
      viewState.candidatesOffset += delta * pageSize;
      refreshCandidates().catch(error => {
        viewState.candidatesOffset -= delta * pageSize;
        toast(error.message);
      });
    });
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
}
