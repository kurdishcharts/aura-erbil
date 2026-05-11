#!/bin/bash
echo "========== AURA SYSTEM HEALTH =========="
echo "Time: $(date)"
echo ""

# 1. Local DB vs live site
echo "--- Article counts ---"
LOCAL_TOTAL=$(sqlite3 ~/aura-erbil/data/aura.db "SELECT COUNT(*) FROM articles;")
LIVE_TOTAL=$(curl -s "https://kurdishcharts.github.io/aura-erbil/data/data.json" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null)
echo "Local DB:  $LOCAL_TOTAL articles"
echo "Live site: $LIVE_TOTAL articles"
echo ""

# 2. Sentiment breakdown (local)
echo "--- Sentiment (local DB) ---"
sqlite3 ~/aura-erbil/data/aura.db "SELECT sentiment, COUNT(*) FROM articles GROUP BY sentiment;"
echo ""

# 3. Last enrichment run
echo "--- Last enrichment ---"
if [ -f ~/aura-erbil/enrich.log ]; then
    tail -3 ~/aura-erbil/enrich.log | grep "===" || echo "No timestamp found"
else
    echo "No enrich log"
fi
echo ""

# 4. Cron job
echo "--- Cron ---"
crontab -l 2>/dev/null | grep enrich || echo "NOT SCHEDULED"
echo ""

# 5. GitHub Actions last run
echo "--- GitHub Actions ---"
curl -s "https://api.github.com/repos/kurdishcharts/aura-erbil/actions/runs?per_page=1" 2>/dev/null | python3 -c "
import json,sys
try:
    runs = json.load(sys.stdin).get('workflow_runs',[])
    if runs:
        r = runs[0]
        print(f'{r[\"name\"]} — {r[\"status\"]} / {r[\"conclusion\"]}')
        print(f'Started: {r[\"created_at\"]}')
    else:
        print('No runs found')
except:
    print('Could not fetch')
"
echo ""

# 6. Git status
echo "--- Git ---"
cd ~/aura-erbil
git status --short
echo ""
echo "========================================="
