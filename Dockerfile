FROM python:3.14.4-slim

ARG RELEASE_VERSION=""

# Install system dependencies for Playwright
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    gosu \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv (fast Python package manager, written in Rust)
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/uv

# Install Python dependencies
COPY app/requirements.txt .
RUN uv pip install --no-cache-dir --system -r requirements.txt

# Create non-root user (uid 1000 matches typical host user for volume mounts)
RUN useradd -m -u 1000 -s /bin/bash appuser

# Install Playwright browsers as appuser (installs to ~appuser/.cache/)
USER appuser
RUN playwright install chromium

# Create writable directories for app data
RUN mkdir -p /home/appuser/.cache/ms-playwright

# Copy application (owned by root, readable by all — only specific dirs need writes)
USER root
COPY app/ .
# Docker preserves host file modes during COPY. Normalize copied application
# files so the non-root runtime user can always read templates, static assets
# and Python modules even if the local checkout has restrictive permissions.
RUN find /app -type d -exec chmod 755 {} + && \
    find /app -type f -exec chmod 644 {} +
RUN chown -R appuser:appuser /app/logs /app/static/recipe_images 2>/dev/null || true
RUN mkdir -p /app/logs /app/static/recipe_images /app/static/vendor && \
    chown appuser:appuser /app/logs /app/static/recipe_images /app/static/vendor

# Download vendor assets to staging dir (copied to /app at startup by entrypoint.sh)
# This eliminates runtime dependency on cdn.jsdelivr.net
# To upgrade (prod): 1) change version below  2) docker compose up -d --build web
# To upgrade (dev):  1) change version below  2) docker compose restart web
RUN mkdir -p /tmp/vendor /vendor-assets/bootstrap-icons /vendor-assets/flag-icons && \
    wget -qO- https://registry.npmjs.org/bootstrap/-/bootstrap-5.3.8.tgz | \
      tar -xz -C /tmp/vendor && \
    cp /tmp/vendor/package/dist/css/bootstrap.min.css /vendor-assets/ && \
    cp /tmp/vendor/package/dist/js/bootstrap.bundle.min.js /vendor-assets/ && \
    rm -rf /tmp/vendor && \
    wget -qO- https://registry.npmjs.org/bootstrap-icons/-/bootstrap-icons-1.13.1.tgz | \
      tar -xz -C /vendor-assets/bootstrap-icons --strip-components=1 && \
    wget -qO- https://registry.npmjs.org/flag-icons/-/flag-icons-7.5.0.tgz | \
      tar -xz -C /vendor-assets/flag-icons --strip-components=1 && \
    wget -qO /vendor-assets/sweetalert2.all.min.js \
      "https://cdn.jsdelivr.net/npm/sweetalert2@11.26.24/dist/sweetalert2.all.min.js"

# Pre-populate vendor assets in the image for production. Dev bind mounts still
# rely on entrypoint.sh to sync the same staged assets back into /app/static/vendor.
RUN cp -r /vendor-assets/. /app/static/vendor/ && \
    chown -R appuser:appuser /app/static/vendor

# Stamp build date and release version — read by app.py for version display
RUN date +%y%m%d > /build_date && \
    printf '%s' "$RELEASE_VERSION" > /release_version

# Entrypoint: starts as root to fix cert permissions, then drops to appuser
COPY app/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

CMD ["tail", "-f", "/dev/null"]
