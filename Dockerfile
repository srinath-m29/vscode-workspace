# Stage 1: Build static React frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Final runtime image preserving working OpenVSCode baseline
FROM gitpod/openvscode-server:latest

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        gcc \
        g++ \
        make \
        git \
        nginx \
    && rm -rf /var/lib/apt/lists/*

# Setup application directories and NGINX template
COPY nginx/nginx.conf.template /etc/nginx/nginx.conf.template
COPY scripts/entrypoint.sh /app/scripts/entrypoint.sh
RUN chmod +x /app/scripts/entrypoint.sh
COPY scripts/git-credential-cloudide /usr/local/bin/git-credential-cloudide
RUN chmod +x /usr/local/bin/git-credential-cloudide
ENV GIT_ASKPASS=/usr/local/bin/git-credential-cloudide

# Copy backend application and install requirements
COPY backend /app/backend
RUN pip3 install --no-cache-dir -r /app/backend/requirements.txt

# Copy static frontend build output from builder stage
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

RUN chown -R openvscode-server:openvscode-server \
    /home/workspace \
    /home/.openvscode-server \
    /app

USER openvscode-server

WORKDIR /home/workspace

ENTRYPOINT [ "/app/scripts/entrypoint.sh" ]
