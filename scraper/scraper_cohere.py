"""
Aura-Erbil — AI Enrichment Scraper (Cohere API)
Free tier: 100 calls/min. Works locally and on GitHub Actions.
Usage: set COHERE_API_KEY env var, then:
  python scraper/scraper_cohere.py
"""

import hashlib, json, os, random, re, sqlite3, time
from datetime import datetime, timedelta, timezone
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import cohere, feedparser, requests
from bs4 import BeautifulSoup

BASE_URL          = "https://www.rudaw.net"
RUDAW_RSS         = "https://www.rudaw.net/rss"
LIST_PATHS        = ["/english","/sorani/kurdistan","/sorani/middleeast","/sorani/business","/kurmanci"]
USER_AGENT        = "RSSReader/2.0"
DB_PATH           = "data/aura.db"
JSON_EXPORT       = "data/data.json"
MAX_AGE_DAYS      = 30
MAX_PAGES_PER_RUN = 40
MIN_DELAY         = 2.0
MAX_DELAY         = 5.0
BACKOFF_BASE      = 2.0
MAX_BACKOFF       = 60.0
COHERE_MODEL      = "command-r7b-12-2024"

KEYWORDS = {
    "security": ["تەقینەوە","ئەمنییەت","چەکدار","کوژران","تیرکردن","explosion","attack","armed","killed","shooting","bomb","ISIS","PKK","militant","arrest","detained"],
    "fire": ["ئاگر","سووتان","fire","blaze","burning","flames","wildfire"],
    "traffic": ["رووداوی هاتووچۆ","ترافیک","ڕووداوی","accident","crash","traffic","road","collision","highway","vehicle","truck","bus"],
    "infrastructure": ["داخستن","کۆپری","ڕێگا","closure","bridge","road closure","construction","power cut","electricity","water supply","outage"],
    "weather": ["باران","بەفر","تەقەر","زەلزەلە","flood","earthquake","storm","rain","snow","temperature","heat","dust storm"],
}

LOCATIONS = {
    "erbil": (36.1912, 44.0092), "hewler": (36.1912, 44.0092), "kurdistan": (36.1912, 44.0092),
    "100 meter road": (36.1911, 44.0092), "100m road": (36.1911, 44.0092),
    "60 meter road": (36.2041, 44.0112), "60m road": (36.2041, 44.0112),
    "30 meter road": (36.1985, 44.0055), "kirkuk road": (36.1722, 44.0489),
    "sulaymaniyah road": (36.1600, 44.0700), "mosul road": (36.2300, 43.9800),
    "airport road": (36.2373, 43.9632), "koya road": (36.1680, 44.0820),
    "shaqlawa road": (36.2400, 44.1000), "bakhtiyari": (36.2078, 44.0231),
    "shoresh": (36.1875, 44.0321), "ankawa": (36.2497, 43.9992),
    "iskan": (36.1950, 44.0150), "dream city": (36.2200, 43.9950),
    "gulan": (36.1980, 44.0050), "sarchinar": (36.1730, 44.0380),
    "azadi": (36.1890, 44.0070), "erbil citadel": (36.1912, 44.0092),
    "qaysari": (36.1910, 44.0080), "family mall": (36.2219, 44.0003),
    "majidi mall": (36.2116, 44.0199), "franso hariri": (36.1886, 44.0024),
}

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en,ku;q=0.9"})

_rp = robotparser.RobotFileParser()
_rp.set_url(urljoin(BASE_URL, "/robots.txt"))
try: _rp.read(); print("  robots.txt loaded")
except Exception as e: print(f"  robots.txt fetch failed ({e}) — proceeding cautiously")

def _allowed(url): return _rp.can_fetch(USER_AGENT, url)
def _jitter(): time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
def _fetch(url, etag=None, last_modified=None, _backoff=BACKOFF_BASE):
    if not _allowed(url): print(f"  [robots.txt] blocked: {url}"); return None,None,None
    headers = {}
    if etag: headers["If-None-Match"] = etag
    if last_modified: headers["If-Modified-Since"] = last_modified
    try:
        r = session.get(url, headers=headers, timeout=12)
        if r.status_code == 304: return "NOT_MODIFIED", etag, last_modified
        if r.status_code == 200: _jitter(); return r.text, r.headers.get("ETag"), r.headers.get("Last-Modified")
        if r.status_code in (429,500,502,503,504):
            wait = min(_backoff*BACKOFF_BASE, MAX_BACKOFF)
            print(f"  [backoff] {r.status_code} → waiting {wait:.1f}s"); time.sleep(wait)
            return _fetch(url, etag, last_modified, _backoff=wait)
        print(f"  [warn] HTTP {r.status_code}: {url}"); _jitter(); return None,None,None
    except requests.RequestException as exc:
        wait = min(_backoff*BACKOFF_BASE, MAX_BACKOFF)
        print(f"  [error] {exc} → waiting {wait:.1f}s"); time.sleep(wait)
        return _fetch(url, etag, last_modified, _backoff=wait)

def _score_breaking(title, all_titles):
    words = set(title.lower().split()); score = 1
    for other in all_titles:
        if other == title: continue
        if len(words & set(other.lower().split())) >= 4: score += 1
    return min(score, 3)

def _make_id(url): return hashlib.sha256(url.encode()).hexdigest()[:16]
def _now_iso(): return datetime.now(timezone.utc).isoformat()
def _clean_title(raw): return re.sub(r'^\d+\s+(second|minute|hour|day)s?\s+ago', '', raw or '', flags=re.IGNORECASE).strip()
def _detect_category(text):
    t = text.lower()
    for cat, words in KEYWORDS.items():
        if any(w.lower() in t for w in words): return cat
    return "general"
def _detect_location(text):
    t = text.lower()
    for place, (lat, lng) in LOCATIONS.items():
        if place.lower() in t: return {"name": place.title(), "lat": lat, "lng": lng}
    return {"name": "Erbil", "lat": 36.1912, "lng": 44.0092}
def _same_origin(url): return urlparse(url).netloc == urlparse(BASE_URL).netloc

# ── Cohere client ──
try:
    co = cohere.Client(api_key=os.environ["COHERE_API_KEY"])
except KeyError:
    print("FATAL: COHERE_API_KEY environment variable not set"); exit(1)

def _enrich_with_ai(title_original, summary):
    loc_keys = list(LOCATIONS.keys()); loc_list_str = ", ".join(loc_keys[:40])
    prompt = f"""You are a news enrichment assistant for the Kurdistan region.
Given the title and body of a news article, perform these tasks:
1. If the title is in Sorani Kurdish (Arabic script), translate it to English.
   If it is already in English, return it unchanged.
2. Classify the article into ONE of these categories:
   security, fire, traffic, infrastructure, weather, general.
3. From the list below, pick the single location most specific to the article.
   If none match, use "erbil".
4. Determine the overall sentiment of the article: positive, negative, or neutral.
5. Extract up to 5 named entities (persons, organizations, places) mentioned in the article.
   For each entity, specify a type: PERSON, ORGANIZATION, or LOCATION.

Available locations: {loc_list_str}

Return ONLY a valid JSON object with exactly these keys:
title_en, category, location_key, sentiment, entities

Entities must be a list of objects like: [{{"name": "...", "type": "PERSON"}}, ...]

Title: {title_original}
Body: {summary[:2000]}"""

    try:
        time.sleep(3)  # stay under 20 calls/min (trial key)
        response = co.chat(model=COHERE_MODEL, message=prompt, temperature=0.0, max_tokens=1000)
        raw = response.text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match: raise ValueError("No JSON found in Cohere response")
        data = json.loads(match.group())
    except Exception as e:
        print(f"  [cohere] AI call failed ({e}), falling back to keyword defaults")
        loc = _detect_location(title_original + " " + summary)
        return {
            "title_en": title_original,
            "category": _detect_category(title_original + " " + summary),
            "loc_name": loc["name"], "lat": loc["lat"], "lng": loc["lng"],
            "sentiment": "neutral", "entities": []
        }

    valid_cats = set(KEYWORDS.keys()) | {"general"}
    cat = data.get("category", "general")
    if cat not in valid_cats: cat = "general"

    loc_key = data.get("location_key", "").strip().lower()
    if loc_key in LOCATIONS: lat, lng = LOCATIONS[loc_key]; loc_name = loc_key.title()
    else: lat, lng = LOCATIONS.get("erbil", (36.1912, 44.0092)); loc_name = "Erbil"

    title_en = data.get("title_en", title_original).strip()
    if not title_en: title_en = title_original

    sentiment = data.get("sentiment", "").strip().lower()
    if sentiment not in ("positive", "negative", "neutral"): sentiment = "neutral"

    entities = data.get("entities", [])
    if not isinstance(entities, list): entities = []
    cleaned_entities = []
    for ent in entities:
        if isinstance(ent, dict) and "name" in ent and "type" in ent:
            cleaned_entities.append({"name": ent["name"], "type": ent["type"]})

    return {
        "title_en": title_en, "category": cat, "loc_name": loc_name,
        "lat": lat, "lng": lng, "sentiment": sentiment, "entities": cleaned_entities
    }

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
            category      TEXT,
            loc_name      TEXT,
            lat           REAL,
            lng           REAL,
            published_at  TEXT,
            fetched_at    TEXT,
            etag          TEXT,
            last_modified TEXT,
            breaking      INTEGER DEFAULT 1
        )
    """)
    for col, col_type in [('title_en','TEXT'),('sentiment','TEXT'),('entities','TEXT')]:
        try: conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError: pass
    conn.commit()
    conn.close()

def _connect():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn

def _db_upsert(conn, item, etag=None, lm=None):
    conn.execute("""
        INSERT INTO articles (id,url,title,title_en,summary,source,category,
            loc_name,lat,lng,published_at,fetched_at,etag,last_modified,breaking,
            sentiment,entities)
        VALUES (:id,:url,:title,:title_en,:summary,:source,:category,
            :loc_name,:lat,:lng,:published_at,:fetched_at,:etag,:lm,:breaking,
            :sentiment,:entities)
        ON CONFLICT(url) DO UPDATE SET
            title=excluded.title, title_en=excluded.title_en,
            summary=excluded.summary, category=excluded.category,
            loc_name=excluded.loc_name, lat=excluded.lat, lng=excluded.lng,
            published_at=excluded.published_at, fetched_at=excluded.fetched_at,
            etag=excluded.etag, last_modified=excluded.last_modified,
            sentiment=excluded.sentiment, entities=excluded.entities
    """, {**item, "etag": etag, "lm": lm})
    conn.commit()

def _db_prune(conn):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).isoformat()
    conn.execute("DELETE FROM articles WHERE published_at < ?", (cutoff,)); conn.commit()

def _export_json(conn):
    rows = conn.execute("SELECT * FROM articles ORDER BY published_at DESC").fetchall()
    all_titles = [r["title"] or "" for r in rows]
    records = []
    for r in rows:
        records.append({
            "id": r["id"], "url": r["url"], "title": r["title"],
            "title_en": r["title_en"] or r["title"], "summary": r["summary"],
            "source": r["source"], "category": r["category"],
            "sentiment": r["sentiment"] or "neutral",
            "entities": json.loads(r["entities"]) if r["entities"] else [],
            "breaking": _score_breaking(r["title"] or "", all_titles),
            "timestamp": r["published_at"],
            "location": {"name": r["loc_name"], "lat": r["lat"], "lng": r["lng"]}
        })
    with open(JSON_EXPORT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"  Exported {len(records)} records → {JSON_EXPORT}")

def _run():
    print("=== Aura-Erbil AI Scraper (Cohere API) ===")
    _ensure_db(); conn = _connect()
    print("→ RSS feed …"); added = 0
    try:
        feed = feedparser.parse(RUDAW_RSS)
        for entry in feed.entries:
            url = entry.get("link", ""); title = _clean_title(entry.get("title", "").strip())
            if not url or not title: continue
            summary = BeautifulSoup(entry.get("summary", ""), "lxml").get_text(" ", strip=True)[:300]
            pub_parsed = entry.get("published_parsed")
            pub = datetime(*pub_parsed[:6], tzinfo=timezone.utc).isoformat() if pub_parsed else _now_iso()
            enrichment = _enrich_with_ai(title, summary) if (title or summary) else {
                "title_en": title, "category": "general", "loc_name": "Erbil", "lat": 36.1912, "lng": 44.0092,
                "sentiment": "neutral", "entities": []}
            _db_upsert(conn, {
                "id": _make_id(url), "url": url, "title": title, "title_en": enrichment["title_en"],
                "summary": summary, "source": "rudaw-rss", "category": enrichment["category"],
                "loc_name": enrichment["loc_name"], "lat": enrichment["lat"], "lng": enrichment["lng"],
                "published_at": pub, "fetched_at": _now_iso(), "breaking": 1,
                "sentiment": enrichment.get("sentiment", "neutral"),
                "entities": json.dumps(enrichment.get("entities", []))
            })
            added += 1
        print(f"  RSS: processed {added} entries")
    except Exception as exc: print(f"  RSS error: {exc}")

    if added == 0:
        print("  RSS returned nothing — triggering scrape fallback …")
        queue = [urljoin(BASE_URL, p) for p in LIST_PATHS]; visited = set(); pages = 0
        while queue and pages < MAX_PAGES_PER_RUN:
            url = queue.pop(0)
            if url in visited: continue
            visited.add(url)
            if any(url.rstrip("/").endswith(p.rstrip("/")) for p in LIST_PATHS):
                html, _, _ = _fetch(url)
                if not html: continue
                pages += 1
                soup = BeautifulSoup(html, "lxml")
                for a in soup.select("a[href]"):
                    href = a["href"]; full = urljoin(BASE_URL, href)
                    if _same_origin(full) and ("/english/" in full or "/sorani/" in full or "/kurmanci/" in full) and len(_clean_title(a.get_text(strip=True))) > 5:
                        if full not in visited: queue.append(full)
                continue
            etag, lm = conn.execute("SELECT etag, last_modified FROM articles WHERE url=?", (url,)).fetchone() or (None, None)
            html, new_etag, new_lm = _fetch(url, etag, lm)
            pages += 1
            if html in (None, "NOT_MODIFIED"): continue
            soup = BeautifulSoup(html, "lxml")
            h1 = soup.find("h1"); title = _clean_title(h1.get_text(strip=True) if h1 else "")
            if not title: continue
            time_tag = soup.find("time"); pub = time_tag["datetime"] if time_tag and time_tag.get("datetime") else _now_iso()
            paras = [p.get_text(" ", strip=True) for p in soup.select("article p, .article-body p")]
            summary = " ".join(paras)[:2000] if paras else ""
            enrichment = _enrich_with_ai(title, summary) if title else {
                "title_en": title, "category": "general", "loc_name": "Erbil", "lat": 36.1912, "lng": 44.0092,
                "sentiment": "neutral", "entities": []}
            _db_upsert(conn, {
                "id": _make_id(url), "url": url, "title": title, "title_en": enrichment["title_en"],
                "summary": summary, "source": "rudaw-scrape", "category": enrichment["category"],
                "loc_name": enrichment["loc_name"], "lat": enrichment["lat"], "lng": enrichment["lng"],
                "published_at": pub, "fetched_at": _now_iso(), "breaking": 1,
                "sentiment": enrichment.get("sentiment", "neutral"),
                "entities": json.dumps(enrichment.get("entities", []))
            })
            added += 1
            print(f"  [saved] {title[:70]}")
        print(f"  Scrape: {added} new articles ({pages} pages fetched)")

    _db_prune(conn); _export_json(conn); conn.close()
    print("=== Done ===")

if __name__ == "__main__":
    _run()
