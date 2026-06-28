"""
<module name="routers/fixtures" layer="api">
  <purpose>
    The "Fixture" section under Booking (stage 4). Captures the fixture
    selections (hardware, lighting, appliances, plumbing…) committed for a
    project. Listing is open to anyone who can see the lead; creating/deleting
    needs the 'leads.edit' permission (sales/admin/manager by default).
  </purpose>
  <endpoints>
    GET    /api/fixtures?project_id=...  -> fixtures for a project.
    POST   /api/fixtures                 -> add a fixture.
    DELETE /api/fixtures/{id}            -> remove a fixture.
  </endpoints>
</module>
"""
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import db, get_current_user, ensure_lead_visible, has_permission, now_iso
from audit import log_audit

router = APIRouter()


class FixtureInput(BaseModel):
    project_id: str
    name: str
    category: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    quantity: Optional[int] = 1
    unit: Optional[str] = None
    notes: Optional[str] = None


async def _lead_for_project(project_id: str) -> Optional[dict]:
    return await db.leads.find_one({"project_id": project_id}, {"_id": 0})


@router.get("/fixtures")
async def list_fixtures(project_id: str, user: dict = Depends(get_current_user)):
    lead = await _lead_for_project(project_id)
    if lead:
        await ensure_lead_visible(user, lead)
    return await db.fixtures.find({"project_id": project_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)


@router.post("/fixtures")
async def create_fixture(payload: FixtureInput, user: dict = Depends(get_current_user)):
    if not has_permission(user, "leads.edit"):
        raise HTTPException(status_code=403, detail="You don't have permission to manage fixtures")
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Fixture name is required")
    proj = await db.projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    lead = await _lead_for_project(payload.project_id)
    if lead:
        await ensure_lead_visible(user, lead)
    doc = {
        "id": str(uuid.uuid4()),
        "project_id": payload.project_id,
        "lead_id": lead["id"] if lead else None,
        "name": payload.name.strip(),
        "category": payload.category,
        "brand": payload.brand,
        "model": payload.model,
        "quantity": payload.quantity if payload.quantity and payload.quantity > 0 else 1,
        "unit": payload.unit,
        "notes": payload.notes,
        "created_by": user["id"],
        "created_at": now_iso(),
    }
    await db.fixtures.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(db, user, "fixture.created", "fixture", doc["id"], doc["name"], {"project_id": payload.project_id})
    return doc


@router.delete("/fixtures/{fixture_id}")
async def delete_fixture(fixture_id: str, user: dict = Depends(get_current_user)):
    if not has_permission(user, "leads.edit"):
        raise HTTPException(status_code=403, detail="You don't have permission to manage fixtures")
    fx = await db.fixtures.find_one({"id": fixture_id}, {"_id": 0})
    if not fx:
        raise HTTPException(status_code=404, detail="Fixture not found")
    lead = await _lead_for_project(fx.get("project_id"))
    if lead:
        await ensure_lead_visible(user, lead)
    await db.fixtures.delete_one({"id": fixture_id})
    await log_audit(db, user, "fixture.deleted", "fixture", fixture_id, fx.get("name"), {"project_id": fx.get("project_id")})
    return {"ok": True}
