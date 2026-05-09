#!/bin/bash
cd ~/aura-erbil
source venv/bin/activate
export OLLAMA_MODEL="llama3.2:3b"
python3 -c "
import sqlite3, json, time, sys, os, re
import ollama

DB_PATH = 'data/aura.db'

def _enrich_local(title, summary):
    prompt = f'''You are a news enrichment assistant for the Kurdistan region.
Given the title and body of a news article, perform these tasks:
1. If the title is in Sorani Kurdish (Arabic script), translate it to English.
   If it is already in English, return it unchanged.
2. Classify the article into ONE of these categories:
   security, fire, traffic, infrastructure, weather, general.
3. Determine the overall sentiment of the article: positive, negative, or neutral.
4. Extract up to 5 named entities (persons, organizations, places) mentioned.

Return ONLY a valid JSON object with exactly these keys:
title_en, category, sentiment, entities

Title: {title}
Body: {summary[:1000]}'''
    resp = ollama.chat(model='llama3.2:3b', messages=[{'role':'user','content':prompt}])
    raw = resp['message']['content']
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    return None

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute(\"SELECT id, title, summary FROM articles WHERE sentiment = 'neutral' OR sentiment IS NULL\").fetchall()
print(f'Enriching {len(rows)} articles...')
success = 0
for i, row in enumerate(rows):
    data = _enrich_local(row['title'] or '', row['summary'] or '')
    if data:
        conn.execute('UPDATE articles SET title_en=?, category=?, sentiment=?, entities=? WHERE id=?',
            (data.get('title_en', row['title']), data.get('category', 'general'),
             data.get('sentiment', 'neutral'), json.dumps(data.get('entities', [])), row['id']))
        conn.commit()
        success += 1
        print(f'  [{i+1}/{len(rows)}] {data[\"sentiment\"]}')
    if i < len(rows)-1:
        time.sleep(1)
conn.close()
print(f'Done: {success}/{len(rows)} enriched.')
"
