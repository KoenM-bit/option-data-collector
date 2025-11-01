import os
from dotenv import load_dotenv

load_dotenv()

print("DEBUG: DB_HOST =", os.getenv("DB_HOST"))
print("DEBUG: DB_USER =", os.getenv("DB_USER"))
print("DEBUG: DB_PASS =", os.getenv("DB_PASS"))
print("DEBUG: DB_NAME =", os.getenv("DB_NAME"))

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "connection_timeout": 10,
    "autocommit": False,
}
