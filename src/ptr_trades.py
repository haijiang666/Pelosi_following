"""Parse Nancy Pelosi House STOCK Act Periodic Transaction Report (PTR) PDFs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber

from .disclosures import load_settings, project_root
from .equity_trades import infer_ticker, is_bond_description, parse_amount_range

# House PTR transaction type codes
_PTR_ACTION = {
    "P": "purchase",
    "S": "sale",
    "E": "exchange",
    "S (partial)": "sale",
    "S (Full)": "sale",
}

_TICKER_RE = re.compile(r"\(([A-Z]{1,5}(?:-[A-Z])?)\)")
_AMOUNT_RE = re.compile(r"\$[\d,]+(?:\.\d+)?(?:\s*-\s*\$[\d,]+(?:\.\d+)?)?")
_DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")


def _analysis_window(settings: dict[str, Any]) -> tuple[pd.Timestamp, pd.Timestamp]:
    house = settings.get("house", {})
    lo = pd.Timestamp(house.get("analysis_start_date", "2023-01-01"))
    hi = pd.Timestamp(house.get("analysis_end_date", "2026-12-31"))
    return lo, hi


def _normalize_ptr_text(text: str) -> str:
    return text.replace("\x00", "").replace("  ", " ")


def _is_garbage_asset(asset_name: str) -> bool:
    """Drop OCR rows that captured PTR header/footer instead of a real asset."""
    u = (asset_name or "").upper()
    if "FILING ID #" in u or "CLERK OF THE HOUSE" in u:
        return True
    if u.strip() in {"P T R", "PTR"}:
        return True
    return False


def _classify_asset_class(desc: str, ticker: str | None, inferred: str) -> str:
    if inferred.startswith("bond"):
        return "bond"
    if not ticker:
        return inferred.replace("_unmapped", "") if inferred else "other"
    upper = (desc or "").upper()
    if "ETF" in upper or "MUTUAL FUND" in upper:
        return "etf"
    if inferred in ("equity", "etf", "reit"):
        return inferred
    return "equity"


def _backfill_missing_amounts(df: pd.DataFrame) -> pd.DataFrame:
    """Copy amount brackets from full-description rows to ticker-only OCR duplicates."""
    if df.empty or "amount_min" not in df.columns:
        return df
    out = df.copy()
    for doc_id, grp in out.groupby("doc_id"):
        has_amt = grp[grp["amount_min"].notna() & (grp["amount_min"] > 0)]
        if has_amt.empty:
            continue
        missing = grp[grp["amount_min"].isna() | (grp["amount_min"] <= 0)]
        for idx in missing.index:
            row = out.loc[idx]
            if not row.get("ticker"):
                continue
            ticker, action, txn = row["ticker"], row["action"], row["transaction_date"]
            match = has_amt[
                (has_amt["ticker"] == ticker)
                & (has_amt["action"] == action)
                & (has_amt["transaction_date"] == txn)
            ]
            if match.empty:
                match = has_amt[(has_amt["ticker"] == ticker) & (has_amt["action"] == action)]
            if match.empty:
                continue
            best = match.sort_values("amount_min", ascending=False).iloc[0]
            out.at[idx, "amount_min"] = best["amount_min"]
            out.at[idx, "amount_max"] = best["amount_max"]
            if len(str(row.get("asset_name", ""))) <= 8:
                out.at[idx, "asset_name"] = best["asset_name"]
    return out


def _parse_table_rows(page) -> list[dict[str, Any]]:
    """Parse structured PTR table when pdfplumber extracts columns cleanly."""
    rows_out: list[dict[str, Any]] = []
    tables = page.extract_tables() or []
    for table in tables:
        if not table or len(table) < 2:
            continue
        header = [str(c or "").replace("\n", " ").strip().lower() for c in table[0]]
        if not any("asset" in h for h in header):
            continue
        col = {name: i for i, name in enumerate(header)}
        idx_asset = next((i for i, h in enumerate(header) if "asset" in h), 2)
        idx_type = next((i for i, h in enumerate(header) if "transaction" in h and "type" in h), 3)
        idx_date = next((i for i, h in enumerate(header) if h == "date"), 4)
        idx_amt = next((i for i, h in enumerate(header) if "amount" in h), 6)
        idx_owner = next((i for i, h in enumerate(header) if "owner" in h), 1)

        owner_carry = ""
        for raw in table[1:]:
            if not raw:
                continue
            cells = [str(c or "").replace("\x00", "").strip() for c in raw]
            while len(cells) < len(header):
                cells.append("")
            owner = cells[idx_owner] or owner_carry
            if cells[idx_owner]:
                owner_carry = cells[idx_owner]
            asset = cells[idx_asset]
            if not asset or asset.lower().startswith("filing id"):
                continue
            tx_type = cells[idx_type].strip().upper()[:1]
            if tx_type not in _PTR_ACTION:
                continue
            date_raw = cells[idx_date] or ""
            dates = _DATE_RE.findall(date_raw)
            txn_date = dates[0] if dates else None
            amount_raw = cells[idx_amt] or ""
            if not amount_raw:
                joined = " ".join(cells)
                am = _AMOUNT_RE.search(joined)
                amount_raw = am.group(0) if am else ""
            ticker_m = _TICKER_RE.search(asset)
            ticker = ticker_m.group(1) if ticker_m else None
            lo, hi = parse_amount_range(amount_raw) if amount_raw else (None, None)
            if not txn_date:
                continue
            if lo is None and not ticker:
                continue
            rows_out.append(
                {
                    "owner": owner or None,
                    "asset_name": asset.split("\n")[0].strip(),
                    "action": _PTR_ACTION[tx_type],
                    "transaction_date": pd.to_datetime(txn_date, errors="coerce"),
                    "amount_min": lo,
                    "amount_max": hi,
                    "ticker": ticker,
                }
            )
    return rows_out


def _parse_text_blocks(text: str) -> list[dict[str, Any]]:
    """Fallback regex parser for PTR body text."""
    text = _normalize_ptr_text(text)
    rows: list[dict[str, Any]] = []
    # Split on ticker lines like (AVGO) [ST]
    chunks = re.split(r"(?=\([A-Z]{1,5}(?:-[A-Z])?\)\s*\[)", text)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or "Transaction" in chunk[:40]:
            continue
        ticker_m = _TICKER_RE.search(chunk)
        if not ticker_m:
            continue
        ticker = ticker_m.group(1)
        type_m = re.search(r"\b([PSE])\b\s+(\d{1,2}/\d{1,2}/\d{4})", chunk)
        if not type_m:
            continue
        action = _PTR_ACTION.get(type_m.group(1), "purchase")
        txn_date = pd.to_datetime(type_m.group(2), errors="coerce")
        amt_m = _AMOUNT_RE.search(chunk)
        lo, hi = parse_amount_range(amt_m.group(0)) if amt_m else (None, None)
        asset_line = chunk.split("(")[0].strip()
        asset_line = re.sub(r"^[A-Z]{1,3}\s+", "", asset_line)
        if is_bond_description(asset_line):
            continue
        rows.append(
            {
                "owner": None,
                "asset_name": asset_line[:120] or ticker,
                "action": action,
                "transaction_date": txn_date,
                "amount_min": lo,
                "amount_max": hi,
                "ticker": ticker,
            }
        )
    return rows


def extract_ptr_transactions(pdf_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            rows.extend(_parse_table_rows(page))
            text = page.extract_text() or ""
            rows.extend(_parse_text_blocks(text))

    # Deduplicate parsed rows
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        key = (
            r.get("ticker"),
            r.get("action"),
            str(r.get("transaction_date")),
            r.get("amount_min"),
            r.get("asset_name", "")[:40],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def parse_ptr_pdf(
    pdf_path: Path,
    doc_id: str,
    disclosure_date: str | None,
    person: str,
) -> list[dict[str, Any]]:
    raw = extract_ptr_transactions(pdf_path)
    trades: list[dict[str, Any]] = []
    for i, parsed in enumerate(raw):
        desc = parsed["asset_name"]
        ticker = parsed.get("ticker")
        if _is_garbage_asset(desc):
            continue
        if "[OP]" in (desc or "").upper():
            continue
        if not ticker:
            ticker, asset_class = infer_ticker(desc)
        else:
            _, asset_class = infer_ticker(desc)
        asset_class = _classify_asset_class(desc, ticker, asset_class)
        if asset_class.startswith("bond"):
            continue
        if parsed["action"] == "exchange":
            continue

        trade_key = (
            f"{person}|{doc_id}|{i}|{desc[:40]}|{parsed['action']}|{parsed['transaction_date']}"
        )
        trades.append(
            {
                "trade_id": hashlib.md5(trade_key.encode()).hexdigest()[:12],
                "person": person,
                "doc_id": doc_id,
                "txn_num": i + 1,
                "owner": parsed.get("owner"),
                "asset_name": desc,
                "action": parsed["action"],
                "transaction_date": parsed["transaction_date"],
                "disclosure_date": pd.to_datetime(disclosure_date, errors="coerce") if disclosure_date else pd.NaT,
                "amount_min": parsed["amount_min"],
                "amount_max": parsed["amount_max"],
                "asset_class": asset_class,
                "ticker": ticker,
                "source_doc": pdf_path.name,
            }
        )
    return trades


def parse_all_ptr_filings(manifest: pd.DataFrame, settings: dict[str, Any] | None = None) -> pd.DataFrame:
    settings = settings or load_settings()
    person = settings["person"]["name"]
    lo, hi = _analysis_window(settings)
    all_trades: list[dict[str, Any]] = []

    ptr = manifest[manifest["report_type"].astype(str).str.contains("ptr", case=False, na=False)]
    ptr = ptr.drop_duplicates(subset=["doc_id"])
    for _, row in ptr.iterrows():
        pdf_path = Path(row["local_path"])
        if not pdf_path.exists() or not str(row.get("status", "")).startswith("ok"):
            continue
        disc = row.get("disclosure_date") or row.get("filing_date")
        trades = parse_ptr_pdf(
            pdf_path,
            doc_id=row["doc_id"],
            disclosure_date=str(disc)[:10] if pd.notna(disc) and disc else None,
            person=person,
        )
        all_trades.extend(trades)

    if not all_trades:
        return pd.DataFrame()

    df = pd.DataFrame(all_trades)
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["disclosure_date"] = pd.to_datetime(df["disclosure_date"])
    df = df[(df["transaction_date"] >= lo) & (df["transaction_date"] <= hi)].reset_index(drop=True)
    df = _backfill_missing_amounts(df)

    dedupe_cols = ["person", "ticker", "action", "transaction_date", "doc_id"]
    df = df.sort_values(["amount_min", "asset_name"], ascending=[False, True], na_position="last")
    df = df.sort_values("disclosure_date").drop_duplicates(
        subset=[c for c in dedupe_cols if c in df.columns], keep="first"
    )
    return df.reset_index(drop=True)


def parse_stats_all(manifest: pd.DataFrame, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    ok = manifest[manifest["status"].astype(str).str.startswith("ok")]
    per_doc = []
    total_extracted = 0
    parsed_rows = 0
    with_amount = 0
    for _, row in ok.iterrows():
        pdf = Path(row["local_path"])
        n_pdf = 0
        if pdf.exists():
            try:
                n_pdf = len(extract_ptr_transactions(pdf))
            except Exception:
                n_pdf = 0
        parsed_df = (
            parse_ptr_pdf(
                pdf,
                doc_id=row["doc_id"],
                disclosure_date=str(row.get("disclosure_date", ""))[:10],
                person=settings["person"]["name"],
            )
            if pdf.exists()
            else []
        )
        n_parsed = len(parsed_df)
        n_amt = sum(1 for t in parsed_df if t.get("amount_min") is not None and t.get("amount_min", 0) > 0)
        total_extracted += n_pdf
        parsed_rows += n_parsed
        with_amount += n_amt
        per_doc.append(
            {
                "doc_id": row["doc_id"],
                "n_pdf_rows": n_pdf,
                "n_parsed_trades": n_parsed,
                "n_with_amount": n_amt,
            }
        )

    rate = parsed_rows / total_extracted if total_extracted else None
    return {
        "n_filings": len(ok),
        "table_rows_in_pdf": total_extracted,
        "parsed_trades": parsed_rows,
        "parsed_with_amount": with_amount,
        "amount_coverage_rate": with_amount / parsed_rows if parsed_rows else 0.0,
        "parse_rate_vs_table": rate,
        "per_document": per_doc,
    }


def save_trades(df: pd.DataFrame, settings: dict[str, Any] | None = None) -> Path:
    settings = settings or load_settings()
    out = project_root() / settings["paths"]["processed"] / "trades.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out


def filter_trades_with_ticker(df: pd.DataFrame, asset_classes: list[str] | None = None) -> pd.DataFrame:
    from .equity_trades import filter_trades_with_ticker as _f

    return _f(df, asset_classes=asset_classes)
