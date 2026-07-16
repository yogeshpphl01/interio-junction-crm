"""
<module name="routers/audit_routes" layer="api">
  <purpose>Admin-only read access to the append-only audit log (written by
  audit.log_audit across the app).</purpose>
  <endpoints>
    GET /api/audit          -> filtered + paginated rows (action/actor/target/q).
    GET /api/audit/actions  -> distinct action names (for the filter dropdown).
  </endpoints>
</module>
"""
from typing import Optional, Any
from fastapi import APIRouter, Depends
from core import db, require_permission, ROLE_CEO, ROLE_ADMIN
from audit import verify_audit_chain

router = APIRouter()


@router.get("/audit/verify-chain")
async def verify_chain(user: dict = Depends(require_permission("audit.view"))):
    """Tamper-evidence: re-derive the audit hash chain and report the first break
    (a deleted or edited entry). AU-9."""
    return await verify_audit_chain(db)


@router.get("/audit")
async def list_audit(
    user: dict = Depends(require_permission("audit.view")),
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    filt: dict[str, Any] = {}
    if action:
        filt["action"] = action
    if actor_id:
        filt["actor_id"] = actor_id
    if target_type:
        filt["target_type"] = target_type
    if target_id:
        filt["target_id"] = target_id
    if q:
        filt["$or"] = [
            {"actor_name": {"$regex": q, "$options": "i"}},
            {"actor_email": {"$regex": q, "$options": "i"}},
            {"target_label": {"$regex": q, "$options": "i"}},
            {"action": {"$regex": q, "$options": "i"}},
        ]
    total = await db.audit_log.count_documents(filt)
    rows = await db.audit_log.find(filt, {"_id": 0}).sort("created_at", -1).skip(offset).limit(min(limit, 500)).to_list(500)
    return {"total": total, "limit": limit, "offset": offset, "rows": rows}


@router.get("/audit/actions")
async def list_audit_actions(user: dict = Depends(require_permission("audit.view"))):
    rows = await db.audit_log.distinct("action")
    return {"actions": sorted(rows)}
