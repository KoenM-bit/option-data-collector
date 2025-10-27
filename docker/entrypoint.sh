#!/usr/bin/env sh
set -e

# Respect direct commands passed via Docker/Compose (e.g., "python -m ...")
if [ "$1" = "python" ] || [ "$1" = "sh" ] || [ "$1" = "bash" ]; then
  exec "$@"
fi

MODE="${MODE:-$1}"
[ -z "$MODE" ] && MODE="api"

log_prefix() {
  # Usage: log_prefix [prefix] -- command ...
  PREFIX="$1"; shift; [ "$1" = "--" ] && shift || true
  # Use unbuffered sed to prefix each line
  sh -c "$* 2>&1 | sed -u 's/^/['$PREFIX'] /'" &
  echo $!
}

PIDS=""
trap 'echo "[entrypoint] termination signal received"; kill $PIDS 2>/dev/null || true; wait; exit 0' INT TERM

case "$MODE" in
  api)
    exec python -m app.api.routes
    ;;
  scraper)
    exec python -m app.etl.beursduivel_scraper --continuous
    ;;
  sentiment)
    exec sh -c 'while true; do python -m app.etl.sentiment_tracker; sleep 86400; done'
    ;;
  daily-etl)
    exec sh -c 'while true; do python -m app.etl.daily_etl; sleep 86400; done'
    ;;
  all|all-in-one)
    echo "[entrypoint] starting all services in one container"
    PID_API=$(log_prefix api -- python -m app.api.routes)
    PID_SCRAPER=$(log_prefix scraper -- python -m app.etl.beursduivel_scraper --continuous)
    PID_SENT=$(log_prefix sentiment -- sh -c 'while true; do python -m app.etl.sentiment_tracker; sleep 86400; done')
    PID_ETL=$(log_prefix daily-etl -- sh -c 'while true; do python -m app.etl.daily_etl; sleep 86400; done')
    PIDS="$PID_API $PID_SCRAPER $PID_SENT $PID_ETL"
    # Wait for any to exit
    wait -n $PID_API $PID_SCRAPER $PID_SENT $PID_ETL
    STATUS=$?
    echo "[entrypoint] a process exited with status $STATUS, shutting down"
    kill $PIDS 2>/dev/null || true
    wait || true
    exit $STATUS
    ;;
  *)
    echo "[entrypoint] Unknown MODE '$MODE'. Valid: api, scraper, sentiment, daily-etl, all" >&2
    exit 1
    ;;
 esac
