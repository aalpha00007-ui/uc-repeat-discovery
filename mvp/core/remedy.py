"""Steps 2 and 4, Fix and Win back: code decides every rupee, slot and route. The AI never sets money."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from core.cases import PROS, SERVICES, Booking, inr
from core.detect import Assessment

IST = timezone(timedelta(hours=5, minutes=30))
WAIT_CREDIT = 100            # credit when a professional cancels late or arrives 30+ min late
OFFER_PCT = {"low": 10, "medium": 15, "high": 20}
OFFER_CAP = 300              # max discount on the next booking, in rupees
OFFER_DAYS = 60              # offer validity, comfortably inside the 90-day window
CALLBACK_MIN = 30
DAMAGE_COVER = 10000         # UC's existing damage protection, up to this amount
REDO_HOURS = 48


def now_ist() -> datetime:
    return datetime.now(IST)


def _fmt(dt: datetime, now: datetime) -> str:
    day = "Today" if dt.date() == now.date() else ("Tomorrow" if dt.date() == (now + timedelta(days=1)).date()
                                                   else dt.strftime("%a %d %b"))
    return f"{day}, {dt.strftime('%I:%M %p').lstrip('0')}"


def redo_slots(now: datetime | None = None) -> list[str]:
    """Free redo slots inside the next 48 hours (demo: fixed times tomorrow and the day after)."""
    now = now or now_ist()
    base = (now + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    times = [base.replace(hour=10), base.replace(hour=13), base.replace(hour=17),
             (base + timedelta(days=1)).replace(hour=10)]
    return [_fmt(t, now) for t in times if t - now <= timedelta(hours=REDO_HOURS + 24)]


def replacements(b: Booking, now: datetime | None = None) -> list[dict]:
    """Two top-rated professionals nearby who can come soon after the original slot (demo data)."""
    now = now or now_ist()
    m = re.search(r"(\d{1,2}):(\d{2}) ?(AM|PM)", b.when, re.I)
    if m and "today" in b.when.lower():
        hour = int(m.group(1)) % 12 + (12 if m.group(3).upper() == "PM" else 0)
        base = now.replace(hour=hour, minute=int(m.group(2)), second=0, microsecond=0)
        times = [base + timedelta(minutes=30), base + timedelta(hours=2)]
    else:
        base = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        times = [base, base + timedelta(hours=2)]
    out = []
    for (name, rating, jobs), t in zip(PROS[b.category], times):
        label = f"Today, {t.strftime('%I:%M %p').lstrip('0')}" if t.date() == base.date() and "today" in \
            b.when.lower() else _fmt(t, now)
        out.append({"name": name, "rating": rating, "jobs": jobs, "time": label})
    return out


def offer(a: Assessment, b: Booking) -> dict:
    pct = OFFER_PCT[a.severity]
    return {"pct": pct, "cap": OFFER_CAP, "days": OFFER_DAYS,
            "text": f"{pct}% off your next booking, any service, up to {inr(OFFER_CAP)}, valid {OFFER_DAYS} days",
            "why": f"Sized by code: {a.severity} severity gives {pct}%, capped at {inr(OFFER_CAP)}. "
                   f"One offer per customer per 90 days."}


def plan(b: Booking, a: Assessment, now: datetime | None = None) -> dict:
    """Everything the customer can be offered, with the facts the message is allowed to mention."""
    now = now or now_ist()
    route = a.route
    p = {"route": route, "service": b.service, "pro": b.pro, "paid": b.paid, "check": SERVICES[b.service]["check"],
         "credit": 0, "fee_waived": False, "refund": 0, "slots": [], "replacements": [], "top_pro": None,
         "diff": 0, "callback_min": 0, "damage_cover": 0}
    if (b.event == "late" and b.late_min >= 30) or (b.event == "cancelled" and b.cancel_min_before <= 180):
        p["credit"] = WAIT_CREDIT
    if route == "fix":
        p["slots"] = redo_slots(now)
        name, rating, jobs = PROS[b.category][0]
        p["top_pro"] = {"name": name, "rating": rating, "jobs": jobs}
        p["refund"] = b.paid
    elif route == "rescue":
        p["fee_waived"] = True
        p["replacements"] = replacements(b, now)
        p["refund"] = b.paid
    elif route == "credit":
        p["credit"] = WAIT_CREDIT
        p["slots"] = redo_slots(now)
    elif route == "refund_diff":
        quoted = b.quoted or 0
        billed = b.billed or b.paid
        p["diff"] = max(0, billed - quoted) if quoted else 0
        p["quoted"], p["billed"] = quoted, billed
    elif route == "person":
        p["callback_min"] = CALLBACK_MIN
        p["refund"] = b.paid
        if a.type == "damage_safety":
            p["damage_cover"] = DAMAGE_COVER
    return p


def message_facts(b: Booking, p: dict) -> dict:
    """The only facts the AI may use in its message. Every number it writes must come from here."""
    f = {"service": b.service, "professional": b.pro, "booking_time": b.when, "amount_paid": inr(b.paid)}
    if b.event == "late":
        f["minutes_late"] = b.late_min
    if b.event == "cancelled":
        f["cancelled_minutes_before"] = b.cancel_min_before
    if p["credit"]:
        f["credit_added"] = inr(p["credit"])
    if p["fee_waived"]:
        f["cancellation_fee"] = "waived"
    if p["route"] in ("fix", "rescue") and p["refund"]:
        f["full_refund_available"] = inr(p["refund"])
    if p["route"] == "fix":
        f["free_redo"] = f"with a top-rated professional within {REDO_HOURS} hours"
    if p["route"] == "rescue":
        f["replacements"] = [f"{r['name']} at {r['time']}" for r in p["replacements"]]
    if p["route"] == "refund_diff":
        f.update({"quoted": inr(p["quoted"]), "billed": inr(p["billed"]), "refund_of_difference": inr(p["diff"])})
    if p["route"] == "person":
        f["callback"] = f"a person calls within {p['callback_min']} minutes"
        if p["damage_cover"]:
            f["damage_cover"] = f"up to {inr(p['damage_cover'])}"
    return f
