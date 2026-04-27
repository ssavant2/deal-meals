# Known Issues & Limitations

Store-specific limitations and known quirks that are unlikely to be fixed.

## Coop

### Physical stores: No product links
Physical store offers on Coop don't have clickable product links in their HTML.
E-commerce product URLs (via EAN) don't resolve either ("Kategorin kunde inte hittas").
Physical store offers will show without link buttons in the recipe popup.

### Offer scraping: No API for offers
Coop has no public REST API for offers. Both e-commerce and physical stores use Playwright
(headless browser) for offer extraction. Price enrichment for physical stores uses
Coop's product search API (httpx) which is fast (~5-10s for all products).


## Matching

### Compound ingredient alternatives ("eller")
Some recipes list alternatives as a single ingredient line, e.g.:
- "Pasta, ris eller potatis och sallad samt ev. lite färsk timjan"
- "pasta, ris eller potatis"

These get extracted as a combined keyword group (`pasta / ris / potatis / timjan / sallad`)
that matches products across all alternatives. The alternatives are grouped together
and sorted by discount, so the best deal is shown first. The offer count for the
ingredient may appear high since it includes all alternatives.

## Scheduling

### One schedule per scraper
Each recipe source and store can only have one schedule. This is enforced by the
database with a unique scraper/store id. To change a schedule, update the
existing one — creating a new one for the same source replaces the old one.

## Security

### No built-in authentication
Deal Meals does not include login or user accounts. Anyone who can reach the app
can use it.

For the full threat model, accepted tradeoffs, and recommended deployment
boundaries, see [SECURITY.md](SECURITY.md).

## General

### One scrape at a time
Only one store scrape can run at a time. Recipe scraper runs are tracked
separately, and the UI prevents starting the same recipe scraper twice. Store
scrapes are serialized because they replace the active offer set and can involve
heavy Playwright/browser work.

### Synchronous database layer
The database layer uses synchronous SQLAlchemy, which blocks the async event loop
during queries. This is fine for a single-user LAN app but would need migration
to async SQLAlchemy if the app were ever scaled to many concurrent users.
