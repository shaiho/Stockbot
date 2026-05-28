from __future__ import annotations

from dataclasses import dataclass

from src.market.prices import PriceProvider
from src.portfolio.calculator import PortfolioSummary


@dataclass
class BenchmarkComparison:
    portfolio_daily_pct: float
    us_name: str
    us_change_pct: float | None
    il_name: str
    il_change_pct: float | None


async def compute_benchmark_comparison(
    summary: PortfolioSummary,
    prices: PriceProvider,
) -> BenchmarkComparison:
    us_name, us_pct = await prices.get_benchmark("US")
    il_name, il_pct = await prices.get_benchmark("IL")
    if summary.total_ils > 0:
        portfolio_daily_pct = summary.daily_change_ils / summary.total_ils * 100
    else:
        portfolio_daily_pct = 0.0
    return BenchmarkComparison(
        portfolio_daily_pct=portfolio_daily_pct,
        us_name=us_name,
        us_change_pct=us_pct,
        il_name=il_name,
        il_change_pct=il_pct,
    )
