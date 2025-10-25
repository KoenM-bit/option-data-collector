# Option Data Collector

Collect, compute, and serve option market data for Ahold Delhaize (and extendable to other tickers):
- Scrapers from FD.nl and Beursduivel (live prices)
- Greeks and implied volatility via Black–Scholes
- Daily option market score
- Sentiment via Yahoo Finance
- REST API with Swagger

## Architecture

- API: `app/api/routes.py` (Flask + Flasgger)
- ETL: `app/etl/`
  - `fd_overview_scraper.py` — header/overview and totals from FD.nl
  - `fd_options_scraper.py` — all option contracts (calls/puts) from FD.nl
  - `daily_etl.py` — orchestrates: overview → contracts → Greeks → scores (idempotent per peildatum)
  - `beursduivel_scraper.py` — live option prices (market-hours loop)
  - `sentiment_tracker.py` — analyst recommendations and price targets (yfinance)
- Compute: `app/compute/`
  - `option_greeks.py` — implied vol + Greeks using mid-price and ECB Euribor-based r
  - `compute_option_score.py` — macro/micro/total scores and price skew
- Utilities: `app/utils/helpers.py` — HTML fetch, EU number parsing, ECB Euribor lookup, etc.
- DB access: `app/db.py`, config from env in `app/config.py`

Tables used (MySQL/MariaDB):
- `fd_option_overview`, `fd_option_contracts`, `fd_option_greeks`, `fd_option_score`
- `option_prices` (live), `sentiment_data`

## Prerequisites

- Python 3.11+ (local dev)
- Docker and Docker Compose (for containerized stack)
- MySQL/MariaDB reachable from your machine/containers

Environment (.env in project root; NOT committed and not copied into Docker image):

```
DB_HOST=your-db-host
DB_USER=your-user
DB_PASS=your-pass
DB_NAME=optionsdb
DB_PORT=3306
PORT=8080
```

## Local development

- Fresh start (new venv + install deps):
  - `make fresh-start`
- Quick sanity check (imports):
  - `make check-imports`
- Run API locally (Ctrl+C to stop):
  - `make run-api`
- Compute flows:
  - `make test-greeks`
  - `make test-score`
- ETL orchestrator once (skips if peildatum exists):
  - `make run-etl`
- Sentiment once (handles 429 and updates same-day record):
  - `make run-sentiment`
- Beursduivel live scraper:
  - `make run-scraper` (loop)
  - `make run-scraper-once` (single iteration)

All run/test targets auto-load `.env`.

## Docker

- Build image:
  - `make docker-build`
- Start services and wait for API health:
  - `make docker-up`
- Tail logs:
  - `make docker-logs`
- Smoke-test API endpoints:
  - `make docker-test` (runs health + basic endpoint checks)
- Stop stack:
  - `make docker-down`

The API listens on `http://127.0.0.1:8080` by default.

## API endpoints

- `GET /api/status` — stack status
- `GET /api/latest` — latest live option price
- `GET /api/recent/<limit>` — recent live prices
- `GET /api/latest/<expiry>/<strike>` — latest price by expiry and strike
- `GET /api/latest/<expiry>/<strike>/<type>` — latest price for a specific option type
- `GET /api/contracts` — unique expiries, strikes, and types
- `GET /api/sentiment/<ticker>` — latest sentiment snapshot
- `GET /api/sentiment/trend/<ticker>` — sentiment trend and summary

Swagger UI is enabled via Flasgger.

## Troubleshooting

- yfinance 429 Too Many Requests:
  - The sentiment tracker will still write a placeholder and update the same-day row later when requests succeed.
  - Retry later or run `make run-sentiment` again.
- ETL skips with existing `peildatum`:
  - This confirms idempotency; it runs only on a new trading day.
- DB connectivity:
  - Ensure `.env` has correct DB credentials and the DB host is reachable from your network and containers.

## Notes

- Rates: the risk-free rate picks Euribor tenor by days-to-expiry via ECB API (with fallbacks).
- Prices: Greeks use mid-price (bid/ask) if available, otherwise last trade.
- Security: `.env` is ignored by git and excluded from Docker build context.

## License

Proprietary/Internal. Contact the author before reuse.