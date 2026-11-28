"""Scores the failure check and the customer messages against the golden set.

    python mvp/eval/run_eval.py            # trained model + rules (uses Gemini instead if GEMINI_API_KEY is set)
    python mvp/eval/run_eval.py --rules    # keyword rules only, to compare

Writes mvp/eval/report.json, which the app shows under "How it works and quality".
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from core import detect, message, remedy  # noqa: E402
from core.cases import Booking  # noqa: E402
from core.llm import Gemini  # noqa: E402

# Expected labels were written from the research themes. Check them by hand before quoting the score,
# then change this line to "labelled by hand".
LABEL_STATUS = "draft, to be checked by hand"


def _int(x: str):
    return int(x) if x.strip() else None


def booking(row: dict) -> Booking:
    return Booking(row["service"], "Test Pro", "Today, 4:00 PM",
                   _int(row["billed"]) or 999, event=row["event"], rating=_int(row["rating"]),
                   text=row["text"], late_min=_int(row["late_min"]) or 0,
                   cancel_min_before=_int(row["cancel_min_before"]) or 0,
                   quoted=_int(row["quoted"]), billed=_int(row["billed"]))


def main(force_rules: bool = False):
    llm = None if force_rules else Gemini()
    use_model = not force_rules
    rows = list(csv.DictReader(open(HERE / "golden_set.csv", encoding="utf-8")))
    out, type_right, safety_total, safety_person, msg_total, msg_clean = [], 0, 0, 0, 0, 0
    modes = set()
    for r in rows:
        b = booking(r)
        a = detect.assess(b, llm, use_model=use_model)
        modes.add(a.mode)
        p = remedy.plan(b, a)
        m = message.write(b, p, remedy.message_facts(b, p), llm)
        ok = a.type == r["expected_type"]
        type_right += ok
        if r["expected_type"] == "damage_safety":
            safety_total += 1
            safety_person += a.route == "person"
        if p["route"] != "none":
            msg_total += 1
            clean = all(c["passed"] for c in m.checks if c["name"] not in ("AI available", "AI draft passed checks"))
            msg_clean += clean
        out.append({"id": r["id"], "customer_words": r["text"] or f"({r['event']}, no words)",
                    "expected": r["expected_type"], "got": a.type, "pass": "✓" if ok else "✗",
                    "route": a.route, "label_mode": a.mode, "message_mode": m.mode, "note": r["note"]})
    mode = ("AI (Gemini) with rules fallback" if "ai" in modes else
            "trained model + rules (no API key)" if "model" in modes else
            "rules only" if modes == {"rules"} else "rules fallback (AI failed)")
    report = {
        "run_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y %H:%M"),
        "mode": mode, "labels": LABEL_STATUS,
        "summary": {"total": len(rows), "type_right": type_right, "safety_total": safety_total,
                    "safety_to_person": safety_person, "messages_total": msg_total, "messages_clean": msg_clean},
        "cases": out,
    }
    (HERE / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    s = report["summary"]
    print(f"{mode}: right type {s['type_right']}/{s['total']} · safety to a person {s['safety_to_person']}/"
          f"{s['safety_total']} · messages clean {s['messages_clean']}/{s['messages_total']}")
    for c in out:
        if c["pass"] != "✓":
            print(f"  ✗ {c['id']}: expected {c['expected']}, got {c['got']} · {c['customer_words']}")


if __name__ == "__main__":
    main(force_rules="--rules" in sys.argv)
