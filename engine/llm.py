"""Small Gemini client (REST, no SDK) with JSON output and polite rate limiting.

Set GEMINI_API_KEY in .env (laptop) or in Streamlit secrets (hosted app).
GEMINI_MODEL defaults to the 'latest Flash' alias so it keeps working when
Google renames models; set it explicitly to pin a version.
"""
import json
import os
import time

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-2.5-flash"]


def get_key():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        try:  # hosted on Streamlit Cloud
            import streamlit as st
            key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
        except Exception:
            key = ""
    return key


def model_name():
    m = os.getenv("GEMINI_MODEL", "").strip()
    if not m:
        try:
            import streamlit as st
            m = str(st.secrets.get("GEMINI_MODEL", "")).strip()
        except Exception:
            m = ""
    return m or FALLBACK_MODELS[0]


class Gemini:
    def __init__(self, rpm: int = 10):
        self.key = get_key()
        if not self.key:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env (see .env.example).")
        self.model = model_name()
        self.min_gap = 60.0 / max(rpm, 1)
        self._last = 0.0

    def _wait(self):
        gap = time.time() - self._last
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self._last = time.time()

    def json(self, system: str, prompt: str, schema: dict | None = None,
             temperature: float = 0.0, max_tries: int = 5) -> dict:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }
        if schema:
            body["generationConfig"]["responseSchema"] = schema
        models = [self.model] + [m for m in FALLBACK_MODELS if m != self.model]
        last_err = None
        for attempt in range(max_tries):
            self._wait()
            model = models[0]
            try:
                r = requests.post(API.format(model=model), params={"key": self.key},
                                  json=body, timeout=120)
            except requests.RequestException as e:
                last_err = e
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 404 and len(models) > 1:   # model renamed / retired
                models.pop(0)
                self.model = models[0]
                continue
            if r.status_code in (429, 500, 503):
                last_err = f"{r.status_code}: {r.text[:200]}"
                time.sleep(min(60, 10 * (attempt + 1)))
                continue
            if r.status_code != 200:
                raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:300]}")
            data = r.json()
            try:
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                last_err = e
                continue
        raise RuntimeError(f"Gemini failed after {max_tries} tries: {last_err}")
