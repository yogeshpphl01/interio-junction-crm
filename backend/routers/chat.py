"""
<module name="routers/chat" layer="api">
  <purpose>
    Project chat (customer <-> staff) REST foundation. A thread is tied to a
    project; it starts as a DM and can convert to a project GROUP once the project
    activates. Staff access is gated by `chat.access` + project visibility;
    customers are scoped to threads on their OWN projects (dual-BFF). Realtime
    delivery (Firestore) + the Flutter chat UI sit on top of this.
  </purpose>
</module>
"""
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from core import (
    db, get_current_customer, require_permission, ensure_project_visible, now_iso,
)
from audit import log_audit

router = APIRouter()

MAX_BODY = 4000


class ThreadIn(BaseModel):
    project_id: str
    kind: str = "dm"
    title: Optional[str] = None


class MessageIn(BaseModel):
    body: str


async def _thread_or_404(thread_id: str) -> dict:
    t = await db.chat_threads.find_one({"id": thread_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    return t


async def _customer_project_ids(customer: dict) -> list[str]:
    rows = await db.leads.find({"customer_id": customer["id"]}, {"_id": 0, "project_id": 1}).to_list(1000)
    return [r["project_id"] for r in rows if r.get("project_id")]


async def _post_message(thread: dict, sender_type: str, sender_id: str,
                        sender_name: Optional[str], body: str, request: Request) -> dict:
    body = (body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message is empty")
    if len(body) > MAX_BODY:
        raise HTTPException(status_code=413, detail="Message too long")
    doc = {
        "id": str(uuid.uuid4()), "thread_id": thread["id"], "sender_type": sender_type,
        "sender_id": sender_id, "sender_name": sender_name, "body": body, "created_at": now_iso(),
    }
    await db.chat_messages.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(db, None, "chat.message_sent", "chat", thread["id"], thread.get("project_id"),
                    {"sender_type": sender_type}, request)
    return doc


# ------------------------------------------------------------------ staff side
@router.post("/chat/threads")
async def create_thread(body: ThreadIn, user: dict = Depends(require_permission("chat.access"))):
    """Create (or return the existing) chat thread for a project."""
    if not await db.projects.find_one({"id": body.project_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Project not found")
    await ensure_project_visible(user, body.project_id)
    existing = await db.chat_threads.find_one({"project_id": body.project_id}, {"_id": 0})
    if existing:
        return existing
    lead = await db.leads.find_one({"project_id": body.project_id}, {"_id": 0, "id": 1})
    doc = {
        "id": str(uuid.uuid4()), "project_id": body.project_id, "lead_id": (lead or {}).get("id"),
        "kind": body.kind if body.kind in ("dm", "group") else "dm", "title": body.title,
        "created_by": user["id"], "created_at": now_iso(),
    }
    await db.chat_threads.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/chat/threads")
async def list_threads(project_id: str, user: dict = Depends(require_permission("chat.access"))):
    await ensure_project_visible(user, project_id)
    return await db.chat_threads.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/chat/threads/{thread_id}/messages")
async def staff_messages(thread_id: str, user: dict = Depends(require_permission("chat.access"))):
    t = await _thread_or_404(thread_id)
    await ensure_project_visible(user, t["project_id"])
    return await db.chat_messages.find({"thread_id": thread_id}, {"_id": 0}).sort("created_at", 1).to_list(2000)


@router.post("/chat/threads/{thread_id}/messages")
async def staff_send(thread_id: str, body: MessageIn, request: Request,
                     user: dict = Depends(require_permission("chat.access"))):
    t = await _thread_or_404(thread_id)
    await ensure_project_visible(user, t["project_id"])
    return await _post_message(t, "staff", user["id"], user.get("full_name"), body.body, request)


@router.post("/chat/threads/{thread_id}/convert-to-group")
async def convert_to_group(thread_id: str, user: dict = Depends(require_permission("chat.access"))):
    """DM -> project group (Rule 1: happens when the project activates)."""
    t = await _thread_or_404(thread_id)
    await ensure_project_visible(user, t["project_id"])
    await db.chat_threads.update_one({"id": thread_id}, {"$set": {"kind": "group"}})
    return {"ok": True, "thread_id": thread_id, "kind": "group"}


# --------------------------------------------------------------- customer side
@router.get("/client/chat")
async def client_threads(customer: dict = Depends(get_current_customer)):
    pids = await _customer_project_ids(customer)
    if not pids:
        return {"threads": []}
    threads = await db.chat_threads.find({"project_id": {"$in": pids}}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"threads": threads}


@router.get("/client/chat/{thread_id}/messages")
async def client_messages(thread_id: str, customer: dict = Depends(get_current_customer)):
    t = await _thread_or_404(thread_id)
    if t["project_id"] not in await _customer_project_ids(customer):
        raise HTTPException(status_code=404, detail="Thread not found")
    return await db.chat_messages.find({"thread_id": thread_id}, {"_id": 0}).sort("created_at", 1).to_list(2000)


@router.post("/client/chat/{thread_id}/messages")
async def client_send(thread_id: str, body: MessageIn, request: Request,
                      customer: dict = Depends(get_current_customer)):
    t = await _thread_or_404(thread_id)
    if t["project_id"] not in await _customer_project_ids(customer):
        raise HTTPException(status_code=404, detail="Thread not found")
    return await _post_message(t, "customer", customer["id"], customer.get("full_name"), body.body, request)
