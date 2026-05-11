"""
Aura-Erbil — Main Scraper (Sitemap-based)
Fetches article URLs + real publish dates from Rudaw's sitemap.
Runs every 30 min via GitHub Actions.
"""

import hashlib, json, os, random, re, sqlite3, time, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── Config ───────────────────────────────────────────────────────────────────
BASE_URL          = "https://www.rudaw.net"
SITEMAP_INDEX     = "https://www.rudaw.net/sitemap.xml"
USER_AGENT        = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
DB_PATH           = "data/aura.db"
JSON_EXPORT       = "data/data.json"
MAX_AGE_DAYS      = 30
MAX_PAGES_PER_RUN = 30
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
    for col, defn in [("title_en","TEXT"), ("entities","TEXT DEFAULT '[]'"),
                      ("loc_name","TEXT"), ("lat","REAL"), ("lng","REAL"),
                      ("published_at","TEXT"), ("breaking","INTEGER DEFAULT 1")]:
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {defn}")
        except Exception:
            pass
    conn.commit()

def _upsert(conn, item):
    existing = conn.execute(
        "SELECT sentiment, category, title_en, lat, lng FROM articles WHERE id=?",
        (item["id"],)
    ).fetchone()

    if existing:
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

# ── Sitemap Scraper ──────────────────────────────────────────────────────────
def _parse_sitemap_index():
    """Fetch the sitemap index and return a list of sub-sitemap URLs."""
    print(f"\n→ Sitemap index: {SITEMAP_INDEX}")
    xml_data = _fetch(SITEMAP_INDEX)
    if not xml_data:
        return []
    try:
        root = ET.fromstring(xml_data)
        ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
        return [elem.find(f'{ns}loc').text for elem in root.findall(f'{ns}sitemap') if elem.find(f'{ns}loc') is not None]
    except Exception as e:
        print(f"  Error parsing sitemap index: {e}")
        return []

def _parse_sub_sitemap(url):
    """Fetch a sub-sitemap and return list of (article_url, lastmod_date)."""
    print(f"  → Sub-sitemap: {url}")
    xml_data = _fetch(url)
    if not xml_data:
        return []
    entries = []
    try:
        root = ET.fromstring(xml_data)
        ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
        for url_elem in root.findall(f'{ns}url'):
            loc = url_elem.find(f'{ns}loc')
            lastmod = url_elem.find(f'{ns}lastmod')
            if loc is not None and loc.text:
                entry_url = loc.text.strip()
                # Only include article URLs (exclude /authors/, /opinion/, etc.)
                if '/authors/' not in entry_url and '/opinion/' not in entry_url:
                    date_str = lastmod.text.strip() if lastmod is not None and lastmod.text else None
                    if date_str:
                        entries.append((entry_url, date_str))
    except Exception as e:
        print(f"    Error parsing sub-sitemap: {e}")
    return entries

def _extract_article_data(html, url):
    """Extract title and body from an article page."""
    soup = BeautifulSoup(html, "html.parser")
    # Title
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else None
    if not title:
        return None, None
    # Body
    body = ""
    for sel in ["article", ".article-body", ".story-body", "main", ".content"]:
        tag = soup.select_one(sel)
        if tag:
            body = tag.get_text(separator=" ", strip=True)[:2000]
            break
    return title, body

def ingest_sitemap(conn):
    """Main ingestion: sitemap → real dates → AI enrichment."""
    sub_sitemaps = _parse_sitemap_index()
    if not sub_sitemaps:
        print("  No sub-sitemaps found.")
        return 0

    # Collect entries from all sub-sitemaps
    all_entries = []
    for sub_url in sub_sitemaps:
        entries = _parse_sub_sitemap(sub_url)
        all_entries.extend(entries)

    # Sort by lastmod descending
    all_entries.sort(key=lambda x: x[1], reverse=True)

    # Take the most recent up to MAX_PAGES_PER_RUN
    to_fetch = all_entries[:MAX_PAGES_PER_RUN]
    print(f"  Collected {len(to_fetch)} most recent articles from sitemap(s)")

    saved = 0
    for article_url, lastmod in to_fetch:
        if not _allowed(article_url):
            continue

        article_id = _make_id(article_url)
        existing = conn.execute(
            "SELECT sentiment, published_at FROM articles WHERE id=?", (article_id,)
        ).fetchone()
        if existing and existing["sentiment"] not in ("neutral", None, "") and existing["published_at"]:
            continue

        html = _fetch(article_url)
        if not html:
            continue

        title, body = _extract_article_data(html, article_url)
        if not title:
            continue

        # Determine source label
        if '/sorani/' in article_url:
            source = "rudaw-sorani"
        elif '/english/' in article_url:
            source = "rudaw-english"
        else:
            source = "rudaw"

        # Convert lastmod to ISO format
        pub_date = lastmod if lastmod else None

        enrichment = _enrich_with_ai(title, body)
        item = {
            "id":           article_id,
            "url":          article_url,
            "title":        _clean_title(title),
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

    print(f"  Sitemap: {saved} new/updated articles")
    return saved

# ── Main ─────────────────────────────────────────────────────────────────────
def _run():
    print("=== Aura-Erbil Main Scraper (Sitemap) ===")
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_db(conn)

    ingested = ingest_sitemap(conn)

    _prune(conn)
    _export(conn)
    conn.close()
    print(f"\n=== Done: {ingested} articles ===")

if __name__ == "__main__":
    _run()
