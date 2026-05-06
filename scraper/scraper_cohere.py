"""
Aura-Erbil — AI Enrichment Scraper (Cohere API)
Free tier: 100 calls/min. Works locally and on GitHub Actions.
Usage: set COHERE_API_KEY env var, then:
  python scraper/scraper_cohere.py
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

import cohere
import feedparser
import requests
from bs4 import BeautifulSoup

# ── CONFIG ──────────────────────────────────────────────────────────────────
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

# Cohere configuration
COHERE_MODEL      = "command-r7b-12-2024"          # or "command-r-plus" if available
# The client is initialised later with the API key from environment

# ── INCIDENT KEYWORDS ───────────────────────────────────────────────────────
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

# ── ERBIL GEOCODER DICTIONARY ───────────────────────────────────────────────
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

# ── HTTP SESSION + ROBOTS ───────────────────────────────────────────────────
session = requests.Session()
session.headers.update({
    "User-Agent":      USER_AGENT,
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,ku;q=0.9",
})

_rp = robotparser.RobotFileParser()
_rp.set_url(urljoin(BASE_URL, "/robots.txt"))
    # Add columns that might be missing from older DBs
    for col, col_type in [('title_en','TEXT'),('sentiment','TEXT'),('entities','TEXT')]:
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass
    return None, None


def _same_origin(url: str) -> bool:
    return urlparse(url).netloc == urlparse(BASE_URL).netloc

# ── COHERE AI ENRICHMENT ────────────────────────────────────────────────────
# Initialise Cohere client once (requires COHERE_API_KEY env var)
    # Add columns that might be missing from older DBs
    for col, col_type in [('title_en','TEXT'),('sentiment','TEXT'),('entities','TEXT')]:
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    # Add sentiment and entities columns if missing
    for col, col_type in [("sentiment", "TEXT"), ("entities", "TEXT")]:
    # Add columns that might be missing from older DBs
    for col, col_type in [('title_en','TEXT'),('sentiment','TEXT'),('entities','TEXT')]:
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {col_type}")
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
             loc_name,lat,lng,published_at,fetched_at,etag,last_modified,breaking,
             sentiment,entities)
        VALUES
            (:id,:url,:title,:title_en,:summary,:source,:category,
             :loc_name,:lat,:lng,:published_at,:fetched_at,:etag,:lm,:breaking,
             :sentiment,:entities)
        ON CONFLICT(url) DO UPDATE SET
            title=excluded.title, title_en=excluded.title_en,
            summary=excluded.summary,
            category=excluded.category, loc_name=excluded.loc_name,
            lat=excluded.lat, lng=excluded.lng,
            published_at=excluded.published_at, fetched_at=excluded.fetched_at,
            etag=excluded.etag, last_modified=excluded.last_modified,
            sentiment=excluded.sentiment, entities=excluded.entities
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
            "title_en":  r["title_en"] or r["title"],
            "summary":   r["summary"],
            "source":    r["source"],
            "category":  r["category"],
            "sentiment": (r["sentiment"] or "neutral"),
            "entities": json.loads(r["entities"] or "[]"),
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

# ── MAIN INGEST (with Cohere) ───────────────────────────────────────────────
def _run():
    print("=== Aura-Erbil AI Scraper (Cohere API) ===")
    _ensure_db()
    conn = _connect()

    # RSS
    print("→ RSS feed …")
    added = 0
    # Add columns that might be missing from older DBs
    for col, col_type in [('title_en','TEXT'),('sentiment','TEXT'),('entities','TEXT')]:
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass
