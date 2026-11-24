# --- Stage 1: build the Vite + TypeScript frontend into dashboard/app/ ---
FROM node:22-slim AS frontend
WORKDIR /build/frontend
ARG VITE_GOOGLE_CLIENT_ID=""
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python app ---
FROM python:3.12-slim

# Prevent interactive prompts during apt-get
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV DASHBOARD_HOST=0.0.0.0

# Install system dependencies, tectonic prerequisites, and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    curl \
    git \
    libxml2-dev \
    libxslt-dev \
    fontconfig \
    libfontconfig1 \
    libharfbuzz0b \
    libgraphite2-3 \
    libicu-dev \
    fonts-liberation \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Install Tectonic for LaTeX compilation (Multi-arch support)
# F13: the tarball checksum is verified before extraction.
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then \
        TECTONIC_URL="https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-aarch64-unknown-linux-musl.tar.gz"; \
        TECTONIC_SHA256="1f59f9fb8eb65e8ba18658fc9016767e7d3e12488ded8b8fffa34254e51ce42c"; \
    else \
        TECTONIC_URL="https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz"; \
        TECTONIC_SHA256="dfb82876f2986862996e564fa507a9e576e0c1e3bee63c2c1bd677c2543e6407"; \
    fi && \
    curl -sL "$TECTONIC_URL" -o /tmp/tectonic.tar.gz && \
    echo "$TECTONIC_SHA256  /tmp/tectonic.tar.gz" | sha256sum -c - && \
    tar -xz -C /usr/local/bin -f /tmp/tectonic.tar.gz && \
    rm /tmp/tectonic.tar.gz && \
    chmod +x /usr/local/bin/tectonic

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# F13: run as a non-root user (uid 1000 matches the usual cloud host user,
# so host bind-mounted data/ and applications/ stay writable).
RUN groupadd -g 1000 app && useradd -u 1000 -g app -m app && chown -R app:app /app

# Built frontend bundle (vite outDir -> dashboard/app)
COPY --from=frontend /build/dashboard/app ./dashboard/app
RUN chown -R app:app /app/dashboard/app

# Expose port for the dashboard
EXPOSE 8000

# F13: drop root privileges before starting the app.
USER app

# Run under tini as init system to reap zombies and forward signals
ENTRYPOINT ["/usr/bin/tini", "--"]

# Run the dashboard by default
CMD ["python", "main.py", "dashboard"]
