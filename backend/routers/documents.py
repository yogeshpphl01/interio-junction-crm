"""
<module name="routers/documents" layer="api">
  <purpose>Upload + download project documents. Metadata rows go to the documents
  table; the file bytes go to object storage (storage.py). Role rules limit which
  document types designers vs supervisors may upload; downloads are access-checked
  against lead visibility and audit-logged.</purpose>
  <endpoints>
    POST /api/documents                 -> multipart upload (max 25MB).
    GET  /api/documents/{doc_id}/download -> stream the file back.
  </endpoints>
</module>
"""
import io
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from core import (
    db, get_current_user, ensure_project_visible, ensure_lead_visible, has_permission,
    DOC_TYPES, now_iso,
    ROLE_DESIGNER, ROLE_SUPERVISOR,
)
from storage import put_object, get_object, APP_NAME
from audit import log_audit

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/documents")
async def upload_document(
    project_id: str = Form(...),
    type: str = Form(...),
    linked_measurement_id: Optional[str] = Form(None),
    linked_revision_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    await ensure_project_visible(user, project_id)
    if not has_permission(user, "documents.upload"):
        raise HTTPException(status_code=403, detail="You don't have permission to upload documents")
    if user["role"] == ROLE_DESIGNER and type not in ("2D CAD", "3D Render", "Quotation PDF", "Other"):
        raise HTTPException(status_code=403, detail="Designers can upload only design files")
    if user["role"] == ROLE_SUPERVISOR and type not in ("Site Measurement Sheet", "Site Photo", "Other"):
        raise HTTPException(status_code=403, detail="Supervisors can upload only site files")
    if type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail="Invalid document type")

    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 25MB)")
    ext = (file.filename or "file").split(".")[-1] if "." in (file.filename or "") else "bin"
    path = f"{APP_NAME}/projects/{project_id}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, content, file.content_type or "application/octet-stream")
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
    doc = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "type": type,
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": result.get("size", len(content)),
        "uploaded_by": user["id"],
        "linked_measurement_id": linked_measurement_id,
        "linked_revision_id": linked_revision_id,
        "is_deleted": False,
        "created_at": now_iso(),
    }
    await db.documents.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(
        db, user, "document.uploaded", "document", doc["id"], file.filename,
        {"project_id": project_id, "type": type, "size": doc["size"], "content_type": file.content_type},
    )
    return doc


@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, request: Request, user: dict = Depends(get_current_user)):
    rec = await db.documents.find_one({"id": doc_id, "is_deleted": {"$ne": True}}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    lead = await db.leads.find_one({"project_id": rec["project_id"]}, {"_id": 0})
    if lead:
        await ensure_lead_visible(user, lead)
    try:
        data, _ct = get_object(rec["storage_path"])
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise HTTPException(status_code=500, detail="Download failed")
    await log_audit(
        db, user, "document.downloaded", "document", doc_id, rec.get("original_filename"),
        {"project_id": rec.get("project_id"), "type": rec.get("type")}, request,
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type=rec.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{rec.get("original_filename","file")}"'},
    )
