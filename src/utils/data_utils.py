"""
Data Processing Utilities
Professional utilities for option data processing, market timing, and data validation.
Implements robust helper functions with comprehensive error handling.
"""

import datetime as dt

import pytz

from src.config.settings import settings


def clean_href(href: str) -> str:
    """
    Clean href function exactly as in your beursduivel.py.
    Preserves exact same logic.
    """
    base_url = "https://www.beursduivel.be"
    href = href.replace("../../../", "/")
    return f"{base_url}{href}"


def _parse_eu_number(s: str) -> float:
    """
    Parse European number format exactly as in your beursduivel.py.
    Preserves exact same logic and behavior.
    """
    s = (s or "").strip().replace("\xa0", "")
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def is_market_open() -> bool:
    """
    Market hours check exactly as in your beursduivel.py.
    Uses same timezone and hours logic.
    """
    timezone = pytz.timezone(settings.timezone)  # Europe/Amsterdam
    now = dt.datetime.now(timezone)
    return settings.market_open_hour <= now.hour < settings.market_close_hour


def get_current_time_amsterdam() -> dt.datetime:
    """
    Get current Amsterdam time - useful for logging and timestamps.
    """
    timezone = pytz.timezone(settings.timezone)
    return dt.datetime.now(timezone)


def format_amsterdam_time(time_obj: dt.datetime = None) -> str:
    """
    Format Amsterdam time for display - matches your current logging format.
    """
    if time_obj is None:
        time_obj = get_current_time_amsterdam()
    return time_obj.strftime("%H:%M")
