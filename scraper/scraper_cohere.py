import requests
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

from bs4 import BeautifulSoup

BASE_URL          = "https://www.rudaw.net"
RUDAW_RSS         = "https://www.rudaw.net/rss"
LIST_PATHS        = ["/english","/sorani/kurdistan","/sorani/middleeast","/sorani/business","/kurmanci"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
DB_PATH           = "data/aura.db"
JSON_EXPORT       = "data/data.json"
MAX_AGE_DAYS      = 30
MAX_PAGES_PER_RUN = 20
MIN_DELAY = 3.0
MAX_DELAY = 5.0
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

def _allowed(url):
    """Check robots.txt for the specific domain (cached per run)."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    domain_robots = f"{base}/robots.txt"

    # Cache the robots for each domain (simple dict, reset each run)
    if not hasattr(_allowed, "cache"):
        _allowed.cache = {}

    if domain_robots not in _allowed.cache:
        rp = robotparser.RobotFileParser()
        rp.set_url(domain_robots)
        try:
            rp.read()
            _allowed.cache[domain_robots] = rp
        except Exception:
            # If we can't fetch robots.txt, allow by default (conservative)
            print(f"  [robots.txt] Could not fetch {domain_robots}, allowing")
            _allowed.cache[domain_robots] = None
            return True

    rp = _allowed.cache[domain_robots]
    if rp is None:
        return True

    allowed = rp.can_fetch(USER_AGENT, url)
    if not allowed:
        print(f"  [robots.txt] DISALLOWED: {url}")
    return allowed
def _jitter(): time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
def _fetch(url, etag=None, last_modified=None, _backoff=BACKOFF_BASE):
    if False: print(f"  [robots.txt] blocked: {url}"); return None,None,None
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

def _enrich_with_ai(title_original: str, summary: str) -> dict:
    """GitHub Models AI — Kurdistan-aware, city-level location."""
    import time, json
    from openai import OpenAI
    import os
    token = os.environ.get("GITHUB_TOKEN","")
    if not token:
        return _keyword_fallback(title_original, summary)
    client = OpenAI(base_url="https://models.github.ai/inference", api_key=token)
    COORDS = {"erbil":(36.1912,44.0092),"hewler":(36.1912,44.0092),
              "sulaymaniyah":(35.5571,45.4357),"slemani":(35.5571,45.4357),
              "duhok":(36.8669,43.0032),"halabja":(35.1787,45.9861),
              "zakho":(37.1441,42.6875),"ranya":(36.2558,44.8783),
              "koya":(36.0862,44.6283),"amadiya":(37.0924,43.4889),
              "chamchamal":(35.5279,44.8318),"kirkuk":(35.4681,44.3922),
              "sinjar":(36.3197,41.8694),"makhmur":(35.7738,43.5908),
              "shaqlawa":(36.5485,44.3397),"soran":(36.6539,44.5472)}
    CITIES = list(COORDS.keys())
    prompt = f"""You are a geopolitical analyst for the Kurdistan Region of Iraq (KRI).
Return ONLY valid JSON with exactly these 5 keys:
"title_en": English translation of the original title (if Sorani, translate; if already English, keep as is)
"sentiment": "positive"|"negative"|"neutral" — impact on KRI only
"category": security|politics|economy|infrastructure|weather|fire|traffic|health|culture|general
"entities": up to 5 objects with name and type (PERSON/ORGANIZATION/LOCATION)
"location_key": primary KRI city lowercase from {CITIES} — use "erbil" for general KRI news, null if entirely outside KRI

Article — Title: {title_original}
Body: {summary[:1500]}
Return ONLY the JSON object:"""
    try:
        time.sleep(2)
        resp = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0, max_tokens=350)
        data = json.loads(resp.choices[0].message.content.strip())
        loc = (data.get("location_key") or "erbil").lower().strip()
        lat,lng = COORDS.get(loc,(36.1912,44.0092))
        return {"title_en":data.get("title_en", title_original),
                "category":data.get("category","general"),
                "sentiment":data.get("sentiment","neutral"),
                "entities":data.get("entities",[]),
                "loc_name":loc.title(),"lat":lat,"lng":lng}
    except Exception as e:
        print(f"  [AI] error: {e}")
        return _keyword_fallback(title_original, summary)

def _keyword_fallback(title_original: str, summary: str) -> dict:
    combined = (title_original or "") + " " + (summary or "")
    loc = _detect_location(combined)
    return {"title_en":data.get("title_en", title_original),"category":_detect_category(combined),
            "loc_name":loc["name"],"lat":loc["lat"],"lng":loc["lng"],
            "sentiment":"neutral","entities":[]}

