"""Step 2, the message the customer reads: AI drafts it from code's facts, code checks it, templates back it up."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from core.cases import SERVICES, Booking, inr

MAX_WORDS = 60


@dataclass
class Message:
    text: str
    mode: str                      # ai | template
    checks: list = field(default_factory=list)
    model: str | None = None


TITLES = {
    "fix": "Sorry it wasn't right. Let's fix it.",
    "rescue": "Your professional can't make it.",
    "credit": "Sorry for the wait.",
    "refund_diff": "Sorry about the bill.",
    "person": "This needs a person, not an app screen.",
    "none": "",
}


def template(b: Booking, p: dict) -> str:
    r = p["route"]
    if r == "fix":
        text = (f"Sorry your {SERVICES[b.service]['noun']} wasn't done right. You can have a free redo with a top-rated "
                f"professional, or a full refund of {inr(p['refund'])}. No forms and no chat needed.")
        if p["credit"]:
            text += f" We've also added a {inr(p['credit'])} credit for the late start."
        return text
    if r == "rescue":
        return (f"Sorry, {b.pro} can't make your {b.when.split(', ')[-1]} booking. We've waived the cancellation "
                f"fee and added a {inr(p['credit'])} credit. Two top-rated professionals near you can come today, "
                f"or you can pick another day or take a full refund.") if p["credit"] else \
               (f"Sorry, {b.pro} can't make your booking. We've waived the cancellation fee. Two top-rated "
                f"professionals near you can come instead, or you can pick another day or take a full refund.")
    if r == "credit":
        return (f"Sorry {b.pro} was {b.late_min} minutes late. We've added a {inr(p['credit'])} credit to your "
                f"account. If anything wasn't done properly, you can ask for a free redo.")
    if r == "refund_diff":
        return (f"You were quoted {inr(p['quoted'])} and charged {inr(p['billed'])}. We're refunding the "
                f"difference of {inr(p['diff'])} to your original payment.")
    if r == "person":
        text = (f"We're sorry. This needs a person, so a case manager will call you within {p['callback_min']} "
                f"minutes to sort it out.")
        if p["damage_cover"]:
            text += f" Damage is covered by our protection of up to {inr(p['damage_cover'])}."
        return text
    return ""


# ---------------------------------------------------------------- gates

BLAME = [r"\byou should have\b", r"\byour fault\b", r"\byou didn'?t\b", r"\byou forgot\b", r"\bunfortunately you\b",
         r"\bas per (our )?policy\b"]
OVERPROMISE = [r"\bguarantee", r"\bnever happen again\b", r"\bwill never\b", r"\b100\s?%", r"\bpromise\b",
               r"\balways\b"]
PRESSURE = [r"\bhurry\b", r"\bact now\b", r"\bonly today\b", r"\blast chance\b", r"\bexpires? soon\b",
            r"\blimited time\b", r"\bdon'?t miss\b"]


def numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def allowed_numbers(facts: dict) -> set[str]:
    return numbers(json.dumps(facts, ensure_ascii=False))


def run_gates(text: str, facts: dict) -> list[dict]:
    t = text.replace("’", "'")
    checks = []
    stray = sorted(numbers(t) - allowed_numbers(facts))
    checks.append({"name": "Numbers match the booking", "passed": not stray,
                   "detail": "every number comes from code" if not stray else f"made-up numbers: {stray}"})
    for name, pats, ok in (("No blame on the customer", BLAME, "no blame found"),
                           ("No promises we can't keep", OVERPROMISE, "no over-promise found"),
                           ("No pressure", PRESSURE, "no pressure language")):
        hits = [p for p in pats if re.search(p, t, re.I)]
        checks.append({"name": name, "passed": not hits, "detail": ok if not hits else f"matched: {hits}"})
    words = len(t.split())
    checks.append({"name": "Short enough to read", "passed": 0 < words <= MAX_WORDS, "detail": f"{words} words"})
    return checks


SYSTEM = """You write the short message an Urban Company customer sees right after a booking went wrong.
Rules:
1. Use ONLY the facts given. Copy every number and amount exactly as written. Never invent a number, time, name or offer.
2. Start with a plain apology that names what went wrong. Never blame the customer.
3. Say what is already done (for example a fee waived or credit added) and what they can choose. The buttons are shown below your message.
4. No promises you can't keep (never "guarantee", "never again", "always"). No pressure or urgency.
5. Warm, plain English. At most 50 words. No headings, lists or emojis."""


def write(b: Booking, p: dict, facts: dict, llm=None) -> Message:
    fallback = template(b, p)
    if p["route"] == "none":
        return Message("", "template", [])
    if llm is None or not getattr(llm, "available", False):
        return Message(fallback, "template", run_gates(fallback, facts))
    user = f"What happened: {p['route']}.\nFacts: {json.dumps(facts, ensure_ascii=False)}"
    feedback, failed = "", []
    for _attempt in range(2):
        try:
            draft = llm.text(SYSTEM, user + feedback).strip()
        except Exception as e:  # noqa: BLE001
            checks = [{"name": "AI available", "passed": False, "detail": str(e)[:140]},
                      {"name": "Template used instead", "passed": True, "detail": "written answer shown"}]
            return Message(fallback, "template", checks + run_gates(fallback, facts))
        checks = run_gates(draft, facts)
        if all(c["passed"] for c in checks):
            return Message(draft, "ai", checks, getattr(llm, "last_model", None))
        failed = [f"{c['name']}: {c['detail']}" for c in checks if not c["passed"]]
        feedback = "\n\nYour last draft broke these rules, fix them:\n- " + "\n- ".join(failed)
    checks = [{"name": "AI draft passed checks", "passed": False,
               "detail": "blocked after one retry: " + "; ".join(failed)[:200]},
              {"name": "Template used instead", "passed": True, "detail": "written answer shown"}]
    return Message(fallback, "template", checks + run_gates(fallback, facts))
