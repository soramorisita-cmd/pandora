// POST /api/click
// Body: { yupoo_id: string, kind: "buy" | "qc" }
// クリックを D1 にカウントアップする

export async function onRequestPost(context) {
  const { request, env } = context;

  // CORS（同一オリジン想定だが念のため）
  const corsHeaders = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };

  let body;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: "invalid json" }), {
      status: 400,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }

  const yupooId = (body.yupoo_id || "").toString().trim();
  const kind = body.kind === "qc" ? "qc" : "buy";

  if (!yupooId || yupooId.length > 200) {
    return new Response(JSON.stringify({ error: "invalid yupoo_id" }), {
      status: 400,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }

  if (!env.DB) {
    return new Response(JSON.stringify({ error: "DB binding not configured" }), {
      status: 500,
      headers: { "Content-Type": "application/json", ...corsHeaders },
    });
  }

  const now = new Date().toISOString();
  const col = kind === "qc" ? "qc_clicks" : "clicks";

  // UPSERT: INSERT or UPDATE 同時実行
  await env.DB.prepare(`
    INSERT INTO clicks (yupoo_id, ${col}, last_clicked, first_clicked)
    VALUES (?, 1, ?, ?)
    ON CONFLICT(yupoo_id) DO UPDATE SET
      ${col} = ${col} + 1,
      last_clicked = excluded.last_clicked
  `).bind(yupooId, now, now).run();

  return new Response(JSON.stringify({ ok: true }), {
    headers: { "Content-Type": "application/json", ...corsHeaders },
  });
}

export async function onRequestOptions() {
  return new Response(null, {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}
