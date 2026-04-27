#!/usr/bin/env python3
"""Simple healthcheck script that auto-detects HTTP/HTTPS."""
import json
import os
import ssl
import sys
import urllib.request

port = int(os.environ.get("APP_PORT", "20080"))
config_file = "/certs/ssl_config.json"

# Check if SSL is enabled
use_ssl = False
if os.path.exists(config_file):
    try:
        with open(config_file) as f:
            use_ssl = json.load(f).get("enabled", False)
    except Exception:
        pass

# Build URL
url = f"https://localhost:{port}/health" if use_ssl else f"http://localhost:{port}/health"

try:
    if use_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        urllib.request.urlopen(url, timeout=5, context=ctx)
    else:
        urllib.request.urlopen(url, timeout=5)
    sys.exit(0)
except Exception as e:
    print(f"Health check failed: {e}", file=sys.stderr)
    sys.exit(1)
