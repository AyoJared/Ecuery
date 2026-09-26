"""The "Read-only & valid?" gate from the diagram, for Gemini-generated SQL.

This is the first layer only. The query also runs inside a READ ONLY
transaction with a statement timeout (see repo.py), so a write that slips past
these checks is still rejected by Postgres itself.
"""

import re

BLOCKED = re.compile(
    r"\b(insert|update|delete|merge|upsert|drop|alter|create|truncate|grant|revoke|"
    r"copy|call|do|vacuum|analyze|refresh|reindex|cluster|comment|lock|set|reset|"
    r"listen|notify|prepare|execute|deallocate|begin|commit|rollback|savepoint|into|"
    r"pg_sleep|pg_read_file|pg_read_binary_file|pg_ls_dir|lo_import|lo_export|dblink)\b",
    re.IGNORECASE,
)


class UnsafeSQL(ValueError):
    pass


def check_readonly(sql: str) -> str:
    """Return the cleaned statement, or raise UnsafeSQL explaining why not."""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise UnsafeSQL("Query is empty.")
    if "--" in cleaned or "/*" in cleaned:
        raise UnsafeSQL("SQL comments are not allowed.")
    if ";" in cleaned:
        raise UnsafeSQL("Only a single statement is allowed.")
    if not re.match(r"(select|with)\b", cleaned, re.IGNORECASE):
        raise UnsafeSQL("Only SELECT (or WITH ... SELECT) queries are allowed.")
    if match := BLOCKED.search(cleaned):
        raise UnsafeSQL(f"Keyword '{match.group(0)}' is not allowed in read-only queries.")
    return cleaned
