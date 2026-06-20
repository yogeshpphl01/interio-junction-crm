"""
<test-module name="test_pg_translation">
  <purpose>
    Validate the pure Mongo->SQL translation functions in database.py without a
    live PostgreSQL connection. These guard the correctness of the storage
    migration (every router relies on these translations behaving like Mongo).
  </purpose>
</test-module>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pg_schema import get_table  # noqa: E402
import database as d  # noqa: E402


LEADS = get_table("leads")
AUDIT = get_table("audit_log")
ACTIVITIES = get_table("activities")
PAYMENTS = get_table("payments")
DOCS = get_table("documents")


# <fake>Minimal stand-in for an asyncpg.Record (supports keys() + indexing).</fake>
class FakeRecord:
    def __init__(self, data: dict):
        self._d = data

    def keys(self):
        return self._d.keys()

    def __getitem__(self, k):
        return self._d[k]


# ---------- WHERE translation ----------
def test_equality():
    p = []
    assert d.build_where(LEADS, {"assigned_to": "u1"}, p) == ' WHERE "assigned_to" = $1'
    assert p == ["u1"]


def test_in_operator():
    p = []
    assert d.build_where(LEADS, {"id": {"$in": ["a", "b"]}}, p) == ' WHERE "id" = ANY($1)'
    assert p == [["a", "b"]]


def test_in_empty_matches_nothing():
    p = []
    assert d.build_where(LEADS, {"id": {"$in": []}}, p) == " WHERE FALSE"
    assert p == []


def test_ne_operator():
    p = []
    assert d.build_where(DOCS, {"is_deleted": {"$ne": True}}, p) == ' WHERE "is_deleted" IS DISTINCT FROM $1'
    assert p == [True]


def test_gte_string_timestamp():
    p = []
    assert d.build_where(LEADS, {"created_at": {"$gte": "2026-01-01"}}, p) == ' WHERE "created_at" >= $1'


def test_none_is_null():
    p = []
    assert d.build_where(LEADS, {"project_id": None}, p) == ' WHERE "project_id" IS NULL'
    assert p == []


def test_or_with_regex():
    p = []
    where = d.build_where(
        AUDIT,
        {"$or": [
            {"action": {"$regex": "x", "$options": "i"}},
            {"actor_name": {"$regex": "x", "$options": "i"}},
        ]},
        p,
    )
    assert where == ' WHERE (("action" ~* $1) OR ("actor_name" ~* $2))'
    assert p == ["x", "x"]


def test_empty_filter_no_where():
    p = []
    assert d.build_where(LEADS, {}, p) == ""


# ---------- INSERT / UPDATE ----------
def test_build_insert_splits_extra():
    sql, p = d.build_insert("leads", LEADS, {"id": "x", "full_name": "A", "weird": "z"})
    assert sql == 'INSERT INTO "leads" ("id", "full_name", "extra") VALUES ($1, $2, $3)'
    assert p == ["x", "A", {"weird": "z"}]


def test_build_update_set():
    p = []
    set_sql = d.build_update_set(LEADS, {"status": "Won", "weird": 1}, p)
    assert set_sql == '"status" = $1, "extra" = COALESCE("extra", \'{}\'::jsonb) || $2::jsonb'
    assert p == ["Won", {"weird": 1}]


# ---------- aggregation ----------
def test_aggregate_count():
    sql, p, names = d.build_aggregate(
        "activities", ACTIVITIES,
        [{"$match": {"lead_id": {"$in": ["a"]}}}, {"$group": {"_id": "$lead_id", "count": {"$sum": 1}}}],
    )
    assert sql == 'SELECT "lead_id" AS "_id", COUNT(*) AS "count" FROM "activities" WHERE "lead_id" = ANY($1) GROUP BY "lead_id"'
    assert p == [["a"]]
    assert names == ["count"]


def test_aggregate_sum_field():
    sql, p, names = d.build_aggregate(
        "payments", PAYMENTS,
        [{"$match": {"project_id": "p"}}, {"$group": {"_id": "$status", "total": {"$sum": "$amount"}}}],
    )
    assert sql == 'SELECT "status" AS "_id", COALESCE(SUM("amount"), 0) AS "total" FROM "payments" WHERE "project_id" = $1 GROUP BY "status"'
    assert names == ["total"]


# ---------- coercion ----------
def test_coerce_types():
    assert d.coerce("DOUBLE PRECISION", 5) == 5.0
    assert d.coerce("INTEGER", "3") == 3
    assert d.coerce("BOOLEAN", "true") is True
    assert d.coerce("BOOLEAN", "false") is False
    assert d.coerce("TEXT", 123) == "123"
    assert d.coerce("JSONB", {"a": 1}) == {"a": 1}
    assert d.coerce("TEXT", None) is None


# ---------- DDL ----------
def test_create_table_ddl():
    ddl = d.create_table_ddl("leads", LEADS)
    assert 'CREATE TABLE IF NOT EXISTS "leads"' in ddl
    assert '"id" TEXT PRIMARY KEY' in ddl
    assert '"extra" JSONB' in ddl
    assert '"lifecycle_phase" TEXT' in ddl  # new journey column present


def test_index_ddl():
    assert d.index_ddl_from_spec("leads", [("stage", 1)], False) == \
        'CREATE INDEX IF NOT EXISTS "ix_leads_stage" ON "leads" ("stage" ASC)'
    assert d.index_ddl_from_spec("leads", [("meta_lead_id", 1)], True) == \
        'CREATE UNIQUE INDEX IF NOT EXISTS "ix_leads_meta_lead_id_uq" ON "leads" ("meta_lead_id" ASC)'
    assert d.index_ddl_from_spec("audit_log", [("created_at", -1)], False) == \
        'CREATE INDEX IF NOT EXISTS "ix_audit_log_created_at" ON "audit_log" ("created_at" DESC)'


# ---------- row -> doc ----------
def test_row_to_doc_merges_extra_and_drops_none():
    rec = FakeRecord({"id": "x", "full_name": "A", "stage": 1, "project_id": None, "extra": {"weird": "z"}})
    doc = d.row_to_doc(LEADS, rec)
    assert doc == {"id": "x", "full_name": "A", "stage": 1, "weird": "z"}


def test_projection_inclusion_exclusion():
    doc = {"id": "x", "password_hash": "h", "full_name": "A"}
    assert d.apply_projection(doc, {"_id": 0, "password_hash": 0}) == {"id": "x", "full_name": "A"}
    assert d.apply_projection({"id": "x", "name": "A"}, {"id": 1, "_id": 0}) == {"id": "x"}


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"  ok  {fn.__name__}")
        except Exception:
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
