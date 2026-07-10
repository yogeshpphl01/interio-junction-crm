"""
=============================================================================
 RAZORPAY BOOKING-PAYMENT INTEGRATION — REFERENCE (INTENTIONALLY INACTIVE)
=============================================================================

STATUS:  Pseudocode / reference only. **All executable code is commented out.**
         Do NOT wire this into any service yet. Activate it only after Razorpay
         credentials exist (see "TO ENABLE LATER" at the bottom).

INTERIM (NOW):  Payments are collected MANUALLY over Business UPI. There is no
         gateway call. The in-app flow is:
             1. Customer accepts the estimate (Client App).
             2. Sales Executive shares the company's Business UPI ID / QR (a
                static image or the `upi://` intent) in chat.
             3. Customer pays 10% from any UPI app and shares the reference.
             4. SE/PM records the payment (amount + UPI reference + screenshot)
                and marks it VERIFIED in the Company App.
             5. That VERIFY action fires the SAME `payment.received` domain event
                that the gateway webhook would have — so project activation +
                chat group conversion work identically, gateway or not.
         => The rest of the system does not care HOW the money arrived; it only
            reacts to a *verified* payment. Swapping manual-UPI for Razorpay
            later changes only WHO sets the payment to "verified" (a human vs. a
            signed webhook). Nothing downstream changes.

WHY THIS SHAPE:  The booking amount is ALWAYS computed server-side from the
         accepted estimate (never trusted from the client), and activation is
         driven by ONE event. This keeps the manual and gateway paths identical
         and tamper-resistant (see ENTERPRISE_ARCHITECTURE.md §16, §21.2).

TARGET RUNTIME:  The future mobile backend reuses the existing Python/FastAPI
         services on Cloud Run, so this reference is written in that style.

SECURITY NOTES (apply when enabled):
  * Never store card data. Razorpay is PCI-DSS; we keep only order/payment IDs.
  * Verify the webhook HMAC signature on every callback.
  * Idempotency: a replayed webhook must not activate a project twice.
  * Amount + currency are authoritative on the server, matched against the order.
  * Keep RAZORPAY_* secrets in Secret Manager, never in code or images.
=============================================================================
"""

# ---------------------------------------------------------------------------
# CONFIG (enable later; keep in Secret Manager / env — NOT in code)
# ---------------------------------------------------------------------------
# RAZORPAY_KEY_ID        = os.environ["RAZORPAY_KEY_ID"]
# RAZORPAY_KEY_SECRET    = os.environ["RAZORPAY_KEY_SECRET"]
# RAZORPAY_WEBHOOK_SECRET = os.environ["RAZORPAY_WEBHOOK_SECRET"]
# BOOKING_PERCENT        = 0.10   # 10% booking amount
#
# import razorpay, hmac, hashlib, uuid
# _client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


# ---------------------------------------------------------------------------
# STEP 1 — CREATE A BOOKING ORDER  (Company/Client BFF, server-side)
#   Amount is derived from the ACCEPTED estimate on the server. The client
#   never sends the amount.
# ---------------------------------------------------------------------------
# async def create_booking_order(project_id: str, user: dict) -> dict:
#     est = await db.estimates.find_one(
#         {"project_id": project_id, "status": "accepted"}, sort=[("version", -1)]
#     )
#     if not est:
#         raise HTTPException(400, "No accepted estimate to book against")
#     amount_paise = int(round(est["total"] * BOOKING_PERCENT * 100))  # INR -> paise
#
#     order = _client.order.create({
#         "amount": amount_paise,
#         "currency": "INR",
#         "receipt": f"booking_{project_id}",
#         "notes": {"project_id": project_id, "kind": "booking"},
#         "payment_capture": 1,
#     })
#     await db.payments.insert_one({
#         "id": str(uuid.uuid4()),
#         "project_id": project_id,
#         "type": "booking",
#         "amount": amount_paise / 100,
#         "currency": "INR",
#         "gateway": "razorpay",
#         "gateway_order_id": order["id"],
#         "status": "created",
#         "created_at": now_iso(),
#     })
#     # Client App opens Razorpay Checkout with {order_id, key_id, amount}.
#     return {"order_id": order["id"], "key_id": RAZORPAY_KEY_ID, "amount": amount_paise}


# ---------------------------------------------------------------------------
# STEP 2 — CHECKOUT  (Client App / Flutter, razorpay_flutter SDK)
#   Pseudocode of the client side:
#     Razorpay().open({ key: key_id, order_id: order_id, amount: amount,
#                       name: "Interio Junction", description: "Booking (10%)" })
#   On success the SDK returns { payment_id, order_id, signature }.
#   The app POSTs these to the backend, but the AUTHORITATIVE confirmation is the
#   webhook in Step 3 (never trust the client callback alone).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# STEP 3 — WEBHOOK  (authoritative; verify signature + idempotency)
#   Razorpay -> POST /v1/webhooks/razorpay
# ---------------------------------------------------------------------------
# @router.post("/v1/webhooks/razorpay")
# async def razorpay_webhook(request: Request):
#     raw = await request.body()
#     sig = request.headers.get("X-Razorpay-Signature", "")
#     expected = hmac.new(RAZORPAY_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
#     if not hmac.compare_digest(sig, expected):
#         raise HTTPException(400, "Bad signature")               # anti-spoof
#
#     event = json.loads(raw)
#     if event.get("event") != "payment.captured":
#         return {"ok": True}                                     # ignore others
#
#     pay = event["payload"]["payment"]["entity"]
#     order_id = pay["order_id"]
#     rec = await db.payments.find_one({"gateway_order_id": order_id})
#     if not rec:
#         return {"ok": True}                                     # unknown order
#     if rec["status"] == "verified":
#         return {"ok": True}                                     # IDEMPOTENT replay
#     if int(round(rec["amount"] * 100)) != pay["amount"]:
#         await log_audit(db, None, "payment.amount_mismatch", "payment", rec["id"], None,
#                         {"expected": rec["amount"], "got": pay["amount"] / 100})
#         raise HTTPException(400, "Amount mismatch")             # anti-tamper
#
#     await db.payments.update_one({"id": rec["id"]}, {"$set": {
#         "status": "verified", "gateway_payment_id": pay["id"], "verified_at": now_iso(),
#     }})
#     await emit_event("payment.received", {"project_id": rec["project_id"]})  # ONE event
#     return {"ok": True}


# ---------------------------------------------------------------------------
# STEP 4 — SHARED ACTIVATION  (used by BOTH manual-UPI verify AND the webhook)
#   This is the ONE place project activation lives, so manual and gateway paths
#   are identical. (Wire the manual-UPI "Mark verified" button to call this too.)
# ---------------------------------------------------------------------------
# async def on_payment_received(project_id: str, actor: dict | None):
#     await db.projects.update_one({"id": project_id}, {"$set": {
#         "booking_paid": True, "stage": 4, "activated_at": now_iso(),  # -> Booking
#     }})
#     await notify_team_and_customer(project_id, "payment.received")
#     await prompt_pm_to_create_group(project_id)   # DM -> project group (Rule 1)
#     await log_audit(db, actor, "payment.received", "project", project_id, None,
#                     {"channel": "razorpay" if actor is None else "manual_upi"})


# ---------------------------------------------------------------------------
# TO ENABLE LATER (checklist)
#   [ ] Create a Razorpay account; get KEY_ID / KEY_SECRET / WEBHOOK_SECRET.
#   [ ] Store them in Secret Manager; inject as env into the payment service.
#   [ ] Register the webhook URL in the Razorpay dashboard (payment.captured).
#   [ ] Uncomment Steps 1-4; add `razorpay` to requirements; add razorpay_flutter
#       to the Client App.
#   [ ] Point the "Mark verified" manual path AND the webhook at on_payment_received.
#   [ ] Test in Razorpay test mode; verify idempotency (replay the webhook).
# ---------------------------------------------------------------------------
