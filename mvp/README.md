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
| Reading the customer's own words | trained model (no API key) | `core/model.py`: TF-IDF + logistic regression trained on 468 posts from the discovery engine (265 problem, 203 fine). Says how likely it is that something went wrong and which part of the message shows it. 89% right on unseen posts in 5-fold cross-validation, catching 249 of 265 problems; keyword rules alone get 64% and catch 101 |
| Checking the model | code | Clear signals first (cancellation, bill above the quote, rude or damage words) · between 35% and 65% the model is unsure and the rating decides · a 1-2 star rating always counts as a problem |
| Safety rule | code | Damage, theft, injury or harassment words always go to a person, even if the AI missed them |
| Money, slots and routes | code | `core/remedy.py`: refunds, Rs 100 wait credit, redo slots within 48 h, offer size (10/15/20% by severity, capped at Rs 300, valid 60 days) |
| The message the customer reads | written template, checked by code | `core/message.py`: numbers must match the booking, no blame, no over-promises, no pressure, 60 words max |

No API key is needed. If you ever add `GEMINI_API_KEY`, Gemini labels the words and drafts the message instead, behind the same checks.

## Run locally

```bash
pip install -r mvp/requirements.txt
streamlit run mvp/app.py        # no API key needed
```

## Tests and evaluation

```bash
python -m pytest -q mvp/tests          # rules, gates (with a fake AI), money rules, templates
python mvp/eval/run_eval.py            # scores the golden set -> mvp/eval/report.json (shown in the app)
python mvp/eval/run_eval.py --rules    # same, keyword rules only, to compare
python mvp/model/train_report.py       # cross-validates the model -> mvp/model/model_card.json
```

`eval/golden_set.csv` has 32 cases written from the discovery-engine themes (poor job, no-show, late,
overcharge, damage or safety, behaviour, no problem), including Hinglish and tricky ones such as "water leakage
fixed nicely". The keyword rules were adjusted while writing these cases, so their score here is optimistic.
**Check the expected labels by hand and add new cases from your interviews before quoting a score**, then change
`LABEL_STATUS` in `run_eval.py`.

## Deploy (Streamlit Community Cloud)

New app → repo `aalpha00007-ui/uc-repeat-discovery` → branch `main` → main file `mvp/app.py`. No secrets needed.
