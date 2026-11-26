"""'Ask the engine': grounded answers with four visible gates.

Gate A  scope            the question is about customers and repeat bookings,
                         not about a named person, stock price or advice
Gate B  enough evidence  at least MIN_EVIDENCE matching posts were retrieved
Gate C  cited claims     every claim carries a quote found word-for-word in a
                         retrieved post (claims without one are dropped)
Gate D  numbers in code  the model may not write numbers; counts shown next to
                         the answer are computed here from the labels

If a gate fails the user gets the evidence, not an AI guess.
"""
import math
import re
from collections import Counter

import pandas as pd

from .config import PROJECT
from .gates import quote_in_text

MIN_EVIDENCE = 5
TOP_K = 25
OUT_OF_SCOPE = [r"\bshare price\b", r"\bstock\b", r"\binvest", r"\bipo\b", r"phone number",
                r"\baddress of\b", r"\bwho is\b", r"\bname of the (pro|technician|beautician)",
                r"\bsalary\b", r"\bhack\b", r"\bpassword\b"]
IN_SCOPE_HINTS = ["customer", "book", "repeat", "return", "again", "service", "clean", "salon",
                  "ac", "plumb", "electric", "pest", "paint", "pro", "technician", "price",
                  "why", "what", "how", "local", "app", "warranty", "slot", "cancel", "need"]
STOP = set("the a an and or of to in on for is are was were be it this that with as at by from "
           "i my me we our you your they their them do does did not no so but if then than "
           "what why how when which who whom urban company uc".split())


def _tok(s):
    return [t for t in re.findall(r"[a-z0-9']+", str(s).lower()) if t not in STOP and len(t) > 1]


class Retriever:
    """Plain BM25 over post text + summary + labels."""

    def __init__(self, df: pd.DataFrame):
        self.df = df.reset_index(drop=True)
        docs = (df["text"].fillna("") + " " + df["summary"].fillna("") + " " +
                df["themes"].fillna("") + " " + df["unmet_need"].fillna("") + " " +
                df["category"].fillna("")).tolist()
        self.toks = [_tok(d) for d in docs]
        self.avg = sum(map(len, self.toks)) / max(len(self.toks), 1)
        dfreq = Counter(t for d in self.toks for t in set(d))
        n = len(self.toks)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in dfreq.items()}
        self.tf = [Counter(d) for d in self.toks]

    def search(self, q, k=TOP_K, k1=1.4, b=0.75):
        qt = _tok(q)
        scores = []
        for i, tf in enumerate(self.tf):
            s, L = 0.0, len(self.toks[i]) or 1
            for t in qt:
                if t in tf:
                    s += self.idf.get(t, 0) * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * L / self.avg))
            scores.append(s)
        out = self.df.assign(score=scores)
        out = out[out["score"] > 0].sort_values("score", ascending=False).head(k)
        return out


def scope_gate(q: str):
    ql = q.lower()
    for pat in OUT_OF_SCOPE:
        if re.search(pat, ql):
            return False, "This tool answers questions about customer behaviour and repeat bookings, " \
                          "not about named people, stock prices or advice."
    if len(_tok(q)) < 2 or not any(h in ql for h in IN_SCOPE_HINTS):
        return False, "Ask about customers, services or repeat bookings."
    return True, "In scope"


SYSTEM = (f"You answer research questions for {PROJECT['team']} using ONLY the posts given. "
          "Write 2-5 short claims. Each claim must cite one record_id and copy a quote of 6-30 "
          "words EXACTLY from that post. Do NOT write any numbers, percentages or counts — the "
          "tool adds counts itself. Do not give advice to customers. If the posts don't answer "
          "the question, return an empty list.")
SCHEMA = {"type": "OBJECT", "properties": {"claims": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {"claim": {"type": "STRING"}, "record_id": {"type": "STRING"},
                                     "quote": {"type": "STRING"}},
    "required": ["claim", "record_id", "quote"]}}}, "required": ["claims"]}


def answer(q: str, df: pd.DataFrame, retriever: Retriever, llm=None):
    """Returns dict with gates (list of (name, passed, note)), claims, evidence, stats."""
    gates = []
    ok, note = scope_gate(q)
    gates.append(("Scope", ok, note))
    if not ok:
        return {"gates": gates, "claims": [], "evidence": pd.DataFrame(), "stats": {}}

    ev = retriever.search(q)
    enough = len(ev) >= MIN_EVIDENCE
    gates.append(("Enough evidence", enough, f"{len(ev)} matching posts (need {MIN_EVIDENCE})"))
    stats = {
        "matching_posts": len(ev),
        "returned": int((ev["group"] == "Returned").sum()),
        "lost": int((ev["group"] == "Lost the repeat").sum()),
        "nothing_wrong": int(ev["nothing_wrong"].sum()),
        "top_needs": ev["unmet_need"][~ev["unmet_need"].isin(["None stated", ""])].value_counts().head(3).to_dict(),
        "sources": ev["source"].value_counts().to_dict(),
    }
    if not enough:
        return {"gates": gates, "claims": [], "evidence": ev, "stats": stats}

    if llm is None:
        gates.append(("Cited claims", False, "No AI key set on this deployment — showing evidence only"))
        gates.append(("Numbers in code", True, "Counts below are computed from labels"))
        return {"gates": gates, "claims": [], "evidence": ev, "stats": stats}

    posts = "\n".join(f"<post record_id=\"{r.record_id}\">{r.text}</post>" for r in ev.itertuples())
    try:
        out = llm.json(SYSTEM, f"Question: {q}\n\nPosts:\n{posts}", SCHEMA, temperature=0)
        raw = out.get("claims", [])
    except Exception as e:
        gates.append(("Cited claims", False, f"AI call failed ({e}) — showing evidence only"))
        gates.append(("Numbers in code", True, "Counts below are computed from labels"))
        return {"gates": gates, "claims": [], "evidence": ev, "stats": stats}

    text_by_id = dict(zip(ev["record_id"], ev["text"]))
    kept, dropped_quote, dropped_num = [], 0, 0
    for c in raw:
        rid = str(c.get("record_id", ""))
        if rid not in text_by_id or not quote_in_text(c.get("quote", ""), text_by_id[rid]):
            dropped_quote += 1
            continue
        if re.search(r"\d", c.get("claim", "")):
            dropped_num += 1
            continue
        kept.append({"claim": c["claim"], "record_id": rid, "quote": c["quote"]})
    gates.append(("Cited claims", bool(kept),
                  f"{len(kept)} claims kept, {dropped_quote} dropped (quote not found word-for-word)"))
    gates.append(("Numbers in code", True,
                  f"{dropped_num} claims dropped for writing numbers; counts below come from labels"))
    return {"gates": gates, "claims": kept, "evidence": ev, "stats": stats}
