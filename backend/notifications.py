"""Email notifications via Resend. Falls back to no-op when not configured."""
import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY"))


def _from_address() -> str:
    return os.environ.get("SENDER_EMAIL") or "onboarding@resend.dev"


def _format_amount_inr(n) -> str:
    try:
        n = float(n)
    except Exception:
        return "—"
    if n >= 1_00_00_000:
        return f"₹ {n/1_00_00_000:.2f} Cr"
    if n >= 1_00_000:
        return f"₹ {n/1_00_000:.2f} L"
    return f"₹ {n:,.0f}"


def _email_shell(title: str, body_html: str, cta_label: Optional[str] = None, cta_url: Optional[str] = None) -> str:
    cta = ""
    if cta_label and cta_url:
        cta = f"""
        <tr><td style="padding:8px 0 24px 0;">
          <a href="{cta_url}" style="background:#C2683D;color:#FFFFFF;text-decoration:none;display:inline-block;padding:10px 18px;border-radius:6px;font-weight:600;font-family:Helvetica,Arial,sans-serif;font-size:13px;">{cta_label}</a>
        </td></tr>
        """
    return f"""
    <html><body style="margin:0;padding:0;background:#F6F2EB;font-family:Helvetica,Arial,sans-serif;color:#2A2421;">
      <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#F6F2EB;padding:24px 0;">
        <tr><td align="center">
          <table cellpadding="0" cellspacing="0" border="0" width="560" style="background:#FFFFFF;border:1px solid #E2DCD0;border-radius:8px;overflow:hidden;">
            <tr><td style="padding:18px 24px;border-bottom:1px solid #E2DCD0;background:#F6F2EB;">
              <span style="font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:#8A817C;">Interio Junction CRM</span>
            </td></tr>
            <tr><td style="padding:24px;">
              <h1 style="margin:0 0 12px 0;font-size:22px;color:#2A2421;font-weight:600;">{title}</h1>
              {body_html}
              {cta}
              <p style="margin:24px 0 0 0;color:#8A817C;font-size:11px;line-height:1.6;">Automated message from Interio Junction. Reply to your account manager if you have questions.</p>
            </td></tr>
          </table>
        </td></tr>
      </table>
    </body></html>
    """


async def _get_settings(db) -> dict:
    doc = await db.settings.find_one({"key": "notifications"}, {"_id": 0})
    return (doc or {}).get("value") or {}


async def _resolve_recipients(db, lead: Optional[dict], extra: Optional[dict] = None) -> list[str]:
    """Owner of the lead + admin (per settings or env)."""
    s = await _get_settings(db)
    recipients: list[str] = []
    if lead and lead.get("assigned_to"):
        u = await db.users.find_one({"id": lead["assigned_to"]}, {"_id": 0, "email": 1, "is_active": 1})
        if u and u.get("is_active", True) and u.get("email"):
            recipients.append(u["email"])
    admin_email = s.get("admin_email") or os.environ.get("ADMIN_EMAIL")
    if admin_email and admin_email not in recipients:
        recipients.append(admin_email)
    if extra and extra.get("extra_email") and extra["extra_email"] not in recipients:
        recipients.append(extra["extra_email"])
    return recipients


async def _send_via_resend(recipients: list[str], subject: str, html: str) -> tuple[bool, str]:
    if not _is_configured():
        return False, "RESEND_API_KEY not configured"
    if not recipients:
        return False, "No recipients"
    try:
        import resend
        resend.api_key = os.environ["RESEND_API_KEY"]
        params = {"from": _from_address(), "to": recipients, "subject": subject, "html": html}
        result = await asyncio.to_thread(resend.Emails.send, params)
        return True, result.get("id") if isinstance(result, dict) else str(result)
    except Exception as e:
        logger.warning(f"Resend send failed: {e}")
        return False, str(e)


async def _log_outcome(db, event: str, recipients: list[str], ok: bool, info: str, lead_id: Optional[str]) -> None:
    try:
        from audit import log_audit
        await log_audit(
            db, None, "notification.sent" if ok else "notification.failed",
            "notification", None, event,
            {"event": event, "recipients": recipients, "info": info, "lead_id": lead_id},
        )
    except Exception:
        pass


EVENT_TITLES = {
    "sla_breach_48h": "SLA breach — lead idle 48 hours",
    "escalate_hot_lead": "🔥 Hot lead untouched — escalation",
    "notify_designer_revision": "Revision requested on your design",
}


def _event_body(event: str, lead: Optional[dict], extra: Optional[dict]) -> str:
    name = (lead or {}).get("full_name") or "—"
    stage = (lead or {}).get("stage") or "—"
    budget = _format_amount_inr((lead or {}).get("tentative_budget"))
    rev = (extra or {}).get("revision") or {}

    if event == "sla_breach_48h":
        return f"""
          <p style="margin:0 0 12px 0;font-size:14px;line-height:1.6;">
            <strong>{name}</strong> has had no activity for 48 hours and is still Active in your pipeline.
          </p>
          <table cellpadding="0" cellspacing="0" border="0" width="100%" style="border-top:1px solid #E2DCD0;border-bottom:1px solid #E2DCD0;margin:12px 0;">
            <tr>
              <td style="padding:8px 0;font-size:12px;color:#8A817C;">Stage</td>
              <td style="padding:8px 0;font-size:13px;text-align:right;color:#2A2421;font-weight:600;">{stage}</td>
            </tr>
            <tr>
              <td style="padding:8px 0;font-size:12px;color:#8A817C;">Budget</td>
              <td style="padding:8px 0;font-size:13px;text-align:right;color:#2A2421;font-weight:600;">{budget}</td>
            </tr>
          </table>
          <p style="margin:0;font-size:13px;color:#5C534D;line-height:1.6;">Reach out today to keep the deal warm.</p>
        """
    if event == "escalate_hot_lead":
        score = (extra or {}).get("score", "—")
        return f"""
          <p style="margin:0 0 12px 0;font-size:14px;line-height:1.6;">
            <strong>{name}</strong> is rated <strong>Hot ({score})</strong> but has had no touch in the last 24 hours.
          </p>
          <p style="margin:0 0 12px 0;font-size:13px;color:#5C534D;line-height:1.6;">Budget {budget} · Stage {stage}. Recommended: a call within the next 2 hours.</p>
        """
    if event == "notify_designer_revision":
        return f"""
          <p style="margin:0 0 12px 0;font-size:14px;line-height:1.6;">
            Revision <strong>R{rev.get('revision_number', '?')}</strong> on project <strong>{(extra or {}).get('lead', {}).get('full_name', '—')}</strong> was marked <strong>Revision Requested</strong>.
          </p>
          <p style="margin:0 0 12px 0;font-size:13px;color:#5C534D;line-height:1.6;">Client feedback:<br/><em>{rev.get('client_feedback') or '—'}</em></p>
        """
    return f"<p>Event {event} for {name}</p>"


async def dispatch_event(db, event: str, lead_id: Optional[str], extra: Optional[dict] = None) -> None:
    """Send an email for the given event if notifications are enabled."""
    s = await _get_settings(db)
    if not s.get("enabled"):
        return
    events = s.get("events") or {}
    if event in events and events[event] is False:
        return  # explicitly disabled for this event

    lead = (extra or {}).get("lead")
    if lead_id and not lead:
        lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})

    recipients = await _resolve_recipients(db, lead, extra)

    if event == "notify_designer_revision":
        designer = (extra or {}).get("designer") or {}
        if designer.get("email"):
            recipients = list(dict.fromkeys([designer["email"]] + recipients))

    title = EVENT_TITLES.get(event, event)
    body = _event_body(event, lead, extra)
    html = _email_shell(title, body)
    ok, info = await _send_via_resend(recipients, title, html)
    await _log_outcome(db, event, recipients, ok, info, lead_id)


async def send_test_email(db, to: str) -> tuple[bool, str]:
    html = _email_shell(
        "Test email from Interio Junction",
        "<p style='font-size:14px;line-height:1.6;'>If you're seeing this, Resend is configured correctly. Your CRM will use this address to deliver SLA + Hot-lead alerts.</p>",
    )
    ok, info = await _send_via_resend([to], "Interio Junction · Test notification", html)
    await _log_outcome(db, "test", [to], ok, info, None)
    return ok, info
