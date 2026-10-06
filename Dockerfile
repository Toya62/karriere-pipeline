# --- Stage 1: build the Vite + TypeScript frontend into dashboard/app/ ---
FROM node:22-slim AS frontend
WORKDIR /build/frontend
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
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then \
        TECTONIC_URL="https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-aarch64-unknown-linux-musl.tar.gz"; \
    else \
        TECTONIC_URL="https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz"; \
    fi && \
    curl -sL "$TECTONIC_URL" | tar -xz -C /usr/local/bin && \
    chmod +x /usr/local/bin/tectonic

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Built frontend bundle (vite outDir -> dashboard/app)
COPY --from=frontend /build/dashboard/app ./dashboard/app

# Expose port for the dashboard
EXPOSE 8000

# Run the dashboard by default
CMD ["python", "main.py", "dashboard"]
