import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def validate_dockerfile():
    print("Checking Dockerfile...")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    
    assert "FROM node:20-slim AS frontend-builder" in dockerfile, "Missing frontend-builder stage"
    assert "npm run build" in dockerfile, "Missing frontend build in Stage 1"
    assert "FROM gitpod/openvscode-server:latest" in dockerfile, "Missing base image gitpod/openvscode-server:latest"
    assert "USER root" in dockerfile, "Missing USER root"
    
    # Check packages
    for pkg in ["python3", "python3-pip", "python3-venv", "gcc", "g++", "make", "git", "nginx"]:
        assert pkg in dockerfile, f"Missing required package in Dockerfile: {pkg}"
        
    assert "COPY backend /app/backend" in dockerfile, "Missing COPY backend /app/backend"
    assert "pip3 install" in dockerfile and "-r /app/backend/requirements.txt" in dockerfile, "Missing pip3 install requirements"
    assert "COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist" in dockerfile, "Missing COPY from frontend-builder"
    assert "USER openvscode-server" in dockerfile, "Missing USER openvscode-server"
    assert "WORKDIR /home/workspace" in dockerfile, "Missing WORKDIR /home/workspace"
    assert 'ENTRYPOINT [ "/app/scripts/entrypoint.sh" ]' in dockerfile, "Missing ENTRYPOINT"
    print("  [PASS] Dockerfile adheres to all Step 6 specifications.")

def validate_nginx_template():
    print("Checking nginx.conf.template...")
    content = (ROOT / "nginx" / "nginx.conf.template").read_text(encoding="utf-8")
    
    # Check brace balance
    open_braces = content.count("{")
    close_braces = content.count("}")
    assert open_braces == close_braces, f"Mismatched braces in nginx.conf: {open_braces} open vs {close_braces} close"
    
    # Must NOT run as root or specify user directive
    assert not re.search(r"^\s*user\s+", content, re.MULTILINE), "Found user directive; non-root NGINX should not specify user directive"
    
    # Check unprivileged paths in /tmp
    assert "pid /tmp/nginx.pid;" in content, "Missing pid in /tmp"
    assert "client_body_temp_path /tmp/client_body;" in content, "Missing client_body in /tmp"
    
    # Check listen placeholder
    assert "listen __PORT__;" in content, "Missing listen __PORT__ placeholder"
    
    # Check WebSocket upgrade map
    assert "map $http_upgrade $connection_upgrade" in content, "Missing WebSocket upgrade map"
    
    # Check dedicated auth_request endpoint (must not be protected by auth_request to avoid recursion)
    assert "location = /api/auth/verify {" in content, "Missing dedicated location = /api/auth/verify"
    assert "proxy_pass_request_body off;" in content, "Missing proxy_pass_request_body off for auth subrequest"
    
    # Check routes
    assert "location / {" in content, "Missing root location /"
    assert "root /app/frontend/dist;" in content, "Missing frontend root /app/frontend/dist"
    assert "try_files $uri $uri/ /index.html;" in content, "Missing try_files for React SPA"
    assert "location /api/ {" in content, "Missing API location /api/"
    assert "proxy_pass http://127.0.0.1:8000" in content, "Missing FastAPI proxy pass"
    assert "location /health {" in content, "Missing health check location /health"
    assert "proxy_pass http://127.0.0.1:8000/health;" in content, "Missing health proxy pass"
    
    # Check /vscode/ route protected by auth_request
    assert "location /vscode/ {" in content, "Missing OpenVSCode location /vscode/"
    assert "auth_request /api/auth/verify;" in content, "Missing auth_request directive in /vscode/"
    assert "error_page 401 = @login_redirect;" in content, "Missing error_page 401 redirect in /vscode/"
    assert "location @login_redirect {" in content, "Missing @login_redirect location"
    assert "proxy_pass http://127.0.0.1:3000/vscode/;" in content, "Missing OpenVSCode proxy pass"
    assert "proxy_set_header Upgrade $http_upgrade;" in content, "Missing WebSocket Upgrade header"
    assert "proxy_set_header Connection $connection_upgrade;" in content, "Missing WebSocket Connection header"
    assert "proxy_read_timeout 86400s;" in content, "Missing long WebSocket read timeout"
    assert "location = /vscode {" in content, "Missing redirect for /vscode"
    
    print("  [PASS] nginx.conf.template adheres to all Step 6 auth_request specifications.")

def validate_entrypoint():
    print("Checking entrypoint.sh...")
    content = (ROOT / "scripts" / "entrypoint.sh").read_text(encoding="utf-8")
    
    assert "sed \"s/__PORT__/$PORT/g\" /etc/nginx/nginx.conf.template > /tmp/nginx.conf" in content, "Missing NGINX port substitution"
    assert "nginx -c /tmp/nginx.conf" in content, "Missing NGINX startup with custom config"
    
    # Verify OpenVSCode startup bindings
    assert "--host 127.0.0.1" in content, "OpenVSCode must bind to loopback 127.0.0.1"
    assert "--port 3000" in content, "OpenVSCode must listen on internal port 3000"
    assert "--server-base-path /vscode" in content, "OpenVSCode must use --server-base-path /vscode"
    assert "--without-connection-token" in content, "OpenVSCode must use --without-connection-token"
    
    # Verify FastAPI startup logic
    assert 'python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &' in content, "Missing FastAPI startup command"
    
    # Verify signals
    assert "trap cleanup SIGINT SIGTERM" in content, "Missing signal trap"
    assert "wait -n" in content, "Missing wait -n"
    print("  [PASS] entrypoint.sh adheres to all Step 6 specifications.")

def validate_frontend():
    print("Checking frontend structure and build output...")
    assert (ROOT / "frontend" / "package.json").exists(), "Missing frontend/package.json"
    assert (ROOT / "frontend" / "tsconfig.json").exists(), "Missing frontend/tsconfig.json"
    assert (ROOT / "frontend" / "vite.config.ts").exists(), "Missing frontend/vite.config.ts"
    assert (ROOT / "frontend" / "index.html").exists(), "Missing frontend/index.html"
    assert (ROOT / "frontend" / "src" / "main.tsx").exists(), "Missing frontend/src/main.tsx"
    assert (ROOT / "frontend" / "src" / "App.tsx").exists(), "Missing frontend/src/App.tsx"
    assert (ROOT / "frontend" / "src" / "index.css").exists(), "Missing frontend/src/index.css"
    assert (ROOT / "frontend" / "src" / "components" / "TopBar" / "TopBar.tsx").exists(), "Missing TopBar.tsx"
    assert (ROOT / "frontend" / "src" / "components" / "Sidebar" / "Sidebar.tsx").exists(), "Missing Sidebar.tsx"
    assert (ROOT / "frontend" / "src" / "components" / "RepositoryCard" / "RepositoryCard.tsx").exists(), "Missing RepositoryCard.tsx"
    assert (ROOT / "frontend" / "src" / "pages" / "Login.tsx").exists(), "Missing Login.tsx"
    assert (ROOT / "frontend" / "src" / "pages" / "Dashboard.tsx").exists(), "Missing Dashboard.tsx"
    assert (ROOT / "frontend" / "src" / "services" / "api.ts").exists(), "Missing api.ts"
    assert (ROOT / "frontend" / "src" / "types" / "index.ts").exists(), "Missing types/index.ts"
    assert (ROOT / "frontend" / "dist" / "index.html").exists(), "Missing frontend/dist/index.html build artifact"
    print("  [PASS] frontend structure and production build verified.")

def validate_toolchain():
    print("Checking toolchain test script and non-destructive configuration...")
    toolchain_script = ROOT / "scripts" / "toolchain_test.sh"
    assert toolchain_script.exists(), "Missing scripts/toolchain_test.sh"
    content = toolchain_script.read_text(encoding="utf-8")
    
    # Verify non-destructive temporary directory isolation
    assert "/tmp/cloudide-toolchain-test" in content, "toolchain_test.sh must use /tmp/cloudide-toolchain-test"
    assert "trap cleanup" in content, "toolchain_test.sh must register trap cleanup"
    assert "git reset --hard" not in content, "toolchain_test.sh must not use git reset --hard"
    assert "git clean -fd" not in content, "toolchain_test.sh must not use git clean -fd"
    
    # Verify tested toolchains
    for tool in ["python", "venv", "gcc", "g++", "Makefile", "git"]:
        assert tool in content, f"Missing {tool} test in toolchain_test.sh"
        
    # Verify test_toolchain.py exists in backend tests
    assert (ROOT / "backend" / "tests" / "test_toolchain.py").exists(), "Missing backend/tests/test_toolchain.py"
    print("  [PASS] toolchain script and non-destructive configuration verified.")

def validate_git_credentials():
    print("Checking Step 11 Git credentials and helper configuration...")
    helper_script = ROOT / "scripts" / "git-credential-cloudide"
    assert helper_script.exists(), "Missing scripts/git-credential-cloudide"
    helper_content = helper_script.read_text(encoding="utf-8")
    assert helper_content.startswith("#!/usr/bin/env python3"), "Helper must have python3 shebang"
    assert "ghp_" not in helper_content, "Helper contains hardcoded token string"
    assert "github_pat_" not in helper_content, "Helper contains hardcoded token string"
    assert "github.com" in helper_content, "Helper must validate host == github.com"
    assert "http://127.0.0.1:8000" in helper_content, "Helper must default to loopback 127.0.0.1:8000"
    assert "/api/git/credential" in helper_content, "Helper must query /api/git/credential endpoint"

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY scripts/git-credential-cloudide /usr/local/bin/git-credential-cloudide" in dockerfile, "Dockerfile must copy helper"
    assert "chmod +x /usr/local/bin/git-credential-cloudide" in dockerfile, "Dockerfile must make helper executable"
    assert "ENV GIT_ASKPASS=/usr/local/bin/git-credential-cloudide" in dockerfile, "Dockerfile must set ENV GIT_ASKPASS"

    # Git backend modules
    git_dir = ROOT / "backend" / "app" / "git"
    assert (git_dir / "__init__.py").exists(), "Missing backend/app/git/__init__.py"
    assert (git_dir / "validation.py").exists(), "Missing backend/app/git/validation.py"
    assert (git_dir / "credentials.py").exists(), "Missing backend/app/git/credentials.py"
    assert (git_dir / "operations.py").exists(), "Missing backend/app/git/operations.py"

    # Backend routes
    main_py = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "git_credential_router" in main_py, "main.py must include git_credential_router"

    # Git tests
    assert (ROOT / "backend" / "tests" / "test_git_credentials.py").exists(), "Missing test_git_credentials.py"
    assert (ROOT / "backend" / "tests" / "test_git_operations.py").exists(), "Missing test_git_operations.py"
    print("  [PASS] Step 11 Git credentials and operations configuration verified.")

def validate_render_deployment():
    print("Checking Step 12 Render deployment integration...")
    # Backend deployment modules
    dep_dir = ROOT / "backend" / "app" / "deployments"
    assert (dep_dir / "__init__.py").exists(), "Missing backend/app/deployments/__init__.py"
    assert (dep_dir / "render.py").exists(), "Missing backend/app/deployments/render.py"
    assert (dep_dir / "routes.py").exists(), "Missing backend/app/deployments/routes.py"

    render_py = (dep_dir / "render.py").read_text(encoding="utf-8")
    assert 'clear_cache: str = "do_not_clear"' in render_py, "clearCache must default to 'do_not_clear'"
    assert "normalize_status" in render_py, "Missing normalize_status in render.py"

    # Config settings
    config_py = (ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")
    assert "RENDER_API_KEY" in config_py, "Missing RENDER_API_KEY in config.py"
    assert "RENDER_SERVICE_MAP" in config_py, "Missing RENDER_SERVICE_MAP in config.py"
    assert "def get_render_service_id" in config_py, "Missing get_render_service_id in config.py"

    # Backend routes included
    main_py = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "deployments_router" in main_py, "main.py must include deployments_router"

    # Deployment tests
    assert (ROOT / "backend" / "tests" / "test_deployments.py").exists(), "Missing test_deployments.py"

    # Frontend deployment service
    assert (ROOT / "frontend" / "src" / "services" / "deployments.ts").exists(), "Missing deployments.ts"

    # Zero token/key leakage in frontend distribution
    dist_dir = ROOT / "frontend" / "dist"
    if dist_dir.exists():
        for f in dist_dir.glob("**/*"):
            if f.is_file():
                content = f.read_text(encoding="utf-8", errors="ignore")
                assert "RENDER_API_KEY" not in content, f"RENDER_API_KEY found in {f.name}"
                assert "rnd_" not in content, f"Possible Render key found in {f.name}"

    print("  [PASS] Step 12 Render deployment integration verified.")

def validate_security_and_step13():
    print("Checking Step 13 Security, Git ignore, and configuration hygiene...")
    # 1. .gitignore checks
    gitignore_file = ROOT / ".gitignore"
    assert gitignore_file.exists(), "Missing .gitignore file"
    gi_content = gitignore_file.read_text(encoding="utf-8")
    assert ".env" in gi_content, ".gitignore must ignore .env"
    assert "node_modules" in gi_content, ".gitignore must ignore node_modules"
    assert "dist" in gi_content, ".gitignore must ignore dist"
    assert "__pycache__" in gi_content, ".gitignore must ignore __pycache__"

    # 2. .env.example checks
    env_example = ROOT / ".env.example"
    assert env_example.exists(), "Missing .env.example"
    ee_content = env_example.read_text(encoding="utf-8")
    for secret_token in ["ghp_", "github_pat_", "rnd_", "sk_"]:
        assert secret_token not in ee_content, f"Found potential secret prefix {secret_token} in .env.example"

    # 3. Security audit test suite
    assert (ROOT / "backend" / "tests" / "test_security_audit.py").exists(), "Missing backend/tests/test_security_audit.py"

    # 4. Ephemeral storage and zero-cost constraints in README
    readme_file = ROOT / "README.md"
    if readme_file.exists():
        rm_content = readme_file.read_text(encoding="utf-8")
        assert "ephemeral" in rm_content.lower() or "temporary" in rm_content.lower(), "README must state workspace storage is temporary/ephemeral"

    print("  [PASS] Step 13 Security and configuration hygiene verified.")

if __name__ == "__main__":
    try:
        validate_dockerfile()
        validate_nginx_template()
        validate_entrypoint()
        validate_frontend()
        validate_toolchain()
        validate_git_credentials()
        validate_render_deployment()
        validate_security_and_step13()
        print("\nAll Step 13 validation checks PASSED successfully.")
    except AssertionError as e:
        print(f"\n[FAIL] Validation error: {e}", file=sys.stderr)
        sys.exit(1)



