"""A small text model trained on our own research, so the app needs no API key.

It answers one question from the customer's own words: did something go wrong?
Training data: 468 customer posts from the discovery engine (Play Store, App Store, Trustpilot, YouTube,
Reddit), labelled problem / no problem. It trains inside the app in about a second, on every start.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline, make_union

HERE = Path(__file__).resolve().parents[1] / "model"
TRAIN = HERE / "train.csv"
CARD = HERE / "model_card.json"
UNSURE = (0.35, 0.65)     # between these, the model is unsure and the rating decides


def build():
    # Words and word pairs, plus character pieces so Hinglish spellings and typos still match.
    features = make_union(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True),
    )
    return make_pipeline(features, LogisticRegression(max_iter=2000, class_weight="balanced", C=4))


@lru_cache(maxsize=1)
def model():
    df = pd.read_csv(TRAIN)
    m = build()
    m.fit(df["text"], df["label"])
    return m


def prob_problem(text: str) -> float:
    m = model()
    i = list(m.classes_).index("problem")
    return float(m.predict_proba([text])[0][i])


def best_clause(text: str) -> str:
    """The part of the customer's words the model reads as most 'problem'."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|,\s+|\s+but\s+|\s+aur\s+", text) if len(p.strip()) > 3]
    if len(parts) <= 1:
        return text.strip()[:90]
    m = model()
    i = list(m.classes_).index("problem")
    probs = m.predict_proba(parts)[:, i]
    return parts[int(probs.argmax())][:90]


def card() -> dict:
    return json.loads(CARD.read_text()) if CARD.exists() else {}
