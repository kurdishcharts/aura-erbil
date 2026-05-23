"""
Aura-Erbil — TikTok Scraper
Scrapes recent posts from Kurdish news TikTok accounts.
Uses TikTok's internal API — no authentication or API key required.
Designed for GitHub Actions and local use.
"""

import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ── CONFIG ───────────────────────────────────────────────────────────────────
DB_PATH           = "data/aura.db"
JSON_EXPORT       = "data/data.json"
MAX_POSTS_PER_ACCOUNT = 10

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

TIKTOK_ACCOUNTS = [
    "rudaw.official",
    "channel8corp",
    "nrttvofficial",
    "964.kurdi",
    "vartvnet",
    "paytextmedia",
    "kurdistan24",
    "avamediatv",
]

# ── DATABASE ─────────────────────────────────────────────────────────────────
def _ensure_db():
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
            category      TEXT DEFAULT 'general',
            sentiment     TEXT DEFAULT 'neutral',
            entities      TEXT DEFAULT '[]',
            loc_name      TEXT DEFAULT 'Erbil',
            lat           REAL DEFAULT 36.1912,
            lng           REAL DEFAULT 44.0092,
            published_at  TEXT,
            fetched_at    TEXT,
            breaking      INTEGER DEFAULT 1
        )
    """)
    # Add columns if missing (safe migration)
    for col in ["title_en", "entities", "sentiment", "loc_name", "lat", "lng",
                 "published_at", "breaking"]:
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _make_id(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _upsert(conn, item):
    existing = conn.execute(
        "SELECT id FROM articles WHERE url=?", (item["url"],)
    ).fetchone()
    if existing:
        return  # skip duplicate
    conn.execute("""
        INSERT INTO articles
            (id, url, title, title_en, summary, source, category,
             sentiment, entities, loc_name, lat, lng,
             published_at, fetched_at, breaking)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        item["id"], item["url"], item["title"], item.get("title_en", item["title"]),
        item.get("summary", ""), item["source"],
        item.get("category", "general"), item.get("sentiment", "neutral"),
        json.dumps(item.get("entities", [])),
        item.get("loc_name", "Erbil"), item.get("lat", 36.1912), item.get("lng", 44.0092),
        item.get("published_at"), _now_iso(), item.get("breaking", 1),
    ))
    conn.commit()

# ── TIKTOK SCRAPING ─────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,ku;q=0.9",
    "Referer": "https://www.tiktok.com/",
})

def _get_secuid(username):
    """Fetch a TikTok profile page and extract secUid from the embedded JSON."""
    url = f"https://www.tiktok.com/@{username}"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"  [{username}] HTTP {resp.status_code}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        script = soup.find("script", id="__UNIVERSAL_DATA_FOR_REHYDRATION__")
        if not script:
            print(f"  [{username}] No embedded data found (page may require JS)")
            return None

        data = json.loads(script.string)
        user_detail = (
            data.get("__DEFAULT_SCOPE__", {})
            .get("webapp.user-detail", {})
        )
        user_info = user_detail.get("userInfo", {}).get("user", {})
        secuid = user_info.get("secUid", "")
        if secuid:
            return secuid
        # Fallback: try alternate key path
        alt = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {})
        return alt.get("userInfo", {}).get("user", {}).get("secUid", "")
    except Exception as e:
        print(f"  [{username}] Error fetching profile: {e}")
        return None

def _fetch_posts(secuid, username, count=MAX_POSTS_PER_ACCOUNT):
    """Call TikTok's internal API to get recent posts for a user."""
    url = "https://www.tiktok.com/api/post/item_list/"
    params = {
        "aid": "1988",
        "count": str(count),
        "cursor": "0",
        "device_platform": "web_pc",
        "secUid": secuid,
        "region": "US",
        "priority_region": "",
        "language": "en",
    }
    headers = {
        "Referer": f"https://www.tiktok.com/@{username}",
        "User-Agent": USER_AGENT,
    }
    try:
        resp = session.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"  [{username}] API returned HTTP {resp.status_code}")
            return []
        data = resp.json()
        items = data.get("itemList", [])
        return items
    except Exception as e:
        print(f"  [{username}] Error fetching posts: {e}")
        return []

def _process_post(post, username):
    """Convert a TikTok post JSON object to an article dict."""
    video_id = post.get("id", "")
    desc = post.get("desc", "") or "(no caption)"
    create_time = post.get("createTime", 0)
    if create_time:
        pub_ts = datetime.fromtimestamp(create_time, tz=timezone.utc).isoformat()
    else:
        pub_ts = _now_iso()

    # Extract hashtags as entities
    hashtags = re.findall(r'#(\w+)', desc)
    entities = [{"name": f"#{tag}", "type": "TAG"} for tag in hashtags]

    # Extract mentions
    mentions = re.findall(r'@(\w+)', desc)
    entities += [{"name": f"@{m}", "type": "MENTION"} for m in mentions]

    # Engagement stats
    stats = post.get("stats", {})
    play_count = stats.get("playCount", 0)
    digg_count = stats.get("diggCount", 0)
    comment_count = stats.get("commentCount", 0)
    share_count = stats.get("shareCount", 0)

    # Build enriched summary
    summary = desc[:500]
    if play_count:
        summary += f" | ❤️{digg_count} 💬{comment_count} 🔄{share_count}"

    video_url = f"https://www.tiktok.com/@{username}/video/{video_id}"

    return {
        "id": _make_id(video_url),
        "url": video_url,
        "title": desc[:200],
        "title_en": desc[:200],
        "summary": summary,
        "source": f"tiktok-{username}",
        "category": "social",
        "sentiment": "neutral",
        "entities": entities,
        "loc_name": "Kurdistan Region",
        "lat": 36.1912,
        "lng": 44.0092,
        "published_at": pub_ts,
        "breaking": 1,
    }

# ── EXPORT ──────────────────────────────────────────────────────────────────
def _export_json(conn):
    rows = conn.execute(
        "SELECT * FROM articles ORDER BY published_at DESC"
    ).fetchall()
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
            "sentiment": r["sentiment"] or "neutral",
            "entities":  json.loads(r["entities"] or "[]"),
            "breaking":  r["breaking"] or 1,
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

# ── MAIN ────────────────────────────────────────────────────────────────────
def main():
    print("=== Aura-Erbil TikTok Scraper ===")
    _ensure_db()
    conn = _connect()
    total = 0

    for username in TIKTOK_ACCOUNTS:
        print(f"\n→ @{username}")
        secuid = _get_secuid(username)
        if not secuid:
            print(f"  [{username}] Could not get secUid — skipping")
            continue

        print(f"  secUid: {secuid[:12]}...")
        posts = _fetch_posts(secuid, username)

        if not posts:
            print(f"  [{username}] No posts returned")
            continue

        print(f"  Fetched {len(posts)} posts")
        saved = 0
        for post in posts:
            article = _process_post(post, username)
            _upsert(conn, article)
            saved += 1
            print(f"  [saved] {article['title'][:60]}")

        total += saved
        time.sleep(2)  # polite delay between accounts

    conn.commit()
    _export_json(conn)
    conn.close()
    print(f"\n=== Done: {total} new TikTok articles ===")

if __name__ == "__main__":
    main()
