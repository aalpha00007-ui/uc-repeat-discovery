"""Urban Company repeat-booking discovery engine: the pipeline.

Run on your laptop (needs internet and your keys in .env):

    python run.py collect              # all 5 sources -> data/records.csv
    python run.py collect --sources play_store app_store
    python run.py prefilter            # dedupe + keep home-service posts (no AI)
    python run.py label --limit 1500   # Gemini coding + quality gates
    python run.py golden               # 20-post blind golden set to hand-label
    python run.py all                  # collect -> prefilter -> label

Then commit the data/ folder and Streamlit Cloud redeploys the dashboard.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv

from engine import analysis, collect, golden, label, prefilter

load_dotenv()
DATA = "data"
REC = os.path.join(DATA, "records.csv")
CODED = os.path.join(DATA, "coded.csv")
LOG = os.path.join(DATA, "run_log.json")


def _log_update(**kw):
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {"runs": []}
    log.setdefault("runs", []).append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **kw})
    json.dump(log, open(LOG, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def _read(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False) if os.path.exists(path) else pd.DataFrame()


def cmd_collect(sources):
    old = _read(REC)
    new_rows = []
    for s in sources:
        print(f"Collecting {s} ...")
        try:
            rows = collect.SOURCES[s]()
        except Exception as e:
            print(f"  {s} skipped: {e}")
            continue
        new_rows += rows
        print(f"  {s}: {len(rows)} records")
    new = pd.DataFrame(new_rows)
    if new.empty:
        print("Nothing collected.")
        return
    merged = pd.concat([old, new], ignore_index=True) if not old.empty else new
    merged = merged.drop_duplicates("record_id", keep="first").fillna("")
    merged.to_csv(REC, index=False)
    _log_update(step="collect", sources=sources, new_records=len(new), total_records=len(merged))
    print(f"records.csv: {len(merged)} records ({len(merged) - len(old)} new)")


def cmd_prefilter():
    df = _read(REC)
    df = prefilter.prefilter(df)
    df.to_csv(REC, index=False)
    counts = df["status"].value_counts().to_dict()
    _log_update(step="prefilter", status_counts=counts)
    print(json.dumps(counts, indent=2))


def cmd_label(limit, rpm, batch):
    rec, coded = _read(REC), _read(CODED)
    cands = rec[rec["status"] == "Candidate"]
    if not coded.empty:
        cands = cands[~cands["record_id"].isin(coded["record_id"])]
    run_id = label.stamp()
    out = label.label_records(cands, run_id, batch_size=batch, rpm=rpm, limit=limit)
    if out.empty:
        print("No new posts coded.")
        return
    merged = pd.concat([coded, out], ignore_index=True) if not coded.empty else out
    merged = merged.drop_duplicates("record_id", keep="last").fillna("")
    merged.to_csv(CODED, index=False)
    rej = out[out["gate_status"] == "rejected"][["record_id", "gate_fails"]]
    rej.to_csv(os.path.join(DATA, "gate_log_latest.csv"), index=False)
    _log_update(step="label", run_id=run_id, model=out["model"].iloc[0],
                coded=len(out), gate_counts=out["gate_status"].value_counts().to_dict())
    print(out["gate_status"].value_counts())


def cmd_golden():
    rec, coded, log, _, _ = analysis.load(DATA)
    df = analysis.prepare(coded, rec, log.get("corrections"))
    gs = golden.pick(df)
    gs.to_csv(os.path.join(DATA, "golden_set.csv"), index=False)
    golden.write_template(gs, os.path.join(DATA, "golden_set_to_label.xlsx"))
    print("Wrote data/golden_set_to_label.xlsx - label it by hand, save as data/golden_labels.xlsx")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["collect", "prefilter", "label", "golden", "all"])
    p.add_argument("--sources", nargs="*", default=list(collect.SOURCES))
    p.add_argument("--limit", type=int, default=None, help="max posts to code this run")
    p.add_argument("--rpm", type=int, default=int(os.getenv("GEMINI_RPM", "10")),
                   help="Gemini requests per minute (free tier: keep low)")
    p.add_argument("--batch", type=int, default=8, help="posts per Gemini call")
    a = p.parse_args()
    os.makedirs(DATA, exist_ok=True)
    if a.step in ("collect", "all"):
        cmd_collect(a.sources)
    if a.step in ("prefilter", "all"):
        cmd_prefilter()
    if a.step in ("label", "all"):
        cmd_label(a.limit, a.rpm, a.batch)
    if a.step == "golden":
        cmd_golden()


if __name__ == "__main__":
    sys.exit(main())
