"""AI coding: label every candidate post against the codebook, then gate it.

- temperature 0, JSON schema output, posts sent in small batches
- every output goes through engine/gates.py
- a failing output gets ONE retry (alone, with the failure reasons)
- still failing -> rejected, logged in data/gate_log.csv, excluded from analysis
- progress is cached in data/cache/labels.jsonl so a stopped run resumes
"""
import json
import os
from datetime import datetime, timezone

import pandas as pd

from .config import CODEBOOK, PROJECT, NS
from .gates import check
from .llm import Gemini

CACHE = "data/cache/labels.jsonl"


def _schema():
    props = {"record_id": {"type": "STRING"}}
    for f, spec in CODEBOOK.items():
        if spec.get("multi"):
            props[f] = {"type": "ARRAY", "items": {"type": "STRING", "enum": spec["values"]}}
        else:
            props[f] = {"type": "STRING", "enum": spec["values"]}
    props["city"] = {"type": "STRING"}
    props["evidence_quote"] = {"type": "STRING"}
    props["summary"] = {"type": "STRING"}
    return {"type": "OBJECT", "properties": {"items": {"type": "ARRAY", "items": {
        "type": "OBJECT", "properties": props, "required": list(props)}}}, "required": ["items"]}


def _system():
    lines = [
        f"You are a careful qualitative researcher coding public feedback for {PROJECT['team']}.",
        f"Research goal: {PROJECT['goal']}.",
        f"Metric: {PROJECT['metric']}",
        "",
        "Code each post against this codebook. Use ONLY the listed values.",
    ]
    for f, spec in CODEBOOK.items():
        many = " (one or more)" if spec.get("multi") else ""
        lines.append(f"- {f}{many}: {spec['q']} Values: {' | '.join(spec['values'])}")
    lines += [
        "- city: the Indian city named in the post, else 'Not stated'.",
        "- evidence_quote: copy 6-30 words EXACTLY as written in the post (same spelling, "
        "Hinglish kept) that best supports your labels. Never paraphrase.",
        "- summary: one plain sentence, max 20 words, saying what happened.",
        "",
        "Rules:",
        f"- Use '{NS}' (or 'None stated') unless the post says it. Do not guess age, income, household or city.",
        "- If relevant is 'No', set every other coded field to its 'Not stated'/'Other'/'None stated' value.",
        "- 'Booked again' only when the post says they booked again; 'Will book again' for stated intent.",
        "- went_wrong='No' cannot go with 'Poor job / redo / refund' or 'Cancelled or no-show'.",
        "- return_timing only when return_status is 'Booked again'.",
        "- You do not give advice; you only label.",
    ]
    return "\n".join(lines)


def _prompt(batch: pd.DataFrame, feedback: dict | None = None):
    parts = ["Code these posts. Return one item per record_id.\n"]
    for _, r in batch.iterrows():
        meta = f"source={r['source']}; rating={r.get('rating', '')}; context={str(r.get('title', ''))[:120]}"
        parts.append(f"<post record_id=\"{r['record_id']}\" {meta}>\n{r['text']}\n</post>")
        if feedback and r["record_id"] in feedback:
            parts.append(f"Your previous output for {r['record_id']} failed these checks; fix them: "
                         + "; ".join(feedback[r["record_id"]]))
    return "\n".join(parts)


def _flatten(label: dict) -> dict:
    out = dict(label)
    for f, spec in CODEBOOK.items():
        if spec.get("multi"):
            v = out.get(f) or []
            out[f] = " | ".join(v) if isinstance(v, list) else str(v)
    return out


def _load_cache():
    done = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                    done[row["record_id"]] = row
                except json.JSONDecodeError:
                    pass
    return done


def label_records(cands: pd.DataFrame, run_id: str, batch_size: int = 8, rpm: int = 10,
                  limit: int | None = None, log=print) -> pd.DataFrame:
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    llm = Gemini(rpm=rpm)
    done = _load_cache()
    todo = cands[~cands["record_id"].isin(done)]
    if limit:
        todo = todo.head(max(0, limit - len(done)))
    log(f"AI coding with {llm.model}: {len(done)} cached, {len(todo)} to code")
    system, schema = _system(), _schema()
    text_by_id = dict(zip(cands["record_id"], cands["text"]))

    def _save(row):
        with open(CACHE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        done[row["record_id"]] = row

    for start in range(0, len(todo), batch_size):
        batch = todo.iloc[start:start + batch_size]
        try:
            items = llm.json(system, _prompt(batch), schema).get("items", [])
        except Exception as e:
            log(f"  batch {start // batch_size + 1} failed: {e}")
            continue
        by_id = {str(i.get("record_id")): i for i in items}
        retry = {}
        for rid in batch["record_id"]:
            lab = by_id.get(rid)
            fails = ["missing from model output"] if lab is None else check(lab, text_by_id[rid])
            if not fails:
                _save({**_flatten(lab), "record_id": rid, "gate_status": "passed_first",
                       "gate_fails": "", "model": llm.model, "run_id": run_id})
            else:
                retry[rid] = fails
        # one retry per failing post, alone, with the reasons
        for rid, fails in retry.items():
            one = batch[batch["record_id"] == rid]
            try:
                items = llm.json(system, _prompt(one, {rid: fails}), schema).get("items", [])
                lab = items[0] if items else None
            except Exception as e:
                lab, fails = None, fails + [f"retry error: {e}"]
            new_fails = ["missing from model output"] if lab is None else check(lab, text_by_id[rid])
            if not new_fails:
                _save({**_flatten(lab), "record_id": rid, "gate_status": "passed_retry",
                       "gate_fails": "; ".join(fails), "model": llm.model, "run_id": run_id})
            else:
                base = _flatten(lab) if lab else {}
                _save({**base, "record_id": rid, "gate_status": "rejected",
                       "gate_fails": "; ".join(new_fails), "first_fails": "; ".join(fails),
                       "model": llm.model, "run_id": run_id})
        n = min(start + batch_size, len(todo))
        if n % (batch_size * 10) == 0 or n == len(todo):
            log(f"  coded {n}/{len(todo)}")

    rows = [done[r] for r in cands["record_id"] if r in done]
    return pd.DataFrame(rows)


def stamp():
    return datetime.now(timezone.utc).strftime("run_%Y-%m-%dT%H-%M")
