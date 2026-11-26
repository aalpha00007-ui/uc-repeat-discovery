"""Project brief, sources and the codebook.

Everything the engine needs to know about the Urban Company brief lives here,
so the pipeline (run.py) and the dashboard (app.py) always agree on the
allowed labels. Change a label here and both sides pick it up.
"""

PROJECT = {
    "title": "Repeat Booking Discovery Engine",
    "company": "Urban Company",
    "team": "Urban Company Consumer Growth",
    "goal": (
        "Why Urban Company customers do or don't book another service "
        "within 90 days of a completed booking"
    ),
    "metric": (
        "Anchor booking = a customer's first completed booking in a core category in a "
        "chosen month (InstaHelp excluded). The customer counts as a repeat if they "
        "complete any later booking, in any category, within 90 days. Redos, warranty "
        "claims and refunded bookings do not count."
    ),
    "disclaimer": (
        "Research tool built on public customer feedback. Quotes are unverified "
        "customer claims. It ranks where to look; interviews and live data then "
        "validate."
    ),
}

# --------------------------------------------------------------------------
# Collection settings (used by engine/collect.py on your laptop)
# --------------------------------------------------------------------------
APP_IDS = {
    "play_store": "com.urbanclap.urbanclap",
    "app_store": "1032480595",
}

LOOKBACK_DAYS = 365
COUNTRY = "in"
LANG = "en"

SEARCH_QUERIES = {
    # Google Search via SerpApi (organic results, India)
    "google_search": [
        "urban company review booked again",
        "urban company stopped using why",
        "urban company vs local technician",
        "urban company professional number directly",
        "urban company deep cleaning experience",
        "urban company ac service experience",
        "urban company salon at home experience",
        "urban company warranty redo experience",
        "urban company complaint site:consumercomplaints.in",
        "urban company review site:mouthshut.com",
        "urban company site:quora.com",
    ],
    # Reddit threads, found through Google (no Reddit API needed)
    "reddit": [
        "site:reddit.com urban company booked again",
        "site:reddit.com urban company or local",
        "site:reddit.com urban company deep cleaning",
        "site:reddit.com urban company ac service",
        "site:reddit.com urban company salon",
        "site:reddit.com urban company professional directly",
        "site:reddit.com urban company stopped using",
        "site:reddit.com plumber electrician app or local india",
        "site:reddit.com snabbit vs urban company",
        "site:reddit.com pest control urban company",
    ],
    # YouTube videos whose comments we read
    "youtube": [
        "urban company review",
        "urban company deep cleaning review",
        "urban company ac service review",
        "urban company salon at home review",
        "urban company vs local",
        "urban company experience honest",
    ],
}

MAX_PER_SOURCE = {
    "play_store": 6000,
    "app_store": 500,       # Apple's public feed stops at 10 pages x 50
    "google_search": 100,   # per query
    "reddit": 20,           # threads per query
    "youtube": 15,          # videos per query (comments: up to 300 per video)
}

# --------------------------------------------------------------------------
# Prefilter (code only, no AI)
# --------------------------------------------------------------------------
MIN_CHARS = 25
SERVICE_TERMS = [
    "urban company", "urbanclap", "urban clap", " uc ", "u.c.", "uc app",
    "clean", "deep clean", "bathroom", "kitchen", "sofa", "ac ", "a.c", "air condition",
    "plumb", "electric", "carpent", "pest", "termite", "cockroach", "paint",
    "salon", "spa", "facial", "wax", "massage", "hair", "beautician", "makeup",
    "technician", "professional", "partner", "service", "booking", "booked",
    "slot", "repair", "warranty", "refund", "ro ", "purifier", "native",
]
EXCLUDE_TERMS = {
    "instahelp": ["instahelp", "insta help"],
    "outside_india": ["dubai", "abu dhabi", "uae", "singapore", "saudi", "riyadh"],
}

# --------------------------------------------------------------------------
# Codebook: every AI output must use exactly these values (gate 1)
# --------------------------------------------------------------------------
NS = "Not stated"

CODEBOOK = {
    "relevant": {
        "q": "Is this a customer, or someone close to one, talking about using or "
             "considering Urban Company home or beauty services in India?",
        "values": ["Yes", "No"],
    },
    "speaker": {
        "q": "Who is speaking?",
        "values": ["Customer", "Professional", "Company", "Other"],
    },
    "category": {
        "q": "Q7: Which service category is this about?",
        "values": ["Cleaning", "AC & appliances", "Electrician, plumber, carpenter",
                   "Salon & spa", "Pest control", "Painting", "Native products",
                   "Multiple", "InstaHelp", NS],
    },
    "return_status": {
        "q": "Where is the person in the repeat journey?",
        "values": ["Booked again", "Will book again", "Won't book again",
                   "Stopped using", NS],
    },
    "went_wrong": {
        "q": "Did something go wrong with the booking?",
        "values": ["Yes", "No", NS],
    },
    "themes": {
        "q": "Q4: Why did they, or didn't they, book again? (one or more)",
        "multi": True,
        "values": [
            "Poor job / redo / refund", "Cancelled or no-show",
            "No slot or pro available", "Job didn't feel right for UC",
            "Went direct to a known pro", "Same service due again",
            "A different need comes up", "Season or life event",
            "Someone else decides or handles it", "Didn't know UC does it",
            "UC not top of mind", "Price or add-on charges felt unfair",
            "Happy, no reason to switch", "Other",
        ],
    },
    "need_trigger": {
        "q": "Q2: What made them decide a service was needed?",
        "values": ["Something broke or urgent problem", "Routine upkeep or service due",
                   "Season, festival or weather", "Life event (moving, guests)",
                   "Personal care or no time to do it", "Offer or reminder", NS],
    },
    "planning_mode": {
        "q": "Q2: Did they plan it or react to it?",
        "values": ["Planned", "Reactive", "Avoided", NS],
    },
    "expectation_after": {
        "q": "Q1: What do they expect once the booking is complete?",
        "values": ["Same professional next time", "Warranty, redo or quick fix",
                   "Price and scope as quoted", "Follow-up or reminder for next time",
                   "Reward for coming back", "Support that responds",
                   "Job done fully and properly", NS],
    },
    "turn_to_next": {
        "q": "Q3: Who or what do they turn to next time?",
        "values": ["Urban Company again", "Same professional directly",
                   "Local provider or technician", "Another app or company",
                   "Brand service centre", "Family, DIY, house help or landlord", NS],
    },
    "outside_app": {
        "q": "Q5: What do they do outside the app?",
        "multi": True,
        "values": ["Calls a local technician", "Contacts the pro directly",
                   "Asks neighbours, society or WhatsApp groups",
                   "Asks family or friends", "Compares other apps or brands",
                   "Does it themselves or uses house help", "None stated"],
    },
    "unmet_need": {
        "q": "Q8: What unmet need does this reveal? (primary)",
        "values": [
            "Rebook or choose a trusted professional",
            "Know exactly what's included before booking",
            "Upfront, fair price (parts, add-ons, visit fee)",
            "A slot and pro when I need it, no cancellations",
            "Job done right first time, easy redo or warranty",
            "Support that resolves problems fast and fairly",
            "Know when the same service is due again",
            "Service or category available where I live",
            "Smooth, reliable app (booking, payment, alerts)",
            "None stated",
        ],
    },
    "household": {
        "q": "Q7: Household type, only if stated",
        "values": ["Family with kids", "Couple", "Single or flatmates",
                   "Elderly parents", "Renter", NS],
    },
    "found_via": {
        "q": "Q7: How did they first find Urban Company, only if stated",
        "values": ["Friend or family", "Ad or app store", "Search", "Social media",
                   "Society or landlord", NS],
    },
    "return_timing": {
        "q": "If they booked again, when?",
        "values": ["Within about 3 months", "Later than 3 months", NS],
    },
    "country": {
        "q": "Which country is this about?",
        "values": ["India", "Outside India", NS],
    },
}
# Free-text fields the model also returns
TEXT_FIELDS = ["city", "evidence_quote", "summary"]

# Which coded fields feed each research question (for the Research questions tab)
RESEARCH_QUESTIONS = [
    ("Q1", "What do customers expect once a booking is complete?", ["expectation_after"]),
    ("Q2", "How do they decide a home service is needed, and when?", ["need_trigger", "planning_mode"]),
    ("Q3", "Who or what do they turn to when they need a service again?", ["turn_to_next"]),
    ("Q4", "Why do they, or don't they, book again — in their own words?", ["themes"]),
    ("Q5", "What do they do outside the app?", ["outside_app"]),
    ("Q6", "What separates customers who return from those who don't?", []),   # own tab
    ("Q7", "How do patterns differ by category, city, household and how they found UC?", []),  # own tab
    ("Q8", "What unmet needs emerge consistently?", ["unmet_need"]),
]

# --------------------------------------------------------------------------
# PM judgement tables (editable in the dashboard)
# --------------------------------------------------------------------------
# Controllability: can a customer-side product change act on this need? 0-1
CONTROLLABILITY = {
    "Rebook or choose a trusted professional": 0.9,
    "Know exactly what's included before booking": 0.9,
    "Upfront, fair price (parts, add-ons, visit fee)": 0.6,
    "A slot and pro when I need it, no cancellations": 0.4,
    "Job done right first time, easy redo or warranty": 0.5,
    "Support that resolves problems fast and fairly": 0.5,
    "Know when the same service is due again": 1.0,
    "Service or category available where I live": 0.2,
    "Smooth, reliable app (booking, payment, alerts)": 0.8,
}

# Each reason (theme) sits on one branch of the repeat-booking metric tree
THEME_BRANCH = {
    "Same service due again": "Need arises",
    "A different need comes up": "Need arises",
    "Season or life event": "Need arises",
    "Job didn't feel right for UC": "UC is chosen",
    "Went direct to a known pro": "UC is chosen",
    "Someone else decides or handles it": "UC is chosen",
    "Didn't know UC does it": "UC is chosen",
    "UC not top of mind": "UC is chosen",
    "Price or add-on charges felt unfair": "UC is chosen",
    "Poor job / redo / refund": "Booking counts",
    "Cancelled or no-show": "Booking counts",
    "No slot or pro available": "Booking counts",
    "Happy, no reason to switch": "UC is chosen",
    "Other": "Other",
}

TOP8_CITIES = {"Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Kolkata",
               "Pune", "Ahmedabad", "Gurugram", "Noida", "Navi Mumbai", "Thane",
               "Ghaziabad", "Faridabad"}  # metro areas folded into their top-8 city
CITY_ALIASES = {"Bangalore": "Bengaluru", "Gurgaon": "Gurugram", "New Delhi": "Delhi",
                "Bombay": "Mumbai", "Calcutta": "Kolkata", "Madras": "Chennai"}

# Customer groups used across the dashboard (computed in code, never by the LLM)
RETURNED = {"Booked again", "Will book again"}
LOST = {"Won't book again", "Stopped using"}
WENT_ELSEWHERE = {"Same professional directly", "Local provider or technician",
                  "Another app or company", "Brand service centre",
                  "Family, DIY, house help or landlord"}

SOURCE_LABELS = {
    "play_store": "Play Store", "app_store": "App Store", "reddit": "Reddit",
    "google_search": "Google Search", "youtube": "YouTube", "trustpilot": "Trustpilot",
    "social_media": "Social media", "complaint_sites": "Complaint sites",
    "quora": "Quora", "investor_reports": "Investor reports",
}
