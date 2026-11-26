"""Prefilter in code (no AI): dedupe, drop noise, keep home-service posts.

Each record gets a `status`; only status == 'Candidate' goes to AI coding.
The status column is what the collection funnel in the dashboard counts.
"""
import hashlib
import re
from datetime import date, timedelta

import pandas as pd

from .config import EXCLUDE_TERMS, LOOKBACK_DAYS, MIN_CHARS, SERVICE_TERMS

STORE_SOURCES = {"play_store", "app_store"}   # every store review is about the UC app


def _key(text):
    t = re.sub(r"[^a-z0-9 ]", "", str(text).lower())
    return hashlib.md5(re.sub(r"\s+", " ", t).strip().encode()).hexdigest()


def _date(v):
    ts = pd.to_datetime(v, errors="coerce", utc=True)
    return None if pd.isna(ts) else ts.date()


def prefilter(df: pd.DataFrame, today: date | None = None) -> pd.DataFrame:
    df = df.copy()
    today = today or date.today()
    cutoff = today - timedelta(days=LOOKBACK_DAYS)
    df["text"] = df["text"].fillna("").astype(str)
    df["dedupe_key"] = df["text"].map(_key)
    if "status" not in df.columns:
        df["status"] = ""
    df["status"] = df["status"].fillna("")
    # posts already filtered in an earlier run keep their status; new posts are
    # checked against everything seen so far
    seen = set(df.loc[df["status"] != "", "dedupe_key"])
    statuses = []
    for _, r in df.iterrows():
        if r["status"]:
            statuses.append(r["status"])
            continue
        low = f" {r['text'].lower()} "
        d = _date(r.get("date"))
        if r["dedupe_key"] in seen:
            s = "Dropped: duplicate"
        elif len(r["text"]) < MIN_CHARS:
            s = "Dropped: too short"
        elif d and d < cutoff:
            s = "Dropped: older than lookback"
        elif any(t in low for t in EXCLUDE_TERMS["instahelp"]):
            s = "Excluded: InstaHelp"
        elif any(t in low for t in EXCLUDE_TERMS["outside_india"]):
            s = "Excluded: outside India"
        elif r["source"] not in STORE_SOURCES and not any(t in low for t in SERVICE_TERMS):
            s = "Dropped: not about home services"
        else:
            s = "Candidate"
        seen.add(r["dedupe_key"])
        statuses.append(s)
    df["status"] = statuses
    return df
