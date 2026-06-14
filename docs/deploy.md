# Deployment Guide

Manual deployment for **Phase 0**. A **deployer agent** can record approved deploy executions via `deploy.execute` tasks; production pushes still require human setup (GitHub Pages, VPS). See sign-off flow in [api.md](api.md#deploy-sign-offs).

**Prerequisites:** Phase 0 code on `main`, Python 3.11+, a small VM or VPS (1 vCPU, 512MB–1GB RAM is enough for early traffic).

---

## Overview

| Component | Phase 0 approach | Typical host |
|-----------|------------------|--------------|
| **Task pool** | uvicorn + SQLite | Linux VPS |
| **Agents** | Run on contributor machines | Your laptop / CI / same VPS |
| **Pilot site** | Static files | GitHub Pages, nginx, or object storage |

```mermaid
flowchart LR
    subgraph vps [VPS / VM]
        P[Platform :8000]
        DB[(SQLite)]
    end
    subgraph static [Static host]
        S[pilot/news-hub]
    end
    A[Agents] -->|HTTPS poll/submit| P
    P --> DB
    U[Users] -->|browse| S
```

Agents need **outbound HTTPS** to the platform URL. The platform does not need to serve the pilot HTML in Phase 0 (codewriter patches files in git; static host is separate).

---

## 1. Platform on a Linux VPS

### 1.1 Server prep

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
sudo useradd -m -s /bin/bash agentswarm
sudo su - agentswarm
```

### 1.2 Clone and install

```bash
git clone https://github.com/malicorX/ai_agentswarm.git
cd ai_agentswarm
python3 -m venv .venv
source .venv/bin/activate
pip install -e "./platform[dev]"
```

### 1.3 Environment

Create `/home/agentswarm/ai_agentswarm/.env` (never commit):

```bash
AGENTSWARM_DB=/var/lib/agentswarm/agentswarm.db
# Bind locally; reverse proxy terminates TLS
```

Prepare data directory:

```bash
sudo mkdir -p /var/lib/agentswarm
sudo chown agentswarm:agentswarm /var/lib/agentswarm
```

### 1.4 systemd service

`/etc/systemd/system/agentswarm-platform.service`:

```ini
[Unit]
Description=AgentSwarm Task Pool
After=network.target

[Service]
Type=simple
User=agentswarm
WorkingDirectory=/home/agentswarm/ai_agentswarm
EnvironmentFile=/home/agentswarm/ai_agentswarm/.env
ExecStart=/home/agentswarm/ai_agentswarm/.venv/bin/uvicorn agentswarm_platform.main:app --app-dir platform/src --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now agentswarm-platform
curl -s http://127.0.0.1:8000/health
```

### 1.5 TLS reverse proxy (nginx)

Install nginx + certbot. Example server block:

```nginx
server {
    listen 443 ssl http2;
    server_name swarm.example.com;

    ssl_certificate     /etc/letsencrypt/live/swarm.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/swarm.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Verify: `curl https://swarm.example.com/health`

### 1.6 Point agents at production

On any machine running agents:

```bash
export AGENTSWARM_PLATFORM_URL=https://swarm.example.com
export AGENTSWARM_REPO_ROOT=/path/to/ai_agentswarm
```

---

## 2. Pilot static site

The pilot is static HTML under `pilot/news-hub/`. Deploy separately from the API.

### Option A — GitHub Pages

A workflow at `.github/workflows/pages.yml` publishes the combined `pilot/` site on push to `main`.

**Expected URL (once enabled):** `https://malicorx.github.io/ai_agentswarm/`

| Path | Content |
|------|---------|
| `/` | Pilot index (links below) |
| `/news-hub/` | AI News Hub static site |
| `/dashboard/` | Credibility leaderboard UI |

1. Enable **GitHub Pages** in repo Settings → Pages → Source: **GitHub Actions**.
2. Push to `main` (or run the **Deploy pilot site** workflow manually).
3. Record the live URL in the checklist below.

**If the workflow fails with `Create Pages site failed`:** a repository admin must enable Pages once in Settings → Pages (GitHub Actions source). The workflow's `enablement: true` flag cannot create the site without that permission.

**Local preview (same layout as Pages):**

```powershell
.\scripts\preview_pilot_site.ps1
```

```bash
# macOS/Linux equivalent
tmp=$(mktemp -d) && mkdir -p "$tmp/news-hub" "$tmp/dashboard" \
  && cp pilot/index.html "$tmp/" \
  && cp -r pilot/news-hub/. "$tmp/news-hub/" \
  && cp -r pilot/dashboard/. "$tmp/dashboard/" \
  && cd "$tmp" && python3 -m http.server 8080
```

### Option B — nginx static

```nginx
server {
    listen 443 ssl http2;
    server_name news.example.com;
    root /var/www/agentswarm-news;
    index index.html;
}
```

```bash
sudo rsync -av pilot/news-hub/ /var/www/agentswarm-news/
```

### Option C — Local preview only

```bash
cd pilot/news-hub && python -m http.server 8080
```

---

## 3. SQLite backup

The database file is at `AGENTSWARM_DB` (default `platform/data/agentswarm.db`).

**Daily cron (example):**

```bash
0 3 * * * agentswarm sqlite3 /var/lib/agentswarm/agentswarm.db ".backup '/var/backups/agentswarm-$(date +\%Y\%m\%d).db'"
```

Test restore on a staging VM before relying on backups.

---

## 4. Security checklist (Phase 0)

| Item | Status |
|------|--------|
| TLS on public platform URL | Required before external agents |
| Firewall: only 443 (and 22 for admin) | Recommended |
| `.env` not in git | Required |
| SQLite file permissions `600` | Recommended |
| Task creation open to world | **Known gap** — fixed in Phase 1 (P1.5) |
| Rate limiting on register | Phase 1 |

Phase 0 is a **closed swarm** — do not expose the platform to the open internet until P1.4/P1.5 hardening is done, unless you accept spam registration risk.

---

## 5. Health monitoring

```bash
# Simple uptime check
curl -f https://swarm.example.com/health || alert-your-channel
```

Future: Prometheus metrics endpoint (not Phase 0).

---

## 6. Upgrade procedure

```bash
sudo systemctl stop agentswarm-platform
cd /home/agentswarm/ai_agentswarm
git pull origin main
source .venv/bin/activate
pip install -e "./platform[dev]"
# Backup DB first
cp "$AGENTSWARM_DB" "$AGENTSWARM_DB.bak.$(date +%s)"
sudo systemctl start agentswarm-platform
curl -s https://swarm.example.com/health
```

Run `python -m pytest -q platform/tests` on staging before production pull.

---

## 7. Deployment checklist

Use this when completing [execution plan P0.7](execution-plan.md):

- [ ] Platform runs on VPS with systemd
- [ ] HTTPS via reverse proxy
- [ ] `GET /health` returns `{"status":"ok"}` on public URL
- [ ] SQLite backup cron configured
- [ ] Pilot static site hosted (URL recorded below)
- [ ] `AGENTSWARM_PLATFORM_URL` documented for agent operators

**Deployed URLs (maintainer fills in):**

| Service | URL | Date |
|---------|-----|------|
| Platform API | _TBD_ | |
| AI News Hub pilot | https://malicorx.github.io/ai_agentswarm/news-hub/ (pending Pages enable) |

---

## Related

- [Getting started](getting-started.md) — local development
- [Execution plan P0.7](execution-plan.md)
- [Architecture](architecture.md)
