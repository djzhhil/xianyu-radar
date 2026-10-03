import { $, api, toast, setResult, setLog, withBusy } from "./common.js";

export async function refreshStatus() {
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

export function initAuth({ activateTab }) {
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
}
