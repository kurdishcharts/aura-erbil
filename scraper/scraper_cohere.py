# Accept main's version completely, discard cohere branch changes
git checkout --theirs scraper/scraper_cohere.py
git add scraper/scraper_cohere.py
git commit -m "Resolve conflict: keep main scraper with GitHub Models AI"
git push origin main