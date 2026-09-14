# Cloud IDE (Render Free ₹0 Web IDE)

A secure, multi-tenant-isolated, private web-based development environment running OpenVSCode Server, FastAPI, and a React dashboard on Render Free tier with zero infrastructure costs (₹0).

> [!WARNING]
> **CRITICAL DATA DURABILITY NOTICE (EPHEMERAL STORAGE)**:
> The Render Free container filesystem is **strictly ephemeral**.
> When the container spins down, restarts, or is redeployed, all local files in `/home/workspace` are wiped.
> **GitHub is your permanent source-code storage.**
> **Workspace storage is temporary. Commit and push your work to GitHub to keep it permanently.**
> Uncommitted local workspace changes can disappear upon container restart.

---

## 1. Project Overview

Cloud IDE provides a browser-based, VSCode-compatible IDE powered by Gitpod's OpenVSCode Server, tailored for a strictly authorized team of **exactly two users**. It bridges GitHub repository management, terminal command-line access with full C/C++ and Python toolchains, secure ephemeral Git push/pull operations, and one-click Render deployment—all hosted within a single free-tier container without needing paid infrastructure, VPS, Kubernetes, PostgreSQL, or Redis.

---

## 2. Architecture

```
                               Internet
                                  │
                          (HTTPS Port 443)
                                  ▼
                         Render Free Web Service
                                  │
                                  ▼
                          NGINX (Port $PORT)
            ┌─────────────────────┼─────────────────────┐
            │ (Reverse Proxy)     │ (Reverse Proxy)     │ (auth_request)
            ▼                     ▼                     ▼
     React Dashboard          FastAPI API        OpenVSCode Server
     (/index.html & assets)  (127.0.0.1:8000)     (127.0.0.1:3000)
                             - OAuth / Auth       - Internal loopback only
                             - Git credentials    - Protected by NGINX
                             - Workspace manager  - WebSocket terminal
                             - Render deployer
                                  │
                                  ▼
                     Ephemeral Container Filesystem
           /home/workspace/<authenticated_user_id>/<owner>/<repo>
                                  │
                       Git Push / Pull via HTTPS
                                  │
                                  ▼
                         GitHub (Permanent)
```

- **Render Free Container**: Single container orchestrating NGINX, FastAPI, and OpenVSCode Server using an unprivileged user (`openvscode-server`).
- **Internal Loopback Binding**: Both FastAPI (`127.0.0.1:8000`) and OpenVSCode Server (`127.0.0.1:3000`) listen **strictly on loopback**. Only NGINX is bound to the public-facing `$PORT`.
- **Authentication Gateway**: NGINX intercepts all `/vscode/` traffic using `auth_request /api/auth/verify`. Unauthenticated requests or requests from unauthorized users are immediately rejected (HTTP 401 redirecting to login).
- **Zero Paid Dependencies**: ₹0 cost architecture. State is managed via signed cryptographic cookies (using `itsdangerous`) and ephemeral in-memory caches, removing any need for external databases or Redis instances.

---

## 3. Technology Stack

- **Container Host**: Docker on Render Free Linux container (512MB RAM, 0.1 vCPU).
- **Reverse Proxy & Web Server**: NGINX (unprivileged runtime in `/tmp`).
- **Frontend SPA**: React 19, Vite, TypeScript, Lucide Icons, Modern Vanilla CSS.
- **Backend API**: FastAPI (Python 3.12), Uvicorn, Pydantic, HTTPX, ItsDangerous.
- **IDE Engine**: OpenVSCode Server (VSCode in the browser).
- **Development Toolchains**:
  - Python 3 (`python3`, `pip`, `python3-venv`).
  - C / C++ (`gcc`, `g++`, `make`, `libc-dev`).
  - Version Control (`git 2.x`).
- **External Integrations**:
  - GitHub REST API & OAuth 2.0.
  - Render API (v1 Deployments).

---

## 4. Local Development

### Prerequisites
- Python 3.12+
- Node.js 20+ & npm
- Git
- (Optional) Docker

### Running Locally

1. **Clone the repository**:
   ```bash
   git clone https://github.com/<owner>/<repo>.git
   cd vs-code-test
   ```

2. **Setup Backend**:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

3. **Setup Frontend**:
   ```bash
   cd ../frontend
   npm install
   npm run dev  # Vite dev server on port 5173
   ```

4. **Environment Variables**:
   Copy `.env.example` to `.env` and fill in your GitHub OAuth App credentials and Render API configurations.

---

## 5. Environment Variables

All configuration is controlled via environment variables. See [`.env.example`](file:///c:/Srinath/Practice%20Projects/Cloud_Code_VScode/vs-code-test/.env.example):

| Variable | Required | Description | Example / Default |
| :--- | :---: | :--- | :--- |
| `PORT` | Yes | HTTP port NGINX listens on (provided by Render) | `10000` |
| `GITHUB_CLIENT_ID` | Yes | GitHub OAuth App Client ID | `Iv1.xxx` |
| `GITHUB_CLIENT_SECRET` | Yes | GitHub OAuth App Client Secret | (Secret from GitHub) |
| `SESSION_SECRET` | Yes | 32+ byte cryptographic key for signed cookies | (Random hex string) |
| `ALLOWED_USERS` | Yes | Comma-separated list of allowed GitHub usernames | `user1,user2` |
| `ALLOWED_USER_IDS` | Recommended | Comma-separated list of numeric GitHub IDs | `123456,789012` |
| `RENDER_API_KEY` | Optional | Render API key for deploying projects from IDE | `rnd_xxx` |
| `RENDER_SERVICE_MAP` | Optional | JSON mapping of `owner/repo` to Render service IDs | `{"owner/repo": "srv-xxx"}` |
| `RENDER_BASE_URL` | No | Render API base URL | `https://api.render.com` |
| `WORKSPACE_BASE_DIR`| No | Root directory for user workspaces | `/home/workspace` |
| `OPENVSCODE_PORT` | No | Internal port for OpenVSCode Server | `3000` |
| `API_PORT` | No | Internal port for FastAPI | `8000` |
| `ENVIRONMENT` | No | Deployment environment (`production`/`development`) | `production` |

---

## 6. GitHub OAuth / App Setup

1. Go to **GitHub Settings** → **Developer Settings** → **OAuth Apps** → **New OAuth App**.
2. Set **Application Name**: `Cloud IDE` (or your preferred name).
3. Set **Homepage URL**: `https://<your-render-app>.onrender.com`.
4. Set **Authorization callback URL**: `https://<your-render-app>.onrender.com/api/auth/callback`.
5. Generate a **Client Secret**.
6. Copy `Client ID` and `Client Secret` into your Render environment settings.

---

## 7. Two-User Configuration

Access to the Cloud IDE is strictly limited to **two authorized users**:

1. Define usernames:
   ```env
   ALLOWED_USERS=srinath-m,partner-dev
   ```
2. (Recommended) Define numeric GitHub user IDs to prevent username-renaming bypass:
   ```env
   ALLOWED_USER_IDS=10203040,50607080
   ```
3. Any third user attempting OAuth login is denied access (HTTP 403 `Access denied: User not authorized`).

---

## 8. Render Deployment

1. Create a **New Web Service** on Render.
2. Connect your Git repository.
3. Choose **Docker** as the Runtime environment.
4. Set **Instance Type**: `Free` (512 MB RAM, 0.1 vCPU).
5. In **Environment Variables**, add the variables documented above.
6. Deploy the service!

---

## 9. Docker Setup

The multi-stage production [`Dockerfile`](file:///c:/Srinath/Practice%20Projects/Cloud_Code_VScode/vs-code-test/Dockerfile) builds:
- **Stage 1 (`frontend-builder`)**: Node 20 slim builds the React SPA (`npm run build`).
- **Stage 2 (`final`)**: Based on `gitpod/openvscode-server:latest`.
  - Installs system packages: `nginx`, `python3`, `python3-pip`, `python3-venv`, `gcc`, `g++`, `make`, `git`.
  - Configures unprivileged NGINX directories and permissions in `/tmp`.
  - Installs Python dependencies into the system environment.
  - Copies built frontend assets to `/app/frontend/dist`.
  - Copies the secure Git credential helper to `/usr/local/bin/git-credential-cloudide`.
  - Sets runtime user: `USER openvscode-server` (UID 1000).
  - Starts all services via [`scripts/entrypoint.sh`](file:///c:/Srinath/Practice%20Projects/Cloud_Code_VScode/vs-code-test/scripts/entrypoint.sh).

---

## 10. GitHub Repository Workflow

1. Authenticate via GitHub OAuth.
2. View all accessible repositories (personal & organization, public & private).
3. Filter or search repositories by name or owner.
4. Select a repository to load active branches.
5. Click **Open in IDE**:
   - Backend checks out/clones the repository into `/home/workspace/<user_id>/<owner>/<repo>`.
   - Browser redirects to `/vscode/?folder=%2Fhome%2Fworkspace%2F...`.
   - OpenVSCode opens the repository workspace directly.

---

## 11. Workspace Behavior

- **User Isolation**:
  Workspaces are partitioned strictly by authenticated GitHub numeric user ID:
  ```
  /home/workspace/<authenticated_user_id>/<owner>/<repo>
  ```
  User 1 cannot view, open, or tamper with User 2's workspace directory.
- **Path Traversal Protection**:
  All path construction is strictly validated. Relative traversal sequences (`../`, `..\\`), null bytes, or symbolic link escapes outside `/home/workspace` are blocked with HTTP 400.
- **Non-Destructive Guarantee**:
  If a workspace has uncommitted local changes, the backend **never** executes `git reset --hard` or `git clean -fd`. The dirty workspace is preserved and returned as-is with a dirty state flag.

---

## 12. Git Operations & Ephemeral Credential Helper

Inside the OpenVSCode integrated terminal, authorized users can execute native Git commands:
```bash
git status
git add .
git commit -m "Update feature"
git pull
git push origin main
```

### Security Guarantees:
- **Zero Token in URL**: Remotes always use clean HTTPS URLs: `https://github.com/<owner>/<repo>.git`.
- **Zero Token in `.git/config`**: No personal access tokens or passwords are ever written to disk.
- **Zero Plaintext Credentials**: Credentials are provided on-demand by `git-credential-cloudide` querying the loopback FastAPI `/api/git/credential` endpoint using the authenticated user's session.
- **Strict User Isolation**: User 1 receives only User 1's GitHub credentials; User 2 receives only User 2's credentials.

---

## 13. Render Deployment Integration

Deploy your work directly from the dashboard:
1. **Commit & Push**: Ensure all changes are committed and pushed to GitHub.
2. **Deploy Button**: Trigger deployment for repositories configured in `RENDER_SERVICE_MAP`.
3. **Exact Commit Deployment**:
   - The backend validates the workspace is clean.
   - Retrieves the exact HEAD commit SHA via `git rev-parse HEAD`.
   - Verifies this commit exists on the upstream GitHub branch.
   - Calls the Render API with `commitId: "<HEAD_SHA>"` and `clearCache: "do_not_clear"`.
4. **Status Polling**:
   - Polls the specific deployment ID (`/v1/services/{serviceId}/deploys/{deployId}`).
   - Displays real-time status: `building`, `live`, `failed`, or `canceled`.
   - Displays the live URL retrieved directly from the Render API.

---

## 14. Security Considerations

- **Private Access Only**: Only two allowed GitHub users can log in. Third-party users receive an HTTP 403 error.
- **Loopback Enforcement**: FastAPI and OpenVSCode Server bind only to `127.0.0.1`. They cannot be accessed directly from the internet.
- **NGINX Reverse Proxy Auth**: Every request to `/vscode/` is authenticated via NGINX `auth_request` pointing to `/api/auth/verify`.
- **No Client Secrets in Frontend**: All OAuth secrets, Render API keys, and GitHub access tokens remain server-side.
- **Session Protection**: Sessions use HMAC-signed, HttpOnly, SameSite cookies with strict expiration.
- **Shell Injection Rejection**: Branch names and inputs are sanitized against shell metacharacters (`;`, `&`, `|`, `` ` ``, `$()`, etc.).

---

## 15. Render Free Limitations

- **512 MB Memory Limit**: Memory is constrained. Heavy IDE extensions (such as full language server packs) are avoided to maintain stability.
- **Spindown after Inactivity**: Render Free services spin down after 15 minutes of inactivity. The first request after spindown may take ~30–50 seconds for cold start.
- **750 Free Hours / Month**: Sufficient to run one free web service continuously.

---

## 16. Ephemeral Storage Warning

> [!CAUTION]
> The Render container filesystem is **temporary and ephemeral**.
> Any uncommitted files or unpushed Git commits will be permanently lost when the container stops, restarts, or deploys.
> **Always push your commits to GitHub before finishing your session.**

---

## 17. Recovery / Recreation of Workspaces from GitHub

If your Render container restarts or redeploys, recover your workspace in seconds:

```
          Render Restart / Container Spin-down
                           ↓
          Open Cloud IDE URL (triggers cold start)
                           ↓
          Login with GitHub OAuth (Session restored)
                           ↓
          Select your repository in Dashboard
                           ↓
          Click "Open in IDE"
                           ↓
  Backend automatically clones repository from GitHub
                           ↓
  OpenVSCode opens workspace at exact latest commit
                           ↓
                   Continue Working!
```

---

## 18. Troubleshooting

| Issue | Cause | Resolution |
| :--- | :--- | :--- |
| **401 Unauthorized on `/vscode/`** | Session expired or missing | Re-authenticate via the dashboard login page. |
| **403 Forbidden on Login** | GitHub user not in `ALLOWED_USERS` | Check `ALLOWED_USERS` and `ALLOWED_USER_IDS` environment variables. |
| **Workspace not opening** | Branch or repository does not exist | Verify repository access and branch name on GitHub. |
| **Git Push fails with 401** | Ephemeral token expired | Refresh page or re-login to renew GitHub OAuth credentials. |
| **Container out of memory (OOM)** | Running heavy background processes | Avoid launching multiple memory-heavy compilers or extensions concurrently. |

---

## 19. Testing

### Run Backend Tests:
```bash
pytest backend/tests/ -v
```
*(All 129 tests passing, covering OAuth, authorization, security audit, Git credentials, workspace isolation, toolchain, and deployments).*

### Run Frontend Tests & Build:
```bash
cd frontend
npm test
npm run build
npx tsc --noEmit
```

### Run Configuration Validator:
```bash
python tests/validate_config.py
```

---

## 20. Project Structure

```
vs-code-test/
├── .env.example                     # Environment configuration template
├── .gitignore                       # Ignored files (secrets, dist, caches)
├── Dockerfile                       # Production multi-stage Docker build
├── README.md                        # Complete system documentation
├── backend/
│   ├── requirements.txt             # Lean backend dependencies
│   ├── app/
│   │   ├── config.py                # Pydantic settings & validation
│   │   ├── main.py                  # FastAPI application entrypoint
│   │   ├── auth/                    # OAuth & session verification
│   │   ├── deployments/             # Render deployment integration
│   │   ├── git/                     # Ephemeral Git credential helper & validation
│   │   ├── github/                  # GitHub API client (repos, branches)
│   │   └── projects/                # Workspace cloning & containment logic
│   └── tests/
│       ├── test_auth.py             # OAuth & allowlist tests
│       ├── test_deployments.py      # Render API deployment tests
│       ├── test_git_credentials.py  # Credential helper tests
│       ├── test_git_operations.py   # Git operations & push tests
│       ├── test_security_audit.py   # 26 comprehensive penetration tests
│       ├── test_toolchain.py        # Python & C/C++ toolchain tests
│       └── test_workspace.py        # Path containment & isolation tests
├── frontend/
│   ├── package.json                 # Minimal React dependencies
│   ├── tsconfig.json                # Strict TypeScript configuration
│   ├── vite.config.ts               # Vite bundler configuration
│   └── src/
│       ├── App.tsx                  # Root React application
│       ├── components/              # TopBar, Sidebar, RepositoryCard
│       ├── pages/                   # Login, Dashboard
│       └── services/                # API and Deployment clients
├── nginx/
│   └── nginx.conf.template          # Reverse proxy with auth_request subrequests
├── scripts/
│   ├── entrypoint.sh                # Container orchestrator entrypoint
│   ├── git-credential-cloudide      # Ephemeral Git credential helper
│   └── toolchain_test.sh            # In-container toolchain test script
└── tests/
    └── validate_config.py           # Comprehensive configuration validator
```

---

## License & Guarantee

This project is built strictly to satisfy a **₹0 budget constraint** on Render Free infrastructure. No paid dependencies, external databases, or third-party paid services are required.