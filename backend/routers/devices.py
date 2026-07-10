"""
<module name="routers/devices" layer="api">
  <purpose>
    Company App (employee) push-token registration. The customer side lives in
    routers/client.py; this is the same capability for authenticated staff, so a
    Site Manager / Production Engineer / Project Manager can receive job push
    alerts on the Company App. Delivery is the shared push.send_push seam.
  </purpose>
</module>
"""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core import get_current_user
from push import register_device, unregister_device

router = APIRouter()


class DeviceIn(BaseModel):
    token: str
    platform: Optional[str] = None


@router.post("/devices")
async def register_employee_device(body: DeviceIn, user: dict = Depends(get_current_user)):
    """Register the signed-in employee's device for Company App push."""
    row = await register_device("user", user["id"], body.token, body.platform, app="company")
    return {"ok": True, "device_id": row["id"]}


@router.delete("/devices")
async def unregister_employee_device(body: DeviceIn, user: dict = Depends(get_current_user)):
    await unregister_device(body.token)
    return {"ok": True}
