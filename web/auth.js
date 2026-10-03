import { $, api, toast, setResult, setLog, withBusy, formatTime, scanErrors } from "./common.js";

export async function refreshStatus() {
  const status = await api("/api/status");
  $("#sSellers").textContent = status.counts.watching_sellers;
  $("#sItems").textContent = status.counts.items;
  $("#sCands").textContent = status.counts.candidates;
  const auth = status.auth;
  const pill = $("#authPill");
  pill.textContent = auth.paused ? "在线工作已暂停 · 到 Helper 恢复"
    : !auth.configured ? "Helper 未配置"
    : auth.connection_status === "error" ? "Helper 连接异常"
    : "Helper 登录态 · 查看状态";
  pill.className = `auth-pill ${auth.paused || !auth.configured || auth.connection_status === "error" ? "bad" : "ok"}`;
  $("#helperAccount").textContent = auth.account_id || "未配置";
  $("#helperConnection").textContent = ({ connected: "已获取快照", unchecked: "尚未检查", error: "连接异常", unconfigured: "未配置" })[auth.connection_status] || "尚未检查";
  $("#helperFetched").textContent = formatTime(auth.last_fetch_at);
  $("#helperSubmitted").textContent = formatTime(auth.last_submit_at);
  $("#helperSync").textContent = ({ synced: "已同步", not_running: "账号未运行", not_needed: "无需同步", failed: "已保存，Helper 运行时同步异常" })[auth.runtime_sync_status] || "暂无提交";
  const reason = auth.pause_reason || auth.last_error_kind;
  $("#helperPause").textContent = reason ? scanErrors[reason] || "在线操作异常，请重新检查" : auth.paused ? "需要重新检查" : "无";
  return status;
}

export function initAuth({ activateTab }) {
  $("#authPill").addEventListener("click", () => activateTab("auth"));
  $("#btnCheckHelper").addEventListener("click", () => withBusy($("#btnCheckHelper"), "检查中…", async () => {
    try {
      const result = await api("/api/auth/check?ping=true", { method: "POST" });
      setLog("#helperLog", result);
      setResult("#authResult", "Helper 快照与闲鱼在线请求检查通过，已解除暂停。");
      toast("检查通过");
    } catch (error) {
      setLog("#helperLog", error.message);
      setResult("#authResult", error.message, true);
      toast(error.message);
    }
    await refreshStatus();
  }));
}
