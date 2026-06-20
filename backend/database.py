"""
<module name="database" layer="persistence">
  <purpose>
    A thin, MongoDB-compatible async data layer backed by PostgreSQL (asyncpg).
    It exposes the SAME surface the routers already use:

        db.leads.find_one({...}, {"_id": 0})
        db.leads.find({...}, {...}).sort("updated_at", -1).to_list(2000)
        db.leads.insert_one({...})
        db.leads.update_one({"id": x}, {"$set": {...}}, upsert=True)
        db.activities.aggregate([{"$match": ...}, {"$group": ...}])
        db.audit_log.distinct("action")
        db.leads.create_index("stage")

    so the 14 routers, core.py and seed_data.py keep working UNCHANGED while the
    data physically lives in your Hostinger PostgreSQL database.
  </purpose>

  <design>
    Each Mongo "collection" is a PostgreSQL table (see pg_schema.py). Declared
    fields become typed columns; anything else overflows into a JSONB `extra`
    column. The Mongo query/update/aggregate dialect the app actually uses is a
    small, fixed subset ($in, $ne, $gte, $lte, $regex/$options, $or, $set, and
    $match/$group/$sum), which this module translates to SQL.
  </design>

  <testability>
    Every SQL string is produced by a PURE function (build_where, build_insert,
    build_update, build_aggregate, row_to_doc, ...). These need no live
    connection and are covered by tests/test_pg_translation.py.
  </testability>
</module>
"""
from __future__ import annotations

import os
import json
import logging
from urllib.parse import quote
from typing import Any, Optional

import asyncpg

from pg_schema import SCHEMA, get_table, EXTRA_COLUMN

logger = logging.getLogger(__name__)


# ============================================================================
# <section name="Pure helpers — value coercion & identifier quoting">
#   <why>
#     The app stores Python-native values; PostgreSQL/asyncpg are strict about
#     types. These helpers make writes robust (especially for the Excel importer)
#     without changing any router code.
#   </why>
# ============================================================================
def _q(ident: str) -> str:
    """Quote a SQL identifier safely (column/table name)."""
    return '"' + ident.replace('"', '""') + '"'


def _base_type(sql_type: str) -> str:
    """Normalise 'DOUBLE PRECISION' / 'TEXT' / 'JSONB' to an upper base token."""
    return sql_type.strip().upper()


def coerce(sql_type: str, value: Any) -> Any:
    """
    <function name="coerce">
      Convert a Python value to something asyncpg will accept for the given SQL
      column type. None passes through as SQL NULL. JSONB values are handed over
      as-is (a registered codec encodes dict/list -> json).
    </function>
    """
    if value is None:
        return None
    t = _base_type(sql_type)
    try:
        if t == "JSONB":
            return value
        if t == "BOOLEAN":
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            return str(value).strip().lower() in ("true", "1", "yes", "y", "t")
        if t in ("INTEGER", "BIGINT", "SMALLINT"):
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            return int(float(str(value).strip()))
        if t in ("DOUBLE PRECISION", "REAL", "NUMERIC"):
            return float(value)
        if t == "TEXT":
            return value if isinstance(value, str) else str(value)
    except (ValueError, TypeError):
        # If a value can't be coerced cleanly, keep the original and let the DB
        # raise a clear error rather than silently corrupting it.
        return value
    return value


def _ph(params: list, value: Any) -> str:
    """Append a parameter and return its positional placeholder ($1, $2, ...)."""
    params.append(value)
    return f"${len(params)}"


def _colref(table: dict, key: str) -> tuple[str, str]:
    """
    Resolve a Mongo field name to a SQL reference.
    Returns (sql_reference, sql_type). Declared fields map to a real quoted
    column; everything else reads out of the JSONB `extra` column as text.
    """
    cols = table["columns"]
    if key in cols:
        return _q(key), cols[key]
    return f"{_q(EXTRA_COLUMN)} ->> '{key}'", "TEXT"


# ============================================================================
# <section name="Pure helpers — WHERE clause translation">
#   <supported-operators>$in, $ne, $gte, $lte, $gt, $lt, $regex (+$options), $or,
#   and plain equality / IS NULL.</supported-operators>
# ============================================================================
def _condition(table: dict, key: str, cond: Any, params: list) -> str:
    """Translate a single {field: condition} pair into a SQL boolean fragment."""
    if key == "$or":
        # cond is a list of sub-filters; OR their AND-groups together.
        ors = [f"({build_where_inline(table, sub, params)})" for sub in cond]
        ors = [o for o in ors if o != "()"]
        return "(" + " OR ".join(ors) + ")" if ors else "TRUE"

    ref, sql_type = _colref(table, key)

    # Operator object, e.g. {"$gte": "..."} or {"$regex": "x", "$options": "i"}.
    if isinstance(cond, dict) and any(str(k).startswith("$") for k in cond):
        frags: list[str] = []
        for op, val in cond.items():
            if op == "$options":
                continue  # consumed alongside $regex
            if op == "$in":
                items = list(val)
                if not items:
                    frags.append("FALSE")  # Mongo: $in [] matches nothing
                else:
                    frags.append(f"{ref} = ANY({_ph(params, [coerce(sql_type, v) for v in items])})")
            elif op == "$ne":
                frags.append(f"{ref} IS DISTINCT FROM {_ph(params, coerce(sql_type, val))}")
            elif op == "$gte":
                frags.append(f"{ref} >= {_ph(params, coerce(sql_type, val))}")
            elif op == "$lte":
                frags.append(f"{ref} <= {_ph(params, coerce(sql_type, val))}")
            elif op == "$gt":
                frags.append(f"{ref} > {_ph(params, coerce(sql_type, val))}")
            elif op == "$lt":
                frags.append(f"{ref} < {_ph(params, coerce(sql_type, val))}")
            elif op == "$regex":
                flags = cond.get("$options", "")
                sql_op = "~*" if "i" in flags else "~"
                frags.append(f"{ref} {sql_op} {_ph(params, str(val))}")
            else:
                logger.warning("Unsupported query operator ignored: %s", op)
        return " AND ".join(frags) if frags else "TRUE"

    # Plain equality / NULL check.
    if cond is None:
        return f"{ref} IS NULL"
    return f"{ref} = {_ph(params, coerce(sql_type, cond))}"


def build_where_inline(table: dict, filt: dict, params: list) -> str:
    """Build the AND-joined body of a WHERE clause (no leading 'WHERE')."""
    if not filt:
        return "TRUE"
    parts = [_condition(table, k, v, params) for k, v in filt.items()]
    parts = [p for p in parts if p]
    return " AND ".join(parts) if parts else "TRUE"


def build_where(table: dict, filt: Optional[dict], params: list) -> str:
    """Build a full ' WHERE ...' clause (empty string when there is no filter)."""
    body = build_where_inline(table, filt or {}, params)
    return "" if body == "TRUE" else f" WHERE {body}"


# ============================================================================
# <section name="Pure helpers — INSERT / UPDATE / aggregate / DDL">
# ============================================================================
def _split_doc(table: dict, doc: dict) -> tuple[dict, dict]:
    """Partition a document into {declared columns} and {overflow -> extra}."""
    cols = table["columns"]
    declared, extra = {}, {}
    for k, v in doc.items():
        if k == "_id":
            continue
        if k in cols:
            declared[k] = coerce(cols[k], v)
        else:
            extra[k] = v
    return declared, extra


def build_insert(name: str, table: dict, doc: dict) -> tuple[str, list]:
    """Produce an INSERT statement + ordered params for one document."""
    declared, extra = _split_doc(table, doc)
    params: list = []
    cols: list[str] = []
    placeholders: list[str] = []
    for k, v in declared.items():
        cols.append(_q(k))
        placeholders.append(_ph(params, v))
    if extra:
        cols.append(_q(EXTRA_COLUMN))
        placeholders.append(_ph(params, extra))
    sql = f'INSERT INTO {_q(name)} ({", ".join(cols)}) VALUES ({", ".join(placeholders)})'
    return sql, params


def build_update_set(table: dict, set_doc: dict, params: list) -> str:
    """Produce the 'SET ...' body for an UPDATE, appending params as it goes."""
    declared, extra = _split_doc(table, set_doc)
    parts = [f"{_q(k)} = {_ph(params, v)}" for k, v in declared.items()]
    if extra:
        parts.append(
            f"{_q(EXTRA_COLUMN)} = COALESCE({_q(EXTRA_COLUMN)}, '{{}}'::jsonb) || {_ph(params, extra)}::jsonb"
        )
    return ", ".join(parts)


def build_aggregate(name: str, table: dict, pipeline: list[dict]) -> tuple[str, list, list[str]]:
    """
    <function name="build_aggregate">
      Translate the small set of aggregation pipelines the app uses
      ([$match?] + $group with $sum) into a GROUP BY query.
      Returns (sql, params, [aggregate_output_field_names]).
    </function>
    """
    match = next((s["$match"] for s in pipeline if "$match" in s), None)
    group = next((s["$group"] for s in pipeline if "$group" in s), None)
    if group is None:
        raise ValueError("Only $group aggregations are supported")

    params: list = []
    where = build_where(table, match, params)

    gid = group["_id"]
    group_col = _colref(table, gid[1:])[0] if isinstance(gid, str) and gid.startswith("$") else "NULL"

    selects = [f'{group_col} AS "_id"']
    agg_names: list[str] = []
    for field, expr in group.items():
        if field == "_id":
            continue
        agg_names.append(field)
        if isinstance(expr, dict) and "$sum" in expr:
            operand = expr["$sum"]
            if isinstance(operand, str) and operand.startswith("$"):
                selects.append(f'COALESCE(SUM({_colref(table, operand[1:])[0]}), 0) AS {_q(field)}')
            else:
                selects.append(f'COUNT(*) AS {_q(field)}')
        else:
            raise ValueError(f"Unsupported aggregation expression: {expr}")

    sql = f'SELECT {", ".join(selects)} FROM {_q(name)}{where} GROUP BY {group_col}'
    return sql, params, agg_names


def row_to_doc(table: dict, record: "asyncpg.Record", projection: Optional[dict] = None) -> dict:
    """
    Rebuild a Mongo-style document from a DB row: real columns + merged `extra`.
    None-valued columns are omitted so the shape matches sparse Mongo documents.
    """
    doc: dict = {}
    for col in table["columns"]:
        if col in record.keys():
            v = record[col]
            if v is not None:
                doc[col] = v
    extra = record["extra"] if "extra" in record.keys() else None
    if extra:
        doc.update(extra if isinstance(extra, dict) else json.loads(extra))
    return apply_projection(doc, projection)


def apply_projection(doc: dict, projection: Optional[dict]) -> dict:
    """Mongo-style field projection. Supports inclusion {f:1} and exclusion {f:0}."""
    if not projection:
        return doc
    inc = {k for k, v in projection.items() if v == 1 and k != "_id"}
    exc = {k for k, v in projection.items() if v == 0 and k != "_id"}
    if inc:
        return {k: doc[k] for k in inc if k in doc}
    if exc:
        return {k: v for k, v in doc.items() if k not in exc}
    return doc


def create_table_ddl(name: str, table: dict) -> str:
    """CREATE TABLE IF NOT EXISTS for one collection (+ the JSONB overflow column)."""
    pk = table.get("pk")
    parts = []
    for col, sql_type in table["columns"].items():
        line = f"{_q(col)} {sql_type}"
        if col == pk:
            line += " PRIMARY KEY"
        parts.append(line)
    parts.append(f"{_q(EXTRA_COLUMN)} JSONB DEFAULT '{{}}'::jsonb")
    return f"CREATE TABLE IF NOT EXISTS {_q(name)} (\n  " + ",\n  ".join(parts) + "\n)"


def _index_name(name: str, cols: list[tuple[str, int]], unique: bool) -> str:
    suffix = "_".join(c for c, _ in cols)
    return f"ix_{name}_{suffix}{'_uq' if unique else ''}"


def index_ddl_from_spec(name: str, cols: list[tuple[str, int]], unique: bool) -> str:
    """Build a CREATE INDEX statement from a [(col, direction)] spec."""
    cols_sql = ", ".join(f"{_q(c)} {'DESC' if d == -1 else 'ASC'}" for c, d in cols)
    uq = "UNIQUE " if unique else ""
    idx = _index_name(name, cols, unique)
    return f"CREATE {uq}INDEX IF NOT EXISTS {_q(idx)} ON {_q(name)} ({cols_sql})"


def normalize_index_keys(keys) -> list[tuple[str, int]]:
    """Accept Motor-style index keys: 'email' or [('project_id',1),('rev',1)]."""
    if isinstance(keys, str):
        return [(keys, 1)]
    return [(k, d) for k, d in keys]


# ============================================================================
# <section name="DSN construction">
#   <accepts>
#     Either a single DATABASE_URL, or discrete PG_HOST / PG_PORT / PG_DB /
#     PG_USER / PG_PASSWORD / PG_SSLMODE environment variables.
#   </accepts>
# ============================================================================
def build_dsn() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    host = os.environ.get("PG_HOST", "localhost")
    port = os.environ.get("PG_PORT", "5432")
    db = os.environ.get("PG_DB") or os.environ.get("PG_DATABASE") or os.environ.get("PG_NAME", "postgres")
    user = os.environ.get("PG_USER", "postgres")
    password = os.environ.get("PG_PASSWORD", "")
    sslmode = os.environ.get("PG_SSLMODE", "require")
    auth = f"{quote(user)}:{quote(password)}@" if user else ""
    return f"postgresql://{auth}{host}:{port}/{db}?sslmode={sslmode}"


async def _init_connection(conn: "asyncpg.Connection") -> None:
    """Register JSON/JSONB codecs so dict/list round-trip as native Python."""
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


# ============================================================================
# <section name="Cursor — chainable find() result">
# ============================================================================
class Cursor:
    """
    <class name="Cursor">
      Mimics a Motor cursor: chainable .sort()/.skip()/.limit(), awaitable
      .to_list(n), and async iteration (async for doc in cursor).
    </class>
    """

    def __init__(self, collection: "Collection", filt: dict, projection: Optional[dict]):
        self._c = collection
        self._filt = filt or {}
        self._projection = projection
        self._sort: list[tuple[str, int]] = []
        self._skip = 0
        self._limit: Optional[int] = None

    def sort(self, key: str, direction: int = 1) -> "Cursor":
        self._sort.append((key, direction))
        return self

    def skip(self, n: int) -> "Cursor":
        self._skip = int(n or 0)
        return self

    def limit(self, n: int) -> "Cursor":
        self._limit = int(n)
        return self

    def _build(self, length: Optional[int]) -> tuple[str, list]:
        table = self._c.table
        params: list = []
        where = build_where(table, self._filt, params)
        order = ""
        if self._sort:
            order = " ORDER BY " + ", ".join(
                f"{_colref(table, k)[0]} {'DESC' if d == -1 else 'ASC'}" for k, d in self._sort
            )
        offset = f" OFFSET {int(self._skip)}" if self._skip else ""
        caps = [x for x in (self._limit, length) if x is not None]
        limit = f" LIMIT {min(caps)}" if caps else ""
        sql = f"SELECT * FROM {_q(self._c.name)}{where}{order}{offset}{limit}"
        return sql, params

    async def to_list(self, length: Optional[int] = None) -> list[dict]:
        sql, params = self._build(length)
        rows = await self._c._fetch(sql, params)
        return [row_to_doc(self._c.table, r, self._projection) for r in rows]

    async def __aiter__(self):
        sql, params = self._build(None)
        rows = await self._c._fetch(sql, params)
        for r in rows:
            yield row_to_doc(self._c.table, r, self._projection)


# ============================================================================
# <section name="AggregateCursor — result of aggregate()">
# ============================================================================
class AggregateCursor:
    def __init__(self, collection: "Collection", pipeline: list[dict]):
        self._c = collection
        self._pipeline = pipeline

    async def _run(self) -> list[dict]:
        sql, params, agg_names = build_aggregate(self._c.name, self._c.table, self._pipeline)
        rows = await self._c._fetch(sql, params)
        out = []
        for r in rows:
            d = {"_id": r["_id"]}
            for n in agg_names:
                d[n] = r[n]
            out.append(d)
        return out

    async def to_list(self, length: Optional[int] = None) -> list[dict]:
        return await self._run()

    async def __aiter__(self):
        for row in await self._run():
            yield row


# ============================================================================
# <section name="Result objects (Motor parity)">
# ============================================================================
class _InsertOneResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class _UpdateResult:
    def __init__(self, matched, modified, upserted_id=None):
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_id = upserted_id


# ============================================================================
# <section name="Collection — the per-table API surface">
# ============================================================================
class Collection:
    def __init__(self, db: "PostgresDatabase", name: str):
        self.db = db
        self.name = name
        self.table = get_table(name)

    # <method>Low-level fetch helper used by cursors + reads.</method>
    async def _fetch(self, sql: str, params: list):
        async with self.db.pool.acquire() as conn:
            return await conn.fetch(sql, *params)

    async def find_one(self, filt: Optional[dict] = None, projection: Optional[dict] = None) -> Optional[dict]:
        params: list = []
        where = build_where(self.table, filt or {}, params)
        sql = f"SELECT * FROM {_q(self.name)}{where} LIMIT 1"
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)
        return row_to_doc(self.table, row, projection) if row else None

    def find(self, filt: Optional[dict] = None, projection: Optional[dict] = None) -> Cursor:
        return Cursor(self, filt or {}, projection)

    async def insert_one(self, doc: dict) -> _InsertOneResult:
        sql, params = build_insert(self.name, self.table, doc)
        async with self.db.pool.acquire() as conn:
            await conn.execute(sql, *params)
        return _InsertOneResult(doc.get("id") or doc.get(self.table.get("pk")))

    async def update_one(self, filt: dict, update: dict, upsert: bool = False) -> _UpdateResult:
        set_doc = update.get("$set", {})
        params: list = []
        set_sql = build_update_set(self.table, set_doc, params)
        where = build_where(self.table, filt, params)
        sql = f"UPDATE {_q(self.name)} SET {set_sql}{where}"
        async with self.db.pool.acquire() as conn:
            status = await conn.execute(sql, *params)
        matched = int(status.split()[-1]) if status else 0
        if matched == 0 and upsert:
            # Merge the equality parts of the filter with $set into a new row.
            merged = {k: v for k, v in filt.items() if not isinstance(v, dict)}
            merged.update(set_doc)
            await self.insert_one(merged)
            return _UpdateResult(0, 0, upserted_id=merged.get(self.table.get("pk")))
        return _UpdateResult(matched, matched)

    async def count_documents(self, filt: Optional[dict] = None) -> int:
        params: list = []
        where = build_where(self.table, filt or {}, params)
        sql = f"SELECT COUNT(*) AS n FROM {_q(self.name)}{where}"
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)
        return int(row["n"]) if row else 0

    def aggregate(self, pipeline: list[dict]) -> AggregateCursor:
        return AggregateCursor(self, pipeline)

    async def distinct(self, field: str) -> list:
        ref = _colref(self.table, field)[0]
        sql = f"SELECT DISTINCT {ref} AS v FROM {_q(self.name)} WHERE {ref} IS NOT NULL"
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(sql)
        return [r["v"] for r in rows]

    async def delete_one(self, filt: dict) -> int:
        params: list = []
        where = build_where(self.table, filt, params)
        sql = (
            f"DELETE FROM {_q(self.name)} WHERE ctid IN "
            f"(SELECT ctid FROM {_q(self.name)}{where} LIMIT 1)"
        )
        async with self.db.pool.acquire() as conn:
            status = await conn.execute(sql, *params)
        return int(status.split()[-1]) if status else 0

    async def create_index(self, keys, unique: bool = False, **_kwargs) -> None:
        cols = normalize_index_keys(keys)
        sql = index_ddl_from_spec(self.name, cols, unique)
        async with self.db.pool.acquire() as conn:
            await conn.execute(sql)


# ============================================================================
# <section name="PostgresDatabase — the db handle (drop-in for a Motor db)">
# ============================================================================
class PostgresDatabase:
    """
    <class name="PostgresDatabase">
      Replaces the Motor database object. `db.<collection>` returns a Collection.
      Lifecycle: build (from_env) -> await connect() -> await create_all() at
      startup; await close() at shutdown.
    </class>
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None
        self._collections: dict[str, Collection] = {}

    @classmethod
    def from_env(cls) -> "PostgresDatabase":
        return cls(build_dsn())

    async def connect(self) -> None:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                dsn=self.dsn,
                min_size=1,
                max_size=int(os.environ.get("PG_POOL_MAX", "10")),
                init=_init_connection,
                command_timeout=60,
            )
            logger.info("PostgreSQL pool established")

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def create_all(self) -> None:
        """Create every table + declared index if they do not already exist."""
        async with self.pool.acquire() as conn:
            for name, table in SCHEMA.items():
                await conn.execute(create_table_ddl(name, table))
                for spec in table.get("indexes", []):
                    await conn.execute(
                        index_ddl_from_spec(name, normalize_index_keys(spec["cols"]), spec.get("unique", False))
                    )
        logger.info("PostgreSQL schema ensured (%d tables)", len(SCHEMA))

    def __getattr__(self, name: str) -> Collection:
        # Only reached for names that are not real attributes (i.e. collections).
        if name.startswith("_"):
            raise AttributeError(name)
        cache = self.__dict__.setdefault("_collections", {})
        if name not in cache:
            cache[name] = Collection(self, name)
        return cache[name]
