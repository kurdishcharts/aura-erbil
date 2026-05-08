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

def _enrich_with_ai(title_original: str, summary: str) -> dict:
    """Try GitHub Models first (free, no key), then Cohere, then Together, then keyword defaults."""
    loc_keys = list(LOCATIONS.keys())
    loc_list_str = ", ".join(loc_keys[:40])

    prompt = f"""You are a news enrichment assistant for the Kurdistan region.
Given the title and body of a news article, perform these tasks:
1. If the title is in Sorani Kurdish (Arabic script), translate it to English.
   If it is already in English, return it unchanged.
2. Classify the article into ONE of these categories:
   security, fire, traffic, infrastructure, weather, general.
3. From the list below, pick the single location most specific to the article.
   If none match, use "erbil".
4. Determine the overall sentiment of the article: positive, negative, or neutral.
5. Extract up to 5 named entities (persons, organizations, places) mentioned.
   For each entity, specify a type: PERSON, ORGANIZATION, or LOCATION.

Available locations: {loc_list_str}

Return ONLY a valid JSON object with exactly these keys:
title_en, category, location_key, sentiment, entities

Entities must be a list of objects like: [{{"name": "...", "type": "PERSON"}}, ...]

Title: {title_original}
Body: {summary[:2000]}"""

    data = None

    # --- 1. GitHub Models (primary, free, zero setup) ---
    if "GITHUB_TOKEN" in os.environ or "GH_TOKEN" in os.environ:
        try:
            import openai as _openai
            gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
            gh_client = _openai.OpenAI(
                base_url="https://models.github.ai/inference",
                api_key=gh_token,
            )
            resp = gh_client.chat.completions.create(
                model="cohere/command-a",  # Cohere model hosted on GitHub Models
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=1000,
            )
            raw = resp.choices[0].message.content
            import re as _re
            match = _re.search(r'\{.*\}', raw, _re.DOTALL)
            if match:
                data = json.loads(match.group())
                print("  [github-models] enriched successfully")
            else:
                print("  [github-models] No JSON found, trying Cohere...")
        except Exception as e:
            print(f"  [github-models] failed ({e}), trying Cohere...")

    # --- 2. Cohere (fallback, 1000 calls/month trial) ---
    if data is None:
        try:
            time.sleep(3)
            response = co.chat(model=COHERE_MODEL, message=prompt, temperature=0.0, max_tokens=1000)
            raw = response.text.strip()
            import re as _re
            match = _re.search(r'\{.*\}', raw, _re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                print("  [cohere] No JSON found, trying Together...")
        except Exception as e:
            print(f"  [cohere] AI call failed ({e}), trying Together AI fallback...")

    # --- 3. Together AI (fallback, credit may be exhausted) ---
    if data is None and "TOGETHER_API_KEY" in os.environ:
        try:
            import openai as _openai2
            together_client = _openai2.OpenAI(
                api_key=os.environ["TOGETHER_API_KEY"],
                base_url="https://api.together.xyz/v1",
            )
            resp = together_client.chat.completions.create(
                model="meta-llama/Llama-3.2-3B-Instruct-Turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=1000,
            )
            raw = resp.choices[0].message.content
            import re as _re
            match = _re.search(r'\{.*\}', raw, _re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                print("  [together] No JSON found.")
        except Exception as e2:
            print(f"  [together] also failed ({e2}), falling back to keyword defaults")

    # --- 4. Keyword fallback ---
    if data is None:
        loc = _detect_location(title_original + " " + summary)
        return {
            "title_en": title_original,
            "category": _detect_category(title_original + " " + summary),
            "loc_name": loc["name"],
            "lat": loc["lat"],
            "lng": loc["lng"],
            "sentiment": "neutral",
            "entities": []
        }

    # --- Process AI response ---
    valid_cats = set(KEYWORDS.keys()) | {"general"}
    cat = data.get("category", "general")
    if cat not in valid_cats:
        cat = "general"

    loc_key = data.get("location_key", "").strip().lower()
    if loc_key in LOCATIONS:
        lat, lng = LOCATIONS[loc_key]
        loc_name = loc_key.title()
    else:
        lat, lng = LOCATIONS.get("erbil", (36.1912, 44.0092))
        loc_name = "Erbil"

    title_en = data.get("title_en", title_original).strip()
    if not title_en:
        title_en = title_original

    sentiment = data.get("sentiment", "").strip().lower()
    if sentiment not in ("positive", "negative", "neutral"):
        sentiment = "neutral"

    entities = data.get("entities", [])
    if not isinstance(entities, list):
        entities = []
    cleaned_entities = []
    for ent in entities:
        if isinstance(ent, dict) and "name" in ent and "type" in ent:
            cleaned_entities.append({"name": ent["name"], "type": ent["type"]})

    return {
        "title_en": title_en,
        "category": cat,
        "loc_name": loc_name,
        "lat": lat,
        "lng": lng,
        "sentiment": sentiment,
        "entities": cleaned_entities
    }