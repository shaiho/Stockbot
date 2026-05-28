CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    language TEXT NOT NULL DEFAULT 'he',
    onboarding_completed INTEGER NOT NULL DEFAULT 0,
    default_commission REAL NOT NULL DEFAULT 0,
    default_commission_currency TEXT NOT NULL DEFAULT 'USD',
    report_morning TEXT NOT NULL DEFAULT '09:00',
    report_evening TEXT NOT NULL DEFAULT '23:00',
    mover_threshold_pct REAL NOT NULL DEFAULT 5.0,
    last_portfolio_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portfolios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    opening_cash_ils REAL NOT NULL DEFAULT 0,
    opening_cash_usd REAL NOT NULL DEFAULT 0,
    commission_min_usd REAL NOT NULL DEFAULT 0,
    commission_min_ils REAL NOT NULL DEFAULT 0,
    commission_extra_type TEXT NOT NULL DEFAULT 'fixed',
    commission_extra_value REAL NOT NULL DEFAULT 0,
    opened_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    asset_type TEXT NOT NULL DEFAULT 'stock',
    action TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    currency TEXT NOT NULL,
    commission REAL NOT NULL DEFAULT 0,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    note TEXT
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, symbol, market)
);

CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    scope TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS alert_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    alert_key TEXT NOT NULL,
    last_sent_date TEXT NOT NULL,
    UNIQUE(user_id, alert_key)
);

CREATE INDEX IF NOT EXISTS idx_trades_portfolio ON trades(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_user ON alert_rules(user_id);
