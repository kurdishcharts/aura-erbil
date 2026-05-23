"""
Aura-Erbil — TikTok Scraper (session‑based API)
Gets profile page for cookies + secUid, then calls post/item_list with same session.
Deduplicates by video ID. No browser needed.
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

def _fetch_posts_for_account(username):
    """Step 1: get profile page (cookies + secUid). Step 2: call API with same session."""
    profile_url = f"https://www.tiktok.com/@{username}"
    try:
        resp = session.get(profile_url, timeout=15)
        if resp.status_code != 200:
            print(f"  [{username}] Profile HTTP {resp.status_code}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        script = soup.find("script", id="__UNIVERSAL_DATA_FOR_REHYDRATION__")
        if not script:
            print(f"  [{username}] No embedded JSON")
            return []
        data = json.loads(script.string)
        scope = data.get("__DEFAULT_SCOPE__", {})
        user_info = scope.get("webapp.user-detail", {}).get("userInfo", {})
        user = user_info.get("user", {})
        secuid = user.get("secUid", "")
        if not secuid:
            print(f"  [{username}] No secUid found")
            return []
        print(f"  secUid: {secuid[:12]}...")
    except Exception as e:
        print(f"  [{username}] Profile error: {e}")
        return []

    # Step 2: API call with same session (cookies set by profile fetch)
    api_url = "https://www.tiktok.com/api/post/item_list/"
    posts = []
    cursor = 0
    while len(posts) < MAX_POSTS_PER_ACCOUNT:
        params = {
            "aid": "1988",
            "count": min(30, MAX_POSTS_PER_ACCOUNT - len(posts)),
            "cursor": str(cursor),
            "device_platform": "web_pc",
            "secUid": secuid,
            "region": "US",
            "language": "en",
        }
        headers = {"Referer": profile_url}
        try:
            r2 = session.get(api_url, params=params, headers=headers, timeout=15)
            if r2.status_code != 200:
                print(f"  API HTTP {r2.status_code}")
                break
            data2 = r2.json()
            items = data2.get("itemList", [])
            if not items:
                break
            posts.extend(items)
            cursor = data2.get("cursor", 0)
            if not data2.get("hasMore", False):
                break
            time.sleep(1)
        except Exception as e:
            print(f"  API error: {e}")
            break
    return posts[:MAX_POSTS_PER_ACCOUNT]

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
    digg_count = stats.get("diggCount", 0)
    comment_count = stats.get("commentCount", 0)
    share_count = stats.get("shareCount", 0)
    summary = desc[:500]
    if stats:
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
    print("=== TikTok Scraper (session‑based API) ===")
    _ensure_db()
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    total_saved = 0

    for username in TIKTOK_ACCOUNTS:
        print(f"\n→ @{username}")
        posts = _fetch_posts_for_account(username)
        print(f"  Fetched {len(posts)} posts")
        saved = 0
        for post in posts:
            article = _process_post(post, username)
            if _upsert(conn, article):
                saved += 1
                print(f"  [saved] {article['title'][:60]}")
        total_saved += saved
        print(f"  New: {saved}")

    conn.commit()
    _export(conn)
    conn.close()
    print(f"\n=== Done: {total_saved} new TikTok articles ===")

if __name__ == "__main__":
    main()
