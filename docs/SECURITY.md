# Security

Deal Meals is a single-user hobby/LAN app. It does not include built-in login or
multi-user access control, and it should not be exposed directly to the public
internet. For remote access, put it behind a VPN or a reverse proxy with
authentication.

Within that model, the app still has several hardening measures in place.

## Application Layer

- **Origin validation for mutating HTTP requests.** `POST`, `PUT`, `PATCH` and
  `DELETE` requests must include an `Origin` matching `ALLOWED_HOSTS`.
- **WebSocket origin validation.** Store and recipe scrape WebSockets reject
  missing or unapproved origins before accepting the connection.
- **Rate limiting.** Global and endpoint-specific limits are enabled with
  `slowapi`; trusted reverse proxy support is explicit through `TRUSTED_PROXY`.
- **Security headers.** Responses include `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy` and a nonce-based
  `Content-Security-Policy`.
- **Safer URL rendering.** UI helpers escape text/attributes, sanitize external
  URLs and add `rel="noopener noreferrer"` for new-tab links.
- **SSL certificate validation.** Uploaded certificates and private keys are
  checked for PEM format and key/certificate match before being saved.
- **SSL upload size guard.** Certificate upload requests that declare a payload
  over 100 KB are rejected.

## Outgoing Requests

- **SSRF guard for `httpx`.** Shared helpers reject non-HTTP(S) URLs and hosts
  that resolve to private, loopback, link-local, multicast or otherwise
  non-global IP addresses.
- **Redirect protection for `httpx`.** Built-in scrapers and image download
  paths use the same SSRF-safe request hook so redirects are checked too.
- **Custom recipe URL checks.** "My Recipes" validates user-provided recipe URLs
  before fetching them, and validates final URLs after redirects.
- **Image download checks.** Recipe image downloads validate URLs before fetching
  remote images.

## Container / Deployment Hardening

The standalone production compose file uses:

- non-root application runtime user
- `no-new-privileges:true`
- `cap_drop: ALL` with only the capabilities needed for startup/runtime
- `read_only: true` for `web`
- tmpfs mounts for `/tmp` and `/run`
- explicit writable volumes for logs, data, recipe images and certificates
- memory, PID and log-size limits
- an explicit backend Docker network
- no published database port

The database image also runs with dropped capabilities and an unpublished
PostgreSQL port.

## Database

- The app connects as `deal_meals_app`, not the PostgreSQL admin user.
- The app role has no superuser or database-creation privileges.
- The database initialization script grants table/sequence privileges required
  for normal app operation plus `TRUNCATE` for cache rebuilds.

## Operational Boundaries

- Origin validation is not access control; it mainly protects normal browser
  flows from cross-site requests.
- Treat network reachability as authorization: anyone who can reach the app can
  use it.
- Store and recipe scrapers depend on third-party websites and APIs, so scraping
  behavior can change when those sites change.

## Known Accepted Tradeoffs

- The SSRF protection is appropriate for the app's current threat model, but it
  does not pin the final TCP connection to a previously resolved IP.
- The Playwright fallback for "My Recipes" is treated as an accepted residual
  risk in the current LAN-only model.
