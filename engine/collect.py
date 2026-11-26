"""Collect public feedback. Runs on your laptop (needs internet + your keys).

Sources
  play_store     google-play-scraper (no key)
  app_store      Apple's public review feed (no key, max 500 newest)
  google_search  SerpApi Google results, India      (SERPAPI_KEY)
  reddit         threads found via SerpApi, comments read from Reddit's public
                 .json pages (no Reddit API); snippet kept if a page is blocked
  youtube        YouTube Data API v3 comments        (YOUTUBE_API_KEY)

Privacy: author names are never stored, only a one-way hash. Phone numbers
and e-mail addresses are masked in the text.
"""
import hashlib
import os
import re
import time
from datetime import datetime, timezone

import requests

from .config import APP_IDS, COUNTRY, LANG, MAX_PER_SOURCE, SEARCH_QUERIES

UA = {"User-Agent": "uc-repeat-discovery/1.0 (student research project)"}
SALT = os.getenv("AUTHOR_SALT", "uc-discovery")
PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _hash(name):
    if not name:
        return ""
    return hashlib.sha256((SALT + str(name)).encode()).hexdigest()[:12]


def _clean(text):
    text = PHONE.sub("[phone]", str(text or ""))
    text = EMAIL.sub("[email]", text)
    return re.sub(r"\s+", " ", text).strip()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rec(source, rid, text, **kw):
    return {
        "record_id": f"{source[:2].upper()}-{rid}",
        "source": source,
        "type": kw.get("type", ""),
        "title": _clean(kw.get("title", ""))[:300],
        "text": _clean(text),
        "author_hash": _hash(kw.get("author")),
        "rating": kw.get("rating", ""),
        "likes": kw.get("likes", ""),
        "date": kw.get("date", ""),
        "link": kw.get("link", ""),
        "query": kw.get("query", ""),
        "community": kw.get("community", ""),
        "collected_at": _now(),
    }


# ----------------------------------------------------------------- Play Store
def play_store(log=print):
    from google_play_scraper import Sort, reviews
    out, token = [], None
    target = MAX_PER_SOURCE["play_store"]
    while len(out) < target:
        batch, token = reviews(APP_IDS["play_store"], lang=LANG, country=COUNTRY,
                               sort=Sort.NEWEST, count=min(200, target - len(out)),
                               continuation_token=token)
        if not batch:
            break
        for r in batch:
            out.append(_rec("play_store", r["reviewId"][:24], r.get("content"),
                            type="review", author=r.get("userName"), rating=r.get("score"),
                            likes=r.get("thumbsUpCount"),
                            date=r["at"].date().isoformat() if r.get("at") else "",
                            link=f"https://play.google.com/store/apps/details?id={APP_IDS['play_store']}&reviewId={r['reviewId']}",
                            query="newest reviews"))
        log(f"  play_store: {len(out)}")
        if token is None:
            break
        time.sleep(1)
    return out


# ------------------------------------------------------------------ App Store
def app_store(log=print):
    out = []
    for page in range(1, 11):
        url = (f"https://itunes.apple.com/{COUNTRY}/rss/customerreviews/page={page}/"
               f"id={APP_IDS['app_store']}/sortby=mostrecent/json")
        try:
            entries = requests.get(url, headers=UA, timeout=30).json().get("feed", {}).get("entry", [])
        except Exception as e:
            log(f"  app_store page {page}: {e}")
            break
        if isinstance(entries, dict):
            entries = [entries]
        if not entries:
            break
        for e in entries:
            if "im:rating" not in e:
                continue
            out.append(_rec("app_store", e["id"]["label"], e["content"]["label"],
                            type="review", title=e.get("title", {}).get("label", ""),
                            author=e.get("author", {}).get("name", {}).get("label"),
                            rating=e["im:rating"]["label"],
                            date=e.get("updated", {}).get("label", "")[:10],
                            link=f"https://apps.apple.com/{COUNTRY}/app/id{APP_IDS['app_store']}?see-all=reviews",
                            query="most recent reviews"))
        log(f"  app_store: {len(out)}")
        time.sleep(1)
    return out


# ------------------------------------------------------------- Google Search
def _serp(q, num=100):
    key = os.getenv("SERPAPI_KEY", "").strip()
    if not key:
        raise RuntimeError("SERPAPI_KEY is not set")
    r = requests.get("https://serpapi.com/search.json", timeout=60, params={
        "engine": "google", "q": q, "gl": COUNTRY, "hl": LANG, "num": num, "api_key": key})
    r.raise_for_status()
    return r.json().get("organic_results", [])


def google_search(log=print):
    out, seen = [], set()
    for q in SEARCH_QUERIES["google_search"]:
        try:
            results = _serp(q, MAX_PER_SOURCE["google_search"])
        except Exception as e:
            log(f"  google_search '{q}': {e}")
            continue
        for r in results:
            link = r.get("link", "")
            if not link or link in seen or "reddit.com" in link or "youtube.com" in link:
                continue
            seen.add(link)
            text = f"{r.get('title', '')}. {r.get('snippet', '')}"
            out.append(_rec("google_search", hashlib.md5(link.encode()).hexdigest()[:10], text,
                            type="web", title=r.get("title", ""), date=r.get("date", ""),
                            link=link, query=q, community=r.get("source", "")))
        log(f"  google_search: {len(out)} after '{q}'")
    return out


# ---------------------------------------------------------------------- Reddit
def _walk_comments(children, depth=0):
    for c in children:
        d = c.get("data", {})
        if c.get("kind") == "t1":
            yield d
            rep = d.get("replies")
            if isinstance(rep, dict) and depth < 4:
                yield from _walk_comments(rep.get("data", {}).get("children", []), depth + 1)


def reddit(log=print):
    out, seen = [], set()
    for q in SEARCH_QUERIES["reddit"]:
        try:
            results = _serp(q, MAX_PER_SOURCE["reddit"])
        except Exception as e:
            log(f"  reddit search '{q}': {e}")
            continue
        for r in results:
            link = r.get("link", "").split("?")[0]
            if "/comments/" not in link or link in seen:
                continue
            seen.add(link)
            sub = re.search(r"/r/([^/]+)/", link)
            community = f"r/{sub.group(1)}" if sub else ""
            try:
                js = requests.get(link.rstrip("/") + ".json?limit=200", headers=UA, timeout=30).json()
                post = js[0]["data"]["children"][0]["data"]
                pid = post.get("id", "")
                date = datetime.fromtimestamp(post.get("created_utc", 0), timezone.utc).date().isoformat()
                body = f"{post.get('title', '')}. {post.get('selftext', '')}"
                out.append(_rec("reddit", pid, body, type="post", title=post.get("title", ""),
                                author=post.get("author"), likes=post.get("score"), date=date,
                                link=link, query=q, community=community))
                for c in _walk_comments(js[1]["data"]["children"]):
                    out.append(_rec("reddit", f"{pid}-{c.get('id')}", c.get("body", ""),
                                    type="comment", title=post.get("title", ""),
                                    author=c.get("author"), likes=c.get("score"),
                                    date=datetime.fromtimestamp(c.get("created_utc", 0), timezone.utc).date().isoformat(),
                                    link=f"{link}{c.get('id')}/", query=q, community=community))
                time.sleep(2)
            except Exception:
                # page blocked or changed: keep the search snippet so the thread still counts
                out.append(_rec("reddit", hashlib.md5(link.encode()).hexdigest()[:10],
                                f"{r.get('title', '')}. {r.get('snippet', '')}", type="snippet",
                                title=r.get("title", ""), link=link, query=q, community=community))
        log(f"  reddit: {len(out)} after '{q}'")
    return out


# --------------------------------------------------------------------- YouTube
def youtube(log=print):
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY is not set")
    base = "https://www.googleapis.com/youtube/v3/"
    out, vids = [], {}
    for q in SEARCH_QUERIES["youtube"]:
        r = requests.get(base + "search", timeout=30, params={
            "part": "snippet", "q": q, "type": "video", "regionCode": "IN",
            "relevanceLanguage": "en", "maxResults": MAX_PER_SOURCE["youtube"], "key": key}).json()
        for it in r.get("items", []):
            vids.setdefault(it["id"]["videoId"], (it["snippet"]["title"], q))
    log(f"  youtube: {len(vids)} videos")
    for vid, (title, q) in vids.items():
        token, n = None, 0
        while n < 300:
            p = {"part": "snippet,replies", "videoId": vid, "maxResults": 100,
                 "textFormat": "plainText", "key": key}
            if token:
                p["pageToken"] = token
            r = requests.get(base + "commentThreads", params=p, timeout=30).json()
            if "error" in r:
                break
            for th in r.get("items", []):
                top = th["snippet"]["topLevelComment"]
                s = top["snippet"]
                out.append(_rec("youtube", top["id"], s.get("textDisplay"), type="comment",
                                title=title, author=s.get("authorDisplayName"),
                                likes=s.get("likeCount"), date=s.get("publishedAt", "")[:10],
                                link=f"https://www.youtube.com/watch?v={vid}&lc={top['id']}",
                                query=q, community=title[:80]))
                n += 1
                for rep in th.get("replies", {}).get("comments", []):
                    rs = rep["snippet"]
                    out.append(_rec("youtube", rep["id"], rs.get("textDisplay"), type="reply",
                                    title=title, author=rs.get("authorDisplayName"),
                                    likes=rs.get("likeCount"), date=rs.get("publishedAt", "")[:10],
                                    link=f"https://www.youtube.com/watch?v={vid}&lc={rep['id']}",
                                    query=q, community=title[:80]))
            token = r.get("nextPageToken")
            if not token:
                break
    log(f"  youtube: {len(out)} comments")
    return out


SOURCES = {
    "play_store": play_store,
    "app_store": app_store,
    "google_search": google_search,
    "reddit": reddit,
    "youtube": youtube,
}
