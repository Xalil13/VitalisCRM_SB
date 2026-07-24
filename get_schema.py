import json
import os

def get_db_schema():
    try:
        # Check environment variable first (for containerized deployments)
        if "DB_SCHEMA" in os.environ:
            return os.environ["DB_SCHEMA"]

        # Try to load from config.json
        if os.path.exists("config.json"):
            with open("config.json", "r") as f:
                config = json.load(f)
                return config.get("DB_SCHEMA", "VITALIS_DEV.APP")

    except Exception:
        pass

    # Fallback to default dev schema
    return "VITALIS_DEV.APP"
