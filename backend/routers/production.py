"""
<module name="routers/production" layer="api">
  <purpose>
    Production tracking (mobile ecosystem, P0). Parts + QR are produced in
    **Infurnia** (see docs/mobile-apps §14) — we INGEST them and track each
    part's journey by scanning its Infurnia-printed QR at our stations
    (QC -> assembly -> packing -> dispatch -> site unload -> install). Ingestion
    and scanning need 'production.manage' (Production Engineer). Reads are allowed
    to production managers or to anyone who can see the project.
  </purpose>
  <endpoints>
    POST /api/cutlists                          -> ingest an Infurnia cut list (creates parts + qr).
    GET  /api/projects/{id}/parts               -> parts for a project (optional ?status=).
    GET  /api/parts/{part_uid}                  -> one part + its full scan history.
    POST /api/parts/scan                        -> record a scan; advance the part's stage (idempotent).
    GET  /api/projects/{id}/production-summary  -> counts by stage (drives reconciliation).
  </endpoints>
</module>
"""
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, get_current_user, has_permission, require_permission, ensure_project_visible, now_iso
from audit import log_audit

router = APIRouter()

# Journey stages a part moves through (our tracking; Infurnia owns cutting/drilling).
PART_STAGES = [
    "ingested", "in_production", "qc", "rework", "assembly",
    "packed", "loaded", "dispatched", "unloaded", "installed", "ticketed",
]


class PartRowIn(BaseModel):
    part_uid: str                       # Infurnia's panel/part id (matches its printed QR)
    name: Optional[str] = None
    material: Optional[str] = None
    dimensions: Optional[str] = None
    quantity: int = 1
    qr_value: Optional[str] = None      # decoded value of the Infurnia QR (for scan matching)


class CutlistIngestIn(BaseModel):
    project_id: str
    source: str = "infurnia"
    infurnia_ref: Optional[str] = None
    pdf_ref: Optional[str] = None
    parts: list[PartRowIn] = []


class ScanIn(BaseModel):
    part_uid: Optional[str] = None      # scan by part id …
    qr_value: Optional[str] = None      # … or by the raw decoded QR value
    station: str
    to_stage: str
    result: Optional[str] = "pass"
    note: Optional[str] = None
    photo_ref: Optional[str] = None
    device_id: Optional[str] = None


async def _read_guard(user: dict, project_id: str) -> None:
    """Production managers see any project; everyone else must have project access."""
    if has_permission(user, "production.manage"):
        return
    await ensure_project_visible(user, project_id)


@router.post("/cutlists")
async def ingest_cutlist(payload: CutlistIngestIn, user: dict = Depends(require_permission("production.manage"))):
    """Ingest an Infurnia cut list: create the cutlist record + one part (with its
    QR value) per row. Idempotent on `part_uid` — re-ingesting skips existing parts
    rather than duplicating them."""
    proj = await db.projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    if not payload.parts:
        raise HTTPException(status_code=400, detail="Cut list has no parts")
    ts = now_iso()
    cutlist = {
        "id": str(uuid.uuid4()),
        "project_id": payload.project_id,
        "pdf_ref": payload.pdf_ref,
        "source": payload.source,
        "infurnia_ref": payload.infurnia_ref,
        "created_by": user["id"],
        "part_count": len(payload.parts),
        "created_at": ts,
    }
    await db.cutlists.insert_one(cutlist)
    created, skipped = 0, 0
    for row in payload.parts:
        puid = (row.part_uid or "").strip()
        if not puid:
            skipped += 1
            continue
        if await db.parts.find_one({"part_uid": puid}):
            skipped += 1                # part_uid is unique — idempotent re-ingest
            continue
        part_id = str(uuid.uuid4())
        await db.parts.insert_one({
            "id": part_id, "cutlist_id": cutlist["id"], "project_id": payload.project_id,
            "part_uid": puid, "source": payload.source, "infurnia_ref": row.qr_value or payload.infurnia_ref,
            "name": row.name, "material": row.material, "dimensions": row.dimensions,
            "quantity": row.quantity or 1, "status": "ingested", "current_station": None,
            "created_at": ts, "updated_at": ts,
        })
        await db.qr_codes.insert_one({
            "id": str(uuid.uuid4()), "part_id": part_id, "part_uid": puid,
            "qr_value": (row.qr_value or puid), "label_ref": payload.pdf_ref, "created_at": ts,
        })
        created += 1
    await log_audit(db, user, "cutlist.ingested", "cutlist", cutlist["id"], payload.infurnia_ref,
                    {"project_id": payload.project_id, "created": created, "skipped": skipped, "source": payload.source})
    return {"cutlist_id": cutlist["id"], "created": created, "skipped": skipped, "part_count": len(payload.parts)}


@router.get("/projects/{project_id}/parts")
async def list_parts(project_id: str, user: dict = Depends(get_current_user), status: Optional[str] = None):
    await _read_guard(user, project_id)
    filt: dict = {"project_id": project_id}
    if status:
        filt["status"] = status
    return await db.parts.find(filt, {"_id": 0}).sort("part_uid", 1).to_list(10000)


@router.get("/parts/{part_uid}")
async def part_detail(part_uid: str, user: dict = Depends(get_current_user)):
    part = await db.parts.find_one({"part_uid": part_uid}, {"_id": 0})
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    await _read_guard(user, part["project_id"])
    scans = await db.part_scans.find({"part_uid": part_uid}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    return {**part, "scans": scans}


@router.post("/parts/scan")
async def scan_part(payload: ScanIn, user: dict = Depends(require_permission("production.manage"))):
    """Record a scan of an Infurnia QR at a station and advance the part's stage.
    Idempotent per (part, station, stage) so a double-scan doesn't double-advance."""
    key = (payload.part_uid or payload.qr_value or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Provide part_uid or qr_value")
    if payload.to_stage not in PART_STAGES:
        raise HTTPException(status_code=400, detail=f"Unknown stage '{payload.to_stage}'")
    # Match the scanned code to an ingested part (by id, else by the QR value).
    part = await db.parts.find_one({"part_uid": key}, {"_id": 0})
    if not part:
        qr = await db.qr_codes.find_one({"qr_value": key}, {"_id": 0})
        if qr:
            part = await db.parts.find_one({"part_uid": qr["part_uid"]}, {"_id": 0})
    if not part:
        raise HTTPException(status_code=404, detail="No ingested part matches this code — import the Infurnia cut list first")

    dup = await db.part_scans.find_one(
        {"part_id": part["id"], "station": payload.station, "to_stage": payload.to_stage}, {"_id": 0})
    if dup:
        return {"idempotent": True, "scan": dup, "part_status": part["status"]}

    ts = now_iso()
    scan = {
        "id": str(uuid.uuid4()), "part_id": part["id"], "part_uid": part["part_uid"],
        "project_id": part["project_id"], "station": payload.station,
        "from_stage": part.get("status"), "to_stage": payload.to_stage,
        "scanned_by": user["id"], "device_id": payload.device_id, "result": payload.result or "pass",
        "note": payload.note, "photo_ref": payload.photo_ref, "gps": None, "created_at": ts,
    }
    await db.part_scans.insert_one(scan)
    await db.parts.update_one({"id": part["id"]},
                              {"$set": {"status": payload.to_stage, "current_station": payload.station, "updated_at": ts}})
    scan.pop("_id", None)
    await log_audit(db, user, "part.scanned", "part", part["part_uid"], part.get("name"),
                    {"project_id": part["project_id"], "station": payload.station, "to_stage": payload.to_stage,
                     "result": scan["result"]})
    return {"idempotent": False, "scan": scan, "part_status": payload.to_stage}


@router.get("/projects/{project_id}/production-summary")
async def production_summary(project_id: str, user: dict = Depends(get_current_user)):
    """Part counts by stage — the basis for the load/unload reconciliation (§18)."""
    await _read_guard(user, project_id)
    parts = await db.parts.find({"project_id": project_id}, {"_id": 0}).to_list(20000)
    by_status: dict = {}
    for p in parts:
        by_status[p.get("status") or "unknown"] = by_status.get(p.get("status") or "unknown", 0) + 1
    return {"project_id": project_id, "total_parts": len(parts), "by_status": by_status}
