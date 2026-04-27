"""
Centralized timeout configuration.

Only GENERIC timeouts that apply across the app.
Specific waits (selectors, animations) stay in their respective files
as they're tuned to specific UI behavior.
"""

# HTTP client timeouts (seconds)
HTTP_TIMEOUT = 30

# Playwright page navigation (milliseconds)
PAGE_LOAD_TIMEOUT = 30000
PAGE_NETWORK_IDLE_TIMEOUT = 30000  # ICA needs more time than Willys

# Default for wait_for_load_state
DOMCONTENT_TIMEOUT = 30000
