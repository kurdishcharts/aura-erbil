"""
Aura-Erbil — TikTok Scraper (profile embedded JSON)
Extracts recent posts from the profile page's __UNIVERSAL_DATA_FOR_REHYDRATION__.
No internal API calls needed. Deduplicates by video ID.
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
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,ku;q=0.9",
})

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

def _fetch_profile_page(username):
    """Fetch the TikTok profile page and extract the embedded JSON."""
    url = f"https://www.tiktok.com/@{username}"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"  [{username}] HTTP {resp.status_code}")
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        script = soup.find("script", id="__UNIVERSAL_DATA_FOR_REHYDRATION__")
        if not script:
            print(f"  [{username}] No embedded JSON found")
            return None
        data = json.loads(script.string)
        return data
    except Exception as e:
        print(f"  [{username}] Error fetching profile: {e}")
        return None

def _process_post(post, username):
    """Convert a TikTok post object to an article dict."""
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
    print("=== TikTok Scraper (profile embedded JSON) ===")
    _ensure_db()
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    total_saved = 0

    for username in TIKTOK_ACCOUNTS:
        print(f"\n→ @{username}")
        data = _fetch_profile_page(username)
        if not data:
            print(f"  [{username}] Failed to load profile page")
            continue

        # Navigate the JSON to find the post list
        try:
            default_scope = data.get("__DEFAULT_SCOPE__", {})
            user_detail = default_scope.get("webapp.user-detail", {})
            user_info = user_detail.get("userInfo", {})
            posts = user_info.get("itemList", [])
        except:
            posts = []

        if not posts:
            print(f"  [{username}] No posts found in embedded data")
            continue

        # Limit to MAX_POSTS_PER_ACCOUNT
        posts = posts[:MAX_POSTS_PER_ACCOUNT]
        print(f"  Found {len(posts)} posts in profile data")

        saved = 0
        for post in posts:
            article = _process_post(post, username)
            if _upsert(conn, article):
                saved += 1
                print(f"  [saved] {article['title'][:60]}")
        total_saved += saved
        print(f"  New: {saved}")

        time.sleep(2)  # polite delay

    conn.commit()
    _export(conn)
    conn.close()
    print(f"\n=== Done: {total_saved} new TikTok articles ===")

if __name__ == "__main__":
    main()
