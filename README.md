# ChainBreak — Blockchain & UPI Forensic Analysis Platform

ChainBreak is a full-stack forensic analysis tool for investigating suspicious blockchain (Bitcoin) transactions and UPI payment mule networks. It combines graph-based transaction tracing, community detection algorithms, and a role-based access control system into a single web application.

---

## Architecture

```
ChainBreak/
├── app.py                        # Entry point — starts FastAPI server or CLI analysis
├── backend/
│   ├── api_root.py               # Main FastAPI app, all route definitions
│   ├── database/
│   │   ├── models.py             # SQLAlchemy ORM: User, Role, UserSession, AuditLog
│   │   ├── auth.py               # JWT auth, login, logout, token refresh endpoints
│   │   └── rbac.py               # Role definitions and permission constants
│   ├── api/v1/
│   │   ├── user_management_routes.py  # Admin user CRUD, role assignment
│   │   └── ...                   # Other v1 route modules
│   ├── logger/
│   │   └── app_logger.py         # Rotating file handler → backend/logs/chainbreak.log
│   ├── services/                 # Blockchain fetcher, temporal analysis, threat intel
│   └── core/
│       └── Community_Detection/  # Louvain, Leiden, Label Propagation, Infomap
└── frontend/
    ├── src/
    │   ├── App.js                # Root component, auth state, layout
    │   ├── components/           # Feature UI components
    │   ├── features/             # Investigation dashboard
    │   ├── hooks/usePermissions.js  # Role/permission checks from localStorage
    │   └── utils/
    │       ├── api.js            # Axios instance with JWT + CSRF interceptors
    │       └── upiCaseManager.js # UPI case save/load/list/delete helpers
    └── build/                    # Production build served by FastAPI
```

---

## Architecture

```
ChainBreak/
├── app.py                        # Entry point — starts FastAPI server or CLI analysis
├── backend/
│   ├── api_root.py               # Main FastAPI app, all route definitions
│   ├── database/
│   │   ├── models.py             # SQLAlchemy ORM: User, Role, UserSession, AuditLog
│   │   ├── auth.py               # JWT auth, login, logout, token refresh endpoints
│   │   └── rbac.py               # Role definitions and permission constants
│   ├── api/v1/
│   │   ├── user_management_routes.py  # Admin user CRUD, role assignment
│   │   └── ...                   # Other v1 route modules
│   ├── logger/
│   │   └── app_logger.py         # Rotating file handler → backend/logs/chainbreak.log
│   ├── services/                 # Blockchain fetcher, temporal analysis, threat intel
│   └── core/
│       └── Community_Detection/  # Louvain, Leiden, Label Propagation, Infomap
└── frontend/
    ├── src/
    │   ├── App.js                # Root component, auth state, layout
    │   ├── components/           # Feature UI components
    │   ├── features/             # Investigation dashboard
    │   ├── hooks/usePermissions.js  # Role/permission checks from localStorage
    │   └── utils/
    │       ├── api.js            # Axios instance with JWT + CSRF interceptors
    │       └── upiCaseManager.js # UPI case save/load/list/delete helpers
    └── build/                    # Production build served by FastAPI
```


**Runtime:** Single port `5000`. FastAPI serves the React production build from `frontend/build/` at the SPA catch-all route. The dev proxy (`package.json` → port 5000) is used only during `npm start`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Database (auth) | SQLite via SQLAlchemy ORM (`instance/chainbreak.db`) |
| Database (graph) | Neo4j (optional — needed only for blockchain graph storage) |
| Authentication | JWT (access + refresh tokens), HttpOnly cookies, CSRF protection |
| Frontend | React 18, Axios, D3.js (canvas renderer), Framer Motion |
| Graphs | D3 force simulation on HTML Canvas for 10k+ node performance |
| Community Detection | Louvain, Leiden, Label Propagation, Infomap |
| Logging | Python rotating file handler → `backend/logs/chainbreak.log` |

---

## Quick Start (Local Development)

### Prerequisites
- Python 3.10+
- Node.js 18+
- pip
- (Optional) Neo4j 5.x for graph database backend

### 1. Clone and configure environment
```bash
git clone <repo-url> && cd ChainBreak
cp .env.example .env
```

Edit `.env` and set at minimum:
```
CHAINBREAK_SECRET_KEY=<random-64-char-hex>   # generate: python -c "import secrets; print(secrets.token_hex(32))"
NEO4J_PASSWORD=<your-neo4j-password>          # if using Neo4j
```

If `CHAINBREAK_SECRET_KEY` is not set the app will auto-generate an ephemeral key and log a warning. **Sessions will not survive a restart** in that mode — always set the key for any shared deployment.

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Build the Next.js frontend
```bash
cd frontend
npm install
npm run build
cd ..
```

### 4. Start the server
```bash
python app.py --api
# Backend: http://localhost:5000
# API docs: http://localhost:5000/docs
# Frontend: http://localhost:3000 (Next.js dev server)
```

The first run auto-creates:
- `instance/chainbreak.db` — SQLite database
- Default roles: `admin`, `investigator`, `analyst`, `viewer`
- `backend/logs/` directory for log output

### 5. Create the first admin user
```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@example.com","password":"Admin@123","role":"admin"}'
```

Then log in at `http://localhost:3000`.

---

## Production Hosting (Docker / VPS)

### Option A — Docker Compose (recommended)

**Requirements:** Docker 24+, Docker Compose v2, a VPS with ports 80 and 443 open.

```bash
# 1. Copy and fill in production values
cp .env.example .env
nano .env   # set CHAINBREAK_SECRET_KEY, DOMAIN, CERTBOT_EMAIL, SERVER_IP

# 2. Build and start all services
docker compose up -d --build

# Services started:
#   neo4j    – graph database (internal only)
#   backend  – FastAPI on port 8000 (internal)
#   frontend – Next.js on port 3000 (internal)
#   nginx    – reverse proxy on 80/443 (public)
```

**Critical `.env` values for production:**

| Variable | Description |
|---|---|
| `CHAINBREAK_SECRET_KEY` | **Required.** 64-char hex string. `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DOMAIN` | Your domain name, e.g. `chainbreak.example.com`. Used by nginx and Let's Encrypt. |
| `CERTBOT_EMAIL` | Email for Let's Encrypt TLS certificate renewal alerts. |
| `SERVER_IP` | Public IP of the server (used if no domain is configured). |
| `NEO4J_PASSWORD` | Neo4j password — change from default before going live. |
| `ADMIN_USERNAME` | Username for the bootstrap admin account (created on first start). |
| `ADMIN_PASSWORD` | Password for the bootstrap admin (must meet complexity rules). |
| `SECURE_COOKIES` | Set to `true` in production (HTTPS only). Default: `true`. |
| `TRUSTED_PROXIES` | CIDR ranges of trusted reverse proxies for `X-Forwarded-For`. |

**Firewall rules needed:**
- `80/tcp` — HTTP (redirects to HTTPS)
- `443/tcp` — HTTPS
- Block `7687`, `8000`, `3000` externally — they are internal Docker ports only

**Health checks:**
```bash
docker compose ps           # all services should show "healthy"
curl https://your.domain/api/health
```

**View logs:**
```bash
docker compose logs -f backend
docker compose logs -f nginx
```

**Update deployment:**
```bash
git pull
docker compose up -d --build
```

---

### Option B — Bare-metal / systemd

Use this if you don't want Docker.

```bash
# Install system deps
sudo apt install python3.10 python3-pip nodejs npm nginx certbot python3-certbot-nginx

# Python deps
pip install -r requirements.txt

# Build frontend
cd frontend && npm install && npm run build && cd ..

# Create systemd unit (save as /etc/systemd/system/chainbreak.service)
```

```ini
[Unit]
Description=ChainBreak API
After=network.target

[Service]
WorkingDirectory=/opt/chainbreak
EnvironmentFile=/opt/chainbreak/.env
ExecStart=/usr/bin/python3 app.py --api --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now chainbreak

# Nginx reverse-proxy config (save as /etc/nginx/sites-available/chainbreak)
```

```nginx
server {
    listen 443 ssl;
    server_name chainbreak.example.com;

    ssl_certificate /etc/letsencrypt/live/chainbreak.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/chainbreak.example.com/privkey.pem;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
server {
    listen 80;
    server_name chainbreak.example.com;
    return 301 https://$host$request_uri;
}
```

```bash
sudo ln -s /etc/nginx/sites-available/chainbreak /etc/nginx/sites-enabled/
sudo certbot --nginx -d chainbreak.example.com
sudo systemctl restart nginx
```

---

### Things to know before going live

1. **Secret key rotation** — changing `CHAINBREAK_SECRET_KEY` invalidates all existing JWTs and logs everyone out. Do not rotate without warning users.
2. **SQLite vs PostgreSQL** — the default database is SQLite (`instance/chainbreak.db`). For high-concurrency production use, swap to PostgreSQL by updating the `DATABASE_URL` in the backend and installing `psycopg2-binary`.
3. **Neo4j memory** — the compose file limits Neo4j to 3 GB. For large graphs adjust `NEO4J_dbms_memory_heap_max__size` and the Docker `memory` limit.
4. **RGCN model** — the RGCN fraud-detection pipeline requires training before scores are available. Run `python backend/services/RGCN/run_pipeline.py` with your UPI CSV data to generate `backend/services/RGCN/model/fraud_pipeline.pkl`. Until then the UI shows heuristic scores as a fallback.
5. **Multiple concurrent logins** — each login creates an independent session. Admins can revoke individual sessions via `POST /api/users/revoke-session`.
6. **Back button** — clicking the Home button in the dashboard header logs the current session out and redirects to the landing page.
7. **Backups** — back up the Docker volumes `chainbreak_db` (SQLite) and `chainbreak_data` (saved cases) regularly. Neo4j data lives in `neo4j_data`.
8. **HTTPS is required** — `SECURE_COOKIES=true` (the default) means auth cookies will not be sent over plain HTTP. Always serve via HTTPS in production.

---

## Role-Based Access Control

| Role | Permissions |
|---|---|
| **admin** | Full access — user management, profile settings, all data |
| **investigator** | Create/read/update/delete cases, run analysis, view users |
| **analyst** | Create/read/update cases, run and view analysis |
| **viewer** | Read-only — view cases and analysis results, cannot save |

- Profile settings (password change) are admin-only in the UI and enforced on the backend.
- UPI case saving is blocked for `viewer` role at both frontend and backend.
- Non-admin users only see UPI cases they created; admins see all.
- All role assignments and admin actions are recorded in the `AuditLog` table.

---

## Key Endpoints

### Auth
| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login` | Login — returns JWT access/refresh tokens as HttpOnly cookies |
| POST | `/api/auth/logout` | Logout — invalidates session and revokes JWT |
| POST | `/api/auth/refresh` | Refresh access token using refresh cookie |
| GET | `/api/auth/me` | Current user info |
| POST | `/api/auth/change-password` | Change own password (admin only) |

### User Management (admin only)
| Method | Path | Description |
|---|---|---|
| GET | `/api/users/roles` | List all roles |
| POST | `/api/users/create` | Create a new user |
| POST | `/api/users/assign-role` | Assign role to user |
| POST | `/api/users/{id}/reset-password` | Reset another user's password |
| GET | `/api/users/sessions` | List active sessions |
| POST | `/api/users/revoke-session` | Revoke a session |

### Blockchain Analysis
| Method | Path | Description |
|---|---|---|
| POST | `/api/analyze` | Analyze a Bitcoin address |
| POST | `/api/graph/address` | Fetch and store transaction graph |
| GET | `/api/graph/list` | List stored graphs |

### UPI Analysis
| Method | Path | Description |
|---|---|---|
| POST | `/api/upi/analyze` | Upload CSV for UPI mule detection |
| GET | `/api/upi/settings` | Get detection settings |
| POST | `/api/upi/communities/detect` | Run community detection on UPI graph |
| POST | `/api/upi/communities/compare` | Compare multiple algorithms |

### UPI Cases (saved analyses)
| Method | Path | Description |
|---|---|---|
| GET | `/api/upi-cases` | List saved UPI cases (filtered by user for non-admins) |
| POST | `/api/upi-cases` | Save UPI analysis (blocked for viewer role) |
| GET | `/api/upi-cases/{id}` | Load a specific case |
| DELETE | `/api/upi-cases/{id}` | Delete a case |

---

## Development

### Run in dev mode (hot reload — two terminals)
```bash
# Terminal 1 — backend
python app.py --api

# Terminal 2 — frontend dev server (proxies /api to port 5000)
cd frontend && npm start
```

### Rebuild frontend and restart server
```bash
cd frontend && npm run build && cd ..
python app.py --api
```

### Logs
Application logs are written to `backend/logs/chainbreak.log` with daily rotation (max 10 files x 10 MB).

### Standalone blockchain CLI (no server)
```bash
python app.py --analyze 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
```

---

## UPI Mule Detection — How It Works

1. Upload a transaction CSV via the UI (UPI tab).
2. The backend builds a bipartite graph of UPI IDs and counterparties.
3. Risk scores are computed per node based on volume, velocity, fan-in/fan-out patterns.
4. Community detection (Louvain/Leiden/etc.) groups related accounts.
5. Suspicious communities are ranked by aggregate risk score.
6. Results are rendered in an interactive D3 canvas graph with a node detail inspector.
7. Analyst/investigator/admin users can save the analysis as a `.json` case file under `data/upi-cases/`.

---

## UPI Graph Controls

- **Click a node** — opens the node intelligence panel (connections, risk score, transaction history). Click again to deselect.
- **Graph Legend** — bottom-right overlay showing risk color coding. Click the header to collapse/expand it.
- **Show Connected Devices** — hidden by default (keeps the graph clean); toggle in the top-right controls if needed.
- **Freeze Layout / Resume Physics** — stop or restart the D3 force simulation.

---

## Data Storage

| What | Where |
|---|---|
| User accounts, roles, sessions | `instance/chainbreak.db` (SQLite) |
| Audit log | `instance/chainbreak.db` — `audit_log` table |
| Blockchain graphs (JSON) | `data/graphs/` |
| UPI case files | `data/upi-cases/` |
| Application logs | `backend/logs/chainbreak.log` |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `REACT_APP_API_URL` | `window.location.origin` | Backend base URL (set in `frontend/.env`) |
| `SECRET_KEY` | auto-generated | JWT signing secret — set this in production |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection (optional) |
| `NEO4J_USER` | `neo4j` | Neo4j credentials (optional) |
| `NEO4J_PASSWORD` | — | Neo4j password (optional) |

---

## Notes for New Contributors

- The backend was migrated from Flask to FastAPI. Route files in `backend/api/v1/` expose `APIRouter` instances; these are included in `api_root.py`.
- The frontend uses Axios with a request interceptor that attaches the JWT Bearer token from `localStorage` (`chainbreak_access_token`). CSRF tokens are read from the `csrf_access_token` cookie.
- On logout, `clearSession()` in `utils/api.js` wipes all `chainbreak_*` and `upi_detection_settings*` keys from localStorage.
- UPI detection settings are scoped per user: stored as `upi_detection_settings_{user_id}` in localStorage so different users do not share settings.
- The React build is served from `frontend/build/`. After any frontend change, run `npm run build` from the `frontend/` directory and restart the server.
- Port 5000 is the single runtime port. Do not run the backend on a different port in production — the frontend build bakes in the origin URL.
