"""One-off: convert the n8n run (Urban Company Discovery Engine - Data (final),
run_2026-11-24T17-44-26) into the engine's files, then re-check every label
with the code gates.

    python -I scripts/import_n8n_seed.py data/seed/n8n_final.xlsx

What comes from where
- records.csv  <- tab '5 Raw Data' (4,503 posts after n8n's de-duplication)
- coded.csv    <- tab '2 Feedback Analysis' (Gemini labels from the n8n run)
- Four codebook fields (Q1 expectation, Q2 trigger, Q3 turn to next, Q5 outside
  app, Q8 unmet need) were free text in n8n. Each distinct answer was grouped
  into one codebook value by Claude (claude-opus-5-5, in session); the mapping
  is the code strings below, in the alphabetical order of the answers, so it is
  fully auditable.
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.config import CODEBOOK, NS  # noqa: E402
from engine.gates import check  # noqa: E402

SRC = {"App Store": "app_store", "Play Store": "play_store", "YouTube": "youtube",
       "Reddit": "reddit", "Google Search": "google_search", "Trustpilot": "trustpilot",
       "Social Media": "social_media", "Review & Complaint Sites": "complaint_sites",
       "Quora": "quora", "Investor Reports": "investor_reports"}
STATUS = {"Valid": "Candidate", "Invalid: text too short": "Dropped: too short",
          "Invalid: older than lookback": "Dropped: older than lookback",
          "Excluded: InstaHelp": "Excluded: InstaHelp",
          "Excluded: outside India": "Excluded: outside India"}

# code strings: position i = i-th distinct answer (sorted); digit = value index (1-based, 0 = not stated)
Q1 = "".join(["2714267737", "2576276732", "2663722774", "6777331422", "3346622111",
            "1176222731", "2222227262", "2271"])
Q2 = "".join(["1032323112", "0601161236", "1111113616", "2444444412", "1200341161",
            "2212222112", "1311111412", "31"])
Q3 = "".join(["4435101120", "4243334466", "3331434431", "1111111111", "1111110114", "5"])
Q5 = "".join(["3651655621", "6116112112", "15561"])
Q8 = "".join(["3965652553", "3333994346", "5643122222", "2244555353", "5556626666",
            "3845544558", "3364663554", "4548333455", "5666994333", "3364722698",
            "5544556564", "4555343444", "5633395554", "4444444444", "4484456665",
            "6589568455", "8888825589", "3223513154", "8555444656", "5333332333",
            "3538941466", "5257532"])
VALS = {
    "expectation_after": ["Same professional next time", "Warranty, redo or quick fix",
                          "Price and scope as quoted", "Follow-up or reminder for next time",
                          "Reward for coming back", "Support that responds",
                          "Job done fully and properly"],
    "need_trigger": ["Something broke or urgent problem", "Routine upkeep or service due",
                     "Season, festival or weather", "Life event (moving, guests)",
                     "Offer or reminder", "Personal care or no time to do it"],
    "turn_to_next": ["Urban Company again", "Same professional directly",
                     "Local provider or technician", "Another app or company",
                     "Brand service centre", "Family, DIY, house help or landlord"],
    "outside_app": ["Calls a local technician", "Contacts the pro directly",
                    "Asks neighbours, society or WhatsApp groups", "Asks family or friends",
                    "Compares other apps or brands", "Does it themselves or uses house help"],
    "unmet_need": CODEBOOK["unmet_need"]["values"][:9],
}
FREE = {"expectation_after": ("Q1 What they expect after the service", Q1, NS),
        "need_trigger": ("Q2 How & when they decided it was needed", Q2, NS),
        "turn_to_next": ("Q3 Who they turn to next time", Q3, NS),
        "outside_app": ("Q5 What they do outside the app", Q5, "None stated"),
        "unmet_need": ("Q8 Unmet need", Q8, "None stated")}
USED_INSTEAD = {"Local provider": "Local provider or technician", "Another app": "Another app or company",
                "Family or did it myself": "Family, DIY, house help or landlord",
                "House help": "Family, DIY, house help or landlord",
                "Landlord": "Family, DIY, house help or landlord",
                "Same professional directly": "Same professional directly"}
HOUSEHOLD = {"renter": "Renter", "elderly parents": "Elderly parents", "couple": "Couple",
             "single or flatmates": "Single or flatmates", "family with kids": "Family with kids"}
FOUND = {"society or landlord": "Society or landlord", "friend or family": "Friend or family",
         "search": "Search", "social media": "Social media", "ad or app store": "Ad or app store"}


def s(v):
    return "" if pd.isna(v) else str(v).strip()


def build_maps(fa):
    maps = {}
    for field, (col, code, empty) in FREE.items():
        answers = sorted(fa[col].dropna().astype(str).str.strip().unique())
        assert len(answers) == len(code), f"{field}: {len(answers)} answers vs {len(code)} codes"
        maps[field] = {a: (VALS[field][int(c) - 1] if c != "0" else empty) for a, c in zip(answers, code)}
    return maps


def main(path):
    x = pd.read_excel(path, sheet_name=None)
    raw, fa, summ = x["5 Raw Data"], x["2 Feedback Analysis"], x["1 Summary"]
    run_id = s(fa["Run ID"].iloc[0])

    rec = pd.DataFrame({
        "record_id": raw["Post ID"].map(s), "source": raw["Source"].map(SRC),
        "type": raw["Type"].map(s), "title": raw["Title / Context"].map(s),
        "text": raw["Text"].map(s), "author_hash": "", "rating": raw["Rating"].map(s),
        "likes": raw["Likes"].map(s), "date": pd.to_datetime(raw["Post Date"], errors="coerce").dt.date.astype(str).replace("NaT", ""),
        "link": raw["Link"].map(s), "query": raw["Found By (search)"].map(s),
        "community": raw["Channel / Community"].map(s), "collected_at": raw["Collected At"].map(s),
        "status": raw["Status"].map(STATUS).fillna("Dropped: other"), "run_id": run_id,
    })

    maps = build_maps(fa)
    with open("data/seed/freetext_mapping.json", "w", encoding="utf-8") as fh:
        json.dump(maps, fh, ensure_ascii=False, indent=1)

    rows = []
    for _, r in fa.iterrows():
        themes = [t.strip() for t in s(r["Theme(s)"]).split(",") if t.strip()]
        relevant = "No" if ("Not relevant" in themes or s(r["Tree Branch"]) == "Not relevant") else "Yes"
        themes = [t for t in themes if t != "Not relevant"] or ["Other"]
        turn = maps["turn_to_next"].get(s(r["Q3 Who they turn to next time"]), NS)
        if turn == NS:
            turn = USED_INSTEAD.get(s(r["Used Instead"]), NS)
        lab = {
            "record_id": s(r["Post ID"]), "relevant": relevant, "speaker": s(r["Speaker"]) or "Other",
            "category": s(r["Q7 Category"]) or NS, "return_status": s(r["Return Status"]) or NS,
            "went_wrong": s(r["Something Went Wrong?"]) or NS, "themes": themes,
            "need_trigger": maps["need_trigger"].get(s(r["Q2 How & when they decided it was needed"]), NS),
            "planning_mode": s(r["Planning Mode"]) or NS,
            "expectation_after": maps["expectation_after"].get(s(r["Q1 What they expect after the service"]), NS),
            "turn_to_next": turn,
            "outside_app": [maps["outside_app"].get(s(r["Q5 What they do outside the app"]), "None stated")],
            "unmet_need": maps["unmet_need"].get(s(r["Q8 Unmet need"]), "None stated"),
            "household": HOUSEHOLD.get(s(r["Q7 Household"]), NS),
            "found_via": FOUND.get(s(r["Q7 Found UC via"]), NS),
            "return_timing": s(r["Return Timing"]) or NS, "country": s(r["Country"]) or NS,
            "city": s(r["Q7 City"]) or NS, "evidence_quote": s(r["Evidence Quote"]),
            "summary": s(r["Q4 Why they did / didn't book again"]),
        }
        text = rec.loc[rec["record_id"] == lab["record_id"], "text"]
        text = text.iat[0] if len(text) else s(r["Post (cleaned)"])
        fails = check(lab, text)
        lab["themes"] = " | ".join(lab["themes"])
        lab["outside_app"] = " | ".join(lab["outside_app"])
        rows.append({**lab, "gate_status": "rejected" if fails else "passed_first",
                     "gate_fails": "; ".join(fails), "first_fails": "",
                     "model": "Gemini via n8n", "run_id": run_id,
                     "source": SRC.get(s(r["Source"]), ""), "link": s(r["Link"]),
                     "date": s(r["Post Date"])[:10], "rating": s(r["Rating"]),
                     "text": text})
    coded = pd.DataFrame(rows)

    # posts n8n labelled that are not in the raw tab: add them as records too
    missing = coded[~coded["record_id"].isin(rec["record_id"])]
    if len(missing):
        add = missing[["record_id", "source", "text", "link", "date", "rating"]].assign(
            status="Candidate", run_id=run_id, type="", title="", author_hash="", likes="",
            query="", community="", collected_at="")
        rec = pd.concat([rec, add], ignore_index=True)

    os.makedirs("data", exist_ok=True)
    rec.to_csv("data/records.csv", index=False)
    coded.drop(columns=["text"]).to_csv("data/coded.csv", index=False)

    collected_line = summ.loc[summ["Item"] == "Data analysed", "Detail"]
    log = {
        "project": "Urban Company repeat bookings",
        "models": {"labelling": "Gemini (n8n run, 24 Nov 2026); new runs: Gemini via run.py",
                   "free-text grouping": "claude-opus-5-5 (in session, seed only)",
                   "ask the engine": "Gemini"},
        "seed": {"run_id": run_id, "file": "Urban Company Discovery Engine - Data (final)",
                 "n8n_note": s(collected_line.iat[0]) if len(collected_line) else "",
                 "collected_before_dedupe": 5087,
                 "sample_note": "The n8n run coded a 1,000-post sample of candidates; run.py codes every candidate."},
        "runs": [{"at": run_id, "step": "seed import", "records": len(rec), "coded": len(coded),
                  "gate_counts": coded["gate_status"].value_counts().to_dict()}],
    }
    json.dump(log, open("data/run_log.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("records", len(rec), rec["status"].value_counts().to_dict())
    print("coded", len(coded), coded["gate_status"].value_counts().to_dict())
    fails = coded.loc[coded["gate_fails"] != "", "gate_fails"].str.split("; ").explode()
    print(fails.str.slice(0, 60).value_counts().head(15))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/seed/n8n_final.xlsx")
