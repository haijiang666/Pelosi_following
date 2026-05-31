#!/usr/bin/env python3
"""Pelosi stock trade analysis pipeline (House STOCK Act PTR)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.backtest import (
    backtest_follow_strategy,
    backtest_metrics,
    compute_returns,
    event_study,
    summarize_event_study,
)
from src.disclosures import load_settings, project_root
from src.house_disclosures import cross_check_manifest, enrich_ptr_manifest, fetch_ptr_disclosures
from src.ptr_options import (
    fifo_match_options,
    filter_options_tradable,
    parse_all_ptr_options,
    parse_option_stats,
    save_options,
)
from src.ptr_trades import filter_trades_with_ticker, parse_all_ptr_filings, parse_stats_all, save_trades
from src.ticker_resolver import enrich_trades_with_tickers
from src.prices import fetch_prices_for_trades
from src.holdings import attach_holding_to_trades, fifo_match_trades, holding_summary_stats
from src.combined_analysis import run_combined_analyses
from src.trade_returns import run_both_analyses
from src.portfolio_snapshot import (
    compute_open_holdings_top_n,
    compute_portfolio_daily_timeseries,
    open_holdings_summary_records,
    portfolio_daily_summary_records,
)
from src.unified_portfolio import (
    compute_unified_portfolio_daily,
    fifo_match_unified,
    unified_portfolio_summary,
)
from src.visualizations import generate_all_charts


def web_cross_check_samples(trades: pd.DataFrame) -> list[dict]:
    """Known Pelosi PTR trades from press / Capitol Trades cross-check."""
    expected = [
        {"ticker": "AVGO", "action": "sale", "date": "2025-06-20", "source": "July 2025 PTR (Matthews fund + AVGO)"},
        {"ticker": "NVDA", "action": "purchase", "date": "2024-07-26", "source": "July 2024 PTR"},
        {"ticker": "AAPL", "action": "purchase", "date": "2023-03-17", "source": "March 2023 PTR"},
    ]
    results = []
    t = trades.copy()
    t["transaction_date"] = pd.to_datetime(t["transaction_date"])
    for exp in expected:
        mask = t["ticker"] == exp["ticker"]
        mask &= t["action"] == exp["action"]
        if "date" in exp:
            mask &= t["transaction_date"] == pd.Timestamp(exp["date"])
        if "amount_min" in exp:
            mask &= t["amount_min"] >= exp["amount_min"]
        matched = t[mask]
        results.append(
            {
                **exp,
                "found_in_parse": len(matched) > 0,
                "match_count": len(matched),
                "sample_asset": matched["asset_name"].iloc[0] if len(matched) else None,
            }
        )
    return results


def main() -> int:
    settings = load_settings()
    proc = project_root() / settings["paths"]["processed"]
    reports = project_root() / "reports"
    figures = reports / "figures"
    reports.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)

    print("=" * 60)
    print("STEP 1: Download Pelosi House PTR filings")
    manifest = fetch_ptr_disclosures(settings)
    manifest = enrich_ptr_manifest(manifest, settings)
    ok = manifest[manifest["status"].astype(str).str.startswith("ok")]
    print(ok[["doc_id", "status", "pages", "filing_date", "disclosure_date"]].to_string())

    print("\nSTEP 2: Cross-check — House STOCK Act PTR?")
    xcheck = cross_check_manifest(manifest)
    print(json.dumps({k: v for k, v in xcheck.items() if k != "documents"}, indent=2, default=str))
    (reports / "cross_check_manifest.json").write_text(json.dumps(xcheck, indent=2, default=str))

    print("\nSTEP 3: Parse stock/ETF trades from PTR PDFs")
    pstats = parse_stats_all(ok, settings)
    print(f"  Filings: {pstats['n_filings']}, PDF rows: {pstats['table_rows_in_pdf']}")
    print(f"  Parsed trades: {pstats['parsed_trades']}")
    trades = parse_all_ptr_filings(ok, settings)
    trades = enrich_trades_with_tickers(trades)
    print(f"  Parsed: {len(trades)} rows, tickers: {trades['ticker'].notna().sum()}")
    save_trades(trades, settings)
    trades.to_csv(reports / "trades_raw.csv", index=False)

    print("\nSTEP 4: Web cross-check (sample trades)")
    samples = web_cross_check_samples(trades)
    for s in samples:
        status = "OK" if s["found_in_parse"] else "MISSING"
        print(f"  [{status}] {s.get('ticker')} {s.get('action')} {s.get('date', '')}")
    (reports / "web_cross_check.json").write_text(json.dumps(samples, indent=2))

    tradable = filter_trades_with_ticker(trades)
    if tradable.empty:
        print("No tradable rows — check PTR parser.")
        return 1

    print("\nSTEP 5: FIFO holding periods")
    matched_lots, holdings_by_ticker, trade_holding, all_lots = fifo_match_trades(tradable)
    hstats = holding_summary_stats(matched_lots)
    print(f"  Matched pairs: {hstats.get('n_matched_pairs', 0)}, median hold {hstats.get('median_holding_days', 0):.0f}d")
    matched_lots.to_csv(reports / "matched_lots.csv", index=False)
    all_lots.to_csv(reports / "all_lots.csv", index=False)
    holdings_by_ticker.to_csv(reports / "holdings_by_ticker.csv", index=False)

    print(f"\nSTEP 6: Prices ({tradable['ticker'].nunique()} tickers)")
    price_cache = fetch_prices_for_trades(tradable, settings)

    print("\nSTEP 7: Horizon returns (txn timing vs follow disclosure)")
    ret_analysis = run_both_analyses(tradable, price_cache, matched_lots=all_lots, settings=settings)
    ret_analysis["trump_timing"].to_parquet(proc / "pelosi_timing_returns.parquet", index=False)
    ret_analysis["follow_disclosure"].to_parquet(proc / "follow_disclosure_returns.parquet", index=False)
    ret_analysis["trump_summary"].to_csv(reports / "pelosi_timing_summary.csv", index=False)
    ret_analysis["trump_buy_summary"].to_csv(reports / "pelosi_timing_buy_summary.csv", index=False)
    ret_analysis["trump_sell_summary"].to_csv(reports / "pelosi_timing_sell_summary.csv", index=False)
    ret_analysis["trump_cumulative"].to_csv(reports / "pelosi_cumulative_pnl.csv", index=False)
    ret_analysis["follow_summary"].to_csv(reports / "follow_disclosure_summary.csv", index=False)
    ret_analysis["follow_buy_summary"].to_csv(reports / "follow_disclosure_buy_summary.csv", index=False)
    ret_analysis["follow_sell_summary"].to_csv(reports / "follow_disclosure_sell_summary.csv", index=False)
    ret_analysis["follow_cumulative"].to_csv(reports / "follow_cumulative_pnl.csv", index=False)
    ret_analysis["follow_buy_cumulative"].to_csv(reports / "follow_buy_cumulative_pnl.csv", index=False)
    ret_analysis["follow_sell_cumulative"].to_csv(reports / "follow_sell_cumulative_pnl.csv", index=False)
    if not ret_analysis["realized_lots"].empty:
        ret_analysis["realized_lots"].to_csv(reports / "realized_fifo_lots.csv", index=False)
    print(ret_analysis["trump_summary"][["horizon_days", "notional_weighted_return", "n_trades"]].to_string(index=False))

    options_analysis: dict = {}
    opt_tradable = pd.DataFrame()
    opt_ret = None
    opt_matched = pd.DataFrame()
    opt_holdings = pd.DataFrame()
    opt_price_cache: dict = {}
    combined_ret: dict = {}
    print("\nSTEP 7b: Parse options ([OP] / call & put) from PTR")
    ostats = parse_option_stats(ok, settings)
    print(f"  Option rows parsed: {ostats['parsed_options']}, with amount: {ostats['parsed_with_amount']}")
    options = parse_all_ptr_options(ok, settings)
    save_options(options, settings)
    options.to_csv(reports / "options_raw.csv", index=False)
    opt_tradable = filter_options_tradable(options)
    print(f"  Tradable options: {len(opt_tradable)} ({opt_tradable['ticker'].nunique()} underlyings)")

    if not opt_tradable.empty:
        print("\nSTEP 7c: Options FIFO + prices (underlying)")
        opt_matched, opt_holdings, opt_trade_holding, opt_all_lots = fifo_match_options(opt_tradable)
        opt_matched.to_csv(reports / "options_matched_lots.csv", index=False)
        opt_all_lots.to_csv(reports / "options_all_lots.csv", index=False)
        opt_price_cache = fetch_prices_for_trades(opt_tradable, settings)
        print("\nSTEP 7d: Options horizon returns (underlying; purchase/exercise +1, sale −1)")
        opt_ret = run_both_analyses(opt_tradable, opt_price_cache, matched_lots=opt_all_lots, settings=settings)
        opt_ret["trump_timing"].to_parquet(proc / "options_timing_returns.parquet", index=False)
        opt_ret["follow_disclosure"].to_parquet(proc / "options_follow_returns.parquet", index=False)
        opt_ret["trump_summary"].to_csv(reports / "options_timing_summary.csv", index=False)
        opt_ret["trump_buy_summary"].to_csv(reports / "options_timing_buy_summary.csv", index=False)
        opt_ret["trump_sell_summary"].to_csv(reports / "options_timing_sell_summary.csv", index=False)
        opt_ret["trump_cumulative"].to_csv(reports / "options_cumulative_pnl.csv", index=False)
        opt_ret["follow_summary"].to_csv(reports / "options_follow_summary.csv", index=False)
        if not opt_ret["realized_lots"].empty:
            opt_ret["realized_lots"].to_csv(reports / "options_realized_fifo_lots.csv", index=False)
        print(opt_ret["trump_summary"][["horizon_days", "notional_weighted_return", "n_trades"]].to_string(index=False))
        options_analysis = {
            "stats": ostats,
            "n_tradable": len(opt_tradable),
            "n_underlyings": int(opt_tradable["ticker"].nunique()),
            "holding_stats": holding_summary_stats(opt_matched),
            "return_analysis": {
                "timing": opt_ret["trump_summary"].to_dict(orient="records"),
                "timing_buy": opt_ret["trump_buy_summary"].to_dict(orient="records"),
                "timing_sell": opt_ret["trump_sell_summary"].to_dict(orient="records"),
                "follow": opt_ret["follow_summary"].to_dict(orient="records"),
                "realized_fifo": opt_ret.get("realized_summary") or {},
            },
            "pnl_method_note": (
                "Options: horizon PnL uses underlying stock price; purchase/exercise sign=+1, sale sign=−1. "
                "Not option contract mark-to-market."
            ),
        }
    else:
        options_analysis = {"stats": ostats, "n_tradable": 0}

    print("\nSTEP 7e: Combined stock + option PnL (options = 100 shares/contract on underlying)")
    merged_prices = dict(price_cache)
    merged_prices.update(opt_price_cache)
    combined_ret = run_combined_analyses(
        tradable,
        opt_tradable if not opt_tradable.empty else None,
        merged_prices,
        settings=settings,
    )
    if combined_ret.get("combined_timing") is not None and not combined_ret["combined_timing"].empty:
        combined_ret["combined_timing"].to_parquet(proc / "combined_timing_returns.parquet", index=False)
        combined_ret["combined_follow"].to_parquet(proc / "combined_follow_returns.parquet", index=False)
        pd.DataFrame(combined_ret["combined_summary"]["timing_all"]).to_csv(
            reports / "combined_timing_summary.csv", index=False
        )
        pd.DataFrame(combined_ret["combined_summary"]["timing_stock"]).to_csv(
            reports / "combined_timing_stock_summary.csv", index=False
        )
        pd.DataFrame(combined_ret["combined_summary"]["timing_option"]).to_csv(
            reports / "combined_timing_option_summary.csv", index=False
        )
        combined_ret["combined_cumulative"].to_csv(reports / "combined_cumulative_pnl.csv", index=False)
        print(
            pd.DataFrame(combined_ret["combined_summary"]["timing_all"])[
                ["horizon_days", "notional_weighted_return", "n_trades"]
            ].to_string(index=False)
        )

    print("\nSTEP 8: Returns + reveal lag")
    returns_df = compute_returns(tradable, price_cache, settings)
    returns_df = attach_holding_to_trades(returns_df, trade_holding)
    returns_df.to_parquet(proc / "returns.parquet", index=False)
    returns_df.to_csv(reports / "trades_analysis.csv", index=False)
    print(f"  {len(returns_df)} trades, median reveal lag {returns_df['reveal_lag_days'].median():.0f}d")

    print("\nSTEP 9: Event study")
    es = event_study(returns_df, settings=settings)
    print(summarize_event_study(es))
    es.to_parquet(proc / "event_study.parquet", index=False)

    print("\nSTEP 10: Backtest")
    bt = backtest_follow_strategy(returns_df, settings)
    metrics = backtest_metrics(bt)
    print(metrics)
    bt.to_parquet(proc / "backtest.parquet", index=False)

    pelosi_for_rank = ret_analysis["trump_timing"].merge(
        returns_df[["trade_id", "return_post_disclosure_1d", "return_post_disclosure_5d"]],
        on="trade_id",
        how="left",
    )
    by_ticker = (
        pelosi_for_rank.drop_duplicates(subset=["trade_id"])
        .groupby("ticker")
        .agg(
            trades=("trade_id", "count"),
            buys=("action", lambda x: (x == "purchase").sum()),
            sales=("action", lambda x: (x == "sale").sum()),
            total_notional=("notional", "sum"),
            avg_post_5d=("return_post_disclosure_5d", "mean"),
            avg_post_1d=("return_post_disclosure_1d", "mean"),
        )
        .sort_values("total_notional", ascending=False)
    )
    by_ticker.to_csv(reports / "summary_by_ticker.csv")

    has_notional = tradable["amount_min"].notna() & (tradable["amount_min"] > 0)
    tradable_with_notional = int(has_notional.sum())

    disc_dates = sorted(trades["disclosure_date"].dropna().astype(str).unique().tolist())
    summary = {
        "person": settings["person"]["name"],
        "source": "House STOCK Act PTR",
        "total_rows_parsed": len(trades),
        "tradable_with_ticker": len(tradable),
        "tradable_with_notional": tradable_with_notional,
        "tradable_missing_amount": int(len(tradable) - tradable_with_notional),
        "unique_tickers": int(tradable["ticker"].nunique()),
        "date_range": [str(trades["transaction_date"].min().date()), str(trades["transaction_date"].max().date())],
        "disclosure_dates": disc_dates,
        "n_filings": int(pstats["n_filings"]),
        "median_reveal_lag_days": float(returns_df["reveal_lag_days"].median()) if len(returns_df) else None,
        "holding_stats": hstats,
        "web_cross_check": samples,
        "backtest_metrics": metrics,
        "return_analysis": {
            "pelosi_timing": ret_analysis["trump_summary"].to_dict(orient="records"),
            "pelosi_timing_buy": ret_analysis["trump_buy_summary"].to_dict(orient="records"),
            "pelosi_timing_sell": ret_analysis["trump_sell_summary"].to_dict(orient="records"),
            "follow_disclosure": ret_analysis["follow_summary"].to_dict(orient="records"),
            "follow_disclosure_buy": ret_analysis["follow_buy_summary"].to_dict(orient="records"),
            "follow_disclosure_sell": ret_analysis["follow_sell_summary"].to_dict(orient="records"),
            "pnl_method_note": "Horizon PnL: purchase sign=+1, sale sign=-1 (disclosure-direction follow); see FIFO for matched long lots.",
            "realized_fifo": ret_analysis.get("realized_summary") or {},
        },
        "parse_rate_vs_table": pstats.get("parse_rate_vs_table"),
        "amount_coverage_rate": pstats.get("amount_coverage_rate"),
        "parsed_with_amount": pstats.get("parsed_with_amount"),
        "per_document_stats": pstats.get("per_document", []),
        "options_analysis": options_analysis,
        "combined_analysis": {
            "option_shares_per_contract": combined_ret.get("option_shares_per_contract", 100),
            "pnl_method_note": (
                "Combined book: stock notional = PTR amount_min; "
                "option notional = n_contracts × 100 × underlying anchor price "
                "(fallback amount_min). Horizon return on underlying; buy/exercise +1, sale −1."
            ),
            "return_analysis": combined_ret.get("combined_summary") or {},
            "n_timing_trades": int(len(combined_ret["combined_timing"]))
            if combined_ret.get("combined_timing") is not None
            else 0,
            "n_timing_stock": int((combined_ret["combined_timing"]["instrument"] == "stock").sum())
            if combined_ret.get("combined_timing") is not None and not combined_ret["combined_timing"].empty
            else 0,
            "n_timing_option": int((combined_ret["combined_timing"]["instrument"] == "option").sum())
            if combined_ret.get("combined_timing") is not None and not combined_ret["combined_timing"].empty
            else 0,
        },
    }

    print("\nSTEP 11: Visualizations")
    open_holdings = compute_open_holdings_top_n(ret_analysis["trump_timing"], all_lots, top_n=10)
    open_holdings.to_csv(reports / "open_holdings_top10.csv", index=False)
    summary["open_holdings"] = open_holdings_summary_records(open_holdings)
    portfolio_daily = compute_portfolio_daily_timeseries(tradable, price_cache, settings)
    portfolio_daily.to_csv(reports / "portfolio_daily.csv", index=False)
    summary["portfolio_daily"] = portfolio_daily_summary_records(portfolio_daily)

    print("\nSTEP 11b: Unified portfolio FIFO (stock + options on underlying)")
    unified_matched, unified_by_ticker, _, unified_all_lots = fifo_match_unified(
        tradable, opt_tradable if not opt_tradable.empty else None, merged_prices
    )
    unified_daily = compute_unified_portfolio_daily(
        tradable, opt_tradable if not opt_tradable.empty else None, merged_prices, settings
    )
    unified_matched.to_csv(reports / "unified_matched_lots.csv", index=False)
    unified_all_lots.to_csv(reports / "unified_all_lots.csv", index=False)
    unified_by_ticker.to_csv(reports / "unified_holdings_by_ticker.csv", index=False)
    if not unified_daily.empty:
        unified_daily.to_csv(reports / "unified_portfolio_daily.csv", index=False)
    summary["unified_portfolio"] = unified_portfolio_summary(
        unified_matched, unified_daily, unified_all_lots
    )
    ufifo = summary["unified_portfolio"].get("fifo") or {}
    print(
        f"  Matched pairs: {ufifo.get('n_matched_pairs', 0)} "
        f"(from option/exercise: {ufifo.get('n_matched_from_option', 0)}), "
        f"prior_position sells: {ufifo.get('n_prior_sells', 0)}"
    )
    (reports / "final_summary.json").write_text(json.dumps(summary, indent=2, default=str))

    # ret_analysis keys still named trump_* internally — charts use same structure
    chart_paths = generate_all_charts(
        trades,
        returns_df,
        bt,
        es,
        figures,
        matched_lots,
        holdings_by_ticker,
        ret_analysis,
        open_holdings=open_holdings,
        portfolio_daily=portfolio_daily,
        options_trades=opt_tradable if not opt_tradable.empty else None,
        option_return_analysis=opt_ret,
        combined_return_analysis=combined_ret if combined_ret else None,
        unified_portfolio_daily=unified_daily if not unified_daily.empty else None,
    )
    if opt_ret is not None and not opt_tradable.empty:
        from src.visualizations import generate_option_charts

        opt_charts = generate_option_charts(
            opt_tradable,
            opt_ret,
            figures,
            opt_matched,
            opt_holdings,
        )
        chart_paths.extend(opt_charts)
    for p in chart_paths:
        print(f"  {p.name}")

    print("\nSTEP 12: Generate report")
    import subprocess

    subprocess.run([sys.executable, str(ROOT / "scripts/generate_report.py")], check=True)
    print("\nDone → reports/FINAL_REPORT.md + reports/FINAL_REPORT.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
