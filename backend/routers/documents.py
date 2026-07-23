"""
<module name="routers/documents" layer="api">
  <purpose>Upload + download project documents. Metadata rows go to the documents
  table; the file bytes go to object storage (storage.py). Uploads are validated
  by their ACTUAL bytes (file_validation) — never the client-declared type — and
  the safe content-type we derive is what we persist and serve. Downloads are
  available two ways: an access-checked, session-authenticated stream, and a
  short-lived SIGNED URL (a capability token) that the mobile apps can load
  directly (P1-10).</purpose>
  <endpoints>
    POST /api/documents                    -> multipart upload (validated, max 25MB).
    GET  /api/documents/{doc_id}/download    -> session-auth stream.
    GET  /api/documents/{doc_id}/signed-url  -> mint a short-lived signed download URL.
    GET  /api/documents/download?token=...   -> redeem a signed URL (no session).
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
from auth_utils import create_doc_download_token, decode_token, DOC_URL_TTL_MIN
from file_validation import validate_upload, safe_filename
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
    if user["role"] == ROLE_DESIGNER and type not in (
        "2D CAD", "3D Render", "Design File", "Quotation PDF", "Cutlist", "BOQ", "BOM", "Other",
    ):
        raise HTTPException(status_code=403, detail="Designers can upload only design files")
    if user["role"] == ROLE_SUPERVISOR and type not in ("Site Measurement Sheet", "Site Photo", "Other"):
        raise HTTPException(status_code=403, detail="Supervisors can upload only site files")
    if type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail="Invalid document type")

    content = await file.read()
    # Validate by the ACTUAL bytes and derive a SAFE content-type + extension —
    # the client-declared type/extension are never trusted (CWE-434 / CWE-79).
    safe_ct, ext = validate_upload(file.filename, file.content_type, content)
    clean_name = safe_filename(file.filename)
    path = f"{APP_NAME}/projects/{project_id}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, content, safe_ct)
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
    doc = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "type": type,
        "storage_path": result["path"],
        "original_filename": clean_name,
        "content_type": safe_ct,           # store the derived-safe type, not the uploader's
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
        db, user, "document.uploaded", "document", doc["id"], clean_name,
        {"project_id": project_id, "type": type, "size": doc["size"], "content_type": safe_ct},
    )
    return doc


def _stream(rec: dict) -> StreamingResponse:
    """Stream stored bytes back with safe response headers (no MIME sniffing,
    forced download, sanitized filename)."""
    try:
        data, _ct = get_object(rec["storage_path"])
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise HTTPException(status_code=500, detail="Download failed")
    fname = safe_filename(rec.get("original_filename"))
    return StreamingResponse(
        io.BytesIO(data),
        media_type=rec.get("content_type") or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


async def _doc_or_404(doc_id: str) -> dict:
    rec = await db.documents.find_one({"id": doc_id, "is_deleted": {"$ne": True}}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    return rec


@router.get("/documents/{doc_id}/signed-url")
async def signed_url(doc_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Mint a short-lived signed URL for a document (access-checked once, here)."""
    rec = await _doc_or_404(doc_id)
    lead = await db.leads.find_one({"project_id": rec["project_id"]}, {"_id": 0})
    if lead:
        await ensure_lead_visible(user, lead)
    token = create_doc_download_token(doc_id, user["id"], "staff")
    return {
        "url": f"/api/documents/download?token={token}",
        "expires_in": DOC_URL_TTL_MIN * 60,
        "filename": safe_filename(rec.get("original_filename")),
    }


@router.get("/documents/download")
async def download_by_token(token: str, request: Request):
    """Redeem a signed URL — the token is the capability (no session needed).
    Access was authorised when the URL was minted; here we only verify the token
    and that the document still exists."""
    invalid = HTTPException(status_code=403, detail="Invalid or expired download link")
    try:
        payload = decode_token(token)
    except HTTPException:
        raise invalid
    if payload.get("type") != "doc_download" or not payload.get("doc"):
        raise invalid
    rec = await _doc_or_404(payload["doc"])
    await log_audit(
        db, None, "document.downloaded", "document", rec["id"], rec.get("original_filename"),
        {"project_id": rec.get("project_id"), "type": rec.get("type"),
         "via": "signed_url", "subject": payload.get("sub"), "kind": payload.get("aud_kind")}, request,
    )
    return _stream(rec)


@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, request: Request, user: dict = Depends(get_current_user)):
    rec = await _doc_or_404(doc_id)
    lead = await db.leads.find_one({"project_id": rec["project_id"]}, {"_id": 0})
    if lead:
        await ensure_lead_visible(user, lead)
    await log_audit(
        db, user, "document.downloaded", "document", doc_id, rec.get("original_filename"),
        {"project_id": rec.get("project_id"), "type": rec.get("type")}, request,
    )
    return _stream(rec)
