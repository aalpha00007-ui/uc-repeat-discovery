"""Quality gates run on every AI output, in code.

Gate 1  allowed values only  - every coded field uses a value from the codebook
Gate 2  exact quote          - the evidence quote appears word-for-word in the post
Gate 3  logic                - the labels don't contradict each other

An output that fails gets one retry with the failure reasons fed back to the
model; if it still fails it is rejected and excluded from every number.
"""
import re
import unicodedata

from .config import CODEBOOK, NS


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[^\w\s']", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def quote_in_text(quote: str, text: str) -> bool:
    q = _norm(quote)
    if len(q) < 8:
        return False
    return q in _norm(text)


def as_list(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if v is None or (isinstance(v, float) and v != v):
        return []
    return [x.strip() for x in str(v).split("|") if x.strip()]


def check(label: dict, text: str) -> list[str]:
    """Return a list of failure reasons (empty list = passed all gates)."""
    fails = []

    # Gate 1: allowed values only
    for field, spec in CODEBOOK.items():
        val = label.get(field)
        if spec.get("multi"):
            vals = as_list(val)
            if not vals:
                fails.append(f"G1 {field}: empty")
            for v in vals:
                if v not in spec["values"]:
                    fails.append(f"G1 {field}: '{v}' is not an allowed value")
        else:
            if val not in spec["values"]:
                fails.append(f"G1 {field}: '{val}' is not an allowed value")

    relevant = label.get("relevant") == "Yes"

    # Gate 2: exact supporting quote (only needed for relevant posts)
    if relevant and not quote_in_text(label.get("evidence_quote", ""), text):
        fails.append("G2 evidence_quote is not word-for-word in the post")

    # Gate 3: logic / consistency
    themes = set(as_list(label.get("themes")))
    if not relevant:
        # category may still describe a non-customer post (e.g. a news item about
        # cleaning), but a customer outcome on a non-customer post is a contradiction
        coded = [f for f in ("return_status", "went_wrong")
                 if label.get(f) not in (NS, None)]
        if coded:
            fails.append(f"G3 marked not relevant but still coded: {', '.join(coded)}")
    else:
        if label.get("went_wrong") == "No" and themes & {"Poor job / redo / refund", "Cancelled or no-show"}:
            fails.append("G3 says nothing went wrong but the reason is a failed or cancelled job")
        if label.get("return_timing") not in (NS, None) and label.get("return_status") != "Booked again":
            fails.append("G3 return timing given but the person did not book again")
        if label.get("return_status") == "Booked again" and "Happy, no reason to switch" not in themes \
                and label.get("turn_to_next") in ("Another app or company",):
            fails.append("G3 booked again on UC but says they turn to another app next")
        if label.get("speaker") in ("Company", "Professional") and label.get("return_status") in ("Booked again", "Stopped using"):
            fails.append("G3 a company or professional cannot have a customer return status")
    return fails
