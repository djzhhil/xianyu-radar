const itemId = location.pathname.split("/").filter(Boolean).at(-1);
const sellerId = new URLSearchParams(location.search).get("seller");
const statusElement = document.querySelector("#detailStatus");
const refreshButton = document.querySelector("#refreshDetail");
const text = (id, value) => { document.querySelector(id).textContent = value; };
if (sellerId && /^[0-9]+$/.test(sellerId)) {
  document.querySelector("#backToCatalog").href = `/?seller=${encodeURIComponent(sellerId)}#pool`;
}
text("#itemIdLabel", `商品 ${itemId}`);

function publishedTime(value) {
  if (value === null || value === undefined || value === "") return "未知";
  let source = value;
  if (/^\d{10,13}$/.test(String(value))) {
    source = Number(value) * (String(value).length === 10 ? 1000 : 1);
  } else if (typeof value === "string" && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)) {
    source = `${value.replace(" ", "T")}+08:00`;
  }
  const date = new Date(source);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", dateStyle: "medium", timeStyle: "short" }).format(date);
}

async function loadDetail() {
  refreshButton.disabled = true;
  document.querySelector("#detailContent").hidden = true;
  statusElement.className = "result-message";
  statusElement.textContent = "正在获取商品详情…";
  try {
    const response = await fetch(`/api/items/${encodeURIComponent(itemId)}/detail`);
    const body = await response.text();
    let data;
    try { data = JSON.parse(body); } catch { throw new Error("商品详情服务返回异常，请稍后重试"); }
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "商品详情获取失败");
    text("#itemTitle", data.title || "未知标题");
    document.title = `${data.title || "商品详情"} · 闲鱼补货工作台`;
    text("#detailItemId", data.item_id);
    text("#itemPrice", data.price === null || data.price === "" ? "未知" : `¥ ${data.price}`);
    text("#itemPublished", publishedTime(data.published_at));
    for (const [selector, key] of [["#itemViews", "views"], ["#itemWants", "wants"], ["#itemFavorites", "favorites"], ["#itemInteractions", "interactions"], ["#itemEvaluations", "evaluations"]]) {
      text(selector, data[key] === null || data[key] === undefined ? "未知" : new Intl.NumberFormat("zh-CN").format(data[key]));
    }
    document.querySelector("#goofishLink").href = `https://www.goofish.com/item?id=${encodeURIComponent(data.item_id)}`;
    const photo = document.querySelector("#itemPhoto");
    photo.replaceChildren();
    photo.hidden = true;
    try {
      const url = new URL(data.image);
      if (["http:", "https:"].includes(url.protocol)) {
        const image = document.createElement("img");
        image.src = url.href;
        image.alt = data.title || "商品主图";
        image.referrerPolicy = "no-referrer";
        image.addEventListener("error", () => { photo.hidden = true; });
        photo.appendChild(image);
        photo.hidden = false;
      }
    } catch { /* No image was returned. */ }
    text("#detailFetchedAt", `获取时间：${publishedTime(Date.now())}`);
    document.querySelector("#detailContent").hidden = false;
    statusElement.textContent = "";
  } catch (error) {
    statusElement.className = "result-message error";
    statusElement.textContent = error.message;
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener("click", loadDetail);
loadDetail();
