# Archived legacy scripts

These files were used in the first version of the project and are now archived. The Docker stack and production code run from `app/`.

- app.py
- beursduivel.py
- fd_option_summary.py
- fd_option_contracts.py
- compute_option_score.py
- option_greeks.py
- sentiment_tracker.py
- daily_etl.py
- fetch_ahold_options.py

Refer to the new modules:
- API: `app/api/routes.py`
- FD scrapers: `app/etl/fd_overview_scraper.py`, `app/etl/fd_options_scraper.py`
- Live Beursduivel: `app/etl/beursduivel_scraper.py`
- Sentiment: `app/etl/sentiment_tracker.py`
- ETL orchestrator: `app/etl/daily_etl.py`
- Greeks and scores: `app/compute/option_greeks.py`, `app/compute/compute_option_score.py`