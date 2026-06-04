-- PANDORA D1 schema (人気商品集計用)
-- Cloudflareダッシュボード > Workers & Pages > D1 > pandora-clicks で実行する

CREATE TABLE IF NOT EXISTS clicks (
  yupoo_id TEXT PRIMARY KEY,
  clicks INTEGER NOT NULL DEFAULT 0,
  qc_clicks INTEGER NOT NULL DEFAULT 0,
  last_clicked TEXT,
  first_clicked TEXT
);

CREATE INDEX IF NOT EXISTS idx_clicks_desc ON clicks(clicks DESC);
