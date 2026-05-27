"""Data-layer checks for the Vantage seed (Brief B).

Loads db/schema.sql then db/seed.sql into Postgres and asserts referential
integrity, chronology, and every planted eval scenario (E1/E2/E3 + the
High/Critical hero) — plus that db/seed.sql is still in sync with its generator.

Run locally against any empty Postgres (one command):

    pip install -r db/tests/requirements.txt
    export DATABASE_URL=postgresql://vantage:vantage@localhost:5432/vantage
    # ...or set PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE instead
    pytest db/tests -v

CI runs exactly this against a Postgres service container
(.github/workflows/data-ci.yml). The suite lives under db/tests/ — not a
top-level tests/ — to stay within the data track's file ownership and clear of
app tests owned by track/infra.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "db" / "schema.sql"
SEED = REPO / "db" / "seed.sql"
GENERATOR = REPO / "scripts" / "generate_seed.py"

# "Open" per 04-Architecture. Hardcoded constants — safe to inline into SQL.
OPEN_SQL = "('open', 'in_progress', 'pending')"


def _psql_load(path: Path) -> None:
    """Load a .sql file with psql, honouring DATABASE_URL or PG* env vars."""
    cmd = ["psql"]
    if url := os.environ.get("DATABASE_URL"):
        cmd.append(url)
    cmd += ["-v", "ON_ERROR_STOP=1", "-q", "-f", str(path)]
    subprocess.run(cmd, check=True)


@pytest.fixture(scope="session")
def conn():
    """A connection to a database freshly loaded with schema then seed.

    schema.sql DROPs first, so this is idempotent and safe to re-run against a
    persistent local database.
    """
    _psql_load(SCHEMA)
    _psql_load(SEED)
    url = os.environ.get("DATABASE_URL")
    connection = psycopg.connect(url) if url else psycopg.connect()
    try:
        yield connection
    finally:
        connection.close()


def scalar(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]


def row(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()


# --- volume + roles ----------------------------------------------------------

@pytest.mark.parametrize("role", ["sales_user", "support_user", "admin"])
def test_every_role_present(conn, role):
    # Every role represented so RBAC + attribution work end to end.
    assert scalar(conn, f"SELECT count(*) FROM users WHERE role = '{role}'") >= 1


@pytest.mark.parametrize("table,lo,hi", [
    ("customers", 10, 14),
    ("issues", 35, 45),
    ("issue_updates", 100, 160),
    ("next_actions", 10, 20),
])
def test_volume_in_range(conn, table, lo, hi):
    # Brief targets, with slack — exact counts are tuning, not contract.
    n = scalar(conn, f"SELECT count(*) FROM {table}")
    assert lo <= n <= hi, f"{table}={n}, expected {lo}..{hi}"


# --- planted eval scenarios --------------------------------------------------

def test_e1_absent_names_not_present(conn):
    # The deliberately-absent names must not exist (drives the "not found" path).
    n = scalar(conn, "SELECT count(*) FROM customers "
                     "WHERE name ILIKE '%Zzzz%' OR name ILIKE '%Globex%'")
    assert n == 0


def test_e2_twins_distinct_account_ref(conn):
    # Near-identical names, separable by account_ref.
    refs = scalar(conn, "SELECT count(DISTINCT account_ref) FROM customers "
                        "WHERE name ILIKE 'Lumen Commerce%'")
    assert refs >= 2


def test_e3_customer_exists_with_zero_open(conn):
    # A real customer that has issues but none open.
    total, open_count = row(conn, f"""
        SELECT count(*),
               count(*) FILTER (WHERE i.status IN {OPEN_SQL})
        FROM issues i JOIN customers c ON c.id = i.customer_id
        WHERE c.name = 'Calm Waters Subscriptions'
    """)
    assert total >= 1, "Calm Waters Subscriptions should have issues"
    assert open_count == 0, "Calm Waters Subscriptions should have zero open issues"


def test_hero_is_high_critical(conn):
    # Velocity Marketplace is clearly High/Critical for the escalation story.
    open_count, crit_count = row(conn, f"""
        SELECT count(*) FILTER (WHERE i.status IN {OPEN_SQL}),
               count(*) FILTER (WHERE i.status IN {OPEN_SQL} AND i.priority = 'critical')
        FROM issues i JOIN customers c ON c.id = i.customer_id
        WHERE c.name = 'Velocity Marketplace'
    """)
    assert crit_count >= 1, "hero needs at least one critical open issue"
    assert open_count >= 3, "hero needs several open issues"


# --- chronology + integrity --------------------------------------------------

def test_no_update_predates_its_issue(conn):
    assert scalar(conn, "SELECT count(*) FROM issue_updates u "
                        "JOIN issues i ON i.id = u.issue_id "
                        "WHERE u.created_at < i.created_at") == 0


def test_issue_updated_at_not_before_created(conn):
    assert scalar(conn, "SELECT count(*) FROM issues WHERE updated_at < created_at") == 0


def test_every_issue_has_history(conn):
    assert scalar(conn, "SELECT count(*) FROM issues i WHERE NOT EXISTS "
                        "(SELECT 1 FROM issue_updates u WHERE u.issue_id = i.id)") == 0


def test_no_future_timestamps(conn):
    assert scalar(conn, "SELECT count(*) FROM issues "
                        "WHERE created_at > now() OR updated_at > now()") == 0
    assert scalar(conn, "SELECT count(*) FROM issue_updates WHERE created_at > now()") == 0


def test_next_actions_admin_owned(conn):
    # RBAC boundary: only admins create next actions (ADR-002).
    assert scalar(conn, "SELECT count(*) FROM next_actions na "
                        "JOIN users u ON u.id = na.created_by_id "
                        "WHERE u.role <> 'admin'") == 0


def test_no_orphan_foreign_keys(conn):
    # FKs enforce these; assert anyway as a guard against a future schema slip.
    assert scalar(conn, "SELECT count(*) FROM issues i "
                        "LEFT JOIN customers c ON c.id = i.customer_id WHERE c.id IS NULL") == 0
    assert scalar(conn, "SELECT count(*) FROM issue_updates u "
                        "LEFT JOIN issues i ON i.id = u.issue_id WHERE i.id IS NULL") == 0
    assert scalar(conn, "SELECT count(*) FROM next_actions n "
                        "LEFT JOIN issues i ON i.id = n.issue_id WHERE i.id IS NULL") == 0


# --- seed is in sync with its generator (no database needed) -----------------

def test_seed_matches_generator():
    """db/seed.sql must be exactly what the generator emits (pinned Faker)."""
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--stdout"],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout == SEED.read_text(), (
        "db/seed.sql is out of date — re-run scripts/generate_seed.py and commit it."
    )
