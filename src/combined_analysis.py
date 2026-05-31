"""Combined stock + option horizon PnL (options as 100-share equivalent)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .disclosures import load_settings
from .instrument_notional import OPTION_SHARES_PER_CONTRACT, trade_side
from .trade_returns import (
    compute_horizon_returns,
    cumulative_pnl_by_date,
    notional_weighted_summary,
)


def tag_trades(df: pd.DataFrame, instrument: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["instrument"] = instrument
    if instrument == "option":
        out["asset_class"] = "option"
    return out


def build_combined_tradable(
    stock: pd.DataFrame,
    options: pd.DataFrame | None,
) -> pd.DataFrame:
    parts = [tag_trades(stock, "stock")]
    if options is not None and not options.empty:
        parts.append(tag_trades(options, "option"))
    return pd.concat(parts, ignore_index=True)


def run_combined_analyses(
    stock: pd.DataFrame,
    options: pd.DataFrame | None,
    price_cache: dict,
    settings: dict[str, Any] | None = None,
    matched_lots=None,
) -> dict[str, Any]:
    """Single union book: timing/follow on economic notional (options × 100 shares when known)."""
    settings = settings or load_settings()
    combined = build_combined_tradable(stock, options)
    if combined.empty:
        return {"combined_timing": pd.DataFrame(), "combined_summary": {}}

    timing = compute_horizon_returns(combined, price_cache, "transaction_date")
    follow = compute_horizon_returns(combined, price_cache, "disclosure_date")

    stock_only = timing[timing["instrument"] == "stock"] if not timing.empty else timing
    option_only = timing[timing["instrument"] == "option"] if not timing.empty else timing

    buy_side = timing[timing["trade_side"] == "purchase"] if "trade_side" in timing.columns else timing
    sell_side = timing[timing["trade_side"] == "sale"] if "trade_side" in timing.columns else timing

    return {
        "combined_trades": combined,
        "combined_timing": timing,
        "combined_follow": follow,
        "combined_summary": {
            "timing_all": notional_weighted_summary(timing).to_dict(orient="records"),
            "timing_stock": notional_weighted_summary(stock_only).to_dict(orient="records"),
            "timing_option": notional_weighted_summary(option_only).to_dict(orient="records"),
            "timing_buy": notional_weighted_summary(buy_side).to_dict(orient="records"),
            "timing_sell": notional_weighted_summary(sell_side).to_dict(orient="records"),
            "follow_all": notional_weighted_summary(follow).to_dict(orient="records"),
            "follow_stock": notional_weighted_summary(
                follow[follow["instrument"] == "stock"] if not follow.empty else follow
            ).to_dict(orient="records"),
            "follow_option": notional_weighted_summary(
                follow[follow["instrument"] == "option"] if not follow.empty else follow
            ).to_dict(orient="records"),
        },
        "combined_cumulative": cumulative_pnl_by_date(timing),
        "combined_cumulative_stock": cumulative_pnl_by_date(stock_only),
        "combined_cumulative_option": cumulative_pnl_by_date(option_only),
        "option_shares_per_contract": OPTION_SHARES_PER_CONTRACT,
    }
