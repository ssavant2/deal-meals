# Async HTTP Guidelines

## Rule: Always use `httpx` for HTTP requests

This project uses async/await throughout. Using blocking `requests` in async code blocks the event loop and prevents concurrency.

## ❌ Wrong - Blocks event loop

```python
import requests

async def fetch_data():
    # This BLOCKS the entire event loop!
    response = requests.get("https://api.example.com/data")
    return response.json()
```

## ✅ Correct - Non-blocking async

```python
import httpx

async def fetch_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data", timeout=30)
    return response.json()
```

## Why this matters

When you use `requests.get()` inside an `async def`:
1. The entire event loop pauses
2. Other async tasks (Playwright scrapes, DB operations, WebSocket messages) cannot run
3. Concurrency benefits are lost

With `httpx.AsyncClient`:
1. The HTTP request happens in the background
2. Other async tasks continue running
3. Multiple HTTP requests can run in parallel

## Quick reference

| requests (blocking) | httpx (async) |
|---------------------|---------------|
| `requests.get(url)` | `await client.get(url)` |
| `requests.post(url, json=data)` | `await client.post(url, json=data)` |
| `response.json()` | `response.json()` |
| `response.text` | `response.text` |
| `response.status_code` | `response.status_code` |

## Common patterns

### Single request

```python
async with httpx.AsyncClient() as client:
    response = await client.get(url, headers=headers, timeout=30)
```

### Multiple parallel requests

```python
import asyncio

async def fetch_all(urls):
    async with httpx.AsyncClient() as client:
        tasks = [client.get(url, timeout=30) for url in urls]
        responses = await asyncio.gather(*tasks)
    return responses
```

### Reusable client (for many requests)

```python
class MyService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30)

    async def close(self):
        await self.client.aclose()

    async def fetch(self, url):
        return await self.client.get(url)
```

## Timeout

Always set a timeout to prevent hanging requests:

```python
# Recommended: 30 seconds for most APIs
await client.get(url, timeout=30)

# Or configure per-phase timeouts
timeout = httpx.Timeout(10.0, connect=5.0)
await client.get(url, timeout=timeout)
```

## SSRF Protection (Recommended)

When making requests to external URLs (especially user-provided or scraped URLs), use the SSRF event hook to block redirects to private/internal networks:

```python
from utils.security import ssrf_safe_event_hook

async with httpx.AsyncClient(
    event_hooks={"request": [ssrf_safe_event_hook]}
) as client:
    response = await client.get(url, timeout=30)
```

This prevents a malicious server from redirecting your request to internal addresses (10.x.x.x, 192.168.x.x, 127.0.0.1, etc.). All built-in scrapers include this hook.
