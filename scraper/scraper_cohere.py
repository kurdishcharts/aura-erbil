"""
Aura-Erbil — Main Scraper with GitHub Models AI
Scrapes Rudaw RSS + listing pages. Saves real pubDate, not scrape time.
Runs every 30 min via GitHub Actions.
"""

import feedparser, hashlib, json, os, random, re, sqlite3, time
from datetime import datetime, timedelta, timezone
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── Config ───────────────────────────────────────────────────────────────────
BASE_URL          = "https://www.rudaw.net"
RUDAW_RSS         = "https://www.rudaw.net/rss"
LIST_PATHS        = ["/english", "/sorani/kurdistan", "/sorani/middleeast", "/sorani/business"]
USER_AGENT        = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
DB_PATH           = "data/aura.db"
JSON_EXPORT       = "data/data.json"
MAX_AGE_DAYS      = 30
MAX_PAGES_PER_RUN = 20
MIN_DELAY         = 3.0
MAX_DELAY         = 5.0
BACKOFF_BASE      = 2.0
MAX_BACKOFF       = 60.0

KEYWORDS = {
    "security":       ["explosion","attack","armed","killed","shooting","bomb","ISIS","PKK","militant","arrest","detained","تەقینەوە","ئەمنییەت"],
    "fire":           ["fire","blaze","burning","flames","wildfire","ئاگر","سووتان"],
    "traffic":        ["accident","crash","traffic","road","collision","highway","vehicle","رووداوی هاتووچۆ"],
    "infrastructure": ["closure","bridge","construction","power cut","electricity","water supply","outage","کۆپری"],
    "weather":        ["flood","earthquake","storm","rain","snow","temperature","heat","dust storm","زەلزەلە","باران"],
}

LOCATIONS = {
    "erbil": (36.1912, 44.0092), "hewler": (36.1912, 44.0092), "kurdistan": (36.1912, 44.0092),
    "sulaymaniyah": (35.5571, 45.4357), "slemani": (35.5571, 45.4357),
    "duhok": (36.8669, 43.0032), "halabja": (35.1787, 45.9861),
    "zakho": (37.1441, 42.6875), "ranya": (36.2558, 44.8783),
    "koya": (36.0862, 44.6283), "amadiya": (37.0924, 43.4889),
    "chamchamal": (35.5279, 44.8318), "kirkuk": (35.4681, 44.3922),
    "sinjar": (36.3197, 41.8694), "makhmur": (35.7738, 43.5908),
    "shaqlawa": (36.5485, 44.3397), "soran": (36.6539, 44.5472),
    "ankawa": (36.2497, 43.9992),
}

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,ku;q=0.9",
})

# ── Robots / HTTP ────────────────────────────────────────────────────────────
def _allowed(url):
    if not hasattr(_allowed, "cache"):
        _allowed.cache = {}
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    if robots_url not in _allowed.cache:
        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)
        try:
            rp.read()
            _allowed.cache[robots_url] = rp
        except Exception:
            _allowed.cache[robots_url] = None
    rp = _allowed.cache[robots_url]
    if rp is None:
        return True
    ok = rp.can_fetch(USER_AGENT, url)
    if not ok:
        print(f"  [robots] DISALLOWED: {url}")
    return ok

def _jitter():
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

def _fetch(url, _backoff=BACKOFF_BASE):
    try:
        r = session.get(url, timeout=12, allow_redirects=True)
        if r.status_code == 200:
            _jitter()
            return r.text
        if r.status_code in (429, 500, 502, 503, 504):
            wait = min(_backoff * BACKOFF_BASE, MAX_BACKOFF)
            print(f"  [backoff] {r.status_code} → {wait:.0f}s")
            time.sleep(wait)
            return _fetch(url, _backoff=wait)
        print(f"  [warn] HTTP {r.status_code}: {url}")
        return None
    except requests.RequestException as e:
        wait = min(_backoff * BACKOFF_BASE, MAX_BACKOFF)
        print(f"  [error] {e} → {wait:.0f}s")
        time.sleep(wait)
        return _fetch(url, _backoff=wait)

# ── Helpers ──────────────────────────────────────────────────────────────────
def _make_id(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _parse_pub_date(entry):
    """Extract real publish date from RSS entry. Never falls back to scrape time."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    return None  # unknown — better than a lie

def _clean_title(raw):
    return re.sub(r'^\d+\s+(second|minute|hour|day)s?\s+ago', '', raw or '', flags=re.IGNORECASE).strip()

def _detect_category(text):
    t = text.lower()
    for cat, words in KEYWORDS.items():
        if any(w.lower() in t for w in words):
            return cat
    return "general"

def _detect_location(text):
    t = text.lower()
    for place, (lat, lng) in LOCATIONS.items():
        if place.lower() in t:
            return {"name": place.title(), "lat": lat, "lng": lng}
    return {"name": "Erbil", "lat": 36.1912, "lng": 44.0092}

# ── AI Enrichment ────────────────────────────────────────────────────────────
def _enrich_with_ai(title_original: str, summary: str) -> dict:
    """GitHub Models AI — Kurdistan-aware, city-level location."""
    from openai import OpenAI
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return _keyword_fallback(title_original, summary)
    client = OpenAI(base_url="https://models.github.ai/inference", api_key=token)
    COORDS = {
        "erbil": (36.1912, 44.0092), "hewler": (36.1912, 44.0092),
        "sulaymaniyah": (35.5571, 45.4357), "slemani": (35.5571, 45.4357),
        "duhok": (36.8669, 43.0032), "halabja": (35.1787, 45.9861),
        "zakho": (37.1441, 42.6875), "ranya": (36.2558, 44.8783),
        "koya": (36.0862, 44.6283), "amadiya": (37.0924, 43.4889),
        "chamchamal": (35.5279, 44.8318), "kirkuk": (35.4681, 44.3922),
        "sinjar": (36.3197, 41.8694), "makhmur": (35.7738, 43.5908),
        "shaqlawa": (36.5485, 44.3397), "soran": (36.6539, 44.5472),
    }
    CITIES = list(COORDS.keys())
    prompt = f"""You are a geopolitical analyst for the Kurdistan Region of Iraq (KRI).
Return ONLY valid JSON with exactly these 5 keys:
"title_en": English translation of the title (translate if Sorani/Kurdish, keep if already English)
"sentiment": "positive"|"negative"|"neutral" — impact on KRI ONLY
"category": security|politics|economy|infrastructure|weather|fire|traffic|health|culture|general
"entities": up to 5 objects with name and type (PERSON/ORGANIZATION/LOCATION), KRI-relevant only
"location_key": primary KRI city lowercase from {CITIES} — "erbil" for general KRI, null if entirely outside KRI

Examples:
Title: "PKK attack kills 2 peshmerga near Duhok"
{{"sentiment":"negative","category":"security","entities":[{{"name":"PKK","type":"ORGANIZATION"}},{{"name":"Duhok","type":"LOCATION"}}],"location_key":"duhok","title_en":"PKK attack kills 2 peshmerga near Duhok"}}
Title: "US Federal Reserve raises rates"
{{"sentiment":"neutral","category":"economy","entities":[{{"name":"US Federal Reserve","type":"ORGANIZATION"}}],"location_key":null,"title_en":"US Federal Reserve raises rates"}}

Article:
Title: {title_original}
Body: {summary[:1500]}
Return ONLY the JSON:"""
    try:
        time.sleep(2)
        resp = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0, max_tokens=350,
        )
        data = json.loads(resp.choices[0].message.content.strip())
        loc = (data.get("location_key") or "erbil").lower().strip()
        lat, lng = COORDS.get(loc, (36.1912, 44.0092))
        return {
            "title_en":  data.get("title_en", title_original),
            "category":  data.get("category", "general"),
            "sentiment": data.get("sentiment", "neutral"),
            "entities":  data.get("entities", []),
            "loc_name":  loc.title(),
            "lat":       lat,
            "lng":       lng,
        }
    except Exception as e:
        print(f"  [AI] error: {e}")
        return _keyword_fallback(title_original, summary)

def _keyword_fallback(title_original: str, summary: str) -> dict:
    combined = (title_original or "") + " " + (summary or "")
    loc = _detect_location(combined)
    return {
        "title_en":  title_original,
        "category":  _detect_category(combined),
        "loc_name":  loc["name"],
        "lat":       loc["lat"],
        "lng":       loc["lng"],
        "sentiment": "neutral",
        "entities":  [],
    }

# ── Database ─────────────────────────────────────────────────────────────────
def _ensure_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            url TEXT UNIQUE,
            title TEXT,
            title_en TEXT,
            summary TEXT,
            source TEXT,
            category TEXT DEFAULT 'general',
            sentiment TEXT DEFAULT 'neutral',
            entities TEXT DEFAULT '[]',
            loc_name TEXT DEFAULT 'Erbil',
            lat REAL DEFAULT 36.1912,
            lng REAL DEFAULT 44.0092,
            published_at TEXT,
            fetched_at TEXT,
            breaking INTEGER DEFAULT 1,
            etag TEXT,
            last_modified TEXT
        )
    """)
    # Add columns if missing (safe migration)
    for col, defn in [("title_en","TEXT"), ("entities","TEXT DEFAULT '[]'"),
                      ("loc_name","TEXT"), ("lat","REAL"), ("lng","REAL"),
                      ("published_at","TEXT"), ("breaking","INTEGER DEFAULT 1")]:
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {defn}")
        except Exception:
            pass
    conn.commit()

def _upsert(conn, item):
    """Insert or update — never overwrites already-enriched sentiment/category."""
    existing = conn.execute(
        "SELECT sentiment, category, title_en, lat, lng FROM articles WHERE id=?",
        (item["id"],)
    ).fetchone()

    if existing:
        # Only update fields that are missing/neutral
        updates, vals = [], []
        if not existing["title_en"] or existing["title_en"] == item["title"]:
            updates.append("title_en=?"); vals.append(item.get("title_en", item["title"]))
        if existing["sentiment"] in ("neutral", None, ""):
            updates.append("sentiment=?"); vals.append(item.get("sentiment", "neutral"))
            updates.append("category=?");  vals.append(item.get("category", "general"))
            updates.append("entities=?");  vals.append(json.dumps(item.get("entities", [])))
        if not existing["lat"]:
            updates.append("lat=?"); vals.append(item.get("lat", 36.1912))
            updates.append("lng=?"); vals.append(item.get("lng", 44.0092))
            updates.append("loc_name=?"); vals.append(item.get("loc_name", "Erbil"))
        if updates:
            vals.append(item["id"])
            conn.execute(f"UPDATE articles SET {','.join(updates)} WHERE id=?", vals)
    else:
        conn.execute("""
            INSERT INTO articles
              (id, url, title, title_en, summary, source, category, sentiment,
               entities, loc_name, lat, lng, published_at, fetched_at, breaking)
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

def _prune(conn):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).isoformat()
    conn.execute("DELETE FROM articles WHERE published_at < ? AND published_at IS NOT NULL", (cutoff,))
    conn.commit()

def _export(conn):
    rows = conn.execute("SELECT * FROM articles ORDER BY published_at DESC").fetchall()
    records = []
    SOURCE_NAMES = {
        "rudaw-scrape": "Rudaw", "rudaw-english": "Rudaw EN",
        "rudaw-sorani": "Rudaw KU", "rudaw-rss": "Rudaw",
        "channel8-sorani": "Channel8", "channel8-english": "Channel8 EN",
        "nrt-sorani": "NRT", "nrt-english": "NRT EN",
        "avanews-kurdish": "AVA News", "avanews-english": "AVA News EN",
        "anf-sorani": "ANF", "multisource": "Multi",
    }
    for r in rows:
        records.append({
            "id":       r["id"],
            "url":      r["url"],
            "title":    r["title"],
            "title_en": r["title_en"] or r["title"],
            "summary":  r["summary"],
            "source":   SOURCE_NAMES.get(r["source"], r["source"] or "Rudaw"),
            "category": r["category"] or "general",
            "sentiment": r["sentiment"] or "neutral",
            "entities": json.loads(r["entities"]) if r["entities"] else [],
            "breaking": r["breaking"] or 1,
            "timestamp": r["published_at"],
            "location": {
                "name": r["loc_name"] or "Erbil",
                "lat":  r["lat"] or 36.1912,
                "lng":  r["lng"] or 44.0092,
            },
        })
    with open(JSON_EXPORT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"  Exported {len(records)} records → {JSON_EXPORT}")

# ── RSS Ingestion ─────────────────────────────────────────────────────────────
def ingest_rss(conn):
    print(f"\n→ RSS: {RUDAW_RSS}")
    feed = feedparser.parse(RUDAW_RSS)
    saved = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    for entry in feed.entries:
        url = entry.get("link", "")
        if not url:
            continue

        # Get REAL publish date from RSS
        pub_date = _parse_pub_date(entry)
        if pub_date:
            try:
                if datetime.fromisoformat(pub_date.replace("Z", "+00:00")) < cutoff:
                    continue
            except Exception:
                pass

        title = _clean_title(entry.get("title", ""))
        summary = entry.get("summary", "") or entry.get("description", "")
        summary = re.sub(r'<[^>]+>', '', summary).strip()
        article_id = _make_id(url)

        # Skip if already enriched
        existing = conn.execute(
            "SELECT sentiment FROM articles WHERE id=?", (article_id,)
        ).fetchone()
        if existing and existing["sentiment"] not in ("neutral", None, ""):
            continue

        enrichment = _enrich_with_ai(title, summary)

        item = {
            "id":           article_id,
            "url":          url,
            "title":        title,
            "title_en":     enrichment.get("title_en", title),
            "summary":      summary[:500],
            "source":       "Rudaw",
            "category":     enrichment.get("category", "general"),
            "sentiment":    enrichment.get("sentiment", "neutral"),
            "entities":     enrichment.get("entities", []),
            "loc_name":     enrichment.get("loc_name", "Erbil"),
            "lat":          enrichment.get("lat", 36.1912),
            "lng":          enrichment.get("lng", 44.0092),
            "published_at": pub_date,
            "breaking":     1,
        }
        _upsert(conn, item)
        saved += 1
        print(f"  [saved] {enrichment.get('sentiment','?'):8} | {title[:60]}")

    print(f"  RSS: {saved} new/updated articles")
    return saved

# ── Listing page scraper (fallback) ──────────────────────────────────────────
def _parse_article_date(soup):
    """Try to extract article publish date from HTML."""
    # Try meta tags first (most reliable)
    for sel in ["meta[property='article:published_time']",
                "meta[name='pubdate']",
                "meta[itemprop='datePublished']"]:
        tag = soup.select_one(sel)
        if tag and tag.get("content"):
            try:
                dt = datetime.fromisoformat(tag["content"].replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pass
    # Try time tags
    for tag in soup.select("time[datetime]"):
        try:
            dt = datetime.fromisoformat(tag["datetime"].replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass
    return None  # Unknown — don't save scrape time as a lie

def _parse_listing(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select("a[href]"):
        href = urljoin(base_url, a["href"])
        if urlparse(href).netloc == urlparse(base_url).netloc:
            if re.search(r'/\d{4,}|/news/|/story/', href):
                title = a.get_text(strip=True)
                if len(title) > 15:
                    links.append((href, title))
    # Deduplicate
    seen = set()
    result = []
    for href, title in links:
        if href not in seen:
            seen.add(href)
            result.append((href, title))
    return result

def ingest_scrape(conn):
    total_saved = 0
    for path in LIST_PATHS:
        url = urljoin(BASE_URL, path)
        if not _allowed(url):
            continue
        print(f"\n→ Listing: {url}")
        html = _fetch(url)
        if not html:
            continue
        links = _parse_listing(html, BASE_URL)
        print(f"  Found {len(links)} potential articles")
        saved = 0
        for article_url, title_hint in links[:MAX_PAGES_PER_RUN]:
            article_id = _make_id(article_url)
            existing = conn.execute(
                "SELECT sentiment, published_at FROM articles WHERE id=?", (article_id,)
            ).fetchone()
            # Skip if already enriched with real data
            if existing and existing["sentiment"] not in ("neutral", None, "") and existing["published_at"]:
                continue
            if not _allowed(article_url):
                continue
            html = _fetch(article_url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            # Get real publish date from article HTML
            pub_date = _parse_article_date(soup)
            # Extract body
            body = ""
            for sel in ["article", ".article-body", ".story-body", "main", ".content"]:
                tag = soup.select_one(sel)
                if tag:
                    body = tag.get_text(separator=" ", strip=True)[:2000]
                    break
            title = _clean_title(
                soup.select_one("h1") and soup.select_one("h1").get_text(strip=True) or title_hint
            )
            source = "rudaw-" + ("sorani" if any(c > '\u0600' for c in title) else "english")
            enrichment = _enrich_with_ai(title, body)
            item = {
                "id":           article_id,
                "url":          article_url,
                "title":        title,
                "title_en":     enrichment.get("title_en", title),
                "summary":      body[:500],
                "source":       source,
                "category":     enrichment.get("category", "general"),
                "sentiment":    enrichment.get("sentiment", "neutral"),
                "entities":     enrichment.get("entities", []),
                "loc_name":     enrichment.get("loc_name", "Erbil"),
                "lat":          enrichment.get("lat", 36.1912),
                "lng":          enrichment.get("lng", 44.0092),
                "published_at": pub_date,
                "breaking":     1,
            }
            _upsert(conn, item)
            saved += 1
            print(f"  [saved] {enrichment.get('sentiment','?'):8} | {title[:55]}")
        total_saved += saved
    return total_saved

# ── Main ─────────────────────────────────────────────────────────────────────
def _run():
    print("=== Aura-Erbil Main Scraper ===")
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_db(conn)

    rss_saved = ingest_rss(conn)
    scrape_saved = ingest_scrape(conn) if rss_saved < 5 else 0

    _prune(conn)
    _export(conn)
    conn.close()
    print(f"\n=== Done: {rss_saved} from RSS, {scrape_saved} from scrape ===")

if __name__ == "__main__":
    _run()
