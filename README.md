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

### Single-container modes (for Portainer/Synology)

The image supports multiple modes via the entrypoint:

- API only (default):
  - Command: `api` (or leave default)
- All-in-one (run API + scraper + daily-etl loop + sentiment loop inside one container):
  - Command: `all` (or set `MODE=all` env)
- Individual workers:
  - Command: `scraper` | `daily-etl` | `sentiment`

All-in-one prefixes logs with `[api]`, `[scraper]`, `[daily-etl]`, and `[sentiment]` so you can see everything in one log stream in Portainer.

### Portainer Stack (multi-container)

Use `deploy/portainer-stack.yml` to run each service as its own container (best practice). In Portainer:

1. Stacks → Add stack
2. Name: `option-data-collector`
3. Paste the contents of `deploy/portainer-stack.yml` (or upload it)
4. Set environment variables (DB_HOST, DB_USER, DB_PASS, DB_NAME, DB_PORT) in the UI or via an env file
5. Deploy the stack

Notes:
- The stack references the prebuilt image `ghcr.io/<owner>/option-data-collector:latest` (owner is lowercase; for this repo it’s `koenm-bit`).
- If your GHCR image is private, configure registry auth in Portainer or provide credentials.
- Logs are per-container; use Portainer’s container logs for each service, or the stack log aggregation if available.

### ETL-only Docker Compose (run once)

For a quick end-to-end ETL test without other services, use the ETL-only compose:

- Build and run once (exits when done):
  - `make docker-etl-up`
- Tail logs:
  - `make docker-etl-logs`
- Tear down:
  - `make docker-etl-down`

This uses `deploy/docker-compose.etl.yml`, which builds the image locally and runs `python -m app.etl.daily_etl` a single time.

### Synology/Portainer: ETL-only options

- One-off run (recommended to verify DB connectivity):
  - In Portainer, Stacks → Add stack
  - Paste `deploy/portainer-etl-once.yml`
  - Provide env vars (DB_HOST, DB_USER, DB_PASS, DB_NAME, DB_PORT)
  - Deploy → the container runs once and exits with status

- Daily loop (24h schedule inside the container):
  - Use `deploy/portainer-stack.yml`, keep only the `daily-etl` service (or deploy whole stack)
  - Command `daily-etl` will run the loop; logs show each daily run

Notes:
- If your DB is on your LAN and Synology can’t reach it over the default bridge, consider enabling host networking in the Portainer stack by adding `network_mode: host` to the service. Ensure port 8080 is free when using host network.

## CI/CD and GHCR

On every push to `main`, GitHub Actions will:

- install deps, run lint (ruff F-only) and formatting check (black), and run pytest smoke tests
- build the Docker image and push it to GitHub Container Registry (GHCR) as:
  - `ghcr.io/<owner>/option-data-collector:latest`
  - `ghcr.io/<owner>/option-data-collector:<git-sha>`

On git tag pushes (e.g., `v1.2.3`), the workflow also publishes semver tags:

- `ghcr.io/<owner>/option-data-collector:1.2.3`
- `ghcr.io/<owner>/option-data-collector:1.2`
- `ghcr.io/<owner>/option-data-collector:1`

Notes:

- The push uses the built-in `GITHUB_TOKEN`, so no extra secrets are needed.
- Images are private by default if the repository is private. To pull from other machines, ensure you’re authenticated to GHCR and have access.

Pull and run (example):

```bash
# Login to GHCR (only needed once per environment)
echo $GITHUB_TOKEN | docker login ghcr.io -u <github-username> --password-stdin

# Pull the latest image
docker pull ghcr.io/<owner>/option-data-collector:latest

# Run the API service (provide DB env vars as needed)
docker run --rm -p 8080:8080 \
  -e DB_HOST=... -e DB_USER=... -e DB_PASS=... -e DB_NAME=... -e DB_PORT=3306 \
  ghcr.io/<owner>/option-data-collector:latest

# Run everything in one container and see all logs prefixed
docker run --rm -p 8080:8080 \
  -e DB_HOST=... -e DB_USER=... -e DB_PASS=... -e DB_NAME=... -e DB_PORT=3306 \
  ghcr.io/<owner>/option-data-collector:latest all
```

Replace `<owner>` with your GitHub username or org (lowercase). If the repo is private, the `GITHUB_TOKEN` or a PAT with `read:packages` scope is required for pulling.

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