"""
Aura-Erbil — Multisource Sorani-first scraper (fixed sources)
Scrapes: Rudaw, Channel8, NRT, AVA News (Sorani first, then English).
Enriches via Cohere, upserts into same DB.
Usage: set COHERE_API_KEY, then: python scraper/scraper_multisource.py
"""

import hashlib, json, os, random, re, sqlite3, sys, time
from datetime import datetime, timezone, timedelta
from urllib import robotparser
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ── config ──────────────────────────────────────────────────────────────────
USER_AGENT        = "RSSReader/2.0"
DB_PATH           = "data/aura.db"
JSON_EXPORT       = "data/data.json"
MIN_DELAY         = 2.0
MAX_DELAY         = 5.0
MAX_PAGES         = 30
LOOKBACK_DAYS     = 7

# Sorani-first, then English — FIXED DOMAINS
SOURCES = [
    # Sorani/Kurdish pages (scraped first)
    ("https://www.rudaw.net/sorani", "rudaw-sorani"),
    ("https://channel8.com", "channel8-sorani"),               # homepage has Kurdish news listing
    ("https://www.nrttv.com/ku/News.aspx", "nrt-sorani"),
    ("https://ava.news", "avanews-kurdish"),                   # root domain — Kurdish content
    ("https://anfsorani.com", "anf-sorani"),                   # may fail if blocked — graceful skip
    # English mirrors
    ("https://www.rudaw.net/english", "rudaw-english"),
    ("https://channel8.com/en", "channel8-english"),
    ("https://www.nrttv.com/En/News.aspx", "nrt-english"),
    ("https://ava.news/en", "avanews-english"),
]

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

# ── polite scraping ─────────────────────────────────────────────────────────
_rp = robotparser.RobotFileParser()
for url, _ in SOURCES:
    _rp.set_url(urljoin(url, "/robots.txt"))
    try:
        _rp.read()
    except:
        pass

def _allowed(url):
    return _rp.can_fetch(USER_AGENT, url)

def _fetch(url):
    if not _allowed(url):
        print(f"  [robots.txt] blocked: {url}")
        return None
    try:
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        r = session.get(url, timeout=15, allow_redirects=True)   # ← fixed NRT redirect
        if r.status_code == 200:
            return r.text
        print(f"  [warn] HTTP {r.status_code} for {url}")
        return None
    except Exception as e:
        print(f"  [error] {e}")
        return None

# ── helpers ────────────────────────────────────────────────────────────────
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _make_id(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _clean_title(raw):
    return re.sub(r'^\d+\s+(second|minute|hour|day)s?\s+ago', '', raw or '', flags=re.IGNORECASE).strip()

def _extract_links(html, base_url, source_name):
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.select("a[href]"):
        href = urljoin(base_url, a.get("href"))
        text = _clean_title(a.get_text(strip=True))
        if len(text) > 10 and base_url in href:
            links.append((href, text))
    return list(set(links))

def _parse_article(html, url):
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    title = _clean_title(h1.get_text(strip=True) if h1 else "")
    if not title or len(title) < 10:
        return None
    paras = soup.select("article p, .article-body p, .content p")
    body = " ".join(p.get_text(" ", strip=True) for p in paras)[:2000]
    time_tag = soup.find("time")
    pub = time_tag.get("datetime") if time_tag else _now_iso()
    return {"title": title, "body": body, "published_at": pub, "url": url}

# ── AI enrichment (import from cohere scraper) ──────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from scraper_cohere import _enrich_with_ai

def _run():
    print("=== Aura-Erbil Multisource Scraper (fixed) ===")
    conn = _connect()
    total = 0

    for base_url, source_name in SOURCES:
        print(f"\n→ Source: {source_name} ({base_url})")
        html = _fetch(base_url)
        if not html:
            print("  Failed to fetch listing page, skipping.")
            continue

        links = _extract_links(html, base_url, source_name)
        print(f"  Found {len(links)} potential articles")

        for i, (article_url, title_hint) in enumerate(links[:MAX_PAGES]):
            art_html = _fetch(article_url)
            if not art_html:
                continue
            article = _parse_article(art_html, article_url)
            if not article:
                continue

            enrichment = _enrich_with_ai(article["title"], article["body"])
            item = {
                "id": _make_id(article_url),
                "url": article_url,
                "title": article["title"],
                "title_en": enrichment["title_en"],
                "summary": article["body"],
                "source": source_name,
                "category": enrichment["category"],
                "loc_name": enrichment["loc_name"],
                "lat": enrichment["lat"],
                "lng": enrichment["lng"],
                "published_at": article["published_at"],
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
            total += 1
            print(f"  [saved] {article['title'][:70]}")
            if total % 3 == 0:
                time.sleep(1)

    # Export
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
    print(f"\n  Exported {len(records)} records → {JSON_EXPORT}")
    conn.close()
    print(f"=== Done ({total} new articles) ===")

if __name__ == "__main__":
    _run()
