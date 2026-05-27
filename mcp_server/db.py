"""PostgreSQL access — parameterised queries only (09-Security T3: no string-built SQL)."""
import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://vantage:changeme@db:5432/vantage")


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a read query with **bound** parameters; return rows as dicts.

    Parameters are always passed to psycopg's execute (never interpolated into the
    SQL string), so untrusted input (e.g. a customer name from the agent) cannot
    alter the query — this is the SQL-injection boundary (T3).
    """
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def execute(sql: str, params: tuple = ()) -> list[dict]:
    """Run a write (INSERT/UPDATE) with **bound** parameters and commit; return any rows.

    Same SQL-injection boundary as query() (T3). The connection context commits on clean
    exit (rolls back on exception), so a tool that raises mid-write leaves no partial change.
    Use `RETURNING` to get the written row back; statements with no result set return [].
    """
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []
