"""
Unified underlying FIFO: stock + options (100 sh/contract) in one queue per ticker.

Option purchase / exercise add long exposure on the underlying; stock sales match
against those lots (fixes orphan sells when exposure came from options).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .disclosures import load_settings, analysis_end_date
from .holdings import holding_summary_stats
from .instrument_notional import economic_notional, trade_notional
from .portfolio_snapshot import (
    HORIZONS,
    _close_on_date,
    _trading_calendar,
    portfolio_daily_summary_records,
)

IN_ACTIONS = frozenset({"purchase", "exercise"})
OUT_ACTIONS = frozenset({"sale"})


def _unified_sort_key(row: pd.Series) -> tuple:
    side_rank = 0 if row["fifo_side"] == "in" else 1
    txn = row.get("txn_num")
    txn = int(txn) if pd.notna(txn) else 0
    return (pd.Timestamp(row["transaction_date"]), side_rank, txn, str(row.get("trade_id", "")))


def build_unified_trades(
    stock: pd.DataFrame,
    options: pd.DataFrame | None,
) -> pd.DataFrame:
    """Merge stock and option rows on underlying ticker with fifo_side in/out."""
    parts: list[pd.DataFrame] = []
    if stock is not None and not stock.empty:
        s = stock[stock["ticker"].notna() & stock["action"].isin(IN_ACTIONS | OUT_ACTIONS)].copy()
        s["instrument"] = "stock"
        parts.append(s)
    if options is not None and not options.empty:
        o = options[options["ticker"].notna() & options["action"].isin(IN_ACTIONS | OUT_ACTIONS)].copy()
        o["instrument"] = "option"
        parts.append(o)
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    df["transaction_date"] = pd.to_datetime(df["transaction_date"]).dt.normalize()
    df["fifo_side"] = df["action"].map(lambda a: "in" if a in IN_ACTIONS else "out")
    df["_sort"] = df.apply(_unified_sort_key, axis=1)
    return df.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)


@dataclass
class _OpenLot:
    ticker: str
    notional: float
    entry_date: pd.Timestamp
    entry_price: float
    instrument: str
    action: str
    trade_id: str


def _row_notional(row: pd.Series, prices: pd.DataFrame, day: pd.Timestamp) -> float:
    p0 = _close_on_date(prices, day)
    if p0 and p0 > 0:
        n = economic_notional(row, anchor_price=p0)
        if pd.notna(n) and n > 0:
            return float(n)
    return float(trade_notional(row)) if pd.notna(trade_notional(row)) else np.nan


def fifo_match_unified(
    stock: pd.DataFrame,
    options: pd.DataFrame | None,
    price_cache: dict[str, pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    FIFO on underlying ticker across stock + options (in = purchase/exercise, out = sale).
    """
    df = build_unified_trades(stock, options)
    if df.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty

    lot_rows: list[dict[str, Any]] = []
    trade_holding: dict[str, float | None] = {}

    for ticker, grp in df.groupby("ticker", sort=False):
        ordered = grp.copy()
        ordered["_sort"] = ordered.apply(_unified_sort_key, axis=1)
        ordered = ordered.sort_values("_sort").drop(columns="_sort")
        buy_queue: deque[_OpenLot] = deque()
        prices = price_cache.get(str(ticker)) if price_cache else None

        for _, row in ordered.iterrows():
            tid = str(row["trade_id"])
            day = pd.Timestamp(row["transaction_date"]).normalize()

            if row["fifo_side"] == "in":
                if prices is None or prices.empty:
                    notional = trade_notional(row)
                    entry_price = np.nan
                else:
                    notional = _row_notional(row, prices, day)
                    entry_price = _close_on_date(prices, day)
                if pd.isna(notional) or notional <= 0:
                    continue
                if not entry_price or entry_price <= 0:
                    entry_price = float(row.get("strike") or 0) or 1.0
                buy_queue.append(
                    _OpenLot(
                        str(ticker),
                        float(notional),
                        day,
                        float(entry_price),
                        str(row.get("instrument", "stock")),
                        str(row["action"]),
                        tid,
                    )
                )
                trade_holding[tid] = None
                continue

            sell_date = day
            if buy_queue:
                lot = buy_queue.popleft()
                days = int((sell_date - lot.entry_date).days)
                lot_rows.append(
                    {
                        "ticker": ticker,
                        "buy_trade_id": lot.trade_id,
                        "sell_trade_id": tid,
                        "buy_date": lot.entry_date,
                        "sell_date": sell_date,
                        "holding_days": days,
                        "buy_instrument": lot.instrument,
                        "buy_action": lot.action,
                        "sell_instrument": row.get("instrument", "stock"),
                        "sell_action": row["action"],
                        "buy_notional": lot.notional,
                        "match_status": "matched",
                    }
                )
                trade_holding[tid] = float(days)
            else:
                lot_rows.append(
                    {
                        "ticker": ticker,
                        "buy_trade_id": None,
                        "sell_trade_id": tid,
                        "buy_date": pd.NaT,
                        "sell_date": sell_date,
                        "holding_days": None,
                        "buy_instrument": None,
                        "buy_action": None,
                        "sell_instrument": row.get("instrument", "stock"),
                        "sell_action": row["action"],
                        "buy_notional": None,
                        "match_status": "prior_position",
                    }
                )
                trade_holding[tid] = None

        for lot in buy_queue:
            lot_rows.append(
                {
                    "ticker": ticker,
                    "buy_trade_id": lot.trade_id,
                    "sell_trade_id": None,
                    "buy_date": lot.entry_date,
                    "sell_date": pd.NaT,
                    "holding_days": None,
                    "buy_instrument": lot.instrument,
                    "buy_action": lot.action,
                    "sell_instrument": None,
                    "sell_action": None,
                    "buy_notional": lot.notional,
                    "match_status": "open",
                }
            )

    all_lots = pd.DataFrame(lot_rows)
    if all_lots.empty:
        return all_lots, pd.DataFrame(), pd.DataFrame(columns=["trade_id", "fifo_holding_days"]), all_lots

    matched_lots = all_lots[all_lots["match_status"] == "matched"].reset_index(drop=True)

    summary_rows = []
    for ticker, sub in all_lots.groupby("ticker"):
        matched_sub = sub[sub["match_status"] == "matched"]
        hd = matched_sub["holding_days"].dropna()
        summary_rows.append(
            {
                "ticker": ticker,
                "n_matched_pairs": len(matched_sub),
                "n_open_buys": int((sub["match_status"] == "open").sum()),
                "n_prior_sells": int((sub["match_status"] == "prior_position").sum()),
                "n_matched_from_option": int((matched_sub["buy_instrument"] == "option").sum()),
                "avg_holding_days": float(hd.mean()) if len(hd) else None,
                "median_holding_days": float(hd.median()) if len(hd) else None,
            }
        )
    ticker_summary = pd.DataFrame(summary_rows).sort_values("n_matched_pairs", ascending=False)

    trade_holding_df = pd.DataFrame(
        [{"trade_id": k, "fifo_holding_days": v} for k, v in trade_holding.items()]
    )
    return matched_lots, ticker_summary, trade_holding_df, all_lots


def compute_unified_portfolio_daily(
    stock: pd.DataFrame,
    options: pd.DataFrame | None,
    price_cache: dict[str, pd.DataFrame],
    settings: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Daily position MTM and PnL using unified underlying FIFO (stock + options)."""
    settings = settings or load_settings()
    end = analysis_end_date(settings)

    df = build_unified_trades(stock, options)
    if df.empty:
        return pd.DataFrame()

    df = df[df["transaction_date"] <= end].copy()
    tickers = set(df["ticker"].astype(str).unique())
    start = df["transaction_date"].min()
    calendar = _trading_calendar(price_cache, tickers, start, end)
    if not calendar:
        return pd.DataFrame()

    by_day: dict[pd.Timestamp, list[pd.Series]] = {}
    for _, row in df.iterrows():
        d = pd.Timestamp(row["transaction_date"]).normalize()
        by_day.setdefault(d, []).append(row)

    queues: dict[str, deque[_OpenLot]] = {t: deque() for t in tickers}
    realized_pnl = 0.0
    prev_total_pnl = 0.0
    rows: list[dict[str, Any]] = []

    for day in calendar:
        for row in by_day.get(day, []):
            ticker = str(row["ticker"])
            prices = price_cache.get(ticker)
            if prices is None or prices.empty:
                continue
            notional = _row_notional(row, prices, day)
            if pd.isna(notional) or notional <= 0:
                continue

            if row["fifo_side"] == "in":
                entry_price = _close_on_date(prices, day)
                if not entry_price or entry_price <= 0:
                    entry_price = float(row.get("strike") or 0) or 1.0
                queues.setdefault(ticker, deque()).append(
                    _OpenLot(
                        ticker,
                        float(notional),
                        day,
                        float(entry_price),
                        str(row.get("instrument", "stock")),
                        str(row["action"]),
                        str(row["trade_id"]),
                    )
                )
                continue

            q = queues.get(ticker)
            if not q:
                continue
            lot = q.popleft()
            exit_price = _close_on_date(prices, day)
            if exit_price and lot.entry_price > 0:
                realized_pnl += lot.notional * (exit_price / lot.entry_price - 1.0)

        position_cost = 0.0
        position_mtm = 0.0
        cost_stock = 0.0
        cost_option = 0.0
        mtm_stock = 0.0
        mtm_option = 0.0
        unrealized_pnl = 0.0
        n_open_lots = 0
        n_open_stock = 0
        n_open_option = 0
        held_tickers: set[str] = set()

        for ticker, q in queues.items():
            prices = price_cache.get(ticker)
            if prices is None or prices.empty:
                continue
            close = _close_on_date(prices, day)
            if not close or close <= 0:
                continue
            for lot in q:
                if lot.entry_price <= 0:
                    continue
                mtm = lot.notional * close / lot.entry_price
                position_cost += lot.notional
                position_mtm += mtm
                unrealized_pnl += lot.notional * (close / lot.entry_price - 1.0)
                n_open_lots += 1
                held_tickers.add(ticker)
                if lot.instrument == "option":
                    cost_option += lot.notional
                    mtm_option += mtm
                    n_open_option += 1
                else:
                    cost_stock += lot.notional
                    mtm_stock += mtm
                    n_open_stock += 1

        total_pnl = realized_pnl + unrealized_pnl
        daily_pnl = total_pnl - prev_total_pnl
        prev_total_pnl = total_pnl

        rows.append(
            {
                "date": day.date(),
                "position_cost": position_cost,
                "position_mtm": position_mtm,
                "position_cost_stock": cost_stock,
                "position_cost_option": cost_option,
                "position_mtm_stock": mtm_stock,
                "position_mtm_option": mtm_option,
                "n_open_lots": n_open_lots,
                "n_open_stock_lots": n_open_stock,
                "n_open_option_lots": n_open_option,
                "n_tickers": len(held_tickers),
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                "total_pnl": total_pnl,
                "daily_pnl": daily_pnl,
                "cum_pnl": total_pnl,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("date").reset_index(drop=True)


def compute_open_holdings_unified_top_n(
    timing: pd.DataFrame,
    all_lots: pd.DataFrame,
    top_n: int = 10,
) -> pd.DataFrame:
    """Top open lots from unified FIFO; horizon stats from combined/pelosi timing table."""
    if all_lots.empty or timing.empty:
        return pd.DataFrame()
    open_lots = all_lots[all_lots["match_status"] == "open"].copy()
    if open_lots.empty:
        return pd.DataFrame()
    timing = timing.copy()
    timing_idx = timing.set_index("trade_id") if "trade_id" in timing.columns else timing

    rows: list[dict[str, Any]] = []
    settings = load_settings()
    end = analysis_end_date(settings)

    for ticker, grp in open_lots.groupby("ticker", sort=False):
        buy_ids = grp["buy_trade_id"].astype(str).tolist()
        buy_trades = timing[timing["trade_id"].astype(str).isin(buy_ids)].copy()
        if buy_trades.empty:
            for bid in buy_ids:
                if bid in timing_idx.index:
                    buy_trades = pd.concat([buy_trades, timing_idx.loc[[bid]]])
        if buy_trades.empty:
            continue
        net_notional = float(buy_trades["notional"].sum())
        if net_notional <= 0:
            continue
        earliest = buy_trades.loc[buy_trades["anchor_date"].idxmin() if "anchor_date" in buy_trades else buy_trades.index[0]]
        entry = pd.Timestamp(earliest.get("anchor_date", earliest.get("transaction_date"))).normalize()
        inst = grp["buy_instrument"].iloc[0] if "buy_instrument" in grp.columns else "stock"
        row: dict[str, Any] = {
            "ticker": ticker,
            "net_notional": net_notional,
            "n_open_lots": len(grp),
            "buy_instrument": inst,
            "first_buy_date": entry.date(),
            "days_held": int((end - entry).days),
            "status": "仍持有",
        }
        for h in HORIZONS:
            rc, pc = f"ret_{h}d", f"pnl_{h}d"
            if rc in earliest.index and pd.notna(earliest.get(rc)):
                row[rc] = float(earliest[rc])
            if pc in earliest.index and pd.notna(earliest.get(pc)):
                row[pc] = float(earliest[pc])
        rows.append(row)

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("net_notional", ascending=False).head(top_n).reset_index(drop=True)


def unified_portfolio_summary(
    matched_lots: pd.DataFrame,
    daily: pd.DataFrame,
    all_lots: pd.DataFrame | None = None,
) -> dict[str, Any]:
    stats = holding_summary_stats(matched_lots)
    meta = portfolio_daily_summary_records(daily)
    if not matched_lots.empty:
        stats["n_matched_from_option"] = int((matched_lots["buy_instrument"] == "option").sum())
        stats["n_matched_from_stock"] = int((matched_lots["buy_instrument"] == "stock").sum())
    if all_lots is not None and not all_lots.empty:
        stats["n_prior_sells"] = int((all_lots["match_status"] == "prior_position").sum())
        stats["n_open_lots"] = int((all_lots["match_status"] == "open").sum())
    return {"fifo": stats, "daily": meta}
