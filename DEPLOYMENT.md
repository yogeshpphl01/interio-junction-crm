<!--
  <doc name="DEPLOYMENT" audience="non-technical">
    A complete, copy-paste guide to get the Interio Junction CRM running on a
    Hostinger server and connect pgAdmin to its database. Follow top to bottom.
  </doc>
-->

# Getting the CRM running — step by step

This guide assumes **no prior knowledge**. Copy each command exactly. Words in
`CAPITALS` are things you replace with your own values.

---

## 0. First, the one important thing to understand

This CRM is a real web application made of **three parts**:

1. a **database** (PostgreSQL — what you see in pgAdmin),
2. a **backend** (the brain / API, written in Python), and
3. a **frontend** (the website you click around in).

👉 Running these needs a **Hostinger VPS** (a small private server you get full
control of). It **cannot** run on Hostinger "Web Hosting / Shared Hosting"
(the kind for normal websites) — that type only runs PHP websites and MySQL,
not Python apps or PostgreSQL.

**How to tell what you have:** log in to Hostinger → top menu **VPS**. If you
see a server there, you're good. If you only see **Hosting** (websites), you'll
need to buy a VPS (the cheapest "KVM 1" plan is enough to start).

> Good news: I've packaged everything with **Docker**, so the entire stack
> (database + backend + frontend) starts with **one command**. You do **not**
> need to install Python, Node, or PostgreSQL by hand.

---

## 1. Get a Hostinger VPS with Docker

1. Hostinger → **VPS → Buy / Manage**.
2. When choosing the **Operating System / template**, pick one that says
   **"Ubuntu 24.04 with Docker"** (Hostinger offers an OS template with Docker
   pre-installed). If you can't find it, pick plain **Ubuntu 24.04** — we'll
   install Docker in step 3.
3. Set a **root password** when asked and note it down.
4. After it's created, copy the server's **IP address** (looks like
   `123.45.67.89`).

---

## 2. Connect to the server

**On Windows:** open **PowerShell** (Start menu → type "PowerShell").
**On Mac:** open **Terminal**.

Then type (replace the IP):

```bash
ssh root@123.45.67.89
```

Type `yes` if asked, then enter the **root password** from step 1. You're now
"inside" the server.

---

## 3. Install Docker (skip if your template already had it)

Paste this and press Enter:

```bash
curl -fsSL https://get.docker.com | sh
```

Check it worked:

```bash
docker --version
```

You should see a version number.

---

## 4. Download the CRM code onto the server

```bash
apt-get update && apt-get install -y git
git clone https://github.com/yogeshpphl01/interio-junction-crm.git
cd interio-junction-crm
```

> If git asks for a login, the repository is private — use a GitHub
> "Personal Access Token" as the password, or make the repo public.

---

## 5. Create your settings file (`.env`)

This is the **only file you edit**. It holds your passwords. Create it:

```bash
nano .env
```

Paste the following, then change the three values marked 👈:

```ini
# A long random secret for login security. Generate one with:
#   openssl rand -hex 32
JWT_SECRET=paste-a-long-random-string-here          # 👈 change

# Password for the CRM's database (pick a strong one).
POSTGRES_PASSWORD=pick-a-strong-db-password         # 👈 change

# The password for the first admin login to the CRM.
ADMIN_PASSWORD=pick-your-admin-password             # 👈 change

# Leave these as-is unless you know you want different values:
POSTGRES_USER=crm
POSTGRES_DB=interio_crm
ADMIN_EMAIL=admin@interiojunction.com
```

Save and exit nano: press **Ctrl+O**, **Enter**, then **Ctrl+X**.

Tip — generate a strong `JWT_SECRET` automatically:
```bash
echo "JWT_SECRET=$(openssl rand -hex 32)"
```
(copy the line it prints into your `.env`).

---

## 6. Start the whole CRM (one command)

```bash
docker compose up -d --build
```

The first run takes a few minutes (it downloads and builds everything). When it
finishes, check everything is running:

```bash
docker compose ps
```

All three services (`db`, `backend`, `frontend`) should show **running / up**.

---

## 7. Open the CRM and log in 🎉

In your web browser go to:

```
http://123.45.67.89
```

(use your server's IP). Log in with:

- **Email:** `admin@interiojunction.com`
- **Password:** the `ADMIN_PASSWORD` you set in `.env`

The database tables and a few demo leads are created automatically on the first
start — nothing to set up by hand.

---

## 8. Upload your leads Excel sheet

1. In the CRM, open **Leads** (left menu).
2. Click the **Import** button (top right).
3. Choose your Meta Lead-Ads `.xlsx` file and click **Import**.

You'll get a summary (created / updated / skipped). Re-uploading the same file
later is safe — it updates existing leads instead of duplicating them, and never
resets your sales team's progress.

---

## 9. Connect pgAdmin to the database

The bundled database is reachable on your server's IP, port **5432**.

In **pgAdmin** → right-click **Servers → Register → Server…**:

| Field | Value |
|---|---|
| Name (General tab) | `Interio CRM` (anything you like) |
| Host name/address (Connection tab) | your server IP, e.g. `123.45.67.89` |
| Port | `5432` |
| Maintenance database | `interio_crm` |
| Username | `crm` |
| Password | the `POSTGRES_PASSWORD` from your `.env` |

Click **Save**. You'll now see the `leads`, `projects`, `import_batches`, etc.
tables and can run SQL reports (examples are in `backend/DATABASE_SETUP.md`).

> 🔐 **Security note:** port 5432 is open to the internet. Use a **strong**
> `POSTGRES_PASSWORD`. For tighter security, restrict it to your own IP in the
> Hostinger VPS **Firewall**, or connect pgAdmin over an SSH tunnel instead.

### Prefer to use a PostgreSQL you already manage?
If you already have a separate PostgreSQL database, edit `.env` and add a line:
```ini
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
```
then in `docker-compose.yml` remove the `db:` service and the `depends_on: db`
lines, and run `docker compose up -d --build` again. The CRM will use your
database instead of the bundled one.

---

## 10. Everyday commands (for later)

Run these from inside the `interio-junction-crm` folder on the server:

```bash
docker compose ps           # see what's running
docker compose logs -f      # watch live logs (Ctrl+C to stop watching)
docker compose down         # stop the CRM (data is kept)
docker compose up -d        # start it again
```

**To deploy updates** (after I push new commits to the branch / PR):
```bash
git pull
docker compose up -d --build
```

---

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| Browser shows nothing / can't connect | Run `docker compose ps`. If `frontend` isn't "running", run `docker compose logs frontend`. Also make sure port **80** is open in the Hostinger VPS firewall. |
| "Invalid credentials" at login | The admin password is the `ADMIN_PASSWORD` from `.env`. If you changed it *after* the first start, the old one is already saved — log in with the original, then change it in **Settings**. |
| pgAdmin can't connect | Check port **5432** is open in the VPS firewall and the password matches `POSTGRES_PASSWORD`. |
| Import says "Could not read spreadsheet" | Make sure it's the `.xlsx` (or `.csv`) exported from Meta Lead Ads. |
| `docker compose up` says **"port is already allocated" / address already in use** | Another program already uses that port (often an existing Traefik/Nginx on port 80). Add `WEB_PORT=8080` to your `.env` (and `DB_PORT=5433` if 5432 clashes), run `docker compose up -d` again, then open `http://YOUR_IP:8080`. |
| You already run a **reverse proxy (Traefik/Nginx)** on this server | Don't fight it — set `WEB_PORT=8080` so the CRM serves on a free port. Later we can route your domain to it through the existing proxy. |
| Need to start clean | `docker compose down -v` wipes the database too (careful!), then `docker compose up -d --build`. |

---

## 12. (Optional, later) Use a domain + HTTPS

Once it works on the IP, you can point a domain at the server's IP (an **A
record**) and add free HTTPS. That's an optional polish step — tell me when
you're ready and I'll walk you through it.
