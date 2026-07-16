"""
One-shot backfill: encrypt existing customer PII + populate blind indexes (C6).

Run AFTER setting PII_ENCRYPTION_KEY and applying the schema (the *_bidx columns
must exist). Idempotent — rows already encrypted (values prefixed 'pii1:') are
skipped, so it is safe to re-run.

    PII_ENCRYPTION_KEY=... DATABASE_URL=... python migrate_pii.py
"""
import asyncio
import logging

import asyncpg

import pii_crypto
from database import build_dsn

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("migrate_pii")

# table -> (encrypted columns)
TARGETS = {"customers": ["phone", "email"]}


async def run() -> None:
    if not pii_crypto.pii_enabled():
        raise SystemExit("PII_ENCRYPTION_KEY is not set (or not a base64 32-byte key) — nothing to do.")
    conn = await asyncpg.connect(build_dsn())
    try:
        for table, cols in TARGETS.items():
            select_cols = ", ".join(['"id"'] + [f'"{c}"' for c in cols])
            rows = await conn.fetch(f'SELECT {select_cols} FROM "{table}"')
            changed = 0
            for r in rows:
                sets, params = [], []
                for c in cols:
                    val = r[c]
                    if val is None or (isinstance(val, str) and val.startswith(pii_crypto.PREFIX)):
                        continue  # empty or already encrypted
                    params.append(pii_crypto.encrypt(str(val)))
                    sets.append(f'"{c}" = ${len(params)}')
                    params.append(pii_crypto.blind_index(str(val)))
                    sets.append(f'"{c}_bidx" = ${len(params)}')
                if sets:
                    params.append(r["id"])
                    await conn.execute(f'UPDATE "{table}" SET {", ".join(sets)} WHERE "id" = ${len(params)}', *params)
                    changed += 1
            log.info("%s: encrypted %d/%d row(s)", table, changed, len(rows))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
