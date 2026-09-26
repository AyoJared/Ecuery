"""Snowflake connection settings from .env.local, shared by the API and setup_db.

Auth: SNOWFLAKE_PRIVATE_KEY_FILE (key-pair, works on MFA-enforced accounts)
takes priority; otherwise SNOWFLAKE_PASSWORD (password or programmatic access token).
"""

import os
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def is_configured() -> bool:
    return bool(os.getenv("SNOWFLAKE_ACCOUNT") and os.getenv("SNOWFLAKE_USER")
                and (os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE") or os.getenv("SNOWFLAKE_PASSWORD")))


def auth_params() -> dict:
    key_file = os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE")
    if key_file:
        path = Path(key_file)
        path = path if path.is_absolute() else BACKEND / path
        return {"authenticator": "SNOWFLAKE_JWT", "private_key_file": str(path)}
    return {"password": os.getenv("SNOWFLAKE_PASSWORD")}


def connect_params(role: str | None = None, with_context: bool = True) -> dict:
    params = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        **auth_params(),
        "login_timeout": 30,
        "network_timeout": 60,
    }
    role = role or os.getenv("SNOWFLAKE_ROLE")
    if role:
        params["role"] = role
    if with_context:
        params |= {
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "ECUERY_WH"),
            "database": os.getenv("SNOWFLAKE_DATABASE", "ECUERY"),
            "schema": os.getenv("SNOWFLAKE_SCHEMA", "HISTORY"),
        }
    return params
