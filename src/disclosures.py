"""Fetch and catalog House STOCK Act PTR disclosure PDFs (Pelosi / House Clerk)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml


def load_settings(config_path: Path | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    path = config_path or root / "config" / "settings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_dirs(settings: dict[str, Any] | None = None) -> dict[str, Path]:
    settings = settings or load_settings()
    root = project_root()
    paths = {
        "raw_disclosures": root / settings["paths"]["raw_disclosures"],
        "processed": root / settings["paths"]["processed"],
        "manual": root / settings["paths"]["manual"],
        "prices": root / settings["paths"]["prices"],
        "raw_social": root / settings["paths"]["raw_social"],
        "raw_news": root / settings["paths"]["raw_news"],
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


def download_pdf(url: str, dest: Path, timeout: int = 60) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "PelosiFollowingResearch/1.0"})
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def disclosure_block(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return house/oge/disclosure config block (Pelosi uses `house`)."""
    settings = settings or load_settings()
    for key in ("house", "oge", "disclosure"):
        block = settings.get(key)
        if isinstance(block, dict):
            return block
    return {}


def analysis_end_date(settings: dict[str, Any] | None = None) -> pd.Timestamp:
    block = disclosure_block(settings)
    return pd.Timestamp(block.get("analysis_end_date", "2026-05-30")).normalize()


def analysis_start_date(settings: dict[str, Any] | None = None) -> pd.Timestamp:
    block = disclosure_block(settings)
    raw = block.get("analysis_start_date") or block.get("inauguration_date") or "2023-01-01"
    return pd.Timestamp(raw).normalize()


def extract_oge_received_date(pdf_path: Path) -> str | None:
    """Parse 'OGE RECEIVED: MM/DD/YYYY' from PDF text (OCR-tolerant)."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages[:5])
    compact = text.replace("\n", " ")
    m = re.search(
        r"OGE\s*RECEIV(?:ED|E)[^\d]{0,40}(\d{1,2})\s*[/\.\s]\s*(\d{1,2})\s*[/\.\s]\s*(\d{4})",
        compact,
        re.I,
    )
    if m:
        mo, da, yr = m.groups()
        return f"{int(mo)}/{int(da)}/{yr}"
    for line in text.splitlines():
        upper = line.upper()
        if "OGE RECEIVED" in upper or ("RECEIVED" in upper and "OGE" in upper):
            parts = line.split(":")
            if len(parts) >= 2:
                return parts[-1].strip()
        m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", line)
        if m and ("RECEIVED" in upper or "OGE" in upper):
            return m.group(1)
    return None
