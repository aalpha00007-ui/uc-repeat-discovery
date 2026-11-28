"""Measures the model with 5-fold cross-validation and writes model_card.json (shown in the app).

    python mvp/model/train_report.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import pandas as pd  # noqa: E402
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score, recall_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold, cross_val_predict  # noqa: E402

from core.cases import Booking  # noqa: E402
from core.detect import rules  # noqa: E402
from core.model import build  # noqa: E402


def main():
    df = pd.read_csv(HERE / "train.csv")
    y = df["label"]
    pred = cross_val_predict(build(), df["text"], y, cv=StratifiedKFold(5, shuffle=True, random_state=0))
    cm = confusion_matrix(y, pred, labels=["problem", "no_problem"])
    # Baseline: the keyword rules on the same posts, from the words alone (no rating), as the model sees them.
    rules_pred = ["problem" if rules(Booking("AC service", "x", "Today, 4:00 PM", 599, text=t))[0] != "no_problem"
                  else "no_problem" for t in df["text"]]
    card = {
        "trained_on": int(len(df)),
        "problem": int((y == "problem").sum()),
        "no_problem": int((y == "no_problem").sum()),
        "sources": df["source"].value_counts().to_dict(),
        "cv_accuracy": round(accuracy_score(y, pred), 3),
        "precision_problem": round(precision_score(y, pred, pos_label="problem"), 3),
        "recall_problem": round(recall_score(y, pred, pos_label="problem"), 3),
        "confusion": {"problem_caught": int(cm[0, 0]), "problem_missed": int(cm[0, 1]),
                      "false_alarm": int(cm[1, 0]), "fine_correct": int(cm[1, 1])},
        "rules_accuracy": round(accuracy_score(y, rules_pred), 3),
        "rules_problems_caught": int(sum(1 for a, b in zip(y, rules_pred) if a == b == "problem")),
        "labels_from": "the discovery engine's Gemini coding (went_wrong = Yes / No), gate-checked",
        "run_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y %H:%M"),
    }
    (HERE / "model_card.json").write_text(json.dumps(card, indent=1), encoding="utf-8")
    print(json.dumps(card, indent=1))


if __name__ == "__main__":
    main()
