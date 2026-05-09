#!/bin/bash
cd ~/aura-erbil
source venv/bin/activate

# Start Ollama if not running
if ! pgrep -x "ollama" > /dev/null; then
    /opt/homebrew/bin/ollama serve &
    sleep 5
fi

export OLLAMA_NUM_THREADS=4
export OLLAMA_KEEP_ALIVE=0

python3 << 'PYEOF'
import sqlite3, json, time, requests, os, subprocess
import ollama

ANALYSIS_MODEL = "llama3.2:3b"
TRANSLATE_MODEL = "translategemma:4b"
DB_PATH = "data/aura.db"

# ------------------------------------------------------------
# Model unloader (same as before, bulletproof)
# ------------------------------------------------------------
def unload_model(model_name):
    for attempt in range(3):
        try:
            r = requests.post("http://localhost:11434/api/generate",
                json={"model": model_name, "prompt": "", "keep_alive": 0}, timeout=10)
            if r.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False

# ------------------------------------------------------------
# Translation step – Sorani → English
# ------------------------------------------------------------
def translate_title(title):
    # Only translate if it contains Arabic script characters
    if not any('\u0600' <= c <= '\u06ff' for c in title):
        return title   # already English

    prompt = (
        "You are a Sorani Kurdish to English translator. "
        "Translate the following title accurately into English. "
        "Return ONLY the translated title, no extra text.\n\n"
        f"Title: {title}"
    )
    try:
        resp = ollama.chat(model=TRANSLATE_MODEL, messages=[{"role":"user","content":prompt}], options={"temperature":0})
        translated = resp["message"]["content"].strip()
        # Clean up common artifacts
        translated = translated.split('\n')[0].strip('"').strip()
        print(f"  [translate] Sorani → English: {translated[:60]}")
        return translated
    except Exception as e:
        print(f"  [translate] failed ({e})")
        return title   # fallback to original

# ------------------------------------------------------------
# Sentiment enrichment – Kurdistan‑aware (same as before)
# ------------------------------------------------------------
def enrich(title, summary):
    prompt = f"""You are an expert geopolitical analyst for the Kurdistan Region of Iraq.
Your job is to classify news articles based on their impact on the **Kurdistan Region** only.

**Key rule:** 
- If an article is about another country’s internal affairs and does NOT directly involve or affect Kurdistan, mark it as **neutral**.
- If an article is about Kurdistan (any city like Erbil, Duhok, Sulaymaniyah, Halabja, Kirkuk), or about Kurdish diaspora, or about international events that **directly impact Kurdistan** (e.g., Strait of Hormuz crisis → affects oil exports; global pandemics → affect the region), then classify sentiment accordingly.

**Sentiment definitions (Kurdistan perspective):**
- **POSITIVE** – good for Kurdistan’s economy, security, diplomacy, infrastructure, minority rights, tourism, autonomy, international standing.
- **NEGATIVE** – bad for Kurdistan’s stability or interests.
- **NEUTRAL** – no clear impact on Kurdistan.

**Additional tasks:**
1. Categorise the article into ONE of: security, fire, traffic, infrastructure, weather, general.
2. Extract up to 5 named entities relevant to the region. Each must have a "name" and a "type" (PERSON, ORGANIZATION, or LOCATION).

Return ONLY a valid JSON object (no extra text) with exactly these keys:
{{"category": "…", "sentiment": "positive|negative|neutral", "entities": [{{"name": "…", "type": "…"}}] }}

**Now analyse this article:**
Title: {title}
Body: {summary[:2000]}"""
    try:
        resp = ollama.chat(model=ANALYSIS_MODEL, messages=[{"role":"user","content":prompt}], format="json", options={"temperature":0})
        return json.loads(resp["message"]["content"])
    except:
        return None

# ------------------------------------------------------------
# Main pipeline
# ------------------------------------------------------------
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, title, summary FROM articles WHERE sentiment='neutral' OR sentiment IS NULL OR sentiment=''").fetchall()

if not rows:
    print("No articles to enrich.")
    conn.close()
    exit(0)

print(f"Enriching {len(rows)} articles…")
count = 0
for i, row in enumerate(rows):
    original_title = row["title"] or ""
    print(f"\n[{i+1}/{len(rows)}] {original_title[:60]}")

    # Step 1: Translate if Sorani
    translated_title = translate_title(original_title)
    unload_model(TRANSLATE_MODEL)   # free translation model immediately

    # Step 2: Perform sentiment analysis (with translated or original title)
    combined_title = translated_title if translated_title != original_title else original_title
    data = enrich(combined_title, row["summary"] or "")
    
    if data:
        loc_key = (data.get("location_key") or "").lower().strip()
        COORDS = {"erbil":(36.1912,44.0092),"hewler":(36.1912,44.0092),"sulaymaniyah":(35.5571,45.4357),"slemani":(35.5571,45.4357),"duhok":(36.8669,43.0032),"halabja":(35.1787,45.9861),"zakho":(37.1441,42.6875),"ranya":(36.2558,44.8783),"koya":(36.0862,44.6283),"amadiya":(37.0924,43.4889),"chamchamal":(35.5279,44.8318),"penjwin":(35.6234,45.9435),"kirkuk":(35.4681,44.3922),"sinjar":(36.3197,41.8694),"makhmur":(35.7738,43.5908)}
        lat, lng = COORDS.get(loc_key, (None, None))
        loc_name = loc_key.title() if loc_key and loc_key != "null" else None
        update_fields = ["title_en=?","category=?","sentiment=?","entities=?"]
        update_vals = [translated_title, data.get("category","general"), data.get("sentiment","neutral"), json.dumps(data.get("entities",[]))]
        if lat and lng:
            update_fields += ["lat=?","lng=?","loc_name=?"]
            update_vals += [lat, lng, loc_name]
        update_vals.append(row["id"])
        conn.execute("UPDATE articles SET " + ",".join(update_fields) + " WHERE id=?", update_vals)
        conn.commit()
        count += 1
        print(f"  → {data['sentiment']:10} | {translated_title[:50]}")
    else:
        print("  → SKIPPED (AI returned unusable response)")

    unload_model(ANALYSIS_MODEL)
    time.sleep(4)

conn.close()

# ------------------------------------------------------------
# Export JSON & push
# ------------------------------------------------------------
conn2 = sqlite3.connect(DB_PATH)
conn2.row_factory = sqlite3.Row
rows2 = conn2.execute("SELECT * FROM articles ORDER BY published_at DESC").fetchall()
records = []
for r in rows2:
    records.append({
        "id": r["id"], "url": r["url"], "title": r["title"],
        "title_en": r["title_en"] or r["title"], "summary": r["summary"],
        "source": r["source"], "category": r["category"],
        "sentiment": r["sentiment"] or "neutral",
        "entities": json.loads(r["entities"]) if r["entities"] else [],
        "breaking": 1, "timestamp": r["published_at"],
        "location": {"name": r["loc_name"], "lat": r["lat"], "lng": r["lng"]}
    })
with open("data/data.json","w") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)
conn2.close()
print(f"\nExported {len(records)} records.")

subprocess.run(["git","add","data/"], cwd=os.path.dirname(os.path.abspath(__file__)))
subprocess.run(["git","commit","-m","Kurdistan enrichment w/ TranslateGemma"], cwd=os.path.dirname(os.path.abspath(__file__)))
subprocess.run(["git","pull","--rebase","origin","main"], cwd=os.path.dirname(os.path.abspath(__file__)))
subprocess.run(["git","push","origin","main"], cwd=os.path.dirname(os.path.abspath(__file__)))
PYEOF

# Stop Ollama to free RAM
pkill ollama
echo "Ollama stopped. RAM freed."
