"""
Aura-Erbil — High‑Volume TikTok Scraper
Fetches up to 50 recent posts per account using cursor pagination.
Deduplicates by video ID. No authentication required.
"""

import hashlib, json, os, re, sqlite3, time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

DB_PATH = "data/aura.db"
JSON_EXPORT = "data/data.json"
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

MAX_POSTS_PER_ACCOUNT = 50

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT,
                         "Referer": "https://www.tiktok.com/"})

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _make_id(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]

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
    if existing: return False
    conn.execute("""
        INSERT INTO articles
            (id, url, title, title_en, summary, source, category, sentiment,
             entities, loc_name, lat, lng, published_at, fetched_at, breaking)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        item["id"], item["url"], item["title"], item.get("title_en", item["title"]),
        item.get("summary",""), item["source"], item.get("category","social"),
        item.get("sentiment","neutral"), json.dumps(item.get("entities", [])),
        item.get("loc_name","Kurdistan Region"), item.get("lat",36.1912), item.get("lng",44.0092),
        item.get("published_at"), _now_iso(), item.get("breaking",1)
    ))
    conn.commit()
    return True

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

def _get_secuid(username):
    url = f"https://www.tiktok.com/@{username}"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        script = soup.find("script", id="__UNIVERSAL_DATA_FOR_REHYDRATION__")
        if not script:
            return None
        data = json.loads(script.string)
        user_detail = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {})
        user_info = user_detail.get("userInfo", {}).get("user", {})
        return user_info.get("secUid", "")
    except:
        return None

def _fetch_posts(secuid, username, max_count=MAX_POSTS_PER_ACCOUNT):
    """Fetch posts with cursor pagination to get up to max_count."""
    posts = []
    cursor = 0
    url = "https://www.tiktok.com/api/post/item_list/"
    while len(posts) < max_count:
        params = {
            "aid": "1988",
            "count": min(30, max_count - len(posts)),
            "cursor": str(cursor),
            "device_platform": "web_pc",
            "secUid": secuid,
            "region": "US",
            "language": "en",
        }
        headers = {"Referer": f"https://www.tiktok.com/@{username}",
                   "User-Agent": USER_AGENT}
        try:
            resp = session.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            items = data.get("itemList", [])
            if not items:
                break
            posts.extend(items)
            cursor = data.get("cursor", 0)
            if not data.get("hasMore", False):
                break
            time.sleep(1)  # be polite
        except Exception as e:
            print(f"  [@{username}] Error: {e}")
            break
    return posts[:max_count]

def _process_post(post, username):
    video_id = post.get("id", "")
    desc = post.get("desc", "") or "(no caption)"
    create_time = post.get("createTime", 0)
    pub_ts = datetime.fromtimestamp(create_time, tz=timezone.utc).isoformat() if create_time else _now_iso()
    hashtags = re.findall(r'#(\w+)', desc)
    mentions = re.findall(r'@(\w+)', desc)
    entities = [{"name": f"#{t}", "type": "TAG"} for t in hashtags]
    entities += [{"name": f"@{m}", "type": "MENTION"} for m in mentions]
    stats = post.get("stats", {})
    play_count = stats.get("playCount", 0)
    digg_count = stats.get("diggCount", 0)
    comment_count = stats.get("commentCount", 0)
    share_count = stats.get("shareCount", 0)
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

def main():
    print("=== High‑Volume TikTok Scraper ===")
    _ensure_db()
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    total_saved = 0
    for username in TIKTOK_ACCOUNTS:
        print(f"\n→ @{username}")
        secuid = _get_secuid(username)
        if not secuid:
            print(f"  Could not get secUid — skipping")
            continue
        posts = _fetch_posts(secuid, username, MAX_POSTS_PER_ACCOUNT)
        print(f"  Fetched {len(posts)} posts")
        saved = 0
        for post in posts:
            article = _process_post(post, username)
            if _upsert(conn, article):
                saved += 1
        total_saved += saved
        print(f"  Saved {saved} new articles")
    conn.commit()
    _export(conn)
    conn.close()
    print(f"\n=== Done: {total_saved} new TikTok articles ===")

if __name__ == "__main__":
    main()
