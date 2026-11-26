# Repeat Booking Discovery Engine · Urban Company

A discovery engine built on public customer feedback. It looks at why Urban Company customers do or don't book another service within 90 days of a completed booking.

- **`run.py`** is the pipeline. It collects posts, filters them in code, has Gemini label them, and checks every label with quality gates.
- **`app.py`** is the Streamlit dashboard. Its tabs are Opportunity areas, Research questions, Returners vs lost, Segments, Ask the engine, Evidence explorer, Quality & evals and How it works.

The `data/` folder ships with the n8n run from 24 Nov 2026 already imported: 4,503 posts, with 892 of them coded by Gemini and re-checked by the code gates. The dashboard therefore works straight away, and every new `run.py` run adds to that data.

---

## 1. Run the dashboard on your laptop

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## 2. Add your keys (never commit them)

Copy `.env.example` to `.env` and fill it in:

| Key | Used for | Where to get it |
|---|---|---|
| `GEMINI_API_KEY` | AI labelling + Ask the engine | aistudio.google.com → Get API key |
| `SERPAPI_KEY` | Google Search + finding Reddit threads | serpapi.com → Dashboard |
| `YOUTUBE_API_KEY` | YouTube comments | console.cloud.google.com → YouTube Data API v3 |

The Play Store and the App Store need no key.

## 3. Collect fresh data and code it

```bash
python run.py collect                 # all 5 sources (takes 10-30 min)
python run.py prefilter               # code-only filter, no AI
python run.py label --limit 1500      # Gemini coding + gates; stop/restart any time, it resumes
```

Gemini's free tier has daily limits, so `label` sends 8 posts per call at 10 calls a minute. Change this with `--batch` and `--rpm`. If you hit the daily cap, run the same command again tomorrow: finished posts are cached in `data/cache/`.

## 4. Golden set (you label 20 posts by hand)

```bash
python run.py golden
```

1. Open `data/golden_set_to_label.xlsx`.
2. Fill in the `hand_` columns using the drop-downs. AI labels are hidden, so the labelling stays blind.
3. Save the file as `data/golden_labels.xlsx`.

Quality & evals then shows agreement and Cohen's kappa for each field.

## 5. Put it online (Streamlit Community Cloud, free)

1. Push this folder to a GitHub repo. `.env` and `data/cache/` are ignored by `.gitignore`.
2. Go to share.streamlit.io and sign in with GitHub. Click **Create app**, pick the repo, set the main file to `app.py`, and choose a URL such as `uc-repeat-discovery`.
3. Under **Advanced settings → Secrets**, paste:
   ```toml
   GEMINI_API_KEY = "your-key"
   ```
   This turns on "Ask the engine". Without it, the tab shows the evidence and no AI answer.
4. Deploy. After each new `run.py` run, commit `data/` and push, and the app updates by itself.

## How the pieces fit

```
engine/config.py     brief, sources, search queries, codebook, PM judgement tables
engine/collect.py    Play Store, App Store, Google Search, Reddit, YouTube
engine/prefilter.py  dedupe, length, lookback, InstaHelp / outside-India exclusion
engine/label.py      Gemini coding, one retry, reject
engine/gates.py      allowed values · word-for-word quote · logic checks
engine/analysis.py   every number on the dashboard
engine/ask.py        grounded Q&A with four gates
engine/golden.py     blind golden set + template
scripts/import_n8n_seed.py   one-off import of the n8n run
```
