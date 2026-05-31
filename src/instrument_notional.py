"""Economic notional: stocks vs options (100 shares per contract)."""

from __future__ import annotations

import numpy as np
import pandas as pd

OPTION_SHARES_PER_CONTRACT = 100
MAX_SANE_NOTIONAL = 1_000_000_001


def trade_notional(row: pd.Series) -> float:
    """PTR bracket lower bound (amount_min); skip OCR-inflated values."""
    lo = row.get("amount_min")
    if pd.notna(lo):
        v = float(lo)
        if 0 < v < MAX_SANE_NOTIONAL:
            return v
    hi = row.get("amount_max")
    if pd.notna(hi):
        v = float(hi)
        if 0 < v < MAX_SANE_NOTIONAL:
            return v
    return np.nan


BUY_ACTIONS = frozenset({"purchase", "exercise"})
SELL_ACTIONS = frozenset({"sale"})


def is_option_row(row: pd.Series) -> bool:
    if str(row.get("instrument", "")).lower() == "option":
        return True
    return str(row.get("asset_class", "")).lower() == "option"


def trade_side(action: str) -> str:
    """Map to buy (purchase/exercise) or sell for charts and summaries."""
    return "purchase" if action in BUY_ACTIONS else "sale"


def shares_equivalent(row: pd.Series, anchor_price: float | None = None) -> float:
    """Share count for exposure; options = contracts × 100."""
    if is_option_row(row):
        n = row.get("n_contracts")
        if pd.notna(n) and float(n) > 0:
            return float(n) * OPTION_SHARES_PER_CONTRACT
        return np.nan
    if pd.notna(anchor_price) and anchor_price > 0:
        base = trade_notional(row)
        if pd.notna(base) and base > 0:
            return float(base) / float(anchor_price)
    return np.nan


def pie_notional(row: pd.Series) -> float:
    """Chart exposure without live prices: options use contracts × 100 × strike when known."""
    base = trade_notional(row)
    if not is_option_row(row):
        return base
    n = row.get("n_contracts")
    strike = row.get("strike")
    if pd.notna(n) and float(n) > 0 and pd.notna(strike) and float(strike) > 0:
        return float(n) * OPTION_SHARES_PER_CONTRACT * float(strike)
    return base


def economic_notional(row: pd.Series, anchor_price: float | None = None) -> float:
    """
    Dollar exposure for PnL: stock = PTR amount_min;
    option = n_contracts × 100 × underlying price (fallback: amount_min).
    """
    base = trade_notional(row)
    if not is_option_row(row):
        return base
    n = row.get("n_contracts")
    if pd.notna(n) and float(n) > 0 and anchor_price and float(anchor_price) > 0:
        return float(n) * OPTION_SHARES_PER_CONTRACT * float(anchor_price)
    return base
