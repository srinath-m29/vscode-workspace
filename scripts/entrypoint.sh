#!/bin/bash
set -e

echo "=== STARTING CLOUD IDE SYSTEM ==="

PORT=${PORT:-10000}
echo "Configuring public port: $PORT"

# Ensure directories exist
mkdir -p /tmp/client_body /tmp/proxy /tmp/fastcgi /tmp/uwsgi /tmp/scgi /home/workspace /app/frontend/dist

# Configure NGINX
sed "s/__PORT__/$PORT/g" /etc/nginx/nginx.conf.template > /tmp/nginx.conf

# Start NGINX
echo "Starting NGINX reverse proxy..."
nginx -c /tmp/nginx.conf

# Start OpenVSCode Server on internal loopback (127.0.0.1:3000)
echo "Starting OpenVSCode Server on 127.0.0.1:3000..."
/home/.openvscode-server/bin/openvscode-server \
    --host 127.0.0.1 \
    --port 3000 \
    --server-base-path /vscode \
    --without-connection-token &
OPENVSCODE_PID=$!

# Start FastAPI backend if available
if [ -f "/app/backend/app/main.py" ]; then
    echo "Starting FastAPI backend on 127.0.0.1:8000..."
    cd /app/backend
    python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
    FASTAPI_PID=$!
fi

# Signal trap for graceful shutdown
cleanup() {
    echo "Received termination signal. Shutting down gracefully..."
    kill -TERM "$OPENVSCODE_PID" 2>/dev/null || true
    if [ -n "$FASTAPI_PID" ]; then
        kill -TERM "$FASTAPI_PID" 2>/dev/null || true
    fi
    nginx -c /tmp/nginx.conf -s stop 2>/dev/null || kill -TERM $(cat /tmp/nginx.pid 2>/dev/null) 2>/dev/null || true
    wait
    echo "All processes stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "=== ALL SERVICES RUNNING SUCCESSFULLY ==="
wait -n
