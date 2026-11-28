"""Small Gemini client (REST, no SDK). Fails safely so the app can fall back to rules and templates.

Key: GEMINI_API_KEY in the environment or in Streamlit secrets.
Model: GEMINI_MODEL (optional). Defaults to the 'latest Flash' alias, then gemini-2.5-flash.
"""
from __future__ import annotations

import json
import os
import time

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODELS = ["gemini-flash-latest", "gemini-2.5-flash"]


class LLMError(Exception):
    pass


def _secret(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name].strip()
    try:
        import streamlit as st
        return str(st.secrets.get(name, "") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


class Gemini:
    def __init__(self, key: str | None = None, timeout: int = 15):
        self.key = key if key is not None else _secret("GEMINI_API_KEY")
        pinned = _secret("GEMINI_MODEL")
        self.models = ([pinned] if pinned else []) + [m for m in DEFAULT_MODELS if m != pinned]
        self.timeout = timeout
        self.last_model = None
        self.last_seconds = 0.0

    @property
    def available(self) -> bool:
        return bool(self.key)

    def _call(self, system: str, user: str, as_json: bool) -> str:
        if not self.available:
            raise LLMError("No GEMINI_API_KEY configured.")
        cfg = {"temperature": 0.1, "maxOutputTokens": 800}
        if as_json:
            cfg["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": cfg}
        errors = []
        for model in self.models:
            t0 = time.monotonic()
            try:
                r = requests.post(API.format(model=model), params={"key": self.key}, json=body, timeout=self.timeout)
            except requests.RequestException as e:
                errors.append(f"{model}: {e.__class__.__name__}")
                continue
            self.last_seconds = time.monotonic() - t0
            if r.status_code in (404, 429, 500, 502, 503):
                errors.append(f"{model}: HTTP {r.status_code}")
                continue
            if r.status_code != 200:
                raise LLMError(f"{model}: HTTP {r.status_code} {r.text[:200]}")
            try:
                parts = r.json()["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
            except (KeyError, IndexError, ValueError):
                errors.append(f"{model}: empty reply")
                continue
            if text:
                self.last_model = model
                return text
            errors.append(f"{model}: empty reply")
        raise LLMError("; ".join(errors) or "No model answered.")

    def json(self, system: str, user: str) -> dict:
        text = self._call(system, user, as_json=True)
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            out = json.loads(text)
        except ValueError as e:
            raise LLMError(f"Not valid JSON: {text[:120]}") from e
        if not isinstance(out, dict):
            raise LLMError("JSON was not an object.")
        return out

    def text(self, system: str, user: str) -> str:
        return self._call(system, user, as_json=False)
