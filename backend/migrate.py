"""
One-shot database migration + seed. Run at deploy time under the DDL-privileged
role (ij_migrate); serving instances then start with RUN_MIGRATIONS=0 as the
DML-only role (ij_app). See db/roles.sql.

    DATABASE_URL=postgresql://ij_migrate:***@host/ij  python migrate.py
"""
import asyncio
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

from core import db  # noqa: E402
from bootstrap import apply_migrations_and_seed  # noqa: E402


async def main() -> None:
    await db.connect()
    try:
        await apply_migrations_and_seed()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
