# Make it right (MVP)

A concept prototype for Urban Company's Consumer Growth goal: more customers booking again within 90 days.

When a job goes wrong (a low rating, a professional who cancels or runs late, a bill above the quote), UC notices
it, offers the fix in one tap, checks it worked, and only then sends an offer for the next booking. Serious cases
(damage, theft, safety, rude behaviour) always go to a person.

Not affiliated with Urban Company. Bookings, professionals and prices are made up. Nothing real is booked,
refunded or messaged.

## How it works

| Step | Done by | Notes |
|---|---|---|
| Hard signals (cancelled, late, rating, bill vs quote) | code | `core/detect.py` |
| Reading the customer's own words (English, Hindi, Hinglish) | AI (Gemini) | Labels the problem, severity and likely cause, and quotes the words it relied on |
| Checking every label | code | Allowed labels only · evidence must be the customer's own words · must agree with the signals · confidence 0.6+ · retry once, then rules |
| Safety rule | code | Damage, theft, injury or harassment words always go to a person, even if the AI missed them |
| Money, slots and routes | code | `core/remedy.py`: refunds, Rs 100 wait credit, redo slots within 48 h, offer size (10/15/20% by severity, capped at Rs 300, valid 60 days) |
| The message the customer reads | AI, checked by code | `core/message.py`: numbers must match the booking, no blame, no over-promises, no pressure, 60 words max; else a written template |

## Run locally

```bash
pip install -r mvp/requirements.txt
export GEMINI_API_KEY=...        # optional; without it the app uses rules and templates
streamlit run mvp/app.py
```

## Tests and evaluation

```bash
python -m pytest -q mvp/tests          # rules, gates (with a fake AI), money rules, templates
python mvp/eval/run_eval.py            # scores the golden set -> mvp/eval/report.json (shown in the app)
python mvp/eval/run_eval.py --rules    # same, forcing the rules, to compare with the AI
```

`eval/golden_set.csv` has 32 cases written from the discovery-engine themes (poor job, no-show, late,
overcharge, damage or safety, behaviour, no problem), including Hinglish and tricky ones such as "water leakage
fixed nicely". The keyword rules were adjusted while writing these cases, so their score here is optimistic.
**Check the expected labels by hand and add new cases from your interviews before quoting a score**, then change
`LABEL_STATUS` in `run_eval.py`.

## Deploy (Streamlit Community Cloud)

New app → repo `aalpha00007-ui/uc-repeat-discovery` → branch `main` → main file `mvp/app.py`.
In **Advanced settings → Secrets** add:

```toml
GEMINI_API_KEY = "your key"
```

After deploying with the key, run `python mvp/eval/run_eval.py` on your laptop with the same key and commit the
new `report.json`, so the app shows the AI's score rather than the rules'.
