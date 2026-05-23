"""
Aura-Erbil — Simple Rudaw Scraper
Scrapes Rudaw RSS + listing pages, keyword-based category/sentiment.
No API key required. Exports data.json.
"""

import feedparser, hashlib, json, os, re, sqlite3, time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.rudaw.net"
RUDAW_RSS = "https://www.rudaw.net/rss"
LIST_PATHS = ["/english", "/sorani", "/kurmanci"]
DB_PATH = "data/aura.db"
JSON_EXPORT = "data/data.json"
MAX_AGE_DAYS = 30

KEYWORDS = {
    "security": ["explosion","attack","armed","killed","shooting","bomb","ISIS","PKK","militant","arrest","detained"],
    "fire": ["fire","blaze","burning","flames","wildfire"],
    "traffic": ["accident","crash","traffic","road","collision","highway","vehicle"],
    "infrastructure": ["closure","bridge","construction","power cut","electricity","water supply","outage"],
    "weather": ["flood","earthquake","storm","rain","snow","temperature","heat","dust storm"],
}

USER_AGENT = "AuraErbilBot/4.0 (monitoring dashboard; non-commercial)"
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _make_id(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]

def _clean_title(raw):
    return re.sub(r'^\d+\s+(second|minute|hour|day)s?\s+ago', '', raw or '', flags=re.IGNORECASE).strip()

def _detect_category(text):
    t = text.lower()
    for cat, words in KEYWORDS.items():
        if any(w.lower() in t for w in words):
            return cat
    return "general"

def _sentiment(text):
    positive = ["celebrate","progress","peace","development","agreement","growth","reform","investment"]
    negative = ["attack","killed","bomb","explosion","casualty","violence","protest","clash","destroy","death","crisis"]
    t = text.lower()
    pos = sum(1 for w in positive if w in t)
    neg = sum(1 for w in negative if w in t)
    if neg > pos: return "negative"
    if pos > neg: return "positive"
    return "neutral"

def _ensure_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY, url TEXT UNIQUE, title TEXT, title_en TEXT,
            summary TEXT, source TEXT, category TEXT, sentiment TEXT,
            entities TEXT DEFAULT '[]', loc_name TEXT DEFAULT 'Erbil',
            lat REAL DEFAULT 36.1912, lng REAL DEFAULT 44.0092,
            published_at TEXT, fetched_at TEXT, breaking INTEGER DEFAULT 1
        )
    """)
    conn.commit(); conn.close()

def _upsert(conn, item):
    existing = conn.execute("SELECT id FROM articles WHERE url=?", (item["url"],)).fetchone()
    if existing: return
    conn.execute("""
        INSERT INTO articles
            (id, url, title, title_en, summary, source, category, sentiment,
             entities, loc_name, lat, lng, published_at, fetched_at, breaking)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        item["id"], item["url"], item["title"], item.get("title_en", item["title"]),
        item.get("summary",""), item["source"], item.get("category","general"),
        item.get("sentiment","neutral"), json.dumps(item.get("entities", [])),
        item.get("loc_name","Erbil"), item.get("lat",36.1912), item.get("lng",44.0092),
        item.get("published_at"), _now_iso(), item.get("breaking",1)
    ))
    conn.commit()

def _export(conn):
    rows = conn.execute("SELECT * FROM articles ORDER BY published_at DESC").fetchall()
    records = []
    for r in rows:
        records.append({
            "id": r["id"], "url": r["url"], "title": r["title"],
            "title_en": r["title_en"] or r["title"], "summary": r["summary"],
            "source": r["source"], "category": r["category"],
            "sentiment": r["sentiment"] or "neutral",
            "entities": json.loads(r["entities"] or "[]"),
            "breaking": r["breaking"] or 1, "timestamp": r["published_at"],
            "location": {"name": r["loc_name"], "lat": r["lat"], "lng": r["lng"]}
        })
    with open(JSON_EXPORT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(records)} records → {JSON_EXPORT}")

def main():
    print("=== Simple Rudaw Scraper ===")
    _ensure_db()
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    feed = feedparser.parse(RUDAW_RSS)
    saved = 0
    for entry in feed.entries:
        url = entry.get("link","")
        title = _clean_title(entry.get("title",""))
        if not url or not title: continue
        summary = BeautifulSoup(entry.get("summary",""), "html.parser").get_text(" ", strip=True)[:300]
        pub = entry.get("published","")
        text = title + " " + summary
        item = {
            "id": _make_id(url), "url": url, "title": title,
            "title_en": title, "summary": summary, "source": "rudaw-rss",
            "category": _detect_category(text), "sentiment": _sentiment(text),
            "entities": [], "loc_name": "Erbil", "lat": 36.1912, "lng": 44.0092,
            "published_at": pub, "breaking": 1
        }
        _upsert(conn, item)
        saved += 1
        print(f"  [saved] {title[:60]}")
    conn.commit()
    _export(conn)
    conn.close()
    print(f"=== Done: {saved} articles ===")

if __name__ == "__main__":
    main()
