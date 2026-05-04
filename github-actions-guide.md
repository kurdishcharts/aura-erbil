# GitHub Actions Navigation Guide for Aura-Erbil Logs
## Copy-Paste Ready Steps

**Direct URL:** https://github.com/kurdishcharts/aura-erbil/actions

1. **Actions tab** → Left sidebar: Click **Update News Data**
2. **Latest run** (top of list) → Click it
3. **Jobs section** → Click **Update News Data** job tile  
4. **Log steps sidebar** → Expand **Run Cohere AI scraper**
5. **Ctrl+F** these exact lines:
   ```
   === Aura-Erbil AI Scraper (Cohere API) ===
   [cohere]                           ← AI working
   [saved]                            ← Data saved to DB/JSON
   === Done ===
   ```

**✅ Success:** All lines present, no errors  
**⚠️ Old scraper:** No `[cohere]` = uses `scraper.py` not `_cohere.py`  
**❌ Error:** Check for 'cohere API' failures (model deprecation noted)

**Re-run:** Top-right **Re-run all jobs**  
**Workflow source:** `.github/workflows/update.yml` (runs `scraper_cohere.py`)

---

**Pro tip:** Bookmark & refresh every 30min (cron schedule)
