"""Step 1, Notice: decide whether a booking went wrong, how badly, and who should handle it.

Pipeline: hard signals (code) -> AI reads the customer's own words -> quality gates -> retry once -> rules.
Code always has the last word on safety: damage, theft or harassment words go to a person.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from core.cases import Booking

TYPES = {
    "poor_job": "Poor or incomplete job",
    "no_show": "Professional cancelled or didn't come",
    "late": "Professional arrived very late",
    "overcharge": "Charged more than quoted",
    "damage_safety": "Damage, theft or safety issue",
    "behaviour": "Rude or unprofessional behaviour",
    "no_problem": "No problem found",
}
SHORT = {
    "poor_job": "Poor job", "no_show": "No-show", "late": "Late arrival", "overcharge": "Overcharged",
    "damage_safety": "Safety", "behaviour": "Behaviour", "no_problem": "None",
}
ROUTE = {
    "poor_job": "fix", "no_show": "rescue", "late": "credit", "overcharge": "refund_diff",
    "damage_safety": "person", "behaviour": "person", "no_problem": "none",
}
ROUTE_LABEL = {
    "fix": "Offer a free redo or a refund in the app",
    "rescue": "Offer a replacement professional now",
    "credit": "Add a credit for the wait",
    "refund_diff": "Refund the difference automatically",
    "person": "Hand to a person (callback in 30 min)",
    "none": "Nothing to do",
}
SEVERITIES = ("low", "medium", "high")
FAULTS = ("professional", "customer", "external", "unclear")

# Words that always send a case to a person, whatever the AI says (English, Hindi, Hinglish).
SAFETY = re.compile(
    r"damag|\bbroke\b|\bbroken\b|crack|\bstole|stolen|theft|\bmissing\b|burn|injur|\bhurt|electric shock|"
    r"\bshock\b|spark|\bfire\b|harass|unsafe|\bdrunk\b|touched me|threat|chori|tod diya|toot gay|"
    r"jal gay|nuksan", re.I)
BEHAVIOUR = re.compile(
    r"\brude\b|misbehav|attitude|shout|argu|\byell|abuse|demand(ed)? (a )?tip|asked for (a )?tip|"
    r"pay (him|her|them) directly|personal number|his (own )?number|her (own )?number|outside the app|"
    r"badtameez|gaali|cash only", re.I)
OVERCHARGE = re.compile(
    r"overcharg|over charg|charged (me )?(more|extra)|charged (me )?(rs\.? ?|₹)?\d+ (extra|more)|"
    r"\d+ (rupees )?extra|extra charge|extra money|hidden (charge|cost)|"
    r"more than (quoted|shown|the estimate)|bill (went|was) (up|higher|from)|went from \d|quoted|estimate|"
    r"zyada paise|extra paise|paise zyada", re.I)
POOR = re.compile(
    r"not (fixed|working|cooling|cleaned|clean|done|repaired|properly)|still (not|weak|leak|dirty|warm|hot|the same)|"
    r"\bstill\b.*\b(weak|dirty|problem|issue)|incomplete|half (done|cleaned|job)|left (early|in \d+|after \d+)|"
    r"rushed|didn'?t (work|fix|clean|finish|do|come back)|same (problem|issue)|dirty|stains? (left|still)|"
    r"\bpoor\b|\bworst\b|useless|waste of money|came back|wapas aa|back in a week|ineffective|"
    r"(only|just) (sprayed )?water|paani spray|abhi bhi|thanda nahi|theek nahi|theek se|saaf nahi|nahi hua|"
    r"kaam nahi|adhura|aadha kaam|"
    r"no difference|didn'?t help|not satisfied", re.I)
POSITIVE = re.compile(r"\b(good|great|excellent|neat|nice|thank|happy|perfect|on time|clean|polite|"
                      r"satisfied|amazing|badhiya|accha|achha)\b", re.I)


@dataclass
class Assessment:
    type: str
    severity: str
    fault: str
    evidence: str
    mode: str                         # ai | rules | rules_fallback
    checks: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    model: str | None = None
    prob: float | None = None         # trained model: chance that something went wrong

    @property
    def route(self) -> str:
        return ROUTE[self.type]


# ---------------------------------------------------------------- helpers

def _clip(text: str, m: re.Match | None, width: int = 70) -> str:
    """The customer's own words around a match, so evidence is always a real quote."""
    if not text:
        return ""
    if not m:
        return text[:width].strip()
    start = max(0, text.rfind(".", 0, m.start()) + 1)
    end = text.find(".", m.end())
    end = len(text) if end == -1 else end
    piece = text[start:end].strip()
    return piece[:width].strip()


def hard_signals(b: Booking) -> list[str]:
    out = []
    if b.event == "cancelled":
        out.append(f"professional cancelled {b.cancel_min_before} min before the slot")
    if b.event == "late" and b.late_min:
        out.append(f"professional arrived {b.late_min} min late")
    if b.rating:
        out.append(f"customer rated {b.rating} out of 5")
    if b.quoted and b.billed and b.billed > b.quoted:
        out.append(f"billed {b.billed} against a quote of {b.quoted}")
    return out


# ---------------------------------------------------------------- rules (fallback and baseline)

def rules(b: Booking) -> tuple[str, str, str, str]:
    t = b.text or ""
    if b.event == "cancelled":
        sev = "high" if b.cancel_min_before <= 180 else "medium"
        return "no_show", sev, "professional", ""
    m = SAFETY.search(t)
    if m:
        return "damage_safety", "high", "professional", _clip(t, m)
    m = BEHAVIOUR.search(t)
    if m:
        return "behaviour", "high" if (b.rating or 5) <= 2 else "medium", "professional", _clip(t, m)
    m = OVERCHARGE.search(t)
    if (b.quoted and b.billed and b.billed > b.quoted) or m:
        return "overcharge", "medium", "professional", _clip(t, m)
    m = POOR.search(t)
    if not m and b.event == "late" and b.late_min >= 30:
        return "late", "medium" if b.late_min >= 60 else "low", "professional", _clip(t, None) if t else ""
    low_rating_no_praise = b.rating is not None and b.rating <= 3 and not POSITIVE.search(t)
    if m or low_rating_no_praise:
        if b.rating == 1 or b.paid >= 2000:
            sev = "high"
        elif b.rating == 3 and not m:
            sev = "low"
        else:
            sev = "medium"
        return "poor_job", sev, "professional", _clip(t, m)
    if b.event == "late" and b.late_min >= 30:
        return "late", "medium" if b.late_min >= 60 else "low", "professional", _clip(t, None) if t else ""
    return "no_problem", "low", "unclear", ""


# ---------------------------------------------------------------- AI + gates

SYSTEM = """You help Urban Company notice when a home-service booking went wrong, so it can fix it fast.
Read the booking facts and the customer's own words (English, Hindi or Hinglish). Return JSON only:
{"failure_type": one of ["poor_job","no_show","late","overcharge","damage_safety","behaviour","no_problem"],
 "severity": one of ["low","medium","high"],
 "fault": one of ["professional","customer","external","unclear"],
 "evidence": the shortest exact phrase copied from the customer's words that shows the problem, or "" if they wrote nothing,
 "confidence": a number from 0 to 1}
Rules:
- no_show = the professional cancelled or never came. late = arrived 30+ minutes late but the job itself was fine.
- poor_job = work not done, not done properly, rushed or the problem came back. overcharge = billed more than quoted or surprise charges.
- damage_safety = anything damaged, broken, stolen, an injury, harassment or feeling unsafe. behaviour = rude, asked for tips or to pay outside the app.
- If more than one applies, pick the most serious: damage_safety > no_show > behaviour > overcharge > poor_job > late.
- no_problem only when nothing went wrong. Copy evidence exactly; never invent or translate it."""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace("’", "'")).strip(" .,!\"'")


def gates(out: dict, b: Booking) -> list[dict]:
    checks = []
    ok = (out.get("failure_type") in TYPES and out.get("severity") in SEVERITIES and out.get("fault") in FAULTS)
    checks.append({"name": "Labels are from the allowed list", "passed": ok,
                   "detail": "type, severity and cause are valid" if ok else f"got {json.dumps(out)[:120]}"})
    ev = _norm(str(out.get("evidence", "")))
    if not b.text.strip():
        ev_ok = ev == ""
        detail = "no customer words, so no quote" if ev_ok else "quoted words the customer never wrote"
    else:
        ev_ok = (ev == "" and out.get("failure_type") == "no_problem") or (ev != "" and ev in _norm(b.text))
        detail = f'"{out.get("evidence")}" is in the customer\'s words' if ev_ok else \
            f'"{out.get("evidence")}" is not in the customer\'s words'
    checks.append({"name": "Evidence is the customer's own words", "passed": ev_ok, "detail": detail})
    sig_ok, why = True, "agrees with the booking's signals"
    if b.event == "cancelled" and out.get("failure_type") not in ("no_show", "damage_safety"):
        sig_ok, why = False, "the professional cancelled, so it must be a no-show"
    elif out.get("failure_type") == "no_show" and b.event != "cancelled":
        sig_ok, why = False, "called it a no-show, but the professional came"
    elif out.get("failure_type") == "late" and b.event != "late":
        sig_ok, why = False, "called it late, but no late arrival was recorded"
    elif out.get("failure_type") == "no_problem" and b.rating and b.rating <= 2:
        sig_ok, why = False, "said no problem, but the customer rated 2 or less"
    checks.append({"name": "Matches the booking's signals", "passed": sig_ok, "detail": why})
    try:
        conf = float(out.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    checks.append({"name": "Confident enough to act", "passed": conf >= 0.6, "detail": f"confidence {conf:.2f}"})
    return checks


def safety_check(b: Booking, a: Assessment) -> Assessment:
    """Code rule: safety words always go to a person, even if the AI missed them."""
    m = SAFETY.search(b.text or "")
    if m and a.route != "person":
        a.notes.append(f'Safety words found ("{m.group(0)}"), so code sent this to a person.')
        a.type, a.severity, a.evidence = "damage_safety", "high", _clip(b.text, m)
        a.checks.append({"name": "Safety words go to a person", "passed": True, "detail": "applied: routed to a person"})
    else:
        a.checks.append({"name": "Safety words go to a person", "passed": True,
                         "detail": "routed to a person" if m else "no safety words found"})
    return a


def assess(b: Booking, llm=None, use_model: bool = True) -> Assessment:
    if llm is not None and getattr(llm, "available", False):
        user = (f"Booking facts: {json.dumps({'service': b.service, 'paid': b.paid, 'signals': hard_signals(b)})}\n"
                f"Customer's words: {json.dumps(b.text)}")
        feedback = ""
        failed = []
        for _attempt in range(2):
            try:
                out = llm.json(SYSTEM, user + feedback)
            except Exception as e:  # noqa: BLE001
                t, s, f, ev = rules(b)
                a = Assessment(t, s, f, ev, "rules_fallback",
                               [{"name": "AI available", "passed": False, "detail": str(e)[:140]},
                                {"name": "Rules used instead", "passed": True, "detail": "keyword and signal rules"}])
                return safety_check(b, a)
            checks = gates(out, b)
            if all(c["passed"] for c in checks):
                a = Assessment(out["failure_type"], out["severity"], out["fault"], str(out.get("evidence", "")),
                               "ai", checks, model=getattr(llm, "last_model", None))
                return safety_check(b, a)
            failed = [f"{c['name']}: {c['detail']}" for c in checks if not c["passed"]]
            feedback = "\n\nYour last answer broke these rules, fix them:\n- " + "\n- ".join(failed)
        t, s, f, ev = rules(b)
        a = Assessment(t, s, f, ev, "rules_fallback",
                       [{"name": "AI label passed checks", "passed": False,
                         "detail": "blocked after one retry: " + "; ".join(failed)[:200]},
                        {"name": "Rules used instead", "passed": True, "detail": "keyword and signal rules"}])
        return safety_check(b, a)
    if use_model:
        return assess_model(b)
    t, s, f, ev = rules(b)
    a = Assessment(t, s, f, ev, "rules",
                   [{"name": "Labels are from the allowed list", "passed": True, "detail": "set by rules"},
                    {"name": "Evidence is the customer's own words", "passed": (not ev) or ev in b.text,
                     "detail": f'"{ev}"' if ev else "no quote needed"}])
    return safety_check(b, a)


def assess_model(b: Booking) -> Assessment:
    """No API key needed: our trained model reads the words, signals and code rules keep it honest.

    Order: a cancellation or clear words (overcharge, behaviour, safety) set the type first. Otherwise the model
    decides whether something went wrong. If it is unsure, or it says "fine" while the customer gave 1-2 stars,
    the rating and rules decide instead.
    """
    from core import model  # local import keeps the module light for the rules-only path

    t, s, f, ev = rules(b)
    p = model.prob_problem(b.text) if b.text.strip() else None
    checks = []
    if p is not None:
        checks.append({"name": "Model read the customer's words", "passed": True,
                       "detail": f"something went wrong: {p:.0%} likely"})
    if b.event == "cancelled" or t in ("damage_safety", "behaviour", "overcharge"):
        why = "the professional cancelled" if b.event == "cancelled" else "clear words in the customer's message"
        checks.append({"name": "Type set by a signal or clear words", "passed": True, "detail": f"{SHORT[t]}: {why}"})
        return safety_check(b, Assessment(t, s, f, ev, "model" if p is not None else "rules", checks, prob=p))
    if p is None:
        checks.append({"name": "No customer words", "passed": True, "detail": "the rating and signals decide"})
        return safety_check(b, Assessment(t, s, f, ev, "rules", checks))
    lo, hi = model.UNSURE
    if lo < p < hi:
        checks.append({"name": "Model confident enough", "passed": False,
                       "detail": f"{p:.0%} is too close to call, so the rating and rules decide"})
        return safety_check(b, Assessment(t, s, f, ev, "rules_fallback", checks, prob=p))
    checks.append({"name": "Model confident enough", "passed": True,
                   "detail": f"{p:.0%} is outside the unsure zone ({lo:.0%} to {hi:.0%})"})
    if p >= hi:
        typ = t if t in ("poor_job", "late") else "poor_job"
        sev = s if typ == t else ("high" if b.rating == 1 or b.paid >= 2000 else "medium")
        checks.append({"name": "Matches the booking's signals", "passed": True, "detail": "nothing contradicts it"})
        return safety_check(b, Assessment(typ, sev, "professional", model.best_clause(b.text), "model", checks,
                                          prob=p))
    if b.rating is not None and b.rating <= 2:
        checks.append({"name": "Matches the booking's signals", "passed": False,
                       "detail": f"the model says fine, but the customer rated {b.rating} of 5, so the rating wins"})
        typ = t if t != "no_problem" else "poor_job"
        return safety_check(b, Assessment(typ, s if typ == t else "medium", "professional", ev, "rules_fallback",
                                          checks, prob=p))
    checks.append({"name": "Matches the booking's signals", "passed": True, "detail": "agrees with the rating"})
    if b.event == "late" and b.late_min >= 30:
        return safety_check(b, Assessment("late", "medium" if b.late_min >= 60 else "low", "professional", "",
                                          "model", checks, prob=p))
    return safety_check(b, Assessment("no_problem", "low", "unclear", "", "model", checks, prob=p))
