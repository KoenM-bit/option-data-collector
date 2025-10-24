"""
Database connection utilities.
Preserves exact same connection logic as your current files.
"""

import mysql.connector

from src.config.settings import settings


def get_db_connection():
    """
    Creates database connection using exact same config as your current files.
    This function replaces the inline mysql.connector.connect() calls.
    """
    return mysql.connector.connect(**settings.db_config)


def create_option_prices_table():
    """
    Creates the option_prices table exactly as in your current beursduivel.py.
    Extracted so it can be reused across services.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS option_prices (
            id INT AUTO_INCREMENT PRIMARY KEY,
            issue_id VARCHAR(32),
            expiry VARCHAR(64),
            type VARCHAR(10),
            strike VARCHAR(10),
            price DECIMAL(10,3),
            source VARCHAR(20),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    conn.commit()
    cursor.close()
    conn.close()


def create_sentiment_table():
    """
    Creates the sentiment_data table for sentiment tracking.
    Based on your sentiment_tracker.py usage.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sentiment_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticker VARCHAR(10),
            rating_avg DECIMAL(3,2),
            rating_label VARCHAR(20),
            target_avg DECIMAL(10,2),
            target_high DECIMAL(10,2),
            target_low DECIMAL(10,2),
            sentiment_score DECIMAL(5,2),
            buy_count INT,
            hold_count INT,
            sell_count INT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    conn.commit()
    cursor.close()
    conn.close()
