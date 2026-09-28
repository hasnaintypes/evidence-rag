"""
Wipes all rows from every app table - schema stays intact, nothing is
dropped or altered. Never touches Supabase's own `auth` schema (a
different Postgres schema entirely; this script only ever runs
statements against `public.*`) - existing user accounts are untouched.

Usage: python scripts/reset_data.py [--yes]
  --yes  skip the confirmation prompt (for CI/scripted use)
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings
from src.storage.database import get_db_connection

# Order doesn't matter functionally (no FK constraints are declared in
# this schema today), but child-before-parent reads more clearly and
# costs nothing if constraints are ever added later.
TABLES = [
    "messages",
    "conversations",
    "entity_edges",
    "entities",
    "document_chunks",
    "knowledge_nodes",
    "documents",
    "query_log",
]


def reset_data() -> None:
    conn = get_db_connection()
    cursor = conn.cursor()

    if settings.storage_mode == "supabase":
        for table in TABLES:
            # RESTART IDENTITY resets serial/autoincrement counters too -
            # a genuine fresh start, not just empty tables with IDs
            # picking up where they left off.
            cursor.execute(f"TRUNCATE TABLE public.{table} RESTART IDENTITY CASCADE")
    else:
        for table in TABLES:
            cursor.execute(f"DELETE FROM {table}")
        cursor.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ({})".format(
                ", ".join("?" for _ in TABLES)
            ),
            TABLES,
        )

    conn.commit()
    conn.close()

    # The in-memory BM25/embedding index cache (src/retrieval/hybrid.py)
    # self-invalidates on the next query via a COUNT(*) check against
    # document_chunks, so no explicit cache-clear call is needed here.


if __name__ == "__main__":
    skip_confirm = "--yes" in sys.argv

    print(f"This will DELETE ALL ROWS from: {', '.join(TABLES)}")
    print(f"storage_mode = {settings.storage_mode}")
    print("Table structure is kept. Supabase Auth users are never touched.")

    if not skip_confirm:
        answer = input("Type 'yes' to continue: ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            sys.exit(0)

    reset_data()
    print("Done - all app tables are now empty.")
