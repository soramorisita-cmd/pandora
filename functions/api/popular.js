// GET /api/popular?limit=100
// クリック数の多い順に yupoo_id とクリック数を返す

export async function onRequestGet(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const limit = Math.min(parseInt(url.searchParams.get("limit") || "100", 10), 500);

  const corsHeaders = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
  };

  if (!env.DB) {
    return new Response(JSON.stringify({ error: "DB binding not configured" }), {
      status: 500,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }

  const { results } = await env.DB.prepare(`
    SELECT yupoo_id, clicks, qc_clicks, last_clicked
    FROM clicks
    WHERE clicks > 0 OR qc_clicks > 0
    ORDER BY (clicks * 3 + qc_clicks) DESC, last_clicked DESC
    LIMIT ?
  `).bind(limit).all();

  return new Response(JSON.stringify({
    updated: new Date().toISOString(),
    count: results.length,
    items: results,
  }), {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, max-age=300", // 5分キャッシュ
      ...corsHeaders,
    },
  });
}
