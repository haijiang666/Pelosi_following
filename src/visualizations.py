"""Generate analysis charts for Pelosi House PTR equity/options reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .instrument_notional import BUY_ACTIONS, economic_notional, pie_notional, trade_notional, trade_side
from .prices import price_on_date

sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({"figure.dpi": 120, "savefig.dpi": 150, "font.size": 10})

_ACTION_COLORS = {"purchase": "#2ecc71", "sale": "#e74c3c", "exchange": "#f39c12"}
_ACTION_LABELS = {"purchase": "Buy", "sale": "Sell", "exchange": "Exchange"}


def _save(fig: plt.Figure, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _fmt_notional_short(x: float) -> str:
    if pd.isna(x) or x <= 0:
        return "$0"
    if x >= 1e6:
        return f"${x / 1e6:.2f}M"
    if x >= 1e3:
        return f"${x / 1e3:.0f}K"
    return f"${x:,.0f}"


def _mpl_label(s: str) -> str:
    """Escape $ so matplotlib renders dollar amounts literally (not as mathtext)."""
    return s.replace("$", r"\$")


def _with_notional(trades: pd.DataFrame, pelosi_df: pd.DataFrame | None = None) -> pd.DataFrame:
    df = trades.copy()
    if pelosi_df is not None and "notional" in pelosi_df.columns and "trade_id" in pelosi_df.columns:
        nmap = pelosi_df.drop_duplicates("trade_id").set_index("trade_id")["notional"]
        if "trade_id" in df.columns:
            df["notional"] = df["trade_id"].map(nmap)
        else:
            df["notional"] = df.apply(trade_notional, axis=1)
    elif "notional" not in df.columns:
        df["notional"] = df.apply(trade_notional, axis=1)
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["disclosure_date"] = pd.to_datetime(df["disclosure_date"])
    return df.dropna(subset=["notional"])


def _pick_granularity(dates: pd.Series) -> tuple[str, str]:
    span = int((dates.max() - dates.min()).days)
    if span <= 45:
        return "D", "day"
    if span <= 120:
        return "W", "week"
    return "W", "week"


def _period_start(dates: pd.Series, granularity: str) -> pd.Series:
    if granularity == "D":
        return dates.dt.normalize()
    if granularity == "W":
        return dates.dt.to_period("W").apply(lambda p: p.start_time)
    return dates.dt.to_period("M").apply(lambda p: p.start_time)


def _top_ticker_lines(sub: pd.DataFrame, top_n: int = 3) -> list[str]:
    """Top-N tickers in a period by total notional, with buy/sell breakdown."""
    sub = sub[sub["ticker"].notna()].copy()
    if sub.empty:
        return []
    rows = []
    for ticker, g in sub.groupby("ticker", sort=False):
        buy = float(g.loc[g["action"] == "purchase", "notional"].sum())
        sell = float(g.loc[g["action"] == "sale", "notional"].sum())
        total = buy + sell
        if total <= 0:
            continue
        parts: list[str] = []
        if buy > 0:
            parts.append(f"buy {_fmt_notional_short(buy)}")
        if sell > 0:
            parts.append(f"sell {_fmt_notional_short(sell)}")
        rows.append((total, f"{ticker} {' '.join(parts)}"))
    rows.sort(key=lambda x: x[0], reverse=True)
    return [line for _, line in rows[:top_n]]


def _annotate_top_tickers(
    ax,
    df: pd.DataFrame,
    periods: list,
    x_positions: np.ndarray,
    heights: np.ndarray,
    top_n: int = 3,
    min_notional: float = 0.0,
    ymax: float = 1.0,
) -> None:
    """Place top-ticker labels on each bar with dark text on white box."""
    bbox = dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#7f8c8d", alpha=0.97, linewidth=0.8)
    for period, xpos, h in zip(periods, x_positions, heights):
        if h < min_notional:
            continue
        sub = df[df["_period"] == period]
        lines = _top_ticker_lines(sub, top_n=top_n)
        if not lines:
            continue
        text = _mpl_label("\n".join(lines))
        ax.text(
            xpos,
            h + ymax * 0.006,
            text,
            ha="center",
            va="bottom",
            fontsize=9.5,
            fontweight="bold",
            color="#1a1a1a",
            linespacing=1.15,
            bbox=bbox,
            zorder=10,
            clip_on=False,
        )


def plot_trade_volume_monthly(
    trades: pd.DataFrame,
    out_dir: Path,
    pelosi_df: pd.DataFrame | None = None,
) -> Path:
    """Timeline of trade count + notional (day/week); top-3 trades labeled per bar."""
    df = _with_notional(trades, pelosi_df)
    df = df[df["action"].isin(["purchase", "sale"])].copy()
    gran, gran_label = _pick_granularity(df["transaction_date"])
    df["_period"] = _period_start(df["transaction_date"], gran)
    periods = sorted(df["_period"].unique())
    x = np.arange(len(periods))
    width = 0.72

    buy_n = []
    sell_n = []
    buy_not = []
    sell_not = []
    for p in periods:
        sub = df[df["_period"] == p]
        buy = sub[sub["action"] == "purchase"]
        sell = sub[sub["action"] == "sale"]
        buy_n.append(len(buy))
        sell_n.append(len(sell))
        buy_not.append(buy["notional"].sum())
        sell_not.append(sell["notional"].sum())

    total_notional = df["notional"].sum()
    total_trades = len(df)
    counts = np.array(buy_n) + np.array(sell_n)
    totals_not = np.array(buy_not) + np.array(sell_not)
    ymax = float(totals_not.max()) if len(totals_not) else 1.0

    fig_w = max(18.0, len(periods) * 0.52)
    fig, ax1 = plt.subplots(figsize=(fig_w, 8))
    ax2 = ax1.twinx()
    ax1.bar(x, buy_not, width, label=f"Buy notional ({sum(buy_n):,} trades)", color=_ACTION_COLORS["purchase"], alpha=0.92)
    ax1.bar(
        x,
        sell_not,
        width,
        bottom=buy_not,
        label=f"Sell notional ({sum(sell_n):,} trades)",
        color=_ACTION_COLORS["sale"],
        alpha=0.92,
    )
    ax2.plot(x, counts, color="#34495e", marker="o", lw=1.5, ms=3, label="Trade count", zorder=5)

    _annotate_top_tickers(
        ax1,
        df,
        periods,
        x,
        totals_not,
        top_n=3,
        min_notional=max(200_000.0, ymax * 0.03),
        ymax=ymax,
    )

    ax1.set_xticks(x)
    ax1.set_xticklabels([pd.Timestamp(p).strftime("%Y-%m-%d") for p in periods], rotation=45, ha="right")
    ax1.set_ylabel("Notional ($) — primary", fontweight="bold")
    ax2.set_ylabel("Trade count")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: _fmt_notional_short(v)))
    ax1.set_title(
        _mpl_label(
            f"Trade Volume by {gran_label.title()} · Total {_fmt_notional_short(total_notional)} notional · {total_trades:,} trades"
        )
    )
    ax1.set_xlabel(f"Period start ({gran_label}) · on-bar labels: top-3 tickers (buy/sell notional)")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
    ax1.set_ylim(0, ymax * 1.10)
    fig.subplots_adjust(top=0.92, bottom=0.14, right=0.92)
    return _save(fig, out_dir, "01_monthly_volume")


def plot_reveal_lag(returns_df: pd.DataFrame, out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 4))
    lag = returns_df["reveal_lag_days"].dropna()
    ax.hist(lag, bins=40, color="#3498db", edgecolor="white")
    ax.axvline(lag.median(), color="#e67e22", ls="--", label=f"Median {lag.median():.0f}d")
    ax.set_title("Reveal Lag: Transaction → House PTR Disclosure")
    ax.set_xlabel("Days")
    ax.set_ylabel("Trades")
    ax.legend()
    return _save(fig, out_dir, "02_reveal_lag")


def plot_top_tickers(
    trades: pd.DataFrame,
    out_dir: Path,
    n: int = 15,
    returns_df: pd.DataFrame | None = None,
) -> Path:
    if returns_df is not None and "notional" in returns_df.columns and "ticker" in returns_df.columns:
        dedupe_col = "trade_id" if "trade_id" in returns_df.columns else "ticker"
        top = (
            returns_df.drop_duplicates(subset=[dedupe_col])
            .groupby("ticker")["notional"]
            .sum()
            .nlargest(n)
        )
        title = f"Top {n} Tickers by Pelosi Notional (amount_min)"
        xlabel = "Notional ($)"
    else:
        df = trades[trades["ticker"].notna()].copy()
        df["notional"] = df.apply(trade_notional, axis=1)
        top = df.groupby("ticker")["notional"].sum().nlargest(n)
        title = f"Top {n} Tickers by Pelosi Notional (amount_min)"
        xlabel = "Notional ($)"
    fig, ax = plt.subplots(figsize=(8, 5))
    top.sort_values().plot(kind="barh", ax=ax, color="#9b59b6")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x/1e6:.1f}M" if x >= 1e6 else f"${x/1e3:.0f}K"))
    return _save(fig, out_dir, "03_top_tickers")


def _buy_sell_bar_frame(
    trades: pd.DataFrame,
    instrument: str,
    price_cache: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Raw PTR rows; notional = economic_notional @ txn date (aligns with horizon PnL)."""
    if trades is None or trades.empty:
        return pd.DataFrame()
    df = trades[trades["action"].isin(list(BUY_ACTIONS) + ["sale"])].copy()
    if df.empty:
        return df
    df["instrument"] = instrument
    df["side"] = df["action"].map(lambda a: trade_side(str(a)))
    df["segment"] = df["instrument"] + "_" + df["side"]
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")

    def _row_notional(row: pd.Series) -> float:
        ticker = row.get("ticker")
        prices = price_cache.get(str(ticker)) if price_cache and pd.notna(ticker) else None
        p0 = None
        if prices is not None and not prices.empty and pd.notna(row["transaction_date"]):
            p0 = price_on_date(prices, row["transaction_date"])
        n = economic_notional(row, anchor_price=p0)
        if pd.notna(n) and n > 0:
            return float(n)
        return float(pie_notional(row)) if pd.notna(pie_notional(row)) else np.nan

    df["notional"] = df.apply(_row_notional, axis=1)
    return df


_BUY_SELL_SEGMENTS: list[tuple[str, str, str, str]] = [
    ("stock", "purchase", "Stock Buy", "#27ae60"),
    ("stock", "sale", "Stock Sell", "#c0392b"),
    ("option", "purchase", "Option Buy\n(incl. exercise)", "#2ecc71"),
    ("option", "sale", "Option Sell", "#e74c3c"),
]


def _segment_summary(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Count all rows per segment; notional sums (NaN → 0 for pie)."""
    keys = [f"{inst}_{side}" for inst, side, _, _ in _BUY_SELL_SEGMENTS]
    if df.empty:
        z = pd.Series(0, index=keys)
        return z, z.astype(float)
    counts = df.groupby("segment", observed=True).size()
    notionals = df.groupby("segment", observed=True)["notional"].sum(min_count=1).fillna(0.0)
    count = counts.reindex(keys, fill_value=0)
    notional = notionals.reindex(keys, fill_value=0.0)
    return count, notional


def _segment_labels() -> list[str]:
    return [lbl.replace("\n", " ") for _, _, lbl, _ in _BUY_SELL_SEGMENTS]


def _segment_colors() -> list[str]:
    return [c for *_, c in _BUY_SELL_SEGMENTS]


def _bar_four_segments(
    ax,
    values: pd.Series,
    *,
    by_count: bool,
    xlabel: str,
) -> None:
    """Horizontal bars for four segments; always show buy + sell rows (zero allowed)."""
    labels = _segment_labels()
    colors = _segment_colors()
    vals = values.reindex([f"{inst}_{side}" for inst, side, _, _ in _BUY_SELL_SEGMENTS], fill_value=0.0)
    y = np.arange(len(labels))
    widths = vals.values.astype(float)
    total = float(widths.sum())
    bars = ax.barh(y, widths, color=colors, edgecolor="white", height=0.62)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel(xlabel)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.25)
    for bar, v in zip(bars, widths):
        if v <= 0:
            ax.text(
                0.01 * (ax.get_xlim()[1] or 1),
                bar.get_y() + bar.get_height() / 2,
                "0",
                va="center",
                ha="left",
                fontsize=8,
                color="#7f8c8d",
            )
            continue
        pct = v / total * 100 if total > 0 else 0
        label = f"{int(round(v)):,}" if by_count else _fmt_notional_short(v)
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            _mpl_label(f" {label} ({pct:.0f}%)"),
            va="center",
            ha="left",
            fontsize=8,
        )
    if total > 0:
        ax.set_xlim(0, max(widths) * 1.28)


def plot_buy_sell(
    trades: pd.DataFrame,
    out_dir: Path,
    pelosi_df: pd.DataFrame | None = None,
    instrument: str = "stock",
) -> Path:
    del pelosi_df
    if instrument == "option":
        return plot_combined_buy_sell(None, trades, out_dir)
    return plot_combined_buy_sell(trades, None, out_dir)


def plot_combined_buy_sell(
    stock: pd.DataFrame,
    options: pd.DataFrame | None,
    out_dir: Path,
    stock_timing: pd.DataFrame | None = None,
    option_timing: pd.DataFrame | None = None,
    price_cache: dict[str, pd.DataFrame] | None = None,
) -> Path:
    """Four-way bar chart: stock/option buy (incl. exercise) vs sell — count & economic notional."""
    del stock_timing, option_timing
    parts: list[pd.DataFrame] = []
    if stock is not None and not stock.empty:
        parts.append(_buy_sell_bar_frame(stock, "stock", price_cache))
    if options is not None and not options.empty:
        parts.append(_buy_sell_bar_frame(options, "option", price_cache))
    if not parts:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        return _save(fig, out_dir, "04_buy_sell")

    df = pd.concat(parts, ignore_index=True)
    count, notional = _segment_summary(df)
    total_c = int(count.sum())
    total_n = float(notional.sum())
    buy_c = int(count.get("stock_purchase", 0) + count.get("option_purchase", 0))
    sell_c = int(count.get("stock_sale", 0) + count.get("option_sale", 0))
    buy_n = float(notional.get("stock_purchase", 0) + notional.get("option_purchase", 0))
    sell_n = float(notional.get("stock_sale", 0) + notional.get("option_sale", 0))

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    _bar_four_segments(axes[0], count, by_count=True, xlabel="Row count")
    axes[0].set_title(_mpl_label(f"By count ({total_c:,} rows)"), fontsize=10, pad=8)
    _bar_four_segments(axes[1], notional, by_count=False, xlabel="Disclosed notional ($)")
    axes[1].set_title(_mpl_label(f"By notional ({_fmt_notional_short(total_n)})"), fontsize=10, pad=8)

    fig.suptitle(
        _mpl_label(
            "Stock + Options — buy vs sell (PTR rows; notional = horizon economic @ txn date) · "
            f"Buy {buy_c:,} / {_fmt_notional_short(buy_n)} · "
            f"Sell {sell_c:,} / {_fmt_notional_short(sell_n)}"
        ),
        fontsize=9,
        y=1.02,
    )
    fig.tight_layout()
    return _save(fig, out_dir, "04_buy_sell")


def plot_combined_cumulative_pnl(
    total_cum: pd.DataFrame,
    stock_cum: pd.DataFrame,
    option_cum: pd.DataFrame,
    out_dir: Path,
    prefix: str = "14_combined_cumulative_pnl",
) -> Path:
    """Cumulative horizon PnL: combined total with stock vs option (default 20td)."""
    h = 20
    col = f"cum_pnl_{h}d"
    fig, ax = plt.subplots(figsize=(11, 5))

    def _plot_one(cum_df: pd.DataFrame, label: str, color: str, lw: float = 1.8) -> None:
        if cum_df is None or cum_df.empty or col not in cum_df.columns:
            return
        sub = cum_df.dropna(subset=[col])
        if sub.empty:
            return
        ax.plot(sub["date"], sub[col], label=label, color=color, lw=lw)

    _plot_one(total_cum, "Combined", "#2c3e50", 2.2)
    _plot_one(stock_cum, "Stock", "#3498db", 1.6)
    _plot_one(option_cum, "Options (100 sh/contract)", "#e67e22", 1.6)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_title(f"Combined PnL — cumulative +{h}td (txn date anchor)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative PnL ($)")
    ax.legend()
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x/1e6:.2f}M" if abs(x) >= 1e6 else f"${x/1e3:.0f}K"))
    plt.xticks(rotation=45, ha="right")
    return _save(fig, out_dir, prefix)


def plot_post_returns(returns_df: pd.DataFrame, out_dir: Path) -> Path:
    cols = ["return_post_disclosure_1d", "return_post_disclosure_5d"]
    data = returns_df[cols].dropna(how="all")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, col in zip(axes, cols):
        s = data[col].dropna()
        if len(s):
            ax.hist(s * 100, bins=40, color="#1abc9c", edgecolor="white")
            ax.axvline(s.mean() * 100, color="#c0392b", ls="--", label=f"Mean {s.mean():.2%}")
        ax.set_title(col.replace("return_post_disclosure_", "Post-disclosure +") + "d")
        ax.set_xlabel("Return (%)")
        ax.legend()
    fig.suptitle("Post-Disclosure Returns (direction-adjusted)")
    return _save(fig, out_dir, "05_post_returns")


def plot_backtest_cum(bt: pd.DataFrame, out_dir: Path) -> Path:
    if bt.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No backtest data", ha="center", va="center")
        return _save(fig, out_dir, "06_backtest_cum")
    daily = bt.groupby("disclosure_date")["net_return"].mean().sort_index()
    cum = (1 + daily).cumprod() - 1
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(cum.index, cum.values * 100, marker="o", color="#2980b9")
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_title("Follow Strategy — Equal-Weight by Disclosure Date")
    ax.set_xlabel("Disclosure Date")
    ax.set_ylabel("Cumulative Return (%)")
    plt.xticks(rotation=45, ha="right")
    return _save(fig, out_dir, "06_backtest_cum")


def plot_event_study(es_df: pd.DataFrame, out_dir: Path) -> Path:
    if es_df.empty:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.text(0.5, 0.5, "No event study data", ha="center", va="center")
        return _save(fig, out_dir, "07_event_study")
    summary = es_df.groupby("event_window_day")["abnormal_return"].agg(["mean", "count"])
    fig, ax = plt.subplots(figsize=(7, 4))
    x = summary.index.astype(str)
    y = summary["mean"] * 100
    colors = ["#27ae60" if v >= 0 else "#c0392b" for v in y]
    ax.bar(x, y, color=colors)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_title("Event Study — Mean Abnormal Return by Window")
    ax.set_xlabel("Event Window (trading days)")
    ax.set_ylabel("AR (%)")
    for i, (xi, yi, n) in enumerate(zip(x, y, summary["count"])):
        ax.text(i, yi, f"n={int(n)}", ha="center", va="bottom" if yi >= 0 else "top", fontsize=8)
    return _save(fig, out_dir, "07_event_study")


def plot_disclosure_timeline(trades: pd.DataFrame, out_dir: Path, pelosi_df: pd.DataFrame | None = None) -> Path:
    df = _with_notional(trades, pelosi_df)
    df = df[df["action"].isin(["purchase", "sale"])].copy()
    df = df.dropna(subset=["disclosure_date"])

    by_disc = (
        df.groupby("disclosure_date")
        .agg(trades=("notional", "size"), notional=("notional", "sum"))
        .sort_index()
    )
    total_notional = df["notional"].sum()
    total_trades = len(df)

    x = np.arange(len(by_disc))
    labels = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in by_disc.index]

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax2 = ax1.twinx()
    bars = ax1.bar(x, by_disc["notional"], width=0.65, color="#8e44ad", alpha=0.9, label="Disclosed notional")
    ax2.plot(x, by_disc["trades"], color="#2c3e50", marker="D", lw=2, ms=6, label="Trade count")

    for i, (_, row) in enumerate(by_disc.iterrows()):
        ax1.text(
            i,
            row["notional"] + by_disc["notional"].max() * 0.02,
            _mpl_label(f"{_fmt_notional_short(row['notional'])}\n({int(row['trades']):,} trades)"),
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=30, ha="right")
    ax1.set_ylabel("Disclosed notional ($) — primary", fontweight="bold")
    ax2.set_ylabel("Trade count")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: _fmt_notional_short(v)))
    ax1.set_title(
        _mpl_label(
            f"Trades by House PTR Disclosure Date · Total {_fmt_notional_short(total_notional)} · {total_trades:,} trades"
        )
    )
    ax1.set_xlabel("Disclosure date")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=8)
    ax1.set_ylim(0, by_disc["notional"].max() * 1.22 if len(by_disc) else 1)
    return _save(fig, out_dir, "08_disclosure_timeline")


def plot_cumulative_pnl(cum_df: pd.DataFrame, title: str, out_dir: Path, prefix: str) -> Path:
    horizons = [1, 3, 5, 10, 20, 30]
    fig, ax = plt.subplots(figsize=(11, 5))
    colors = plt.cm.tab10(np.linspace(0, 1, len(horizons)))
    max_abs = 0.0
    series_data = []
    for h, c in zip(horizons, colors):
        col = f"cum_pnl_{h}d"
        if col not in cum_df.columns:
            continue
        sub = cum_df.dropna(subset=[col])
        if sub.empty:
            continue
        vals = sub[col].values
        max_abs = max(max_abs, float(np.nanmax(np.abs(vals))))
        series_data.append((h, c, sub, vals))
    scale, ylab = (1e6, "Cumulative PnL ($M)") if max_abs >= 5e5 else (1e3, "Cumulative PnL ($K)")
    if max_abs < 5e3:
        scale, ylab = (1.0, "Cumulative PnL ($)")
    for h, c, sub, vals in series_data:
        ax.plot(sub["date"], vals / scale, label=f"+{h}td", color=c, lw=1.8)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel(ylab)
    ax.legend(title="Horizon")
    plt.xticks(rotation=45, ha="right")
    return _save(fig, out_dir, prefix)


def plot_buy_sell_bars(
    buy_summary: pd.DataFrame,
    sell_summary: pd.DataFrame,
    title: str,
    out_dir: Path,
    prefix: str,
) -> Path:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    buy_summary = buy_summary.copy() if buy_summary is not None else pd.DataFrame()
    sell_summary = sell_summary.copy() if sell_summary is not None else pd.DataFrame()
    if buy_summary.empty and sell_summary.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        return _save(fig, out_dir, prefix)
    horizons = sorted(
        set(buy_summary.get("horizon_days", pd.Series(dtype=int)).tolist())
        | set(sell_summary.get("horizon_days", pd.Series(dtype=int)).tolist())
    )
    hz = pd.DataFrame({"horizon_days": horizons})
    buy_m = hz.merge(buy_summary, on="horizon_days", how="left") if not buy_summary.empty else hz.copy()
    sell_m = hz.merge(sell_summary, on="horizon_days", how="left") if not sell_summary.empty else hz.copy()
    for frame in (buy_m, sell_m):
        if "notional_weighted_return" not in frame.columns:
            frame["notional_weighted_return"] = 0.0
    labels = buy_m["horizon_days"].astype(str) + "d"
    x = np.arange(len(labels))
    w = 0.35
    buy_y = buy_m["notional_weighted_return"].fillna(0).values * 100
    sell_y = sell_m["notional_weighted_return"].fillna(0).values * 100
    ax.bar(x - w / 2, buy_y, w, label="BUY (long)", color="#27ae60")
    ax.bar(x + w / 2, sell_y, w, label="SELL (short)", color="#c0392b")
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title(title)
    ax.set_xlabel("Trading days after anchor")
    ax.set_ylabel("Notional-weighted return (%)")
    ax.legend()
    return _save(fig, out_dir, prefix)


def plot_follow_buy_sell_bars(
    buy_summary: pd.DataFrame,
    sell_summary: pd.DataFrame,
    out_dir: Path,
    prefix: str = "14_follow_buy_vs_sell",
) -> Path:
    return plot_buy_sell_bars(
        buy_summary,
        sell_summary,
        "Follow Pelosi — Buy vs Sell (notional-weighted, anchor = disclosure date)",
        out_dir,
        prefix,
    )


def plot_notional_weighted_bars(summary: pd.DataFrame, title: str, out_dir: Path, prefix: str) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4))
    x = summary["horizon_days"].astype(str) + "d"
    y = summary["notional_weighted_return"] * 100
    colors = ["#27ae60" if v >= 0 else "#c0392b" for v in y]
    ax.bar(x, y, color=colors)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_title(title)
    ax.set_xlabel("Trading days after anchor")
    ax.set_ylabel("Notional-weighted return (%)")
    return _save(fig, out_dir, prefix)


def plot_holding_days(matched_lots: pd.DataFrame, ticker_summary: pd.DataFrame, out_dir: Path) -> Path | None:
    if matched_lots.empty:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    hd = matched_lots["holding_days"].dropna()
    axes[0].hist(hd, bins=50, color="#e67e22", edgecolor="white")
    axes[0].axvline(hd.median(), color="#2c3e50", ls="--", label=f"Median {hd.median():.0f}d")
    axes[0].set_title("FIFO Holding Period (matched lots)")
    axes[0].set_xlabel("Days (sell − buy)")
    axes[0].legend()

    top = ticker_summary.nlargest(12, "n_matched_pairs").dropna(subset=["avg_holding_days"])
    if not top.empty:
        top.sort_values("avg_holding_days").plot(
            kind="barh", y="avg_holding_days", ax=axes[1], color="#16a085", legend=False
        )
        axes[1].set_title("Avg Holding Days by Ticker (top pairs)")
        axes[1].set_xlabel("Days")
    fig.suptitle("FIFO Lot-Matched Holding Periods")
    return _save(fig, out_dir, "09_holding_days")


def plot_media_match_timelines(timelines: list[dict], out_dir: Path) -> Path | None:
    """Swimlane: buy / news post / sell-or-hold for top matched tickers."""
    if not timelines:
        return None

    n = len(timelines)
    fig, axes = plt.subplots(n, 1, figsize=(14, 3.2 * n), squeeze=False)
    buy_c, sell_c, post_c, hold_c = "#2ecc71", "#e74c3c", "#3498db", "#ecf0f1"

    for ax, tl in zip(axes.flat, timelines):
        ticker = tl["ticker"]
        t0 = tl.get("first_buy")
        t1 = tl.get("hold_end")
        if t0 is None:
            ax.set_visible(False)
            continue
        t0 = pd.Timestamp(t0)
        t1 = pd.Timestamp(t1)
        ax.axhspan(0.35, 0.65, xmin=0, xmax=1, color=hold_c, alpha=0.5, zorder=0)
        if t1 > t0:
            ax.barh(0.5, (t1 - t0).days, left=0, height=0.18, color="#bdc3c7", alpha=0.6, zorder=1)

        def _x(d: pd.Timestamp) -> float:
            return (pd.Timestamp(d) - t0).days

        span = max((t1 - t0).days, 1)
        for b in tl.get("buys", []):
            x = _x(b["date"])
            ax.scatter(x, 0.72, marker="v", s=120, color=buy_c, zorder=3)
            ax.text(x, 0.78, _mpl_label(f"Buy {_fmt_notional_short(b['notional'])}"), ha="center", va="bottom", fontsize=8, fontweight="bold")

        for s in tl.get("sells", []):
            x = _x(s["date"])
            ax.scatter(x, 0.28, marker="^", s=120, color=sell_c, zorder=3)
            ax.text(x, 0.22, _mpl_label(f"Sell {_fmt_notional_short(s['notional'])}"), ha="center", va="top", fontsize=8, fontweight="bold")

        for i, p in enumerate(tl.get("posts", [])):
            x = _x(p["date"])
            y = 0.5 + (0.12 if i % 2 == 0 else -0.12)
            ax.scatter(x, y, marker="D", s=70, color=post_c, zorder=4)
            ax.annotate(
                "Truth",
                (x, y),
                textcoords="offset points",
                xytext=(0, 10 if i % 2 == 0 else -12),
                ha="center",
                fontsize=7,
                color=post_c,
            )

        end_label = "Open" if tl.get("still_open") else "Closed"
        ax.text(span * 0.98, 0.5, end_label, ha="right", va="center", fontsize=9, fontweight="bold", color="#2c3e50")

        ax.set_xlim(-2, span + 5)
        ax.set_ylim(0, 1)
        ax.set_yticks([])
        ax.set_xlabel("Days from first buy")
        ax.set_title(
            _mpl_label(f"{ticker} · max matched trade {_fmt_notional_short(tl.get('max_trade_notional', 0))} · {end_label}"),
            fontsize=11,
            loc="left",
        )
        ax.grid(axis="x", alpha=0.3)

    fig.suptitle("Top 3 Matched Tickers — Buy / News / Sell or Hold", fontsize=12, y=1.01)
    fig.subplots_adjust(hspace=0.55)
    return _save(fig, out_dir, "16_media_match_timelines")


def plot_open_holdings_snapshot(holdings: pd.DataFrame, out_dir: Path) -> Path | None:
    """Net-long open holdings: notional bars + horizon return heatmap-style table."""
    if holdings.empty:
        return None

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), gridspec_kw={"width_ratios": [1.1, 1.4]})
    df = holdings.sort_values("net_notional", ascending=True)

    axes[0].barh(df["ticker"], df["net_notional"] / 1e6, color="#8e44ad", alpha=0.9)
    axes[0].set_xlabel("Net notional ($M)")
    axes[0].set_title("Open Holdings Top 10 (FIFO unmatched buys)")
    for i, (_, r) in enumerate(df.iterrows()):
        axes[0].text(r["net_notional"] / 1e6 + 0.02, i, f"${r['net_notional']/1e6:.2f}M", va="center", fontsize=8)

    horizons = [1, 3, 5, 10, 20, 30]
    ret_cols = [f"ret_{h}d" for h in horizons if f"ret_{h}d" in df.columns]
    if ret_cols:
        mat = df.set_index("ticker")[ret_cols].astype(float) * 100
        mat.columns = [c.replace("ret_", "+").replace("d", "d") for c in mat.columns]
        im = axes[1].imshow(mat.values, aspect="auto", cmap="RdYlGn", vmin=-5, vmax=5)
        axes[1].set_xticks(range(len(mat.columns)))
        axes[1].set_xticklabels(mat.columns, rotation=45, ha="right")
        axes[1].set_yticks(range(len(mat.index)))
        axes[1].set_yticklabels(mat.index)
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                v = mat.iloc[i, j]
                if pd.notna(v):
                    axes[1].text(j, i, f"{v:.1f}%", ha="center", va="center", fontsize=8, color="#222")
        axes[1].set_title("Return since earliest open buy (txn anchor)")
        fig.colorbar(im, ax=axes[1], fraction=0.046, label="Return %")
    else:
        axes[1].axis("off")

    fig.suptitle("Pelosi Current Net-Long Portfolio Snapshot", fontsize=12)
    return _save(fig, out_dir, "17_open_holdings")


def plot_portfolio_daily_timeseries(
    daily: pd.DataFrame,
    out_dir: Path,
    prefix: str = "18_portfolio_timeseries",
    title_suffix: str = "",
) -> Path | None:
    """Gross-long FIFO portfolio: MTM exposure and cumulative PnL over time."""
    if daily.empty:
        return None

    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw={"height_ratios": [1.1, 1]})

    ax0 = axes[0]
    cost_m = df["position_cost"] / 1e6
    mtm_m = df["position_mtm"] / 1e6
    ax0.fill_between(df["date"], 0, mtm_m, alpha=0.18, color="#8e44ad")
    ax0.plot(df["date"], mtm_m, color="#8e44ad", lw=2.0, label="MTM value")
    ax0.plot(df["date"], cost_m, color="#566573", lw=1.4, ls="--", label="Cost basis")
    if "position_mtm_stock" in df.columns and "position_mtm_option" in df.columns:
        ax0.plot(
            df["date"],
            df["position_mtm_stock"] / 1e6,
            color="#3498db",
            lw=1.2,
            alpha=0.85,
            label="MTM stock lots",
        )
        ax0.plot(
            df["date"],
            df["position_mtm_option"] / 1e6,
            color="#e67e22",
            lw=1.2,
            alpha=0.85,
            label="MTM option/exercise lots",
        )
    ax0.set_ylabel("Position size ($M)")
    ax0.set_title(f"Gross-long portfolio size (FIFO, EOD){title_suffix}")
    ax0.legend(loc="upper left", fontsize=9)
    ax0.grid(True, alpha=0.3)

    ax1 = axes[1]
    pnl = df["cum_pnl"]
    scale = 1e6 if pnl.abs().max() >= 5e5 else 1e3
    ylab = "Cumulative PnL ($M)" if scale == 1e6 else "Cumulative PnL ($K)"
    ax1.plot(df["date"], pnl / scale, color="#1e4d8c", lw=2.0, label="Cumulative PnL")
    ax1.fill_between(
        df["date"],
        0,
        pnl / scale,
        where=pnl >= 0,
        alpha=0.15,
        color="#2ecc71",
        interpolate=True,
    )
    ax1.fill_between(
        df["date"],
        0,
        pnl / scale,
        where=pnl < 0,
        alpha=0.15,
        color="#e74c3c",
        interpolate=True,
    )
    ax1.axhline(0, color="gray", lw=0.8)
    ax1.set_ylabel(ylab)
    ax1.set_xlabel("Date")
    ax1.set_title("Portfolio cumulative PnL (sum of daily MTM changes)")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)

    for ax in axes:
        for label in ax.get_xticklabels():
            label.set_rotation(45)
            label.set_ha("right")

    main_title = "Portfolio — Position Size & Cumulative PnL" + title_suffix
    fig.suptitle(main_title, fontsize=12, y=1.01)
    fig.tight_layout()
    return _save(fig, out_dir, prefix)


def _remove_legacy_trump_charts(out_dir: Path) -> None:
    """Delete leftover Trump_following PNG filenames so reports do not embed them."""
    if not out_dir.exists():
        return
    for path in out_dir.glob("*trump*.png"):
        try:
            path.unlink()
        except OSError:
            pass


def _timing_returns(return_analysis: dict | None) -> pd.DataFrame | None:
    if not return_analysis:
        return None
    if "pelosi_timing" in return_analysis:
        return return_analysis["pelosi_timing"]
    return return_analysis.get("trump_timing")


def _timing_summary(return_analysis: dict | None, key_legacy: str, key_pelosi: str | None = None) -> pd.DataFrame:
    if not return_analysis:
        return pd.DataFrame()
    k = key_pelosi or key_legacy.replace("trump_", "pelosi_")
    for key in (k, key_legacy):
        val = return_analysis.get(key)
        if val is not None and not (isinstance(val, pd.DataFrame) and val.empty):
            return val if isinstance(val, pd.DataFrame) else pd.DataFrame()
    return pd.DataFrame()


def generate_all_charts(
    trades: pd.DataFrame,
    returns_df: pd.DataFrame,
    bt: pd.DataFrame,
    es_df: pd.DataFrame,
    out_dir: Path,
    matched_lots: pd.DataFrame | None = None,
    ticker_summary: pd.DataFrame | None = None,
    return_analysis: dict | None = None,
    media_timelines: list | None = None,
    open_holdings: pd.DataFrame | None = None,
    portfolio_daily: pd.DataFrame | None = None,
    options_trades: pd.DataFrame | None = None,
    option_return_analysis: dict | None = None,
    combined_return_analysis: dict | None = None,
    unified_portfolio_daily: pd.DataFrame | None = None,
    price_cache: dict[str, pd.DataFrame] | None = None,
) -> list[Path]:
    _remove_legacy_trump_charts(out_dir)
    pelosi_df = _timing_returns(return_analysis)
    if options_trades is not None and not options_trades.empty:
        buy_sell_chart = plot_combined_buy_sell(
            trades, options_trades, out_dir, price_cache=price_cache
        )
    else:
        buy_sell_chart = plot_buy_sell(trades, out_dir)
    paths = [
        plot_trade_volume_monthly(trades, out_dir, pelosi_df=pelosi_df),
        plot_reveal_lag(returns_df, out_dir),
        plot_top_tickers(trades, out_dir, returns_df=pelosi_df),
        buy_sell_chart,
    ]
    if open_holdings is not None and not open_holdings.empty:
        oh = plot_open_holdings_snapshot(open_holdings, out_dir)
        if oh:
            paths.append(oh)
    if portfolio_daily is not None and not portfolio_daily.empty:
        pt = plot_portfolio_daily_timeseries(portfolio_daily, out_dir)
        if pt:
            paths.append(pt)
    if unified_portfolio_daily is not None and not unified_portfolio_daily.empty:
        up = plot_portfolio_daily_timeseries(
            unified_portfolio_daily,
            out_dir,
            prefix="19_unified_portfolio_timeseries",
            title_suffix=" · stock+options FIFO",
        )
        if up:
            paths.append(up)
    paths += [
        plot_post_returns(returns_df, out_dir),
        plot_backtest_cum(bt, out_dir),
        plot_event_study(es_df, out_dir),
        plot_disclosure_timeline(trades, out_dir, pelosi_df=pelosi_df),
    ]
    if media_timelines:
        mt = plot_media_match_timelines(media_timelines, out_dir)
        if mt:
            paths.append(mt)
    if matched_lots is not None and ticker_summary is not None:
        h = plot_holding_days(matched_lots, ticker_summary, out_dir)
        if h:
            paths.append(h)
    if return_analysis:
        paths.append(
            plot_notional_weighted_bars(
                _timing_summary(return_analysis, "trump_summary", "pelosi_summary"),
                "Pelosi Timing — Notional-Weighted Return (by txn date)",
                out_dir,
                "10_pelosi_notional_returns",
            )
        )
        buy_s = _timing_summary(return_analysis, "trump_buy_summary", "pelosi_buy_summary")
        sell_s = _timing_summary(return_analysis, "trump_sell_summary", "pelosi_sell_summary")
        if not buy_s.empty or not sell_s.empty:
            paths.append(
                plot_buy_sell_bars(
                    buy_s,
                    sell_s,
                    "Pelosi Timing — Buy vs Sell (anchor = transaction date)",
                    out_dir,
                    "15_pelosi_buy_vs_sell",
                )
            )
        paths.append(
            plot_notional_weighted_bars(
                return_analysis["follow_summary"],
                "Follow Pelosi — Notional-Weighted Return (by disclosure date)",
                out_dir,
                "11_follow_notional_returns",
            )
        )
        paths.append(
            plot_cumulative_pnl(
                return_analysis.get("pelosi_cumulative", return_analysis.get("trump_cumulative")),
                "Pelosi Timing — Cumulative PnL (anchor = transaction date)",
                out_dir,
                "12_pelosi_cumulative_pnl",
            )
        )
        paths.append(
            plot_cumulative_pnl(
                return_analysis["follow_cumulative"],
                "Follow Pelosi — Cumulative PnL (anchor = disclosure date)",
                out_dir,
                "13_follow_cumulative_pnl",
            )
        )
        if "follow_buy_summary" in return_analysis and "follow_sell_summary" in return_analysis:
            if not return_analysis["follow_buy_summary"].empty or not return_analysis["follow_sell_summary"].empty:
                paths.append(
                    plot_follow_buy_sell_bars(
                        return_analysis["follow_buy_summary"],
                        return_analysis["follow_sell_summary"],
                        out_dir,
                    )
                )
    if combined_return_analysis:
        cs = combined_return_analysis.get("combined_summary") or {}
        paths.append(
            plot_notional_weighted_bars(
                pd.DataFrame(cs.get("timing_all") or []),
                "Combined Stock+Options — NW Return (txn date; options ×100 sh)",
                out_dir,
                "14_combined_timing_returns",
            )
        )
        paths.append(
            plot_combined_cumulative_pnl(
                combined_return_analysis.get("combined_cumulative"),
                combined_return_analysis.get("combined_cumulative_stock"),
                combined_return_analysis.get("combined_cumulative_option"),
                out_dir,
            )
        )
    return paths


def generate_option_charts(
    options: pd.DataFrame,
    return_analysis: dict,
    out_dir: Path,
    matched_lots: pd.DataFrame | None = None,
    ticker_summary: pd.DataFrame | None = None,
) -> list[Path]:
    """Charts for PTR options (underlying-price horizon returns)."""
    timing_df = _timing_returns(return_analysis)
    chart_opts = options.copy()
    chart_opts.loc[chart_opts["action"] == "exercise", "action"] = "purchase"
    paths: list[Path] = [
        plot_top_tickers(chart_opts, out_dir, returns_df=timing_df),
        plot_disclosure_timeline(chart_opts, out_dir, pelosi_df=timing_df),
    ]
    if matched_lots is not None and ticker_summary is not None and not matched_lots.empty:
        h = plot_holding_days(matched_lots, ticker_summary, out_dir)
        if h and h.exists():
            dest = out_dir / "opt_09_holding_days.png"
            dest.write_bytes(h.read_bytes())
            paths.append(dest)
    if return_analysis:
        paths.append(
            plot_notional_weighted_bars(
                _timing_summary(return_analysis, "trump_summary"),
                "Options — NW Return on Underlying (txn date)",
                out_dir,
                "opt_10_timing_returns",
            )
        )
        opt_buy = _timing_summary(return_analysis, "trump_buy_summary")
        opt_sell = _timing_summary(return_analysis, "trump_sell_summary")
        if not opt_buy.empty or not opt_sell.empty:
            paths.append(
                plot_buy_sell_bars(
                    opt_buy,
                    opt_sell,
                    "Options — Buy vs Sell (underlying, txn date)",
                    out_dir,
                    "opt_15_buy_vs_sell",
                )
            )
        paths.append(
            plot_cumulative_pnl(
                return_analysis.get("pelosi_cumulative", return_analysis.get("trump_cumulative")),
                "Options — Cumulative PnL (underlying, txn date)",
                out_dir,
                "opt_12_cumulative_pnl",
            )
        )
        paths.append(
            plot_notional_weighted_bars(
                return_analysis["follow_summary"],
                "Options — NW Return on Underlying (disclosure date)",
                out_dir,
                "opt_11_follow_returns",
            )
        )
    # Rename outputs that used wrong save - fix holding_days
    return [p for p in paths if p is not None]
