"""
Aura-Erbil — AI Enrichment Scraper (Ollama local)
Uses the SAME database and JSON export as the main scraper.
Run manually:  python scraper/scraper_ollama.py
Safe to run alongside the original scraper.py.
"""

import hashlib
import json
import os
import random
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

# ── CONFIG (identical to main scraper) ───────────────────────────────────────
BASE_URL          = "https://www.rudaw.net"
RUDAW_RSS         = "https://www.rudaw.net/rss"
LIST_PATHS        = [
    "/english",
    "/sorani/kurdistan",
    "/sorani/middleeast",
    "/sorani/business",
    "/kurmanci",
]
USER_AGENT        = "AuraErbilBot/4.0 (monitoring dashboard; non-commercial)"
DB_PATH           = "data/aura.db"
JSON_EXPORT       = "data/data.json"
MAX_AGE_DAYS      = 30
MAX_PAGES_PER_RUN = 40
MIN_DELAY         = 2.0
MAX_DELAY         = 5.0
BACKOFF_BASE      = 2.0
MAX_BACKOFF       = 60.0
OLLAMA_MODEL      = "llama3.2:3b"
OLLAMA_TIMEOUT    = 30

# ── INCIDENT KEYWORDS ────────────────────────────────────────────────────────
KEYWORDS: dict[str, list[str]] = {
    "security": [
        "تەقینەوە", "ئەمنییەت", "چەکدار", "کوژران", "تیرکردن",
        "explosion", "attack", "armed", "killed", "shooting",
        "bomb", "ISIS", "PKK", "militant", "arrest", "detained",
    ],
    "fire": [
        "ئاگر", "سووتان",
        "fire", "blaze", "burning", "flames", "wildfire",
    ],
    "traffic": [
        "رووداوی هاتووچۆ", "ترافیک", "ڕووداوی",
        "accident", "crash", "traffic", "road", "collision",
        "highway", "vehicle", "truck", "bus",
    ],
    "infrastructure": [
        "داخستن", "کۆپری", "ڕێگا",
        "closure", "bridge", "road closure", "construction",
        "power cut", "electricity", "water supply", "outage",
    ],
    "weather": [
        "باران", "بەفر", "تەقەر", "زەلزەلە",
        "flood", "earthquake", "storm", "rain", "snow",
        "temperature", "heat", "dust storm",
    ],
}

# ── ERBIL GEOCODER DICTIONARY ────────────────────────────────────────────────
LOCATIONS: dict[str, tuple[float, float]] = {
    "100 meter road":    (36.1911, 44.0092),
    "100m road":         (36.1911, 44.0092),
    "60 meter road":     (36.2041, 44.0112),
    "60m road":          (36.2041, 44.0112),
    "30 meter road":     (36.1985, 44.0055),
    "kirkuk road":       (36.1722, 44.0489),
    "sulaymaniyah road": (36.1600, 44.0700),
    "mosul road":        (36.2300, 43.9800),
    "airport road":      (36.2373, 43.9632),
    "koya road":         (36.1680, 44.0820),
    "shaqlawa road":     (36.2400, 44.1000),
    "bakhtiyari":        (36.2078, 44.0231),
    "shoresh":           (36.1875, 44.0321),
    "ankawa":            (36.2497, 43.9992),
    "iskan":             (36.1950, 44.0150),
    "dream city":        (36.2200, 43.9950),
    "gulan":             (36.1980, 44.0050),
    "sarchinar":         (36.1730, 44.0380),
    "azadi":             (36.1890, 44.0070),
    "erbil citadel":     (36.1912, 44.0092),
    "qaysari":           (36.1910, 44.0080),
    "family mall":       (36.2219, 44.0003),
    "majidi mall":       (36.2116, 44.0199),
    "franso hariri":     (36.1886, 44.0024),
    "هەولێر":            (36.1912, 44.0092),
    "بەختیاری":          (36.2078, 44.0231),
    "ئەنکەوە":           (36.2497, 43.9992),
    "شۆڕەش":            (36.1875, 44.0321),
    "سەرچنار":           (36.1730, 44.0380),
    "ئیسکان":            (36.1950, 44.0150),
    "erbil":             (36.1912, 44.0092),
    "hewler":            (36.1912, 44.0092),
    "kurdistan":         (36.1912, 44.0092),
}

# ── HTTP SESSION + ROBOTS ────────────────────────────────────────────────────
session = requests.Session()
session.headers.update({
    "User-Agent":      USER_AGENT,
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,ku;q=0.9",
})

_rp = robotparser.RobotFileParser()
_rp.set_url(urljoin(BASE_URL, "/robots.txt"))
try:
    _rp.read()
    print("  robots.txt loaded")
except Exception as e:
    print(f"  robots.txt fetch failed ({e}) — proceeding cautiously")

def _allowed(url: str) -> bool:
    return _rp.can_fetch(USER_AGENT, url)

def _jitter():
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

def _fetch(url: str, etag=None, last_modified=None, _backoff=BACKOFF_BASE):
    if not _allowed(url):
        print(f"  [robots.txt] blocked: {url}")
        return None, None, None
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    try:
        r = session.get(url, headers=headers, timeout=12)
        if r.status_code == 304:
            return "NOT_MODIFIED", etag, last_modified
        if r.status_code == 200:
            _jitter()
            return r.text, r.headers.get("ETag"), r.headers.get("Last-Modified")
        if r.status_code in (429, 500, 502, 503, 504):
            wait = min(_backoff * BACKOFF_BASE, MAX_BACKOFF)
            print(f"  [backoff] {r.status_code} → waiting {wait:.1f}s")
            time.sleep(wait)
            return _fetch(url, etag, last_modified, _backoff=wait)
        print(f"  [warn] HTTP {r.status_code}: {url}")
        _jitter()
        return None, None, None
    except requests.RequestException as exc:
        wait = min(_backoff * BACKOFF_BASE, MAX_BACKOFF)
        print(f"  [error] {exc} → waiting {wait:.1f}s")
        time.sleep(wait)
        return _fetch(url, etag, last_modified, _backoff=wait)

# ── HELPERS ──────────────────────────────────────────────────────────────────
def _score_breaking(title: str, all_titles: list[str]) -> int:
    words = set(title.lower().split())
    score = 1
    for other in all_titles:
        if other == title:
            continue
        other_words = set(other.lower().split())
        if len(words & other_words) >= 4:
            score += 1
    return min(score, 3)

def _make_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _clean_title(raw: str) -> str:
    return re.sub(
        r'^\d+\s+(second|minute|hour|day)s?\s+ago', '',
        raw or '', flags=re.IGNORECASE
    ).strip()

def _detect_category(text: str) -> str:
    t = text.lower()
    for cat, words in KEYWORDS.items():
        if any(w.lower() in t for w in words):
            return cat
    return "general"

def _detect_location(text: str) -> dict:
    t = text.lower()
    for place, (lat, lng) in LOCATIONS.items():
        if place.lower() in t:
            return {"name": place.title(), "lat": lat, "lng": lng}
    return {"name": "Erbil", "lat": 36.1912, "lng": 44.0092}

def _same_origin(url: str) -> bool:
    return urlparse(url).netloc == urlparse(BASE_URL).netloc

# ── OLLAMA AI ENRICHMENT ────────────────────────────────────────────────────
def _has_sorani(text: str) -> bool:
    return bool(re.search(r'[\u0600-\u06FF\u0750-\u077F]', text))

def _enrich_with_ai(title_original: str, summary: str) -> dict:
    loc_keys = list(LOCATIONS.keys())
    loc_list_str = ", ".join(loc_keys[:40])

    prompt = f"""You are a news enrichment assistant for the Kurdistan region.
Given the title and body of a news article, perform these tasks:
1. If the title is in Sorani Kurdish (Arabic script), translate it to English.
   If it is already in English, return it unchanged.
2. Classify the article into ONE of these categories:
   security, fire, traffic, infrastructure, weather, general.
3. From the list below, pick the single location most specific to the article.
   If none match, use "erbil".

Available locations: {loc_list_str}

Return ONLY a valid JSON object with exactly these keys:
title_en, category, location_key

Title: {title_original}
Body: {summary[:500]}"""

    try:
        import ollama
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.0, "num_predict": 200},
            stream=False,
        )
        raw = response['message']['content']
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            raise ValueError("No JSON found in Ollama response")
        data = json.loads(match.group())
    except Exception as e:
        print(f"  [ollama] AI call failed ({e}), falling back to keyword defaults")
        loc = _detect_location(title_original + " " + summary)
        return {
            "title_en": title_original,
            "category": _detect_category(title_original + " " + summary),
            "loc_name": loc["name"],
            "lat": loc["lat"],
            "lng": loc["lng"],
        }

    valid_cats = set(KEYWORDS.keys()) | {"general"}
    cat = data.get("category", "general")
    if cat not in valid_cats:
        cat = "general"

    loc_key = data.get("location_key", "").strip().lower()
    if loc_key in LOCATIONS:
        lat, lng = LOCATIONS[loc_key]
        loc_name = loc_key.title()
    else:
        lat, lng = LOCATIONS.get("erbil", (36.1912, 44.0092))
        loc_name = "Erbil"

    title_en = data.get("title_en", title_original).strip()
    if not title_en:
        title_en = title_original

    return {
        "title_en": title_en,
        "category": cat,
        "loc_name": loc_name,
        "lat": lat,
        "lng": lng,
    }

# ── DATABASE (adds title_en column automatically) ────────────────────────────
def _ensure_db():
    """Make sure the DB table has the title_en column (safe no matter who runs first)."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id            TEXT PRIMARY KEY,
            url           TEXT UNIQUE NOT NULL,
            title         TEXT,
            title_en      TEXT,
            summary       TEXT,
            source        TEXT,
            category      TEXT,
            loc_name      TEXT,
            lat           REAL,
            lng           REAL,
            published_at  TEXT,
            fetched_at    TEXT,
            etag          TEXT,
            last_modified TEXT,
            breaking      INTEGER DEFAULT 1
        )
    """)
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN title_en TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _db_upsert(conn, item: dict, etag=None, lm=None):
    conn.execute("""
        INSERT INTO articles
            (id,url,title,title_en,summary,source,category,
             loc_name,lat,lng,published_at,fetched_at,etag,last_modified,breaking)
        VALUES
            (:id,:url,:title,:title_en,:summary,:source,:category,
             :loc_name,:lat,:lng,:published_at,:fetched_at,:etag,:lm,:breaking)
        ON CONFLICT(url) DO UPDATE SET
            title=excluded.title, title_en=excluded.title_en,
            summary=excluded.summary,
            category=excluded.category, loc_name=excluded.loc_name,
            lat=excluded.lat, lng=excluded.lng,
            published_at=excluded.published_at, fetched_at=excluded.fetched_at,
            etag=excluded.etag, last_modified=excluded.last_modified
    """, {**item, "etag": etag, "lm": lm})
    conn.commit()

def _db_prune(conn):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).isoformat()
    conn.execute("DELETE FROM articles WHERE published_at < ?", (cutoff,))
    conn.commit()

def _export_json(conn):
    rows = conn.execute("SELECT * FROM articles ORDER BY published_at DESC").fetchall()
    all_titles = [r["title"] or "" for r in rows]
    records = []
    for r in rows:
        records.append({
            "id":        r["id"],
            "url":       r["url"],
            "title":     r["title"],
            "title_en":  r["title_en"] or r["title"],   # fallback if null
            "summary":   r["summary"],
            "source":    r["source"],
            "category":  r["category"],
            "breaking":  _score_breaking(r["title"] or "", all_titles),
            "timestamp": r["published_at"],
            "location": {
                "name": r["loc_name"],
                "lat":  r["lat"],
                "lng":  r["lng"],
            },
        })
    with open(JSON_EXPORT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"  Exported {len(records)} records → {JSON_EXPORT}")

# ── INGEST LOGIC (with AI) ───────────────────────────────────────────────────
def _run():
    print("=== Aura-Erbil AI Scraper (Ollama) ===")
    _ensure_db()
    conn = _connect()

    # RSS
    print("→ RSS feed …")
    added = 0
    try:
        feed = feedparser.parse(RUDAW_RSS)
        for entry in feed.entries:
            url   = entry.get("link", "")
            title = _clean_title(entry.get("title", "").strip())
            if not url or not title:
                continue
            summary = BeautifulSoup(
                entry.get("summary", ""), "lxml"
            ).get_text(" ", strip=True)[:300]
            pub_parsed = entry.get("published_parsed")
            pub = datetime(*pub_parsed[:6], tzinfo=timezone.utc).isoformat() if pub_parsed else _now_iso()

            enrichment = _enrich_with_ai(title, summary) if (title or summary) else {
                "title_en": title, "category": "general",
                "loc_name": "Erbil", "lat": 36.1912, "lng": 44.0092,
            }

            _db_upsert(conn, {
                "id": _make_id(url), "url": url, "title": title,
                "title_en": enrichment["title_en"],
                "summary": summary, "source": "rudaw-rss",
                "category": enrichment["category"],
                "loc_name": enrichment["loc_name"],
                "lat": enrichment["lat"], "lng": enrichment["lng"],
                "published_at": pub, "fetched_at": _now_iso(), "breaking": 1,
            })
            added += 1
            if added % 5 == 0:
                time.sleep(1)
        print(f"  RSS: processed {added} entries")
    except Exception as exc:
        print(f"  RSS error: {exc}")

    # Scrape fallback
    if added == 0:
        print("  RSS returned nothing — triggering scrape fallback …")
        queue   = [urljoin(BASE_URL, p) for p in LIST_PATHS]
        visited = set()
        pages   = 0
        while queue and pages < MAX_PAGES_PER_RUN:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            if any(url.rstrip("/").endswith(p.rstrip("/")) for p in LIST_PATHS):
                html, _, _ = _fetch(url)
                if not html:
                    continue
                pages += 1
                soup = BeautifulSoup(html, "lxml")
                for a in soup.select("a[href]"):
                    href = a["href"]
                    full = urljoin(BASE_URL, href)
                    text = _clean_title(a.get_text(strip=True))
                    if (
                        _same_origin(full)
                        and ("/english/" in full or "/sorani/" in full or "/kurmanci/" in full)
                        and len(text) > 20
                    ):
                        queue.append(full)
                continue
            # article page
            etag, lm = conn.execute(
                "SELECT etag, last_modified FROM articles WHERE url=?", (url,)
            ).fetchone() or (None, None)
            html, new_etag, new_lm = _fetch(url, etag, lm)
            pages += 1
            if html in (None, "NOT_MODIFIED"):
                continue
            soup = BeautifulSoup(html, "lxml")
            h1 = soup.find("h1")
            title = _clean_title(h1.get_text(strip=True) if h1 else "")
            if not title:
                continue
            time_tag = soup.find("time")
            pub = time_tag["datetime"] if time_tag and time_tag.get("datetime") else _now_iso()
            paras = [p.get_text(" ", strip=True) for p in soup.select("article p, .article-body p")]
            summary = " ".join(paras)[:300] if paras else ""
            enrichment = _enrich_with_ai(title, summary) if title else {
                "title_en": title, "category": "general",
                "loc_name": "Erbil", "lat": 36.1912, "lng": 44.0092,
            }
            _db_upsert(conn, {
                "id": _make_id(url), "url": url, "title": title,
                "title_en": enrichment["title_en"],
                "summary": summary, "source": "rudaw-scrape",
                "category": enrichment["category"],
                "loc_name": enrichment["loc_name"],
                "lat": enrichment["lat"], "lng": enrichment["lng"],
                "published_at": pub, "fetched_at": _now_iso(), "breaking": 1,
            })
            added += 1
            print(f"  [saved] {title[:70]}")
            if added % 3 == 0:
                time.sleep(1)
        print(f"  Scrape: {added} new articles ({pages} pages fetched)")

    _db_prune(conn)
    _export_json(conn)
    conn.close()
    print("=== Done ===")

if __name__ == "__main__":
    _run()