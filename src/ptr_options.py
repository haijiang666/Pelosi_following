"""Parse and analyze House PTR option transactions ([OP] / call & put)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber

from .disclosures import load_settings, project_root
from .equity_trades import parse_amount_range
from .holdings import fifo_match_trades
from .ptr_trades import _analysis_window, _backfill_missing_amounts, _is_garbage_asset

_PTR_ACTION = {"P": "purchase", "S": "sale"}

_TICKER_OP_RE = re.compile(r"\(([A-Z]{1,5}(?:-[A-Z])?)\)\s*\[OP\]", re.I)
_OP_ROW_RE = re.compile(
    r"\(([A-Z]{1,5}(?:-[A-Z])?)\)\s*\[OP\]\s*([PS])\s*(\d{1,2}/\d{1,2}/\d{4})",
    re.I,
)
_AMOUNT_RE = re.compile(r"\$[\d,]+(?:\.\d+)?(?:\s*-\s*\$[\d,]+(?:\.\d+)?)?")
_DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
_N_CONTRACTS = re.compile(r"(\d[\d,]*)\s+(call|put)\s+options?", re.I)
_EXERCISE_RE = re.compile(
    r"Exercised\s+(\d[\d,]*)\s+(call|put)\s+options?",
    re.I,
)
_STRIKE_RE = re.compile(r"strike price of\s*\$?\s*([\d,]+(?:\.\d+)?)", re.I)
_EXPIRY_RE = re.compile(r"expiration date of\s*(\d{1,2}/\d{1,2}/\d{4})", re.I)
_PURCHASED_RE = re.compile(r"Purchased\s+(\d[\d,]*)\s+(call|put)\s+options?", re.I)
_SOLD_RE = re.compile(r"Sold\s+(\d[\d,]*)\s+(call|put)\s+options?", re.I)


def _normalize(text: str) -> str:
    return (text or "").replace("\x00", "").replace("\ufffd", "").replace("  ", " ")


def _parse_description_fields(desc: str) -> dict[str, Any]:
    desc = _normalize(desc)
    out: dict[str, Any] = {
        "option_type": None,
        "n_contracts": None,
        "strike": None,
        "expiration": None,
        "is_exercise": False,
    }
    ex = _EXERCISE_RE.search(desc)
    if ex:
        out["is_exercise"] = True
        out["n_contracts"] = int(ex.group(1).replace(",", ""))
        out["option_type"] = ex.group(2).lower()
    else:
        for pat in (_PURCHASED_RE, _SOLD_RE, _N_CONTRACTS):
            m = pat.search(desc)
            if m:
                out["n_contracts"] = int(m.group(1).replace(",", ""))
                out["option_type"] = m.group(2).lower()
                break
    sm = _STRIKE_RE.search(desc)
    if sm:
        out["strike"] = float(sm.group(1).replace(",", ""))
    em = _EXPIRY_RE.search(desc)
    if em:
        out["expiration"] = pd.to_datetime(em.group(1), errors="coerce")
    return out


def _parse_op_blob(blob: str, owner: str | None = None) -> dict[str, Any] | None:
    blob = _normalize(blob)
    if _is_garbage_asset(blob):
        return None
    has_op = "[OP]" in blob.upper()
    has_ex = bool(_EXERCISE_RE.search(blob))
    has_opt_lang = bool(re.search(r"\b(call|put)\s+options?\b", blob, re.I))
    if not has_op and not (has_ex and has_opt_lang):
        return None

    m = _OP_ROW_RE.search(blob)
    if not m and not has_ex:
        return None

    ticker = m.group(1) if m else None
    action_code = m.group(2).upper() if m else None
    txn_date = pd.to_datetime(m.group(3), errors="coerce") if m else None

    meta = _parse_description_fields(blob)
    if meta["is_exercise"]:
        action = "exercise"
    elif action_code:
        action = _PTR_ACTION.get(action_code, "purchase")
    else:
        action = "sale" if _SOLD_RE.search(blob) else "purchase"

    if not ticker:
        tm = re.search(r"\(([A-Z]{1,5})\)", blob)
        ticker = tm.group(1) if tm else None
    if not ticker:
        return None

    if txn_date is None or pd.isna(txn_date):
        dates = _DATE_RE.findall(blob)
        txn_date = pd.to_datetime(dates[0], errors="coerce") if dates else None

    amt_m = _AMOUNT_RE.search(blob)
    lo, hi = parse_amount_range(amt_m.group(0)) if amt_m else (None, None)

    asset_line = blob.split("(")[0].strip()[:120] if "(" in blob else blob[:120]
    exp = meta["expiration"]
    strike = meta["strike"]
    opt_type = meta["option_type"] or "call"
    contract_id = f"{ticker}|{opt_type}|{strike}|{exp.date() if pd.notna(exp) else 'na'}"

    return {
        "owner": owner,
        "asset_name": asset_line or f"{ticker} {opt_type} option",
        "ticker": ticker,
        "underlying": ticker,
        "action": action,
        "transaction_date": txn_date,
        "amount_min": lo,
        "amount_max": hi,
        "option_type": opt_type,
        "n_contracts": meta["n_contracts"],
        "strike": strike,
        "expiration": exp,
        "contract_id": contract_id,
        "description": blob[:500],
        "asset_class": "option",
    }


def extract_ptr_option_transactions(pdf_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = _normalize(page.extract_text() or "")
            owner_carry = ""
            for table in page.extract_tables() or []:
                if not table:
                    continue
                for raw in table:
                    if not raw:
                        continue
                    cells = [_normalize(str(c or "")) for c in raw]
                    blob = " ".join(c for c in cells if c)
                    if not blob:
                        continue
                    if cells[0].strip().upper() in {"ID", "OWNER"}:
                        continue
                    owner = ""
                    if cells[0].strip().upper() in {"SP", "JT", "DC"}:
                        owner = cells[0].strip().upper()
                    elif blob.upper().startswith("SP "):
                        owner = "SP"
                    parsed = _parse_op_blob(blob, owner=owner or owner_carry)
                    if parsed:
                        if owner:
                            owner_carry = owner
                        rows.append(parsed)
            # Full-page scan for exercise / option description lines
            for line in text.split("\n"):
                line = _normalize(line)
                if "[OP]" in line.upper() or _EXERCISE_RE.search(line):
                    parsed = _parse_op_blob(line)
                    if parsed:
                        rows.append(parsed)

    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        key = (
            r.get("ticker"),
            r.get("action"),
            str(r.get("transaction_date")),
            r.get("strike"),
            str(r.get("expiration")),
            r.get("n_contracts"),
            r.get("amount_min"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def parse_option_pdf(
    pdf_path: Path,
    doc_id: str,
    disclosure_date: str | None,
    person: str,
) -> list[dict[str, Any]]:
    raw = extract_ptr_option_transactions(pdf_path)
    trades: list[dict[str, Any]] = []
    for i, parsed in enumerate(raw):
        if parsed["action"] == "exchange":
            continue
        desc = parsed["asset_name"]
        trade_key = (
            f"{person}|{doc_id}|opt|{i}|{parsed.get('contract_id')}|"
            f"{parsed['action']}|{parsed['transaction_date']}"
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
                "disclosure_date": pd.to_datetime(disclosure_date, errors="coerce")
                if disclosure_date
                else pd.NaT,
                "amount_min": parsed["amount_min"],
                "amount_max": parsed["amount_max"],
                "asset_class": "option",
                "ticker": parsed["ticker"],
                "underlying": parsed["underlying"],
                "option_type": parsed["option_type"],
                "n_contracts": parsed["n_contracts"],
                "strike": parsed["strike"],
                "expiration": parsed["expiration"],
                "contract_id": parsed["contract_id"],
                "description": parsed.get("description"),
                "source_doc": pdf_path.name,
            }
        )
    return trades


def parse_all_ptr_options(manifest: pd.DataFrame, settings: dict[str, Any] | None = None) -> pd.DataFrame:
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
        trades = parse_option_pdf(
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
    df["expiration"] = pd.to_datetime(df["expiration"], errors="coerce")
    df = df[(df["transaction_date"] >= lo) & (df["transaction_date"] <= hi)].reset_index(drop=True)
    df = _backfill_missing_amounts(df)

    dedupe_cols = ["person", "contract_id", "action", "transaction_date", "doc_id", "n_contracts"]
    df = df.sort_values(["amount_min", "asset_name"], ascending=[False, True], na_position="last")
    df = df.sort_values("disclosure_date").drop_duplicates(
        subset=[c for c in dedupe_cols if c in df.columns], keep="first"
    )
    return df.reset_index(drop=True)


def parse_option_stats(manifest: pd.DataFrame, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    ok = manifest[manifest["status"].astype(str).str.startswith("ok")]
    parsed_rows = 0
    with_amount = 0
    for _, row in ok.iterrows():
        pdf = Path(row["local_path"])
        if not pdf.exists():
            continue
        trades = parse_option_pdf(
            pdf,
            doc_id=row["doc_id"],
            disclosure_date=str(row.get("disclosure_date", ""))[:10],
            person=settings["person"]["name"],
        )
        parsed_rows += len(trades)
        with_amount += sum(1 for t in trades if t.get("amount_min") and t["amount_min"] > 0)
    return {
        "n_filings": len(ok),
        "parsed_options": parsed_rows,
        "parsed_with_amount": with_amount,
        "amount_coverage_rate": with_amount / parsed_rows if parsed_rows else 0.0,
    }


def save_options(df: pd.DataFrame, settings: dict[str, Any] | None = None) -> Path:
    settings = settings or load_settings()
    out = project_root() / settings["paths"]["processed"] / "options.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out


def filter_options_tradable(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df[df["ticker"].notna() & df["asset_class"].eq("option")].copy()
    out = out[out["action"].isin(["purchase", "sale", "exercise"])].copy()
    return out.reset_index(drop=True)


def fifo_match_options(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """FIFO per option contract (ticker + type + strike + expiration)."""
    if trades.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty

    df = trades.copy()
    df["contract_id"] = df["contract_id"].fillna(
        df["ticker"].astype(str)
        + "|"
        + df["option_type"].fillna("call").astype(str)
        + "|"
        + df["strike"].astype(str)
        + "|"
        + df["expiration"].astype(str)
    )
    # Map exercise → sale for FIFO (close long option); purchase opens long option
    df["fifo_action"] = df["action"].replace({"exercise": "sale"})
    fifo_df = df.copy()
    fifo_df["action"] = fifo_df["fifo_action"]
    fifo_df["ticker"] = fifo_df["contract_id"]
    matched, summary, trade_holding, all_lots = fifo_match_trades(fifo_df)
    if not all_lots.empty:
        all_lots["contract_id"] = all_lots["ticker"]
        # Restore display ticker from contract_id first segment
        all_lots["ticker"] = all_lots["contract_id"].str.split("|").str[0]
    if not matched.empty:
        matched["contract_id"] = matched["ticker"]
        matched["ticker"] = matched["contract_id"].str.split("|").str[0]
    if not summary.empty:
        summary["ticker"] = summary["ticker"].str.split("|").str[0]
    return matched, summary, trade_holding, all_lots
