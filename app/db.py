import mysql.connector
from app.config import DB_CONFIG


def get_connection():
    """Open een nieuwe MySQL-verbinding."""
    return mysql.connector.connect(**DB_CONFIG)
