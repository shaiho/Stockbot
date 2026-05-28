from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    language = State()
    portfolio_name = State()
    opening_cash_ils = State()
    opening_cash_ils_custom = State()
    opening_cash_usd = State()
    opening_cash_usd_custom = State()
    default_commission = State()
    default_commission_custom = State()
    default_commission_currency = State()
    add_holdings_now = State()
    symbol = State()
    market = State()
    quantity = State()
    price = State()
    trade_date = State()
    add_another = State()


class NewPortfolioStates(StatesGroup):
    name = State()
    opening_cash_ils = State()
    opening_cash_ils_custom = State()
    opening_cash_usd = State()
    opening_cash_usd_custom = State()
    add_holdings_now = State()
    symbol = State()
    market = State()
    quantity = State()
    price = State()
    trade_date = State()
    add_another = State()


class TradeStates(StatesGroup):
    portfolio = State()
    action = State()
    symbol = State()
    market = State()
    quantity = State()
    price = State()
    trade_date = State()
    commission = State()
    note = State()


class CashStates(StatesGroup):
    portfolio = State()
    action = State()
    currency = State()
    amount = State()
    trade_date = State()


class EditTradeStates(StatesGroup):
    value = State()


class QuoteStates(StatesGroup):
    symbol = State()
    market = State()


class PnlStates(StatesGroup):
    portfolio = State()
    symbol = State()


class HistoryStates(StatesGroup):
    portfolio = State()
    symbol = State()


class TaxStates(StatesGroup):
    portfolio = State()
    year = State()


class MonthlyStates(StatesGroup):
    portfolio = State()


class PortfolioManageStates(StatesGroup):
    rename = State()
    edit_cash_ils = State()
    edit_cash_ils_custom = State()
    edit_cash_usd = State()
    edit_cash_usd_custom = State()
    confirm_delete = State()
    commission_min_usd = State()
    commission_min_ils = State()
    commission_extra_type = State()
    commission_extra_value = State()


class WatchlistStates(StatesGroup):
    symbol = State()
    market = State()


class AlertStates(StatesGroup):
    scope = State()
    alert_type = State()
    symbol = State()
    market = State()
    portfolio = State()
    threshold = State()
    target_price = State()
    direction = State()
    milestone = State()


class SettingsStates(StatesGroup):
    menu = State()
    commission = State()
    commission_currency = State()
    report_morning = State()
    report_evening = State()
    mover_threshold = State()


class ImportStates(StatesGroup):
    portfolio = State()
    json_data = State()


class ExportStates(StatesGroup):
    portfolio = State()
