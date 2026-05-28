from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from src.db.models import Portfolio


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇮🇱 עברית", callback_data="lang:he"),
                InlineKeyboardButton(text="🇺🇸 English", callback_data="lang:en"),
            ]
        ]
    )


def main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    if lang == "he":
        rows = [
            [KeyboardButton(text="📊 התיק שלי"), KeyboardButton(text="📋 החזקות")],
            [KeyboardButton(text="💱 מחיר"), KeyboardButton(text="➕ עסקה")],
            [KeyboardButton(text="💵 הפקדה"), KeyboardButton(text="📈 רווח/הפסד")],
            [KeyboardButton(text="📜 היסטוריה"), KeyboardButton(text="📋 דוח מס")],
            [KeyboardButton(text="📅 דוח חודשי"), KeyboardButton(text="👁 מעקב")],
            [KeyboardButton(text="🔔 התראות"), KeyboardButton(text="📁 תיקים")],
            [KeyboardButton(text="⚙️ הגדרות"), KeyboardButton(text="🏠 תפריט ראשי")],
        ]
    else:
        rows = [
            [KeyboardButton(text="📊 Portfolio"), KeyboardButton(text="📋 Holdings")],
            [KeyboardButton(text="💱 Quote"), KeyboardButton(text="➕ Trade")],
            [KeyboardButton(text="💵 Deposit"), KeyboardButton(text="📈 P&L")],
            [KeyboardButton(text="📜 History"), KeyboardButton(text="📋 Tax report")],
            [KeyboardButton(text="📅 Monthly report"), KeyboardButton(text="👁 Watchlist")],
            [KeyboardButton(text="🔔 Alerts"), KeyboardButton(text="📁 Portfolios")],
            [KeyboardButton(text="⚙️ Settings"), KeyboardButton(text="🏠 Main menu")],
        ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def portfolio_picker_keyboard(
    portfolios: list[Portfolio], lang: str, *, include_new: bool = False, action: str = "pick_portfolio"
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📁 {p.name}", callback_data=f"{action}:{p.id}")]
        for p in portfolios
    ]
    if include_new:
        label = "➕ תיק חדש" if lang == "he" else "➕ New portfolio"
        rows.append([InlineKeyboardButton(text=label, callback_data="new_portfolio")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def yes_no_keyboard(lang: str) -> InlineKeyboardMarkup:
    yes = "כן" if lang == "he" else "Yes"
    no = "לא" if lang == "he" else "No"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=yes, callback_data="yes"),
                InlineKeyboardButton(text=no, callback_data="no"),
            ]
        ]
    )


def zero_or_custom_keyboard(step: str, lang: str, prefix: str = "ob") -> InlineKeyboardMarkup:
    zero = "0 — אין" if lang == "he" else "0 — none"
    custom = "✏️ הזן סכום" if lang == "he" else "✏️ Enter amount"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=zero, callback_data=f"{prefix}:{step}:0"),
                InlineKeyboardButton(text=custom, callback_data=f"{prefix}:{step}:custom"),
            ]
        ]
    )


def currency_keyboard(lang: str, prefix: str = "ob:currency") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="₪ ILS", callback_data=f"{prefix}:ILS"),
                InlineKeyboardButton(text="$ USD", callback_data=f"{prefix}:USD"),
            ]
        ]
    )


def holdings_now_keyboard(lang: str) -> InlineKeyboardMarkup:
    yes = "כן — יש לי ניירות" if lang == "he" else "Yes — I have holdings"
    no = "לא — ריק לעת עתה" if lang == "he" else "No — empty for now"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=yes, callback_data="ob:holdings:yes"),
                InlineKeyboardButton(text=no, callback_data="ob:holdings:no"),
            ]
        ]
    )


def market_keyboard(lang: str) -> InlineKeyboardMarkup:
    us = "🇺🇸 ארה\"ב" if lang == "he" else "🇺🇸 US"
    il = "🇮🇱 ישראל" if lang == "he" else "🇮🇱 Israel"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=us, callback_data="market:US"),
                InlineKeyboardButton(text=il, callback_data="market:IL"),
            ]
        ]
    )


def trade_action_keyboard(lang: str) -> InlineKeyboardMarkup:
    buy = "קנייה" if lang == "he" else "Buy"
    sell = "מכירה" if lang == "he" else "Sell"
    dividend = "דיבידנד" if lang == "he" else "Dividend"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=buy, callback_data="trade:buy"),
                InlineKeyboardButton(text=sell, callback_data="trade:sell"),
            ],
            [InlineKeyboardButton(text=dividend, callback_data="trade:dividend")],
        ]
    )


def cash_action_keyboard(lang: str) -> InlineKeyboardMarkup:
    deposit = "💵 הפקדה" if lang == "he" else "💵 Deposit"
    withdraw = "💸 משיכה" if lang == "he" else "💸 Withdraw"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=deposit, callback_data="cash:action:deposit"),
                InlineKeyboardButton(text=withdraw, callback_data="cash:action:withdraw"),
            ]
        ]
    )


def holdings_shortcuts_keyboard(portfolio_id: int, items: list, t: dict) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        sym = item.symbol
        mkt = item.market
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📈 {sym}",
                    callback_data=f"hold:pnl:{portfolio_id}:{sym}",
                ),
                InlineKeyboardButton(
                    text="📜",
                    callback_data=f"hold:hist:{portfolio_id}:{sym}",
                ),
                InlineKeyboardButton(
                    text="💱",
                    callback_data=f"hold:quote:{portfolio_id}:{sym}:{mkt}",
                ),
                InlineKeyboardButton(
                    text="🔻",
                    callback_data=f"hold:sell:{portfolio_id}:{sym}:{mkt}",
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=t["holdings_shortcuts_hint"],
                callback_data=f"hold:noop:{portfolio_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trade_history_manage_keyboard(trades: list, t: dict) -> InlineKeyboardMarkup:
    rows = []
    row: list[InlineKeyboardButton] = []
    for trade in trades[-8:]:
        row.append(
            InlineKeyboardButton(
                text=f"✏️ #{trade.id}",
                callback_data=f"trade_manage:{trade.id}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trade_manage_keyboard(trade_id: int, t: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t["edit_trade"], callback_data=f"trade_edit:{trade_id}"),
                InlineKeyboardButton(text=t["delete_trade"], callback_data=f"trade_del:{trade_id}"),
            ]
        ]
    )


def trade_edit_fields_keyboard(trade_id: int, t: dict) -> InlineKeyboardMarkup:
    fields = [
        ("quantity", t["quantity"]),
        ("price", t["price"]),
        ("commission", t["commissions"]),
        ("date", "📅"),
        ("note", t["trade_note"]),
    ]
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"trade_edit_field:{trade_id}:{field}")]
        for field, label in fields
    ]
    rows.append(
        [InlineKeyboardButton(text=t["cancel"], callback_data=f"trade_manage:{trade_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def portfolio_manage_keyboard(portfolio_id: int, t: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["edit_commission"], callback_data=f"edit_commission:{portfolio_id}")],
            [
                InlineKeyboardButton(
                    text=t["recalc_commissions"],
                    callback_data=f"recalc_commissions:{portfolio_id}",
                )
            ],
            [InlineKeyboardButton(text=t["rename_portfolio"], callback_data=f"rename_portfolio:{portfolio_id}")],
            [InlineKeyboardButton(text=t["add_cash_portfolio"], callback_data=f"add_cash_portfolio:{portfolio_id}")],
            [InlineKeyboardButton(text=t["edit_opening_cash"], callback_data=f"edit_cash_portfolio:{portfolio_id}")],
            [InlineKeyboardButton(text=t["delete_portfolio"], callback_data=f"delete_portfolio:{portfolio_id}")],
            [InlineKeyboardButton(text=t["back_to_list"], callback_data="portfolios_back")],
        ]
    )


def commission_extra_type_keyboard(t: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t["commission_extra_fixed"],
                    callback_data="comm_extra:fixed",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t["commission_extra_percent"],
                    callback_data="comm_extra:percent",
                )
            ],
        ]
    )


def cancel_keyboard(lang: str) -> InlineKeyboardMarkup:
    label = "ביטול" if lang == "he" else "Cancel"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data="cancel")]]
    )


def alert_scope_keyboard(t: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["alert_scope_stock"], callback_data="alert_scope:stock")],
            [InlineKeyboardButton(text=t["alert_scope_watchlist"], callback_data="alert_scope:watchlist")],
            [InlineKeyboardButton(text=t["alert_scope_portfolio"], callback_data="alert_scope:portfolio")],
        ]
    )


def alert_type_keyboard(scope: str, t: dict) -> InlineKeyboardMarkup:
    stock_types = [
        ("pct_daily", "alert_type_pct_daily"),
        ("price_target", "alert_type_price_target"),
        ("premarket", "alert_type_premarket"),
        ("afterhours", "alert_type_afterhours"),
        ("volume_spike", "alert_type_volume"),
    ]
    watchlist_types = stock_types + [("news", "alert_type_news")]
    portfolio_types = [
        ("portfolio_value_change", "alert_type_value_change"),
        ("daily_loss_limit", "alert_type_daily_loss"),
        ("pnl_milestone", "alert_type_pnl_milestone"),
    ]
    types = {"stock": stock_types, "watchlist": watchlist_types, "portfolio": portfolio_types}[scope]
    rows = [
        [InlineKeyboardButton(text=t[label_key], callback_data=f"alert_type:{alert_type}")]
        for alert_type, label_key in types
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def alert_direction_keyboard(t: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t["alert_above"], callback_data="alert_direction:above"),
                InlineKeyboardButton(text=t["alert_below"], callback_data="alert_direction:below"),
            ]
        ]
    )


def settings_menu_keyboard(t: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["settings_language"], callback_data="settings:language")],
            [InlineKeyboardButton(text=t["settings_commission"], callback_data="settings:commission")],
            [InlineKeyboardButton(text=t["settings_reports"], callback_data="settings:reports")],
            [InlineKeyboardButton(text=t["settings_mover"], callback_data="settings:mover")],
            [InlineKeyboardButton(text=t["settings_import"], callback_data="settings:import")],
            [InlineKeyboardButton(text=t["settings_export"], callback_data="settings:export")],
        ]
    )


def year_keyboard(years: list[int]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=str(y), callback_data=f"tax_year:{y}")] for y in years]
    return InlineKeyboardMarkup(inline_keyboard=rows)
