// GET /api/popular?limit=100&period=all|today|week|month
// クリック数の多い順に yupoo_id とクリック数を返す
// period: all=累計 / today=当日 / week=直近7日 / month=直近30日（JST基準・日次バケット集計）

// JST基準で days 日前の日付文字列 (YYYY-MM-DD) を返す
function jstDay(daysAgo) {
  return new Date(Date.now() + 9 * 3600e3 - daysAgo * 86400e3)
    .toISOString()
    .slice(0, 10);
}

export async function onRequestGet(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const limit = Math.min(parseInt(url.searchParams.get("limit") || "100", 10), 500);
  const periodRaw = (url.searchParams.get("period") || "all").toLowerCase();
  const period = ["all", "today", "week", "month"].includes(periodRaw) ? periodRaw : "all";

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

  let results = [];
  try {
    if (period === "all") {
      ({ results } = await env.DB.prepare(`
        SELECT yupoo_id, clicks, qc_clicks, last_clicked
        FROM clicks
        WHERE clicks > 0 OR qc_clicks > 0
        ORDER BY (clicks + qc_clicks) DESC, last_clicked DESC
        LIMIT ?
      `).bind(limit).all());
    } else {
      const cutoff = period === "today" ? jstDay(0) : period === "week" ? jstDay(6) : jstDay(29);
      ({ results } = await env.DB.prepare(`
        SELECT yupoo_id,
               SUM(clicks) AS clicks,
               SUM(qc_clicks) AS qc_clicks,
               MAX(day) AS last_clicked
        FROM clicks_daily
        WHERE day >= ?
        GROUP BY yupoo_id
        HAVING (SUM(clicks) + SUM(qc_clicks)) > 0
        ORDER BY (SUM(clicks) + SUM(qc_clicks)) DESC, MAX(day) DESC
        LIMIT ?
      `).bind(cutoff, limit).all());
    }
  } catch {
    // clicks_daily 未作成など（期間別データがまだ無い）→ 空で返す
    results = [];
  }

  return new Response(JSON.stringify({
    updated: new Date().toISOString(),
    period,
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
