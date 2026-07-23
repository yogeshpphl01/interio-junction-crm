#!/usr/bin/env python3
"""Generate 4 architecture diagrams as .drawio (editable) + .svg + .html (for PNG)."""
import html, os

OUT = os.path.dirname(os.path.abspath(__file__))
W = 1640

# draw.io standard palette (fill, stroke)
BLUE   = ("#DAE8FC", "#6C8EBF")
PURPLE = ("#E1D5E7", "#9673A6")
ORANGE = ("#FFE6CC", "#D79B00")
GRAY   = ("#F5F5F5", "#666666")
GREEN  = ("#D5E8D4", "#82B366")   # done
YELLOW = ("#FFF2CC", "#D6B656")   # needs creds / partial
RED    = ("#F8CECC", "#B85450")   # not built
SEC    = ("#D6DCF5", "#5B62B3")   # security & compliance layer (complete-view colour)
BANDBG = ("#FBFBFB", "#DDDDDD")


def esc(s):
    return html.escape(s, quote=True)


# ---------------------------------------------------------------- layout
def lay_row(items, bx, bw, y, h, gap=18):
    """Even row of boxes across [bx, bx+bw]; items = list of (label, (fill,stroke))."""
    n = len(items)
    box_w = (bw - (n + 1) * gap) / n
    nodes = []
    x = bx + gap
    for label, color in items:
        nodes.append((label, color, round(x), y, round(box_w), h))
        x += box_w + gap
    return nodes


def build(spec):
    """spec: title, subtitle, bands[list of (title, y, h, items)], edges labels, legend, notes, height."""
    svg, cells = [], []
    cid = [10]

    def nid():
        cid[0] += 1
        return f"n{cid[0]}"

    H = spec["height"]
    # background
    svg.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#FFFFFF"/>')

    # title / subtitle
    svg.append(f'<text x="50" y="46" font-family="Helvetica,Arial" font-size="26" font-weight="700" fill="#2A2421">{esc(spec["title"])}</text>')
    if spec.get("subtitle"):
        svg.append(f'<text x="50" y="74" font-family="Helvetica,Arial" font-size="15" fill="#6B6B6B">{esc(spec["subtitle"])}</text>')
    cells.append(f'<mxCell id="{nid()}" value="{esc(spec["title"])}" style="text;html=1;fontSize=24;fontStyle=1;align=left;verticalAlign=middle;" vertex="1" parent="1"><mxGeometry x="40" y="20" width="1000" height="34" as="geometry"/></mxCell>')
    if spec.get("subtitle"):
        cells.append(f'<mxCell id="{nid()}" value="{esc(spec["subtitle"])}" style="text;html=1;fontSize=13;align=left;fontColor=#6B6B6B;" vertex="1" parent="1"><mxGeometry x="40" y="56" width="1200" height="22" as="geometry"/></mxCell>')

    # legend
    if spec.get("legend"):
        lx, ly = W - 520, 24
        svg.append(f'<rect x="{lx}" y="{ly}" width="490" height="60" rx="8" fill="#FFFFFF" stroke="#CCCCCC"/>')
        items = spec["legend"]
        step = 490 // len(items)
        for i, (lab, col) in enumerate(items):
            ix = lx + 12 + i * step
            svg.append(f'<rect x="{ix}" y="{ly+14}" width="16" height="16" rx="3" fill="{col[0]}" stroke="{col[1]}"/>')
            svg.append(f'<text x="{ix+22}" y="{ly+26}" font-family="Helvetica,Arial" font-size="12" fill="#333">{esc(lab)}</text>')
        # legend in drawio
        for i, (lab, col) in enumerate(items):
            cells.append(f'<mxCell id="{nid()}" value="{esc(lab)}" style="rounded=1;fillColor={col[0]};strokeColor={col[1]};fontSize=11;align=left;spacingLeft=6;" vertex="1" parent="1"><mxGeometry x="{1180}" y="{24+i*22}" width="220" height="18" as="geometry"/></mxCell>')

    band_centers = []
    for (btitle, by, bh, items) in spec["bands"]:
        # band container
        svg.append(f'<rect x="40" y="{by}" width="{W-80}" height="{bh}" rx="10" fill="{BANDBG[0]}" stroke="{BANDBG[1]}"/>')
        svg.append(f'<text x="56" y="{by+24}" font-family="Helvetica,Arial" font-size="15" font-weight="700" fill="#4A4A4A">{esc(btitle)}</text>')
        cells.append(f'<mxCell id="{nid()}" value="{esc(btitle)}" style="rounded=1;fillColor={BANDBG[0]};strokeColor={BANDBG[1]};verticalAlign=top;align=left;spacingLeft=14;spacingTop=8;fontSize=14;fontStyle=1;fontColor=#4A4A4A;" vertex="1" parent="1"><mxGeometry x="40" y="{by}" width="{W-80}" height="{bh}" as="geometry"/></mxCell>')
        band_centers.append((by, by + bh))
        # inner boxes
        nodes = lay_row(items, 40, W - 80, by + 40, bh - 54)
        for (label, color, nx, ny, nw, nh) in nodes:
            lines = label.split("\n")
            svg.append(f'<rect x="{nx}" y="{ny}" width="{nw}" height="{nh}" rx="7" fill="{color[0]}" stroke="{color[1]}" stroke-width="1.5"/>')
            total = len(lines)
            cy = ny + nh / 2 - (total - 1) * 8
            for li, ln in enumerate(lines):
                fw = "700" if li == 0 else "400"
                fs = 13 if li == 0 else 11.5
                fc = "#222" if li == 0 else "#555"
                svg.append(f'<text x="{nx+nw/2}" y="{round(cy+li*16)}" font-family="Helvetica,Arial" font-size="{fs}" font-weight="{fw}" fill="{fc}" text-anchor="middle">{esc(ln)}</text>')
            raw = "<br>".join(f'<b>{l}</b>' if i == 0 else f'<font color="#555">{l}</font>' for i, l in enumerate(lines))
            val = esc(raw)  # XML-escape the HTML label for the attribute; draw.io un-escapes it
            cells.append(f'<mxCell id="{nid()}" value="{val}" style="rounded=1;whiteSpace=wrap;html=1;fillColor={color[0]};strokeColor={color[1]};fontSize=12;verticalAlign=middle;" vertex="1" parent="1"><mxGeometry x="{nx}" y="{ny}" width="{nw}" height="{nh}" as="geometry"/></mxCell>')

    # vertical arrows between consecutive FLOW bands (a trailing cross-cutting
    # band, e.g. Security, is excluded so it doesn't look "downstream").
    cx = W / 2
    labels = spec.get("edges", [])
    flow = spec.get("flow_bands", len(band_centers))
    for i in range(flow - 1):
        y1 = band_centers[i][1]
        y2 = band_centers[i + 1][0]
        svg.append(f'<line x1="{cx}" y1="{y1}" x2="{cx}" y2="{y2}" stroke="#8A817C" stroke-width="2" marker-end="url(#arrow)"/>')
        if i < len(labels) and labels[i]:
            svg.append(f'<rect x="{cx+8}" y="{(y1+y2)/2-11}" width="{9*len(labels[i])+14}" height="20" rx="4" fill="#FFFFFF" stroke="#CFC8C0"/>')
            svg.append(f'<text x="{cx+15}" y="{(y1+y2)/2+3}" font-family="Helvetica,Arial" font-size="12" fill="#5C534D">{esc(labels[i])}</text>')

    # notes
    for (txt, nx, ny, col) in spec.get("notes", []):
        c = col or ("#FFFDF5", "#C9A94B")
        wpx = 9 * max(len(l) for l in txt.split("\n")) + 24
        hpx = 20 * len(txt.split("\n")) + 12
        svg.append(f'<rect x="{nx}" y="{ny}" width="{wpx}" height="{hpx}" rx="6" fill="{c[0]}" stroke="{c[1]}"/>')
        for li, ln in enumerate(txt.split("\n")):
            svg.append(f'<text x="{nx+12}" y="{ny+20+li*18}" font-family="Helvetica,Arial" font-size="12" fill="#5C534D">{esc(ln)}</text>')
        cells.append(f'<mxCell id="{nid()}" value="{esc(txt).replace(chr(10),"&#10;")}" style="rounded=1;whiteSpace=wrap;html=1;fillColor={c[0]};strokeColor={c[1]};align=left;spacingLeft=8;fontSize=12;" vertex="1" parent="1"><mxGeometry x="{nx}" y="{ny}" width="{wpx}" height="{hpx}" as="geometry"/></mxCell>')

    svg_doc = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
        '<defs><marker id="arrow" markerWidth="12" markerHeight="12" refX="9" refY="5" orient="auto">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#8A817C"/></marker></defs>'
        + "".join(svg) + "</svg>"
    )
    drawio = (
        '<mxfile host="app.diagrams.net">'
        f'<diagram name="{esc(spec["title"])}">'
        f'<mxGraphModel dx="1200" dy="800" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" '
        f'arrows="1" fold="1" page="1" pageWidth="{W}" pageHeight="{spec["height"]}" math="0" shadow="0">'
        '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
        + "".join(cells) +
        '</root></mxGraphModel></diagram></mxfile>'
    )
    html_doc = f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;padding:0}}</style></head><body>{svg_doc}</body></html>'
    return svg_doc, drawio, html_doc


def write(name, spec):
    svg_doc, drawio, html_doc = build(spec)
    open(f"{OUT}/{name}.drawio", "w").write(drawio)
    open(f"{OUT}/{name}.svg", "w").write(svg_doc)
    open(f"{OUT}/{name}.html", "w").write(html_doc)
    print("wrote", name)


# ============================================================ DIAGRAM DATA
def client_bands(status=False):
    def c(done=GREEN, layer=None):
        return done if status else layer
    app = [
        ("OTP Login", c(GREEN, BLUE)), ("Home /\nProjects", c(GREEN, BLUE)),
        ("Estimates\n+ Accept", c(GREEN, BLUE)), ("Designs\n+ Feedback", c(GREEN, BLUE)),
        ("Payments", c(GREEN, BLUE)), ("Documents", c(GREEN, BLUE)),
    ]
    core = [
        ("ApiClient\nBearer + refresh", c(GREEN, PURPLE)), ("TokenStore\ncustomer", c(GREEN, PURPLE)),
        ("CustomerAuth\nRepository", c(GREEN, PURPLE)), ("Client\nRepository", c(GREEN, PURPLE)),
        ("Models", c(GREEN, PURPLE)),
    ]
    be = [
        ("OTP Auth\nrequest / verify", c(GREEN, ORANGE)), ("/client/projects", c(GREEN, ORANGE)),
        ("/client/estimates\n+ accept", c(GREEN, ORANGE)), ("/client/designs\n+ feedback", c(GREEN, ORANGE)),
        ("/client/payments", c(GREEN, ORANGE)), ("/client/documents", c(GREEN, ORANGE)),
        ("/client/devices\nFCM token", c(GREEN, ORANGE)),
    ]
    data = [
        ("Booking activation\non_payment_received", c(GREEN, GRAY)),
        ("PostgreSQL\ncustomers · otps ·\nestimates · payments", c(GREEN, GRAY)),
        ("Object storage\nrenders / PDFs", c(YELLOW, GRAY) if status else GRAY),
        ("FCM push", c(YELLOW, GRAY) if status else GRAY),
        ("Payments\nUPI now / Razorpay", c(YELLOW, GRAY) if status else GRAY),
    ]
    sec = [
        ("Phone-OTP auth\ndual-BFF boundary", c(GREEN, SEC)),
        ("Token revocation\ntoken_version", c(GREEN, SEC)),
        ("App Check gate\nattestation (RS256)", c(GREEN, SEC)),
        ("Rate-limit +\ndaily OTP cap", c(GREEN, SEC)),
        ("Signed doc URLs\n+ upload validation", c(GREEN, SEC)),
        ("DPDP\nconsent·export·erase", c(GREEN, SEC)),
    ]
    return [
        ("CLIENT APP  (Flutter · Dart)", 110, 150, app),
        ("ij_core  —  shared Dart package", 300, 120, core),
        ("BACKEND  —  Client BFF  (FastAPI, /api/client/*)", 452, 165, be),
        ("DOMAIN · DATA · EXTERNAL", 649, 170, data),
        ("SECURITY & COMPLIANCE  —  cross-cutting (P0–P1 built & verified)", 851, 150, sec),
    ]


def company_bands(status=False):
    def c(done=GREEN, layer=None):
        return done if status else layer
    app = [
        ("Login", c(GREEN, BLUE)), ("Work\nworklist", c(GREEN, BLUE)),
        ("Projects\nlist + detail", c(GREEN, BLUE)), ("Production\nparts · scan · import", c(GREEN, BLUE)),
        ("Tickets\nraise · resolve", c(GREEN, BLUE)), ("Checklists\n+ reconciliation", c(GREEN, BLUE)),
        ("Expenses\nsubmit · approve", c(GREEN, BLUE)),
    ]
    core = [
        ("ApiClient\nBearer + refresh", c(GREEN, PURPLE)), ("TokenStore\ncompany", c(GREEN, PURPLE)),
        ("EmployeeAuth\nRepository", c(GREEN, PURPLE)), ("Company\nRepository", c(GREEN, PURPLE)),
        ("Models", c(GREEN, PURPLE)),
    ]
    be = [
        ("Auth + RBAC\n/auth/login", c(GREEN, ORANGE)), ("/me/worklist", c(GREEN, ORANGE)),
        ("/projects", c(GREEN, ORANGE)), ("Estimates\nworkflow", c(GREEN, ORANGE)),
        ("Production\ncutlists · scan", c(GREEN, ORANGE)), ("Tickets +\nChecklists", c(GREEN, ORANGE)),
        ("Expenses", c(GREEN, ORANGE)), ("Campaigns +\nBooking", c(GREEN, ORANGE)),
    ]
    data = [
        ("PostgreSQL\nusers · roles · projects\nparts · tickets · audit", c(GREEN, GRAY)),
        ("Infurnia\nQR source (external)", c(YELLOW, GRAY) if status else GRAY),
        ("Object storage", c(YELLOW, GRAY) if status else GRAY),
        ("FCM push", c(YELLOW, GRAY) if status else GRAY),
        ("RBAC\n31 perms · 9 roles", c(GREEN, GRAY)),
    ]
    sec = [
        ("Password + MFA\nTOTP · AAL2", c(GREEN, SEC)),
        ("Revocation +\nrefresh rotation", c(GREEN, SEC)),
        ("RBAC + SoD\nfour-eyes · step-up", c(GREEN, SEC)),
        ("Signed URLs +\nupload validation", c(GREEN, SEC)),
        ("Webhook HMAC +\nrefund dual-control", c(GREEN, SEC)),
        ("Least-priv DB ·\nsecrets · CI scans", c(GREEN, SEC)),
    ]
    return [
        ("COMPANY APP  (Flutter · Dart)", 110, 150, app),
        ("ij_core  —  shared Dart package", 300, 120, core),
        ("BACKEND  —  Company surface  (FastAPI)", 452, 165, be),
        ("DOMAIN · DATA · EXTERNAL", 649, 170, data),
        ("SECURITY & COMPLIANCE  —  cross-cutting (P0–P1 built & verified)", 851, 150, sec),
    ]


EDGES = ["calls typed repo methods", "HTTPS · Bearer JWT (dual-BFF)", "async SQL · services"]
LEGEND = [("Done & verified", GREEN), ("Needs creds / input", YELLOW), ("Not built", RED)]
LAYERS = [("App", BLUE), ("ij_core", PURPLE), ("Backend", ORANGE), ("Data/Ext", GRAY), ("Security", SEC)]

# 1. Client complete
write("1_customer_app_complete", {
    "title": "1 · Customer App — Complete Architecture",
    "subtitle": "Flutter Client App → ij_core → FastAPI Client BFF → PostgreSQL. Dual-BFF: customer_access JWT. Security is cross-cutting.",
    "height": 1090, "bands": client_bands(False), "edges": EDGES, "legend": LAYERS, "flow_bands": 4,
    "notes": [("Dual-BFF: a customer_access token is rejected by every employee endpoint. The Security band wraps all layers (P0–P1, verified).", 50, 1024, None)],
})

# 2. Client done vs left
write("2_customer_app_progress", {
    "title": "2 · Customer App — Done vs Remaining",
    "subtitle": "Green = built & verified against Postgres.  Yellow = needs your credentials/input.  Red = not built.  (Security band: P0–P1 all done.)",
    "height": 1130, "bands": client_bands(True), "edges": EDGES, "legend": LEGEND, "flow_bands": 4,
    "notes": [(
        "REMAINING (config / not built):  real OTP delivery (SMS/WhatsApp or Firebase phone-auth) · FCM key for live push ·\n"
        "Razorpay online checkout — backend webhook is built, staff-verified UPI works now · object-storage go-live ·\n"
        "App Check / cert-pins — backend ready, add Firebase config + pins · Chat — backend built, realtime Firestore + UI remaining · Flutter run on a device.", 50, 1022, YELLOW)],
})

# 3. Company complete
write("3_employee_app_complete", {
    "title": "3 · Employee App — Complete Architecture",
    "subtitle": "Flutter Company App → ij_core → FastAPI (RBAC) → PostgreSQL + Infurnia. Dual-BFF: access JWT + permission gates. Security cross-cutting.",
    "height": 1090, "bands": company_bands(False), "edges": EDGES, "legend": LAYERS, "flow_bands": 4,
    "notes": [("Dual-BFF (access JWT) + RBAC on every write (31 perms · 9 roles incl. Finance). Security band wraps all layers (P0–P1, verified).", 50, 1024, None)],
})

# 4. Company done vs left
write("4_employee_app_progress", {
    "title": "4 · Employee App — Done vs Remaining",
    "subtitle": "Green = built & verified against Postgres.  Yellow = needs your credentials/input.  Red = not built.  (Security band: P0–P1 all done.)",
    "height": 1130, "bands": company_bands(True), "edges": EDGES, "legend": LEGEND, "flow_bands": 4,
    "notes": [(
        "REMAINING (config / not built):  camera QR scan — drop-in ready, needs a device; manual entry works · Infurnia real QR ingest (paste works) ·\n"
        "pricing Excel for the estimate engine · FCM key for live push · mobile FLAG_SECURE / manifest / obfuscation config ·\n"
        "Chat — backend built, realtime Firestore + UI remaining · Flutter compile / run on a device.", 50, 1022, YELLOW)],
})
print("done")
