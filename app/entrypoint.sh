#!/bin/bash
# Entrypoint: starts as root, fixes permissions, drops to appuser via gosu
#
# Why: SSL key.pem is often root-only (0600). Non-root appuser can't read it.
# Fix: chmod in-place (bind mount changes host too, fine for self-signed certs)

if [ -d /certs ]; then
    chown -R appuser:appuser /certs 2>/dev/null || true
    if [ -f /certs/key.pem ]; then
        chmod 600 /certs/key.pem 2>/dev/null || true
    fi
fi

# Ensure writable dirs exist (volume mounts may reset ownership)
chown -R appuser:appuser /app/logs /app/static/recipe_images /app/data 2>/dev/null || true

# Sync vendor assets from build stage (staged in /vendor-assets at build time because
# dev volume mount hides image's /app). Use -rn so new components are added without
# overwriting existing files — handles the case where vendor dir exists but is incomplete.
# Run as appuser since bind-mounted /app/static is owned by appuser (root lacks DAC_OVERRIDE).
if [ "${SKIP_VENDOR_SYNC:-false}" != "true" ]; then
    gosu appuser mkdir -p /app/static/vendor
    gosu appuser cp -r /vendor-assets/. /app/static/vendor/
fi

exec gosu appuser "$@"
