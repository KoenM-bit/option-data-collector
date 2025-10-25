import importlib

# Basic import smoke of key modules (no DB calls)
MODS = [
    "app.api.routes",
    "app.etl.fd_overview_scraper",
    "app.etl.fd_options_scraper",
    "app.etl.daily_etl",
    "app.etl.sentiment_tracker",
    "app.etl.beursduivel_scraper",
    "app.compute.option_greeks",
    "app.compute.compute_option_score",
    "app.utils.helpers",
    "app.db",
]


def test_smoke_imports():
    for m in MODS:
        importlib.import_module(m)


def test_api_status_endpoint():
    # Import Flask app without running server
    from app.api.routes import app

    with app.test_client() as client:
        res = client.get("/api/status")
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, dict)
        assert data.get("status") == "running"
