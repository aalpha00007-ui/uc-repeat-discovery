"""Demo bookings, services and professionals. All made up; the problems come from our research."""
from __future__ import annotations

from dataclasses import dataclass, field

SERVICES = {
    "AC service": {"category": "AC & appliances", "price": 599, "noun": "AC service",
                   "check": "Is your AC cooling properly now?"},
    "Full home deep cleaning": {"category": "Cleaning", "price": 3499, "noun": "deep cleaning",
                                "check": "Is your home as clean as you expected?"},
    "Bathroom cleaning": {"category": "Cleaning", "price": 899, "noun": "bathroom cleaning",
                          "check": "Are your bathrooms clean now?"},
    "Salon at home (waxing + facial)": {"category": "Salon & spa", "price": 1299, "noun": "salon service",
                                        "check": "Are you happy with your salon service now?"},
    "Tap and fitting repair": {"category": "Electrician, plumber, carpenter", "price": 259, "noun": "tap repair",
                               "check": "Is the tap working properly now?"},
    "Pest control (cockroaches)": {"category": "Pest control", "price": 1099, "noun": "pest control",
                                   "check": "Are the cockroaches gone now?"},
    "Switchboard repair": {"category": "Electrician, plumber, carpenter", "price": 199, "noun": "switchboard repair",
                           "check": "Is the switchboard working properly now?"},
}

# Top-rated professionals offered for a redo or a replacement (made up).
PROS = {
    "AC & appliances": [("Imran R.", 4.9, 1200), ("Suresh P.", 4.8, 940)],
    "Cleaning": [("Priya S.", 4.9, 860), ("Anil K.", 4.8, 1240)],
    "Salon & spa": [("Meena D.", 4.9, 640), ("Farah A.", 4.8, 910)],
    "Electrician, plumber, carpenter": [("Ravi T.", 4.8, 980), ("Joseph M.", 4.9, 720)],
    "Pest control": [("Kiran B.", 4.8, 530), ("Vikas N.", 4.9, 610)],
}


@dataclass
class Booking:
    service: str
    pro: str
    when: str                      # e.g. "Today, 11:00 AM"
    paid: int
    event: str = "done"            # done | cancelled | late
    rating: int | None = None      # 1-5, None if no rating yet
    text: str = ""                 # what the customer wrote, any language
    late_min: int = 0
    cancel_min_before: int = 0
    quoted: int | None = None
    billed: int | None = None
    extra: dict = field(default_factory=dict)

    @property
    def category(self) -> str:
        return SERVICES[self.service]["category"]

    def key(self) -> str:
        return "|".join(str(x) for x in (self.service, self.pro, self.paid, self.event, self.rating, self.text,
                                          self.late_min, self.cancel_min_before, self.quoted, self.billed))


SCENARIOS = [
    {"label": "AC service: rated 2 stars, \"cooling still weak\"",
     "research": "Poor job, redo or refund: the most common problem in our research (167 of 265 posts where "
                 "something went wrong).",
     "booking": Booking("AC service", "Rakesh V.", "Today, 11:00 AM", 599, rating=2,
                        text="Cooling still weak, he left in 20 minutes.")},
    {"label": "Deep cleaning: the professional cancelled 40 minutes before",
     "research": "Cancelled or no-show: the second most common problem (88 posts), and named by 38% of customers "
                 "who said they won't book again.",
     "booking": Booking("Full home deep cleaning", "Sunita K.", "Today, 4:00 PM", 3499, event="cancelled",
                        cancel_min_before=40)},
    {"label": "Plumber: quoted ₹259, billed ₹521",
     "research": "Upfront, fair price: the third biggest unmet need in our research (38 posts).",
     "booking": Booking("Tap and fitting repair", "Mahesh G.", "Yesterday, 6:00 PM", 521, rating=2,
                        text="Bill went from 259 to 521 for a small tap fitting.", quoted=259, billed=521)},
    {"label": "Pest control: \"cockroaches back in a week\" (Hinglish)",
     "research": "Poor job, redo or refund. Many customers write in Hindi or Hinglish, so the check has to read both.",
     "booking": Booking("Pest control (cockroaches)", "Deepak S.", "8 days ago", 1099, rating=2,
                        text="Ek hafte mein cockroach wapas aa gaye, lagta hai sirf paani spray kiya.")},
    {"label": "Salon at home: 45 minutes late and rushed",
     "research": "Late arrival plus a rushed job, a common pair in salon and spa posts.",
     "booking": Booking("Salon at home (waxing + facial)", "Neha J.", "Today, 2:00 PM", 1299, event="late",
                        late_min=45, rating=2, text="Came 45 minutes late and rushed through everything.")},
    {"label": "Bathroom cleaning: acid took the shine off the taps",
     "research": "Damage cases are rare but serious. They always go to a person, never to an automatic offer.",
     "booking": Booking("Bathroom cleaning", "Ajay M.", "Yesterday, 10:00 AM", 899, rating=1,
                        text="The acid he used damaged all my bathroom fittings, the chrome is gone.")},
    {"label": "Switchboard repair: rated 5 stars (nothing went wrong)",
     "research": "A control case: a happy customer should see nothing extra and get no offer.",
     "booking": Booking("Switchboard repair", "Sanjay L.", "Today, 9:00 AM", 199, rating=5,
                        text="Quick and neat work, thank you.")},
]


def stars(n: int | None) -> str:
    if not n:
        return "No rating yet"
    return "★" * n + "☆" * (5 - n)


def inr(x: float | int) -> str:
    x = int(round(x))
    s = str(x)
    if len(s) > 3:   # Indian grouping: 1,23,456
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"₹{s}"
