"""Repeat Booking Discovery Engine - Urban Company (Streamlit dashboard)."""
import json
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from engine import analysis as A
from engine import ask as K
from engine.config import (CODEBOOK, CONTROLLABILITY, NS, PROJECT, RESEARCH_QUESTIONS,
                           SOURCE_LABELS, THEME_BRANCH)

st.set_page_config(page_title="Repeat Booking Discovery Engine · Urban Company",
                   page_icon="🔎", layout="wide")

BLUE, ORANGE, GREY = "#2563EB", "#E8710A", "#9CA3AF"
BRANCH_COLORS = {"Need arises": "#2563EB", "UC is chosen": "#60A5FA",
                 "Booking counts": "#E8710A", "Other": GREY}
FIELD_TITLES = {f: spec["q"].split(": ", 1)[-1] for f, spec in CODEBOOK.items()}
SHORT = {"themes": "reason", "went_wrong": "something went wrong", "need_trigger": "trigger",
         "planning_mode": "planning", "expectation_after": "expects after", "turn_to_next": "turns to",
         "outside_app": "outside app", "unmet_need": "unmet need", "category": "category"}

st.markdown("""<style>
div[data-testid="stMetricValue"] {font-size: 2.1rem;}
.gate {display:inline-block;padding:4px 10px;border-radius:14px;margin:2px 6px 2px 0;font-size:.9rem}
.gate.ok {background:#DBEAFE;color:#1E3A8A} .gate.no {background:#FDE7D3;color:#7C2D12}
.quote {border-left:3px solid #2563EB;padding:2px 10px;margin:6px 0;color:#111827}
.small {color:#6B7280;font-size:.85rem}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ data
@st.cache_data
def load_all():
    rec, coded, log, gset, golden = A.load()
    df = A.prepare(coded, rec, log.get("corrections"))
    return rec, df, log, gset, golden


rec, df_all, run_log, gset, golden = load_all()
passed = df_all[df_all["passed"] & df_all["in_scope"]]


def src_label(s):
    return SOURCE_LABELS.get(s, s)


def hbar(d, x, y, color=BLUE, height=None, hover=None, text=None, xtitle=""):
    d = d.iloc[::-1]
    fig = go.Figure(go.Bar(x=d[x], y=d[y], orientation="h", marker_color=color,
                           text=d[text] if text else None, textposition="outside",
                           hovertext=d[hover] if hover else None,
                           hoverinfo="text" if hover else "x+y", cliponaxis=False))
    fig.update_layout(height=height or max(180, 34 * len(d) + 60), margin=dict(l=10, r=40, t=10, b=30),
                      xaxis_title=xtitle, plot_bgcolor="white", bargap=0.35,
                      yaxis=dict(automargin=True), xaxis=dict(gridcolor="#E5E7EB"))
    return fig


def quotes_block(rows, k=3):
    for r in rows.head(k).itertuples():
        link = f" · [open]({r.link})" if getattr(r, "link", "") else ""
        st.markdown(f"<div class='quote'>“{r.evidence_quote}”</div>"
                    f"<span class='small'>{r.record_id} · {src_label(r.source)} · {r.group}</span>{link}",
                    unsafe_allow_html=True)


# ------------------------------------------------------------------ sidebar lens
with st.sidebar:
    st.header("Lens")
    lens = st.radio("Posts included", ["All relevant feedback", "Customers only",
                                       "Core repeat evidence", "Nothing went wrong"],
                    help="Core repeat evidence = customer posts that state a return decision, "
                         "where they went instead, or a reason tied to booking again. "
                         "'Nothing went wrong' keeps posts where the booking went fine — the "
                         "silent-churn case the brief cares most about.")
    srcs = sorted(passed["source"].unique(), key=lambda s: -len(passed[passed["source"] == s]))
    pick_src = st.multiselect("Sources", srcs, default=srcs, format_func=src_label)
    cats = [c for c in CODEBOOK["category"]["values"] if c in set(passed["category"])]
    pick_cat = st.multiselect("Service category", cats, default=cats)
    st.divider()
    seed = run_log.get("seed", {})
    st.caption(f"Data: {len(rec):,} public posts · seed run {seed.get('run_id', '—')}"
               + (f" + {len(run_log.get('runs', [])) - 1} pipeline step(s)" if len(run_log.get("runs", [])) > 1 else ""))

df = passed[passed["source"].isin(pick_src) & passed["category"].isin(pick_cat)]
if lens == "Customers only":
    df = df[df["speaker"] == "Customer"]
elif lens == "Core repeat evidence":
    df = df[df["core"]]
elif lens == "Nothing went wrong":
    df = df[df["nothing_wrong"]]

# ------------------------------------------------------------------ header
st.title(PROJECT["title"])
st.caption(f"{PROJECT['team']} · {PROJECT['goal']}")
st.info(PROJECT["disclaimer"], icon="ℹ️")
m = st.columns(5)
m[0].metric("Records collected", f"{len(rec):,}")
m[1].metric("Home-service candidates", f"{(rec['status'] == 'Candidate').sum():,}")
m[2].metric("AI-coded (passed gates)", f"{df_all['passed'].sum():,}")
m[3].metric("Core repeat evidence", f"{(df_all['passed'] & df_all['core']).sum():,}")
m[4].metric("In current lens", f"{len(df):,}")

tabs = st.tabs(["Opportunity areas", "Research questions", "Returners vs lost", "Segments",
                "Ask the engine", "Evidence explorer", "Quality & evals", "How it works"])

# ================================================================== 1 Opportunities
with tabs[0]:
    st.subheader("Which unmet needs could move the 90-day repeat rate the most?")
    st.caption("Score = reach (how often the need appears) × closeness to a lost repeat (share of "
               "mentions from customers who won't book again, stopped, or went elsewhere) × "
               "nothing-went-wrong weight (share of mentions where the booking itself went fine) × "
               "controllability (can a customer-side product change act on it). Move the weights "
               "to test how robust the ranking is.")
    c1, c2, c3 = st.columns(3)
    w_reach = c1.slider("Weight: reach", 0.0, 2.0, 1.0, 0.1)
    w_lost = c2.slider("Weight: closeness to lost repeat", 0.0, 2.0, 1.0, 0.1)
    w_nww = c3.slider("Weight: nothing went wrong", 0.0, 2.0, 0.5, 0.1)
    with st.expander("Controllability assumptions (PM judgement)"):
        ctl = pd.DataFrame({"Unmet need": list(CONTROLLABILITY), "Controllability (0-1)": list(CONTROLLABILITY.values())})
        ctl = st.data_editor(ctl, hide_index=True, width="stretch", disabled=["Unmet need"])
        control = dict(zip(ctl["Unmet need"], ctl["Controllability (0-1)"]))
    opp = A.opportunity(df, w_reach, w_lost, w_nww, control)
    if opp.empty:
        st.warning("No coded unmet needs in this lens.")
    else:
        opp["hover"] = opp.apply(lambda r: f"{r['need']}<br>{r['mentions']} mentions · "
                                           f"{r['lost_share']:.0f}% lost the repeat · "
                                           f"{r['nothing_wrong_share']:.0f}% nothing went wrong · "
                                           f"control {r['controllability']:.1f}", axis=1)
        opp["label"] = opp["score"].map(lambda v: f"{v:.0f}")
        st.plotly_chart(hbar(opp, "score", "need", hover="hover", text="label", xtitle="Opportunity score (top = 100)"),
                        width="stretch")
        for r in opp.itertuples():
            flag = " · ⚠ small sample" if r.mentions < 10 else ""
            with st.expander(f"{r.need} — {r.mentions} mentions, {r.lost_share:.0f}% from customers who "
                             f"lost the repeat, {r.nothing_wrong_share:.0f}% nothing went wrong{flag}"):
                st.markdown(f"Most common category: **{r.top_category}** · came back: "
                            f"{r.returned_share:.0f}% · controllability (PM judgement): {r.controllability:.1f}")
                quotes_block(A.examples(df, "unmet_need", r.need))

    st.subheader("Where on the repeat-booking tree do the reasons sit?")
    st.caption("A repeat needs three things: a need arises → Urban Company is chosen → the booking "
               "counts (done, not cancelled, not a redo). Each reason a customer gives sits on one branch.")
    th = A.label_shares(df, "themes")
    if not th.empty:
        th["branch"] = th["label"].map(lambda t: THEME_BRANCH.get(t, "Other"))
        th = th.sort_values("share", ascending=True)
        fig = px.bar(th, x="share", y="label", color="branch", orientation="h",
                     color_discrete_map=BRANCH_COLORS, labels={"share": "% of posts in lens", "label": ""},
                     hover_data={"count": True, "share": ":.1f"})
        fig.update_layout(height=max(220, 32 * len(th) + 60), margin=dict(l=10, r=20, t=10, b=30),
                          plot_bgcolor="white", legend_title_text="Tree branch",
                          xaxis=dict(gridcolor="#E5E7EB"))
        st.plotly_chart(fig, width="stretch")

# ================================================================== 2 Research questions
with tabs[1]:
    st.caption("Share = % of posts in this lens carrying that label. One post can carry several "
               "labels for list fields. 'Not stated' is left out of the charts but counted in the base.")
    for code, question, fields in RESEARCH_QUESTIONS:
        st.subheader(f"{code}: {question}")
        if not fields:
            st.markdown("See the **Returners vs lost** tab." if code == "Q6" else "See the **Segments** tab.")
            continue
        for f in fields:
            sh = A.label_shares(df, f)
            if sh.empty:
                st.caption(f"No posts state this ({FIELD_TITLES[f]}).")
                continue
            stated = sh["count"].sum()
            st.markdown(f"**{FIELD_TITLES[f]}** <span class='small'>· {stated} labels from {len(df)} posts</span>",
                        unsafe_allow_html=True)
            sh["txt"] = sh.apply(lambda r: f"{r['share']:.1f}% ({r['count']})", axis=1)
            st.plotly_chart(hbar(sh, "share", "label", text="txt", xtitle="% of posts in lens"),
                            width="stretch", key=f"rq_{code}_{f}")
            with st.expander("Example quotes"):
                for lab in sh["label"].head(3):
                    st.markdown(f"**{lab}**")
                    quotes_block(A.examples(df, f, lab), k=2)

# ================================================================== 3 Returners vs lost
with tabs[2]:
    st.subheader("What separates customers who lost the repeat from customers who came back?")
    cmp, n_lost, n_ret = A.compare_groups(df)
    st.caption(f"Lost the repeat = won't book again, stopped using, or went to someone else (n={n_lost}). "
               f"Came back = booked again or says they will (n={n_ret}). Bars show the percentage-point "
               "gap in how often each label appears. * = fewer than 8 posts, read with care.")
    if cmp.empty or n_lost < 5 or n_ret < 5:
        st.warning("Not enough posts in both groups in this lens to compare.")
    else:
        top = cmp.head(22).copy()
        top["name"] = top.apply(lambda r: f"{SHORT.get(r['field'], r['field'])}: "
                                          f"{r['label']}{' *' if r['small'] else ''}", axis=1)
        top["color"] = top["gap"].map(lambda g: ORANGE if g > 0 else BLUE)
        top["hover"] = top.apply(lambda r: f"Lost: {r['lost_pct']:.0f}% · Came back: {r['returned_pct']:.0f}% · n={r['n']}", axis=1)
        top = top.sort_values("gap")
        fig = go.Figure(go.Bar(x=top["gap"], y=top["name"], orientation="h", marker_color=top["color"],
                               hovertext=top["hover"], hoverinfo="text"))
        fig.update_layout(height=34 * len(top) + 80, margin=dict(l=10, r=20, t=30, b=30), plot_bgcolor="white",
                          xaxis_title="Percentage-point gap (orange = more common among lost, blue = among returners)",
                          xaxis=dict(gridcolor="#E5E7EB", zeroline=True, zerolinecolor="#111827"))
        st.plotly_chart(fig, width="stretch")
        with st.expander("Full comparison table"):
            st.dataframe(cmp.rename(columns={"lost_pct": "% lost", "returned_pct": "% came back",
                                             "gap": "gap (pts)"}).round(1), hide_index=True,
                         width="stretch")

# ================================================================== 4 Segments
with tabs[3]:
    st.subheader("How do patterns differ by category, city, household and how they found Urban Company?")
    seg_opts = {"Service category": "category", "City tier": "city_tier", "City": "city_norm",
                "Household": "household", "How they found Urban Company": "found_via",
                "Source": "source"}
    seg_name = st.selectbox("Segment by", list(seg_opts))
    seg = seg_opts[seg_name]
    tab = A.segment_table(df, seg)
    stated = (df[seg] != NS).sum()
    st.caption(f"{stated} of {len(df)} posts state this ({stated / max(len(df), 1) * 100:.0f}%). "
               "Segments with fewer than 10 posts are marked thin.")
    if tab.empty:
        st.warning("Too few posts state this segment.")
    else:
        if seg == "source":
            tab["segment"] = tab["segment"].map(src_label)
        tab["thin"] = tab["posts"] < 10
        long = tab.melt(id_vars="segment", value_vars=["returned", "lost"], var_name="outcome", value_name="n")
        long["outcome"] = long["outcome"].map({"returned": "Came back", "lost": "Lost the repeat"})
        fig = px.bar(long, x="n", y="segment", color="outcome", orientation="h", barmode="group",
                     color_discrete_map={"Came back": BLUE, "Lost the repeat": ORANGE},
                     labels={"segment": "", "n": "posts", "outcome": ""})
        fig.update_layout(height=max(220, 44 * len(tab) + 60), margin=dict(l=10, r=20, t=10, b=30),
                          plot_bgcolor="white", yaxis=dict(categoryorder="array", categoryarray=tab["segment"][::-1]),
                          xaxis=dict(gridcolor="#E5E7EB"))
        st.plotly_chart(fig, width="stretch")
        show = tab.rename(columns={"segment": seg_name, "posts": "Posts", "returned": "Came back",
                                   "lost": "Lost the repeat", "something_went_wrong": "% something went wrong",
                                   "top_reason": "Top reason", "top_need": "Top unmet need", "thin": "Thin (<10)"})
        st.dataframe(show.round(0), hide_index=True, width="stretch")

# ================================================================== 5 Ask the engine
with tabs[4]:
    st.subheader("Ask a research question")
    st.caption("Answers come only from matching posts in the current lens and pass four visible "
               "gates: scope (customer behaviour only), enough evidence, every claim cited with a "
               "word-for-word quote, and numbers computed in code. If a gate fails you get the "
               "evidence, not an AI guess.")
    examples_q = {"Why go to a local technician?": "Why do customers go to a local technician instead of rebooking?",
                  "What do they expect after a job?": "What do customers expect after the service is complete?",
                  "Why don't happy customers rebook?": "Why do happy customers still not book again?",
                  "Why keep the pro's number?": "Why do customers keep the professional's number and book directly?"}
    st.markdown("<span class='small'>Try an example or write your own</span>", unsafe_allow_html=True)
    cols = st.columns(len(examples_q))
    for i, (lab, q) in enumerate(examples_q.items()):
        if cols[i].button(lab, key=f"ex{i}", width="stretch"):
            st.session_state["q"] = q
            st.session_state["run_now"] = True
    q = st.text_input("Question", key="q", placeholder="e.g. Why do customers stop after one AC service?")
    ask_now = st.button("Ask", type="primary") or st.session_state.pop("run_now", False)
    if ask_now and q.strip():
        @st.cache_resource
        def _retriever(ids):
            return K.Retriever(df.set_index("record_id").loc[list(ids)].reset_index())
        retr = _retriever(tuple(df["record_id"]))
        try:
            from engine.llm import Gemini
            llm = Gemini(rpm=30)
        except Exception:
            llm = None
        with st.spinner("Checking scope, finding evidence, drafting cited claims..."):
            res = K.answer(q, df, retr, llm)
        st.markdown(" ".join(f"<span class='gate {'ok' if ok else 'no'}'>{'✓' if ok else '✗'} {name}</span>"
                             for name, ok, _ in res["gates"]), unsafe_allow_html=True)
        for name, ok, note in res["gates"]:
            st.caption(f"{name}: {note}")
        stx = res["stats"]
        if res["claims"]:
            st.markdown("#### What the evidence says")
            text_by = df.set_index("record_id")
            for c in res["claims"]:
                src = src_label(text_by.loc[c["record_id"], "source"]) if c["record_id"] in text_by.index else ""
                st.markdown(f"- {c['claim']}<div class='quote'>“{c['quote']}”</div>"
                            f"<span class='small'>{c['record_id']} · {src}</span>", unsafe_allow_html=True)
        if stx:
            st.markdown("#### Counts (computed in code)")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Matching posts", stx["matching_posts"])
            k2.metric("Came back", stx["returned"])
            k3.metric("Lost the repeat", stx["lost"])
            k4.metric("Nothing went wrong", stx["nothing_wrong"])
            if stx["top_needs"]:
                st.caption("Top unmet needs among matching posts: " +
                           " · ".join(f"{k} ({v})" for k, v in stx["top_needs"].items()))
        if len(res["evidence"]):
            with st.expander(f"Evidence ({len(res['evidence'])} posts)", expanded=not res["claims"]):
                for r in res["evidence"].head(12).itertuples():
                    st.markdown(f"<div class='quote'>{r.text[:500]}</div><span class='small'>{r.record_id} · "
                                f"{src_label(r.source)} · {r.group} · {r.unmet_need}</span>", unsafe_allow_html=True)

# ================================================================== 6 Evidence explorer
with tabs[5]:
    f1, f2, f3, f4 = st.columns(4)
    g_pick = f1.multiselect("Outcome", ["Returned", "Lost the repeat", "Unclear"])
    t_pick = f2.multiselect("Reason", [v for v in CODEBOOK["themes"]["values"]])
    n_pick = f3.multiselect("Unmet need", CODEBOOK["unmet_need"]["values"])
    w_pick = f4.multiselect("Something went wrong", ["Yes", "No", NS])
    s_txt = st.text_input("Search text")
    ev = df
    if g_pick:
        ev = ev[ev["group"].isin(g_pick)]
    if t_pick:
        ev = ev[ev["theme_list"].map(lambda t: bool(set(t) & set(t_pick)))]
    if n_pick:
        ev = ev[ev["unmet_need"].isin(n_pick)]
    if w_pick:
        ev = ev[ev["went_wrong"].isin(w_pick)]
    if s_txt:
        ev = ev[ev["text"].str.contains(s_txt, case=False, na=False)]
    st.caption(f"{len(ev)} posts")
    view = ev[["record_id", "source", "date", "group", "themes", "unmet_need", "category",
               "evidence_quote", "text", "link"]].copy()
    view["source"] = view["source"].map(src_label)
    st.dataframe(view, hide_index=True, width="stretch", height=520,
                 column_config={"link": st.column_config.LinkColumn("link", display_text="open"),
                                "text": st.column_config.TextColumn("post", width="large"),
                                "evidence_quote": st.column_config.TextColumn("evidence quote", width="medium")})
    st.download_button("Download these posts (CSV)", ev.drop(columns=["theme_list", "outside_list"]).to_csv(index=False),
                       "uc_evidence.csv", "text/csv")

# ================================================================== 7 Quality & evals
with tabs[6]:
    st.subheader("Gate results on every AI output")
    gc = df_all["gate_status"].value_counts()
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Passed first try", int(gc.get("passed_first", 0)))
    q2.metric("Passed after one retry", int(gc.get("passed_retry", 0)))
    q3.metric("Rejected (excluded)", int(gc.get("rejected", 0)))
    q4.metric("Quotes found word-for-word", f"{(df_all['passed'] & (df_all['relevant'] == 'Yes')).sum()} / "
                                            f"{(df_all['relevant'] == 'Yes').sum()}")
    models = run_log.get("models", {})
    st.markdown("**Models used:** " + " · ".join(f"{k}: {v}" for k, v in models.items()))
    st.caption("Gates: allowed values only · evidence quote must exist word-for-word in the post · "
               "labels must not contradict each other. One retry, then reject.")
    if run_log.get("corrections"):
        with st.expander(f"Researcher corrections to AI labels ({len(run_log['corrections'])})"):
            st.dataframe(pd.DataFrame(run_log["corrections"]), hide_index=True, width="stretch")
    with st.expander("Rejected outputs and why"):
        rej = df_all[df_all["gate_status"] == "rejected"][["record_id", "source", "gate_fails", "evidence_quote", "text"]]
        rej = rej.assign(source=rej["source"].map(src_label))
        st.dataframe(rej, hide_index=True, width="stretch")

    st.subheader("Golden set: hand labels vs AI")
    if golden is not None and len(golden):
        gf, gr = A.golden_score(golden, df_all)
        if gf.empty:
            st.warning("golden_labels file found but no hand labels filled in yet.")
        else:
            st.metric("Field-level agreement", f"{gf['agreement'].mean():.0f}%")
            gf["txt"] = gf.apply(lambda r: f"{r['agreement']:.0f}% · κ {r['kappa']:.2f}", axis=1)
            st.plotly_chart(hbar(gf, "agreement", "field", text="txt", xtitle="% agreement with hand labels"),
                            width="stretch")
            st.dataframe(gf.round(2), hide_index=True)
            for r in gr:
                with st.expander(f"{r['record_id']} · {src_label(r['source'])} · {len(r['disagreements'])} disagreement(s)"):
                    if r["disagreements"]:
                        st.table(pd.DataFrame(r["disagreements"]))
                    else:
                        st.write("Full agreement.")
    else:
        n = len(gset) if gset is not None else 0
        st.info(f"{n} posts were picked blind and stratified by source. They are waiting for the "
                "researcher's hand labels: open the template, fill the 'hand_' columns from the "
                "drop-downs, save it as data/golden_labels.xlsx and redeploy. Agreement and Cohen's "
                "kappa per field then appear here.")
        if os.path.exists("data/golden_set_to_label.xlsx"):
            with open("data/golden_set_to_label.xlsx", "rb") as fh:
                st.download_button("Download the golden-set template (.xlsx)", fh.read(),
                                   "golden_set_to_label.xlsx")
        if gset is not None:
            st.dataframe(gset.assign(source=gset["source"].map(src_label))[["record_id", "source", "text"]],
                         hide_index=True, width="stretch")
    if os.path.exists("data/seed/freetext_mapping.json"):
        with st.expander("Audit: how the n8n run's free-text answers were grouped into codebook values"):
            mp = json.load(open("data/seed/freetext_mapping.json", encoding="utf-8"))
            fld = st.selectbox("Field", list(mp))
            st.dataframe(pd.DataFrame(list(mp[fld].items()), columns=["n8n answer", "codebook value"]),
                         hide_index=True, width="stretch")
    with st.expander("Classification run log"):
        st.json(run_log)

# ================================================================== 8 How it works
with tabs[7]:
    st.subheader("Pipeline (code: run.py)")
    st.markdown(f"""
1. **Collect public feedback** — Play Store and App Store reviews of the Urban Company app, Reddit threads (found through Google, comments read from public pages), Google Search results (review and complaint sites, Quora, blogs) and YouTube comments on Urban Company videos. India only. Authors are stored only as one-way hashes; phone numbers and e-mails are masked.
2. **Prefilter (code, no AI)** — de-duplicate, drop posts under 25 characters or older than 365 days, exclude InstaHelp (Urban Company's quick-service housekeeping, including its old 'Insta Maid' name and 'maid on call' wording) and posts about other countries, keep posts about home or beauty services.
3. **AI coding (Gemini, temperature 0)** — every candidate post is labelled against a {len(CODEBOOK)}-field codebook mapped to the brief's eight questions: relevance, speaker, category, return status, something went wrong, reasons, need trigger, planning, expectation after the job, who they turn to next, what they do outside the app, unmet need, household, how they found UC, return timing and country — plus a word-for-word evidence quote.
4. **Quality gates on every output** — allowed values only, an exact supporting quote from the post, and logical consistency. Failures get one retry, then are rejected and excluded.
5. **Analysis in code** — label shares, returners vs lost comparison, segment splits, the metric-tree view and an opportunity score per unmet need. No number is produced by the LLM.
6. **Validation** — a blind, source-stratified golden set of 20 posts hand-labelled by the researcher; agreement and Cohen's kappa per field are reported in Quality & evals.
7. **Ask the engine** — grounded Q&A with four visible gates and a safe fallback to the evidence.

**Metric:** {PROJECT['metric']}

**Limits:** public feedback over-represents complaints and very happy customers, and silent churners rarely post; household, city and how they found UC are rarely stated; post dates are not booking dates, so this cannot measure the 90-day repeat rate itself — it ranks where to look, and interviews and booking data then validate. {seed.get('sample_note', '')}
""")
    st.subheader("Collection funnel by source")
    fun = rec.assign(source=rec["source"].map(src_label)).groupby(["source", "status"]).size().reset_index(name="posts")
    order = rec["source"].map(src_label).value_counts().index.tolist()
    status_colors = {"Candidate": BLUE, "Dropped: too short": "#CBD5E1", "Dropped: older than lookback": GREY,
                     "Dropped: duplicate": "#E5E7EB", "Dropped: not about home services": "#D1D5DB",
                     "Excluded: InstaHelp": ORANGE, "Excluded: outside India": "#FDBA74"}
    fig = px.bar(fun, x="posts", y="source", color="status", orientation="h", color_discrete_map=status_colors,
                 labels={"source": ""}, category_orders={"source": order})
    fig.update_layout(height=60 + 40 * len(order), margin=dict(l=10, r=20, t=10, b=30), plot_bgcolor="white",
                      xaxis=dict(gridcolor="#E5E7EB"), legend_title_text="")
    st.plotly_chart(fig, width="stretch")
    coded_by = df_all.groupby("source").agg(coded=("record_id", "size"), passed=("passed", "sum"),
                                            in_scope=("in_scope", "sum"), core=("core", "sum")).reset_index()
    coded_by["source"] = coded_by["source"].map(src_label)
    collected = rec.assign(source=rec["source"].map(src_label)).groupby("source").agg(
        collected=("record_id", "size"), candidates=("status", lambda s: (s == "Candidate").sum())).reset_index()
    st.dataframe(collected.merge(coded_by, on="source", how="left").fillna(0).sort_values("collected", ascending=False),
                 hide_index=True, width="stretch")
