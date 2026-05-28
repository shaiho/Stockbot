CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    language TEXT NOT NULL DEFAULT 'he',
    onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
    default_commission DOUBLE PRECISION NOT NULL DEFAULT 0,
    default_commission_currency TEXT NOT NULL DEFAULT 'USD',
    report_morning TEXT NOT NULL DEFAULT '09:00',
    report_evening TEXT NOT NULL DEFAULT '23:00',
    mover_threshold_pct DOUBLE PRECISION NOT NULL DEFAULT 5.0,
    last_portfolio_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolios (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    opening_cash_ils DOUBLE PRECISION NOT NULL DEFAULT 0,
    opening_cash_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    commission_min_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    commission_min_ils DOUBLE PRECISION NOT NULL DEFAULT 0,
    commission_extra_type TEXT NOT NULL DEFAULT 'fixed',
    commission_extra_value DOUBLE PRECISION NOT NULL DEFAULT 0,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    asset_type TEXT NOT NULL DEFAULT 'stock',
    action TEXT NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    currency TEXT NOT NULL,
    commission DOUBLE PRECISION NOT NULL DEFAULT 0,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    note TEXT
);

CREATE TABLE IF NOT EXISTS watchlist (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, symbol, market)
);

CREATE TABLE IF NOT EXISTS alert_rules (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    scope TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alert_state (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    alert_key TEXT NOT NULL,
    last_sent_date TEXT NOT NULL,
    UNIQUE(user_id, alert_key)
);

CREATE INDEX IF NOT EXISTS idx_trades_portfolio ON trades(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_user ON alert_rules(user_id);
