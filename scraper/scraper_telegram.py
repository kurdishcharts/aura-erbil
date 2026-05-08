"""
Aura-Erbil — Telegram RSS scraper (no token needed)
Reads public Telegram RSS feeds, extracts posts, enriches via Cohere,
and upserts into the same database.
Usage: set COHERE_API_KEY, then: python scraper/scraper_telegram.py
"""

import hashlib, json, os, sqlite3, sys, time
from datetime import datetime, timezone

import feedparser

# ── config ──────────────────────────────────────────────────────────────────
TELEGRAM_FEEDS = [
    "https://tg.i-c-a.su/rss/rudawenglish",
    "https://tg.i-c-a.su/rss/AvaNews",
]
USER_AGENT        = "RSSReader/2.0"
DB_PATH           = "data/aura.db"
JSON_EXPORT       = "data/data.json"

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _make_id(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

# ── AI enrichment (import from cohere scraper) ──────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from scraper_cohere import _enrich_with_ai

def _enrich_and_save(posts, channel_name):
    conn = _connect()
    added = 0
    for post in posts:
        title = post["text"].split("\n")[0][:150]
        summary = post["text"][:500]
        enrichment = _enrich_with_ai(title, summary)
        item = {
            "id": _make_id(post["url"]),
            "url": post["url"],
            "title": title,
            "title_en": enrichment["title_en"],
            "summary": summary,
            "source": "telegram",
            "category": enrichment["category"],
            "loc_name": enrichment["loc_name"],
            "lat": enrichment["lat"],
            "lng": enrichment["lng"],
            "published_at": post["published_at"],
            "fetched_at": _now_iso(),
            "breaking": 1,
            "sentiment": enrichment.get("sentiment", "neutral"),
            "entities": json.dumps(enrichment.get("entities", []))
        }
        conn.execute("""
            INSERT INTO articles (id,url,title,title_en,summary,source,category,
                loc_name,lat,lng,published_at,fetched_at,breaking,
                sentiment,entities)
            VALUES (:id,:url,:title,:title_en,:summary,:source,:category,
                :loc_name,:lat,:lng,:published_at,:fetched_at,:breaking,
                :sentiment,:entities)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title, title_en=excluded.title_en,
                summary=excluded.summary, category=excluded.category,
                loc_name=excluded.loc_name, lat=excluded.lat, lng=excluded.lng,
                published_at=excluded.published_at, fetched_at=excluded.fetched_at,
                sentiment=excluded.sentiment, entities=excluded.entities
        """, item)
        conn.commit()
        added += 1
        print(f"  [saved] {title[:70]}")
        if added % 3 == 0:
            time.sleep(1)
    conn.close()
    return added

def _export_json(conn):
    rows = conn.execute("SELECT * FROM articles ORDER BY published_at DESC").fetchall()
    records = []
    for r in rows:
        records.append({
            "id": r["id"], "url": r["url"], "title": r["title"],
            "title_en": r["title_en"] or r["title"], "summary": r["summary"],
            "source": r["source"], "category": r["category"],
            "sentiment": r["sentiment"] or "neutral",
            "entities": json.loads(r["entities"]) if r["entities"] else [],
            "breaking": 1,
            "timestamp": r["published_at"],
            "location": {"name": r["loc_name"], "lat": r["lat"], "lng": r["lng"]}
        })
    with open(JSON_EXPORT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"  Exported {len(records)} records → {JSON_EXPORT}")

def _run():
    print("=== Aura-Erbil Telegram Scraper (RSS) ===")
    conn = _connect()
    total = 0
    for feed_url in TELEGRAM_FEEDS:
        print(f"→ Feed: {feed_url}")
        feed = feedparser.parse(feed_url)
        posts = []
        for entry in feed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            published = entry.get("published_parsed")
            pub = datetime(*published[:6], tzinfo=timezone.utc).isoformat() if published else _now_iso()
            if not title or not link:
                continue
            text = f"{title}\n{summary}"
            posts.append({"text": text, "published_at": pub, "url": link})
        print(f"  Found {len(posts)} posts")
        added = _enrich_and_save(posts, feed_url.split("/")[-1])
        total += added
    _export_json(conn)
    conn.close()
    print(f"=== Done ({total} new articles) ===")

if __name__ == "__main__":
    _run()
