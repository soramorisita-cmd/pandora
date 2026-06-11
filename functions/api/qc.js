// GET /api/qc?url=<商品URL or エージェントURL>
// UUFinds 変換API (api.uufinds.com) をプロキシして QCページURL と QC枚数を返す。
// UUFinds API は CORS ヘッダを返さないため、ブラウザから直接叩けない。このFunction経由で回避する。

export async function onRequestGet(context) {
  const { request } = context;
  const url = new URL(request.url);
  const target = url.searchParams.get("url");

  const cors = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
  };

  if (!target) {
    return json({ success: false, message: "url parameter required" }, 400, cors);
  }

  try {
    const api =
      "https://api.uufinds.com/open/api/convertUrl?from=pandora&url=" +
      encodeURIComponent(target);
    const r = await fetch(api, { headers: { "User-Agent": "Mozilla/5.0" } });
    const data = await r.json();
    // UUFinds のレスポンスをそのまま返す（success / result.url / result.qcQuantity）
    return json(data, 200, { ...cors, "Cache-Control": "public, max-age=3600" });
  } catch (e) {
    return json({ success: false, message: String(e) }, 502, cors);
  }
}

function json(obj, status, headers) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}
