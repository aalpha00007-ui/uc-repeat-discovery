"""Run: python -m pytest -q mvp/tests"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import cases, detect, message, remedy  # noqa: E402
from core.cases import Booking, inr  # noqa: E402


class FakeLLM:
    """Plays back canned answers so the AI path and its gates can be tested offline."""
    available = True
    last_model = "fake"

    def __init__(self, json_answers=None, text_answers=None, fail=False):
        self.json_answers = list(json_answers or [])
        self.text_answers = list(text_answers or [])
        self.fail = fail

    def json(self, system, user):
        if self.fail:
            raise RuntimeError("down")
        return self.json_answers.pop(0)

    def text(self, system, user):
        if self.fail:
            raise RuntimeError("down")
        return self.text_answers.pop(0)


AC = Booking("AC service", "Rakesh V.", "Today, 11:00 AM", 599, rating=2, text="Cooling still weak, he left in 20 minutes.")


def good(**kw):
    base = {"failure_type": "poor_job", "severity": "medium", "fault": "professional",
            "evidence": "Cooling still weak", "confidence": 0.9}
    base.update(kw)
    return base


# ---------------------------------------------------------------- detection

def test_every_research_case_gets_the_expected_route():
    want = ["fix", "rescue", "refund_diff", "fix", "fix", "person", "none"]
    got = [detect.assess(s["booking"]).route for s in cases.SCENARIOS]
    assert got == want


def test_ai_label_used_when_it_passes_every_gate():
    a = detect.assess(AC, FakeLLM([good()]))
    assert a.mode == "ai" and a.type == "poor_job"
    assert all(c["passed"] for c in a.checks)


def test_invented_evidence_is_blocked_then_rules_take_over():
    a = detect.assess(AC, FakeLLM([good(evidence="AC exploded"), good(evidence="AC exploded")]))
    assert a.mode == "rules_fallback" and a.type == "poor_job"


def test_retry_can_fix_a_bad_first_answer():
    a = detect.assess(AC, FakeLLM([good(failure_type="banana"), good()]))
    assert a.mode == "ai"


def test_ai_cannot_ignore_a_cancellation():
    b = cases.SCENARIOS[1]["booking"]
    a = detect.assess(b, FakeLLM([good(failure_type="late", evidence="", confidence=0.9)] * 2))
    assert a.type == "no_show" and a.mode == "rules_fallback"


def test_safety_words_always_go_to_a_person_even_if_ai_misses_them():
    b = Booking("Bathroom cleaning", "Ajay M.", "Yesterday", 899, rating=2, text="Floor tile is broken and it is not clean")
    a = detect.assess(b, FakeLLM([good(evidence="it is not clean")]))
    assert a.route == "person" and a.type == "damage_safety" and a.notes


def test_ai_outage_falls_back_to_rules():
    a = detect.assess(AC, FakeLLM(fail=True))
    assert a.mode == "rules_fallback" and a.type == "poor_job"


def test_leak_fixed_is_not_damage():
    b = Booking("AC service", "X", "Today", 599, rating=5, text="Water leakage fixed nicely. Very polite technician.")
    assert detect.assess(b).type == "no_problem"


def test_low_confidence_is_not_acted_on():
    a = detect.assess(AC, FakeLLM([good(confidence=0.3), good(confidence=0.3)]))
    assert a.mode == "rules_fallback"


# ---------------------------------------------------------------- money is decided by code

def test_refund_difference_is_exact():
    b = cases.SCENARIOS[2]["booking"]
    p = remedy.plan(b, detect.assess(b))
    assert p["diff"] == 262 and p["route"] == "refund_diff"


def test_short_notice_cancellation_waives_fee_and_adds_credit():
    b = cases.SCENARIOS[1]["booking"]
    p = remedy.plan(b, detect.assess(b))
    assert p["fee_waived"] and p["credit"] == remedy.WAIT_CREDIT and len(p["replacements"]) == 2


def test_offer_is_sized_by_severity_and_capped():
    for sev, pct in remedy.OFFER_PCT.items():
        a = detect.Assessment("poor_job", sev, "professional", "", "rules")
        o = remedy.offer(a, AC)
        assert o["pct"] == pct and o["cap"] == 300 and o["days"] <= 90


def test_damage_case_mentions_cover_and_callback():
    b = cases.SCENARIOS[5]["booking"]
    p = remedy.plan(b, detect.assess(b))
    assert p["route"] == "person" and p["callback_min"] == 30 and p["damage_cover"] == 10000


# ---------------------------------------------------------------- messages

def _msg(llm_texts):
    a = detect.assess(AC)
    p = remedy.plan(AC, a)
    f = remedy.message_facts(AC, p)
    return message.write(AC, p, f, FakeLLM(text_answers=llm_texts))


def test_good_ai_message_is_used():
    m = _msg(["Sorry your AC service wasn't done right. Pick a free redo with a top-rated professional, "
              "or a full refund of ₹599."])
    assert m.mode == "ai"


def test_made_up_numbers_are_blocked():
    m = _msg(["Sorry! Here is ₹500 off.", "Sorry! Here is ₹500 off."])
    assert m.mode == "template" and "500" not in m.text


def test_over_promises_are_blocked():
    m = _msg(["Sorry. We guarantee this will never happen again.", "Sorry. We guarantee it."])
    assert m.mode == "template"


def test_every_template_passes_its_own_gates():
    for s in cases.SCENARIOS:
        b = s["booking"]
        p = remedy.plan(b, detect.assess(b))
        m = message.write(b, p, remedy.message_facts(b, p))
        assert all(c["passed"] for c in m.checks), (s["label"], m.checks)


def test_inr_uses_indian_grouping():
    assert inr(599) == "₹599" and inr(3499) == "₹3,499" and inr(123456) == "₹1,23,456"


# ---------------------------------------------------------------- trained model (no API key)

def test_model_reads_words_without_any_key():
    a = detect.assess(AC)
    assert a.mode == "model" and a.prob is not None and a.prob >= 0.65 and a.type == "poor_job"


def test_model_says_fine_for_praise():
    b = Booking("Switchboard repair", "S", "Today", 199, rating=5, text="Quick and neat work, thank you.")
    a = detect.assess(b)
    assert a.type == "no_problem" and a.prob < 0.35


def test_low_rating_beats_a_model_that_says_fine():
    b = Booking("Switchboard repair", "S", "Today", 199, rating=1, text="Quick and neat work, thank you.")
    a = detect.assess(b)
    assert a.type == "poor_job" and a.mode == "rules_fallback"


def test_unsure_model_hands_over_to_rules():
    b = cases.SCENARIOS[4]["booking"]          # late and rushed salon: the model is near 50%
    a = detect.assess(b)
    assert a.mode == "rules_fallback" and a.type == "poor_job"


def test_cancellation_and_safety_do_not_depend_on_the_model():
    assert detect.assess(cases.SCENARIOS[1]["booking"]).type == "no_show"
    assert detect.assess(cases.SCENARIOS[5]["booking"]).route == "person"


def test_model_card_shows_it_beats_keyword_rules():
    from core import model
    c = model.card()
    assert c["trained_on"] == 468 and c["cv_accuracy"] > c["rules_accuracy"]
