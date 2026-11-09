from datetime import date
from pathlib import Path

from psycopg import Connection

SQL = Path(__file__).resolve().with_suffix(".sql")


def refresh_corridor(conn: Connection, as_of: date) -> int:
    """Refresh the complete mart, including cells affected by MoM and YoY."""
    conn.execute("DELETE FROM mart.market_corridor")
    return conn.execute(
        SQL.read_text(encoding="utf-8"), {"as_of": as_of}
    ).rowcount
