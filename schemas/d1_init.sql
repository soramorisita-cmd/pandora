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

-- 期間別ランキング用の日次バケット（JST基準の day='YYYY-MM-DD'）
-- 未適用でも /api/click が初回書き込み時に自動生成するが、事前に実行しておくと確実。
CREATE TABLE IF NOT EXISTS clicks_daily (
  yupoo_id TEXT NOT NULL,
  day TEXT NOT NULL,
  clicks INTEGER NOT NULL DEFAULT 0,
  qc_clicks INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (yupoo_id, day)
);

CREATE INDEX IF NOT EXISTS idx_clicks_daily_day ON clicks_daily(day);
