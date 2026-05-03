# Phase 2: Cohere API Integration TODO

- [x] 1. Add cohere to scraper/requirements.txt
- [x] 2. Fix .env with COHERE_API_KEY
- [x] 3. Install and test locally (pip install, source .env, run scraper_cohere.py)
- [x] 4. Verify AI enrichment in data/data.json
- [x] 5. Create .github/workflows/update.yml
- [ ] 6. Add GitHub secret and push changes

## Commands to run:
```
echo "cohere" >> scraper/requirements.txt
echo 'export COHERE_API_KEY=your_key_here' > .env
source venv/bin/activate
pip install -r scraper/requirements.txt
source .env
python scraper/scraper_cohere.py
python -c "import json; data=json.load(open('data/data.json')); print(data[0]['title'], '→', data[0].get('title_en','?'))"
mkdir -p .github/workflows
# (then cat > .github/workflows/update.yml as provided)
**Note: Use new API key from repo secrets after setup.**
```

