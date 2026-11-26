"""All numbers in the dashboard are computed here, in code. The LLM never
produces a number."""
import json
import os
from collections import Counter

import numpy as np
import pandas as pd

from .config import (CITY_ALIASES, CODEBOOK, CONTROLLABILITY, LOST, NS, RETURNED,
                     THEME_BRANCH, TOP8_CITIES, WENT_ELSEWHERE)
from .gates import as_list

DATA = "data"
UNKNOWN = {NS, "None stated", "Other", "", "nan", "None"}


# ---------------------------------------------------------------- loading
def load(data_dir: str = DATA):
    rec = pd.read_csv(os.path.join(data_dir, "records.csv"), dtype=str, keep_default_na=False)
    coded = pd.read_csv(os.path.join(data_dir, "coded.csv"), dtype=str, keep_default_na=False)
    log = {}
    if os.path.exists(os.path.join(data_dir, "run_log.json")):
        log = json.load(open(os.path.join(data_dir, "run_log.json"), encoding="utf-8"))
    golden = None
    gx, gl = os.path.join(data_dir, "golden_labels.xlsx"), os.path.join(data_dir, "golden_labels.csv")
    if os.path.exists(gx):
        golden = pd.read_excel(gx, sheet_name=0, dtype=str).fillna("")
    elif os.path.exists(gl):
        golden = pd.read_csv(gl, dtype=str, keep_default_na=False)
    gset = None
    gs = os.path.join(data_dir, "golden_set.csv")
    if os.path.exists(gs):
        gset = pd.read_csv(gs, dtype=str, keep_default_na=False)
    return rec, coded, log, gset, golden


def prepare(coded: pd.DataFrame, rec: pd.DataFrame) -> pd.DataFrame:
    df = coded.copy()
    meta = rec.set_index("record_id")[["source", "text", "link", "date", "rating", "type"]]
    for c in meta.columns:
        if c not in df.columns or (df[c] == "").all():
            df[c] = df["record_id"].map(meta[c]).fillna("")
    df["passed"] = df["gate_status"].isin(["passed_first", "passed_retry"])
    df["theme_list"] = df["themes"].map(as_list)
    df["outside_list"] = df["outside_app"].map(as_list)
    df["primary_theme"] = df["theme_list"].map(lambda t: t[0] if t else "Other")
    df["branch"] = df["primary_theme"].map(lambda t: THEME_BRANCH.get(t, "Other"))
    city = df["city"].fillna("").str.strip().str.title()
    city = city.replace(CITY_ALIASES)
    df["city_norm"] = city.where(~city.isin(["", "Not Stated", "None", "Nan"]), NS)
    df["city_tier"] = np.where(df["city_norm"] == NS, NS,
                               np.where(df["city_norm"].isin(TOP8_CITIES), "Top-8 metro", "Other city"))

    def group(r):
        if r["return_status"] in RETURNED:
            return "Returned"
        if r["return_status"] in LOST or r["turn_to_next"] in WENT_ELSEWHERE:
            return "Lost the repeat"
        return "Unclear"
    df["group"] = df.apply(group, axis=1)
    df["went_elsewhere"] = df["turn_to_next"].isin(WENT_ELSEWHERE)
    df["nothing_wrong"] = df["went_wrong"] == "No"
    df["in_scope"] = (df["relevant"] == "Yes") & (df["country"] != "Outside India") & \
                     (df["category"] != "InstaHelp")
    df["core"] = df["in_scope"] & (df["speaker"] == "Customer") & (
        (df["return_status"] != NS) | df["went_elsewhere"] |
        df["theme_list"].map(lambda t: any(x not in ("Other",) for x in t)))
    return df


# ---------------------------------------------------------------- shares
def label_shares(df: pd.DataFrame, field: str) -> pd.DataFrame:
    """Share of records in df carrying each label. Unknowns excluded from the
    rows but kept in the base (n)."""
    n = len(df)
    multi = CODEBOOK.get(field, {}).get("multi", False)
    cnt = Counter()
    for v in df[field]:
        for x in (as_list(v) if multi else [v]):
            if x not in UNKNOWN:
                cnt[x] += 1
    rows = [{"label": k, "count": c, "share": c / n * 100 if n else 0} for k, c in cnt.most_common()]
    return pd.DataFrame(rows, columns=["label", "count", "share"])


def examples(df: pd.DataFrame, field: str, label: str, k: int = 3) -> pd.DataFrame:
    multi = CODEBOOK.get(field, {}).get("multi", False)
    m = df[field].map(lambda v: label in (as_list(v) if multi else [v]))
    sub = df[m & (df["evidence_quote"] != "")]
    sub = sub.assign(_len=sub["evidence_quote"].str.len()).sort_values("_len", ascending=False)
    return sub.head(k)


# ---------------------------------------------------------------- opportunity
def opportunity(df: pd.DataFrame, w_reach=1.0, w_lost=1.0, w_nww=0.5, control=None) -> pd.DataFrame:
    """Score = reach^w1 x closeness-to-lost-repeat^w2 x (1 + nothing-went-wrong share)^w3
    x controllability, scaled so the top need = 100."""
    control = control or CONTROLLABILITY
    base = len(df)
    rows = []
    for need, g in df.groupby("unmet_need"):
        if need in UNKNOWN or not len(g):
            continue
        reach = len(g) / base if base else 0
        lost = (g["group"] == "Lost the repeat").mean()
        nww = g["nothing_wrong"].mean()
        ctrl = float(control.get(need, 0.5))
        raw = (reach ** w_reach) * ((lost + 0.05) ** w_lost) * ((1 + nww) ** w_nww) * ctrl
        rows.append({"need": need, "mentions": len(g), "reach": reach * 100,
                     "lost_share": lost * 100, "nothing_wrong_share": nww * 100,
                     "returned_share": (g["group"] == "Returned").mean() * 100,
                     "controllability": ctrl, "raw": raw,
                     "top_category": g["category"][g["category"] != NS].mode().iat[0]
                     if (g["category"] != NS).any() else NS})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["score"] = out["raw"] / out["raw"].max() * 100
    return out.sort_values("score", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------- Q6 comparison
COMPARE_FIELDS = ["themes", "went_wrong", "need_trigger", "planning_mode", "expectation_after",
                  "turn_to_next", "outside_app", "unmet_need", "category"]


def compare_groups(df: pd.DataFrame, min_n=3) -> tuple[pd.DataFrame, int, int]:
    a = df[df["group"] == "Lost the repeat"]
    b = df[df["group"] == "Returned"]
    rows = []
    for f in COMPARE_FIELDS:
        sa, sb = label_shares(a, f), label_shares(b, f)
        labels = set(sa["label"]) | set(sb["label"])
        for lab in labels:
            ca = int(sa.loc[sa["label"] == lab, "count"].sum())
            cb = int(sb.loc[sb["label"] == lab, "count"].sum())
            if ca + cb < min_n:
                continue
            pa = ca / len(a) * 100 if len(a) else 0
            pb = cb / len(b) * 100 if len(b) else 0
            rows.append({"field": f, "label": lab, "lost_pct": pa, "returned_pct": pb,
                         "gap": pa - pb, "n": ca + cb, "small": (ca + cb) < 8})
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.reindex(out["gap"].abs().sort_values(ascending=False).index)
    return out, len(a), len(b)


# ---------------------------------------------------------------- segments
def segment_table(df: pd.DataFrame, seg: str) -> pd.DataFrame:
    rows = []
    for val, g in df.groupby(seg):
        if val in UNKNOWN:
            continue
        themes = Counter(t for ts in g["theme_list"] for t in ts if t != "Other")
        needs = Counter(n for n in g["unmet_need"] if n not in UNKNOWN)
        rows.append({"segment": val, "posts": len(g),
                     "returned": int((g["group"] == "Returned").sum()),
                     "lost": int((g["group"] == "Lost the repeat").sum()),
                     "something_went_wrong": (g["went_wrong"] == "Yes").mean() * 100,
                     "top_reason": themes.most_common(1)[0][0] if themes else "—",
                     "top_need": needs.most_common(1)[0][0] if needs else "—"})
    out = pd.DataFrame(rows)
    return out.sort_values("posts", ascending=False) if not out.empty else out


# ---------------------------------------------------------------- golden set
GOLDEN_FIELDS = ["relevant", "speaker", "return_status", "went_wrong", "primary_theme",
                 "turn_to_next", "unmet_need", "category"]


def cohen_kappa(a, b):
    a, b = list(a), list(b)
    n = len(a)
    if n == 0:
        return float("nan")
    labels = sorted(set(a) | set(b))
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[l] * cb[l] for l in labels) / (n * n)
    return float("nan") if pe == 1 else (po - pe) / (1 - pe)


def golden_score(golden: pd.DataFrame, df: pd.DataFrame):
    """Compare hand labels (golden_labels.csv) with AI labels for the same posts."""
    ai = df.set_index("record_id")
    g = golden[golden["record_id"].isin(ai.index)].copy()
    per_field, per_record = [], []
    for f in GOLDEN_FIELDS:
        hand_col = f"hand_{f}"
        if hand_col not in g.columns:
            continue
        sub = g[g[hand_col].str.strip() != ""]
        if sub.empty:
            continue
        if f == "primary_theme":   # agree if the hand theme is one of the AI's themes
            ai_vals = [h if h in ai.loc[r, "theme_list"] else ai.loc[r, "primary_theme"]
                       for r, h in zip(sub["record_id"], sub[hand_col])]
        else:
            ai_vals = [ai.loc[r, f] for r in sub["record_id"]]
        hand = sub[hand_col].str.strip().tolist()
        agree = np.mean([h == a for h, a in zip(hand, ai_vals)])
        per_field.append({"field": f, "n": len(sub), "agreement": agree * 100,
                          "kappa": cohen_kappa(hand, ai_vals)})
    for _, r in g.iterrows():
        dis = []
        for f in GOLDEN_FIELDS:
            hc = f"hand_{f}"
            if hc not in g.columns or not str(r[hc]).strip():
                continue
            a = ai.loc[r["record_id"], f]
            if f == "primary_theme":
                ok = r[hc] in ai.loc[r["record_id"], "theme_list"]
            else:
                ok = r[hc] == a
            if not ok:
                dis.append({"field": f, "hand": r[hc], "ai": a})
        per_record.append({"record_id": r["record_id"], "source": ai.loc[r["record_id"], "source"],
                           "disagreements": dis})
    return pd.DataFrame(per_field), per_record
