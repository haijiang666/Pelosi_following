"""Discover and download Nancy Pelosi House STOCK Act PTR filings."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber
import requests

from .disclosures import download_pdf, ensure_dirs, load_settings, project_root

USER_AGENT = "PelosiFollowingResearch/1.0"
FILING_TYPE_PTR = "P"


def _normalize_date(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        mo, da, yr = m.groups()
        return f"{yr}-{int(mo):02d}-{int(da):02d}"
    return None


def _ptr_pdf_url(doc_id: str, filing_date: str, settings: dict[str, Any]) -> str:
    house = settings["house"]
    year = pd.Timestamp(filing_date).year
    return f"{house['ptr_base'].rstrip('/')}/{year}/{doc_id}.pdf"


def discover_ptr_filings(settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Load Nancy Pelosi PTR entries from House Clerk annual XML indexes."""
    settings = settings or load_settings()
    house = settings["house"]
    person = settings["person"]
    cfg = house.get("filings") or []
    if cfg:
        return list(cfg)

    years = house.get("index_years") or [2023, 2024, 2025, 2026]
    types = set(house.get("filing_types") or [FILING_TYPE_PTR])
    start = pd.Timestamp(house.get("analysis_start_date", "2023-01-01"))
    end = pd.Timestamp(house.get("analysis_end_date", "2026-12-31"))
    base = house["index_base"].rstrip("/")

    rows: list[dict[str, Any]] = []
    for year in years:
        url = f"{base}/{year}FD.xml"
        try:
            resp = requests.get(url, timeout=60, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as exc:
            print(f"  WARN: index {year}: {exc}")
            continue

        for member in root.findall("Member"):
            last = (member.findtext("Last") or "").strip()
            first = (member.findtext("First") or "").strip()
            if last.upper() != person["last_name"].upper():
                continue
            if first and first.upper() != person["first_name"].upper():
                continue
            ftype = (member.findtext("FilingType") or "").strip()
            if ftype not in types:
                continue
            filing_date = _normalize_date(member.findtext("FilingDate"))
            doc_id = (member.findtext("DocID") or "").strip()
            if not doc_id or not filing_date:
                continue
            fd = pd.Timestamp(filing_date)
            if fd < start - pd.Timedelta(days=30) or fd > end + pd.Timedelta(days=30):
                continue
            doc_slug = f"pelosi_ptr_{doc_id}"
            rows.append(
                {
                    "doc_id": doc_slug,
                    "doc_id_numeric": doc_id,
                    "url": _ptr_pdf_url(doc_id, filing_date, settings),
                    "report_type": "house_ptr",
                    "filing_date": filing_date,
                    "disclosure_date": filing_date,
                    "filing_year": member.findtext("Year") or str(year),
                    "state_district": member.findtext("StateDst"),
                    "notes": f"House PTR #{doc_id}",
                }
            )

    rows.sort(key=lambda r: r["filing_date"])
    return rows


def extract_ptr_signature_date(pdf_path: Path) -> str | None:
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages[:2])
    m = re.search(r"Digitally Signed:[^,]+,\s*(\d{1,2}/\d{1,2}/\d{4})", text, re.I)
    if m:
        return _normalize_date(m.group(1))
    m = re.search(r"Filing ID #(\d+)", text)
    return None


def fetch_ptr_disclosures(settings: dict[str, Any] | None = None) -> pd.DataFrame:
    settings = settings or load_settings()
    paths = ensure_dirs(settings)
    person = settings["person"]
    docs = discover_ptr_filings(settings)
    rows: list[dict[str, Any]] = []

    for doc in docs:
        doc_id = doc["doc_id"]
        url = doc["url"]
        dest = paths["raw_disclosures"] / f"{doc_id}.pdf"
        try:
            if not dest.exists() or dest.stat().st_size < 1000:
                download_pdf(url, dest)
            status = "ok"
        except Exception as exc:
            status = f"error:{exc}"
            dest = Path("")

        pages = None
        sig_date = None
        if dest.exists() and dest.stat().st_size > 500:
            try:
                with pdfplumber.open(dest) as pdf:
                    pages = len(pdf.pages)
                sig_date = extract_ptr_signature_date(dest)
            except Exception:
                pages = None

        rows.append(
            {
                **doc,
                "person": person["name"],
                "local_path": str(dest) if dest else "",
                "status": status,
                "pages": pages,
                "likely_equity_filing": True,
                "disclosure_date": sig_date or doc.get("disclosure_date"),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df.to_csv(project_root() / settings["paths"]["processed"] / "manifest.csv", index=False)
    return df


def enrich_ptr_manifest(manifest: pd.DataFrame, settings: dict[str, Any] | None = None) -> pd.DataFrame:
    return manifest.copy()


def cross_check_manifest(manifest: pd.DataFrame) -> dict[str, Any]:
    ok = manifest[manifest["status"].astype(str).str.startswith("ok")]
    docs = []
    for _, row in manifest.iterrows():
        docs.append(
            {
                "doc_id": row.get("doc_id"),
                "file_exists": Path(row.get("local_path", "")).exists(),
                "status": row.get("status"),
                "pages": row.get("pages"),
                "filing_date": row.get("filing_date"),
                "disclosure_date": row.get("disclosure_date"),
                "report_type": row.get("report_type"),
            }
        )
    return {
        "source": "U.S. House Clerk — STOCK Act PTR",
        "is_house_ptr": True,
        "n_documents": len(manifest),
        "n_valid_documents": len(ok),
        "all_valid": len(ok) == len(manifest) and len(ok) > 0,
        "documents": docs,
    }
