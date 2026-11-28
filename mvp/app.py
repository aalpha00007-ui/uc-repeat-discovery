"""Make it right: win back Urban Company customers after a bad job (concept prototype).

Run locally:  streamlit run mvp/app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from core import cases, detect, message, remedy  # noqa: E402
from core.cases import Booking, inr  # noqa: E402
from core.llm import Gemini  # noqa: E402

REPO_URL = "https://github.com/aalpha00007-ui/uc-repeat-discovery/tree/main/mvp"
MODE_LABEL = {
    "ai": "Labelled by AI, checked by code",
    "rules": "Labelled by rules (AI not configured)",
    "rules_fallback": "Rules used (AI off or blocked)",
}
MSG_LABEL = {"ai": "Written by AI, checked by code", "template": "Written template, checked by code"}

st.set_page_config(page_title="Make it right · UC prototype", page_icon="🛠️", layout="centered")


# ------------------------------------------------------------------ helpers

def log(event: str, **details):
    st.session_state.setdefault("log", []).append(
        {"time": pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %H:%M:%S"), "event": event, **details})


@st.cache_resource
def get_llm():
    return Gemini()


def show_checks(checks: list, label: str, model: str | None = None):
    ok = sum(1 for c in checks if c["passed"])
    with st.expander(f"Quality checks: {ok} of {len(checks)} passed · {label}"):
        for c in checks:
            st.markdown(f"{'✓' if c['passed'] else '✗'} **{c['name']}**: {c['detail']}")
        if model:
            st.caption(f"Model: {model}")


def choose(choice: str, kind: str):
    if st.session_state.get("choice") != choice:
        st.session_state.update(choice=choice, kind=kind, checkin=None, feedback=None)
        log("chose", choice=choice)


def reset_flow():
    st.session_state.update(assessed=None, plan=None, msg=None, choice=None, kind=None, checkin=None,
                            feedback=None)


# ------------------------------------------------------------------ page

st.info("**Concept prototype** for a product course project. Not affiliated with Urban Company. Bookings, "
        "professionals and prices are made up. **Nothing real is booked, refunded or messaged.**")
st.title("Make it right")
st.caption("What a customer sees when an Urban Company job goes wrong: UC spots it, offers the fix in one tap, "
           "checks it worked, and earns the next booking.")

llm = get_llm()
tab_try, tab_how = st.tabs(["Try it", "How it works and quality"])

# ================================================================== HOW IT WORKS
with tab_how:
    st.subheader("The problem")
    st.markdown(
        "UC's goal is more customers booking again within 90 days. Our discovery engine read 549 relevant "
        "customer posts from India (Play Store, App Store, Trustpilot, YouTube, Reddit; Nov 2025 to Nov 2026):\n"
        "- **Something went wrong in 48%** of them (265 of 549).\n"
        "- **A bad job decides whether they come back.** Of customers with a problem who said what they'd do next, "
        "**90% won't book again** (83 of 92). Without a problem, 97% did or will (35 of 36).\n"
        "- **Why they leave:** 71% of lost customers mention a poor job, redo or refund problem, and 38% a "
        "cancellation or no-show. Only 7% went direct to a professional they knew.\n"
        "- **Today the customer has to chase the fix:** recovery starts only when they complain, mostly through "
        "chat, and some are charged a cancellation fee when the professional cancelled.\n\n"
        "Public posts lean negative, so these are shares of complaints, not failure rates.")
    st.subheader("What this prototype does")
    st.markdown(
        "1. **Notice:** the moment a customer rates a job 3 stars or less, or a professional cancels or runs 30+ "
        "minutes late, UC checks what went wrong, how badly and whose fault it likely was.\n"
        "2. **Fix:** within minutes, the customer gets the fix in one tap: a free redo by a top-rated professional, "
        "a replacement who can come today, a refund, or a person for serious cases. Fees are waived "
        "automatically.\n"
        "3. **Check:** after the redo, UC asks whether it's fixed. If not, a person calls within 30 minutes.\n"
        "4. **Win back:** only once it's fixed, an offer for the next booking in any service brings them back "
        "inside the 90 days.")
    st.subheader("Where AI earns its place")
    st.markdown(
        "Star ratings alone can't tell a rushed facial from a damaged floor. **The AI reads the customer's own "
        "words, in English, Hindi or Hinglish**, and labels the problem, how serious it is and the likely cause, "
        "quoting the words it relied on. It also writes the short apology from the booking's facts.\n\n"
        "**Code decides every rupee and every route; the AI never sets money.** Code checks every AI output "
        "before anyone acts on it. If the AI is off, or its answer fails a check twice, keyword rules and a written "
        "template take over.")
    st.subheader("Quality checks")
    st.markdown(
        "**On every label:** labels come from the allowed list · the evidence is copied from the customer's own "
        "words · the label agrees with the booking's signals (a cancellation must be a no-show) · confidence is "
        "high enough to act · **safety words (damage, theft, harassment, injury) always go to a person**, even "
        "if the AI missed them.\n\n"
        "**On every message:** every number matches the booking · no blame on the customer · no promises we "
        "can't keep (\"guarantee\", \"never again\") · no pressure · short enough to read.")
    st.subheader("Golden set results")
    report_path = HERE / "eval" / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text())
        s = report["summary"]
        g1, g2, g3 = st.columns(3)
        g1.metric("Right problem type", f"{s['type_right']} of {s['total']}")
        g2.metric("Safety cases to a person", f"{s['safety_to_person']} of {s['safety_total']}")
        g3.metric("Messages passing checks", f"{s['messages_clean']} of {s['messages_total']}")
        st.caption(f"Run on {report['run_at']} · labels by: {report['mode']} · expected labels: {report['labels']}")
        st.dataframe(pd.DataFrame(report["cases"])[["id", "customer_words", "expected", "got", "pass", "note"]],
                     width="stretch", hide_index=True)
    else:
        st.caption("No evaluation report yet. Run: python mvp/eval/run_eval.py")
    st.subheader("Status")
    st.caption(f"AI: {'connected (Gemini)' if llm.available else 'not configured, so rules and templates are used'}"
               f" · Code: {REPO_URL}")

# ================================================================== TRY IT
with tab_try:
    st.info("**How to try it**  \n"
            "1. **Pick a booking:** a case from our research, or write your own.  \n"
            "2. **Send it to UC** and see what UC's system spots (customers never see this part).  \n"
            "3. **Pick a fix** the way a customer would.  \n"
            "4. **Answer the check-in** and see what brings them back. Nothing real changes.")

    # ---------------------------------------------------------- 1. booking
    st.subheader("1. Pick a booking")
    source = st.radio("Start from", ["A case from our research", "Write your own"], horizontal=True)
    if source == "A case from our research":
        pick = st.selectbox("Case", cases.SCENARIOS, format_func=lambda s: s["label"])
        st.caption(f"From our research: {pick['research']} Names and prices are made up.")
        b: Booking = pick["booking"]
    else:
        c1, c2 = st.columns(2)
        service = c1.selectbox("Service", list(cases.SERVICES))
        paid = c2.number_input("Amount paid (₹)", min_value=99, max_value=50000,
                               value=cases.SERVICES[service]["price"], step=50)
        what = st.radio("What happened", ["The job was done", "The professional cancelled",
                                          "The professional was late"], horizontal=True)
        event = {"The job was done": "done", "The professional cancelled": "cancelled",
                 "The professional was late": "late"}[what]
        late_min = cancel_before = 0
        rating = None
        if event == "cancelled":
            cancel_before = st.slider("Minutes before the slot that they cancelled", 0, 600, 40, step=10)
        else:
            if event == "late":
                late_min = st.slider("Minutes late", 0, 120, 45, step=5)
            rating = st.select_slider("Customer's rating", options=[1, 2, 3, 4, 5], value=2)
        text = st.text_area("What the customer wrote (any language)", max_chars=400,
                            placeholder="e.g. AC still not cooling, he left in 20 minutes")
        quoted = billed = None
        if event != "cancelled" and st.checkbox("The final bill was higher than the quote"):
            q1, q2 = st.columns(2)
            quoted = int(q1.number_input("Quoted (₹)", min_value=0, value=int(paid)))
            billed = int(q2.number_input("Billed (₹)", min_value=0, value=int(paid) * 2))
            paid = billed
        b = Booking(service, "Rahul P.", "Today, 4:00 PM", int(paid), event=event, rating=rating,
                    text=text.strip(), late_min=late_min, cancel_min_before=cancel_before,
                    quoted=quoted, billed=billed)

    if st.session_state.get("bkey") != b.key():
        st.session_state.bkey = b.key()
        reset_flow()

    # ---------------------------------------------------------- 2. booking card
    st.subheader("2. The booking")
    with st.container(border=True):
        st.markdown(f"**{b.service}** with {b.pro}")
        st.caption(f"{b.category} · {b.when} · paid {inr(b.paid)}")
        if b.event == "cancelled":
            st.markdown(f"🚫 **{b.pro} cancelled {b.cancel_min_before} minutes before the slot.**")
        else:
            if b.event == "late":
                st.markdown(f"⏱️ Arrived **{b.late_min} minutes late**.")
            if b.rating:
                st.markdown(f"Rating: :orange[{'★' * b.rating}]:gray[{'★' * (5 - b.rating)}] ({b.rating} of 5)")
            else:
                st.markdown("Rating: none yet")
            if b.quoted and b.billed:
                st.markdown(f"Quoted **{inr(b.quoted)}**, billed **{inr(b.billed)}**.")
            if b.text:
                st.markdown(f"> {b.text}")
    send_label = "Record the cancellation" if b.event == "cancelled" else "Submit the rating"
    if st.button(f"{send_label} and send to UC", type="primary"):
        with st.spinner("Checking what went wrong..."):
            a = detect.assess(b, llm)
            p = remedy.plan(b, a)
            facts = remedy.message_facts(b, p)
            msg = message.write(b, p, facts, llm)
        st.session_state.update(assessed=a, plan=p, msg=msg, choice=None, kind=None, checkin=None, feedback=None)
        log("sent", service=b.service, what_happened=b.event, rating=b.rating, problem=a.type, severity=a.severity,
            route=a.route, label_mode=a.mode, message_mode=msg.mode)

    a: detect.Assessment | None = st.session_state.get("assessed")
    p: dict | None = st.session_state.get("plan")
    msg: message.Message | None = st.session_state.get("msg")

    if a is not None:
        # ------------------------------------------------------ 3. what UC spots
        st.subheader("3. What UC's system spots")
        with st.container(border=True):
            m1, m2, m3 = st.columns(3)
            m1.metric("Problem", detect.SHORT[a.type])
            m2.metric("How serious", a.severity.capitalize())
            m3.metric("Likely cause", a.fault.capitalize())
            st.markdown(f"**{detect.TYPES[a.type]}.** Next: {detect.ROUTE_LABEL[a.route].lower()}.")
            if a.evidence:
                st.markdown(f"**Based on the customer's words:** \"{a.evidence}\"")
            signals = detect.hard_signals(b)
            if signals:
                st.caption("Signals from the booking: " + "; ".join(signals) + ".")
            for n in a.notes:
                st.warning(n)
            show_checks(a.checks, MODE_LABEL[a.mode], a.model)
        st.caption("Customers never see this panel. It runs within seconds of the rating or the cancellation.")

        # ------------------------------------------------------ 4. what the customer sees
        st.subheader("4. What the customer sees")
        route = p["route"]
        if route == "none":
            st.success("Nothing went wrong, so the customer sees nothing extra and gets no offer. "
                       "Happy customers don't get spammed.")
        else:
            with st.container(border=True):
                st.markdown(f"#### {message.TITLES[route]}")
                st.markdown(msg.text)
                show_checks(msg.checks, MSG_LABEL[msg.mode], msg.model)

                if route == "fix":
                    tp = p["top_pro"]
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**Free redo** with {tp['name']} ({tp['rating']}★, {tp['jobs']:,} jobs)")
                        slot = st.selectbox("Slot", p["slots"], label_visibility="collapsed")
                        if st.button("Book free redo", type="primary"):
                            choose(f"Free redo with {tp['name']}, {slot}", "redo")
                    with c2:
                        st.markdown(f"**Full refund** of {inr(p['refund'])} to the original payment, "
                                    f"3 to 5 working days")
                        if st.button(f"Refund {inr(p['refund'])}"):
                            choose(f"Full refund of {inr(p['refund'])}", "refund")
                    if st.button("Talk to a person"):
                        choose("Talk to a person", "person")
                    extra = f" {inr(p['credit'])} credit added for the late start." if p["credit"] else ""
                    st.caption("Visit fee waived. The rating still counts." + extra)

                elif route == "rescue":
                    done = "Cancellation fee waived automatically."
                    if p["credit"]:
                        done += f" {inr(p['credit'])} credit added for the short notice."
                    st.success(done)
                    st.markdown("**Top-rated professionals who can come today**")
                    for i, r in enumerate(p["replacements"]):
                        c1, c2 = st.columns([3, 2])
                        c1.markdown(f"**{r['name']}** · {r['rating']}★ · {r['jobs']:,} jobs  \n{r['time']}")
                        if c2.button(f"Confirm {r['name'].split()[0]}", key=f"rep{i}",
                                     type="primary" if i == 0 else "secondary"):
                            choose(f"Replacement: {r['name']}, {r['time']}", "replacement")
                    c1, c2 = st.columns(2)
                    with c1:
                        day = st.selectbox("Another day", remedy.redo_slots(), label_visibility="collapsed")
                        if st.button("Pick this time instead"):
                            choose(f"Rebooked for {day}", "replacement")
                    with c2:
                        if st.button(f"Cancel with full refund of {inr(p['refund'])}"):
                            choose(f"Cancelled with full refund of {inr(p['refund'])}", "refund")

                elif route == "credit":
                    st.success(f"{inr(p['credit'])} credit added automatically.")
                    c1, c2 = st.columns(2)
                    if c1.button("All good, thanks", type="primary"):
                        choose("Kept the credit, job was fine", "credit")
                    if c2.button("Something wasn't done right"):
                        choose(f"Free redo, {p['slots'][0]}", "redo")

                elif route == "refund_diff":
                    c1, c2 = st.columns(2)
                    if c1.button(f"OK, refund {inr(p['diff'])}", type="primary"):
                        choose(f"Refund of the difference, {inr(p['diff'])}", "refund")
                    if c2.button("Talk to a person"):
                        choose("Talk to a person", "person")

                elif route == "person":
                    st.warning(f"No automatic offer here. A UC case manager calls within {p['callback_min']} minutes "
                               f"(8 AM to 10 PM) and stays with the case until it's closed.")
                    if a.type == "behaviour":
                        st.caption(f"{b.pro} won't be sent to this customer again.")
                    c1, c2 = st.columns(2)
                    if c1.button("Call me now", type="primary"):
                        choose("Callback now", "person")
                    if c2.button("Call me later today"):
                        choose("Callback later today", "person")

        # ------------------------------------------------------ 5. after the fix
        choice, kind = st.session_state.get("choice"), st.session_state.get("kind")
        if choice:
            st.subheader("5. After the fix")
            st.success(f"Prototype: nothing real was changed. The customer chose: **{choice}**.")
            show_offer = False
            if kind in ("redo", "replacement"):
                st.markdown(f"Two hours after the job is marked done, UC asks: **{p['check']}**")
                c1, c2 = st.columns(2)
                if c1.button("Yes, it's fixed", type="primary"):
                    st.session_state.checkin = "fixed"
                    log("check-in", answer="fixed")
                if c2.button("Still not right"):
                    st.session_state.checkin = "not fixed"
                    log("check-in", answer="not fixed")
                if st.session_state.get("checkin") == "fixed":
                    show_offer = True
                elif st.session_state.get("checkin") == "not fixed":
                    st.warning(f"A person calls within {remedy.CALLBACK_MIN} minutes. No automatic offer on this case "
                               f"until it's closed.")
            elif kind in ("refund", "credit"):
                show_offer = True
            elif kind == "person":
                st.info("The case is with a person now. An offer is sent only after the case is closed, never "
                        "before.")
            if show_offer:
                o = remedy.offer(a, b)
                with st.container(border=True):
                    st.markdown("#### Thanks for giving us another go")
                    st.markdown(f"**{o['text']}.**")
                    st.caption(o["why"])
                if st.session_state.get("offer_logged") != (st.session_state.bkey, choice):
                    st.session_state.offer_logged = (st.session_state.bkey, choice)
                    log("offer", offer=o["text"])

            if show_offer or kind == "person" or st.session_state.get("checkin"):
                fb = st.radio("If this happened to you, would you book Urban Company again in the next 3 months?",
                              ["Yes", "Maybe", "No"], index=None, horizontal=True,
                              key=f"fb_{st.session_state.bkey}_{choice}")
                if fb and st.session_state.get("feedback") != fb:
                    st.session_state.feedback = fb
                    log("would book again", answer=fb)

    with st.expander("Session log (for user tests)"):
        rows = st.session_state.get("log", [])
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, width="stretch", hide_index=True)
            st.download_button("Download this session as CSV", df.to_csv(index=False).encode("utf-8"),
                               file_name="make_it_right_session.csv", mime="text/csv")
        else:
            st.caption("Nothing yet.")
