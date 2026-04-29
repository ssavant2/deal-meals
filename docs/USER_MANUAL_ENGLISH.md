# Deal Meals - User Manual

Welcome to Deal Meals! This app helps you save money on groceries by finding recipes that match the current deals at your grocery store.

**How it works:** You choose the store you do your weekly shopping at. The app fetches their current offers and matches them against thousands of recipes. The result? A personalized list of meal suggestions based on what's actually on sale this week.

**Important to understand:** Deal Meals is designed to be used with **one store at a time** — the one you normally do your weekly shopping at. It is not a price comparison service for comparing prices between stores. Choose a large grocery store with a wide assortment (like Willys, ICA Maxi or Coop) for best results. You can use a smaller neighborhood store too, but expect a significantly smaller selection of recipes where you actually save money.

---

## Table of Contents

1. [First-Time Setup](#1-first-time-setup)
2. [Home Page - Your Weekly Meals](#2-home-page---your-weekly-meals)
3. [Stores - Managing Your Grocery Stores](#3-stores---managing-your-grocery-stores)
4. [Recipes - Managing Recipe Sources](#4-recipes---managing-recipe-sources)
5. [Settings](#5-settings)
6. [Tips & FAQ](#6-tips--faq)

---

## 1. First-Time Setup

When you open Deal Meals for the first time, you'll see a **Start Guide** card on the home page. It walks you through these steps:

### Step 1: Allow your browser's address (Origin Validation)

This is the one slightly technical step, but it's essential - without it, the app will block all actions like fetching offers and recipes.

Deal Meals verifies that requests come from a trusted address. By default, only `localhost` and `127.0.0.1` are trusted. If you're accessing the app from another computer or using a hostname (like `docker01` or `192.168.1.50`), you need to add that address.

**How to do it:**

1. Open the file `.env` in the Deal Meals installation folder
2. Find the section called `# Origin validation` and the `ALLOWED_HOSTS=` line
3. Add your server's hostname or IP address to the list (comma-separated, no spaces)

**Example:**
```
ALLOWED_HOSTS=localhost,127.0.0.1,docker01,192.168.1.50
```

If you use a domain name (e.g. `deal-meals.example.com`), add that too.

4. After saving the file, restart the web container for the change to take effect:
```
docker compose up -d web
```

> **Tip:** The Start Guide on the home page will detect which hostname you're connecting from and suggest what to add.

> **Note:** A normal `docker compose restart web` does **not** reload `.env` changes. You must use `docker compose up -d web` instead.

### Step 2: Set your home address

Go to **Settings** and scroll to the **Home Address** section. Enter your:
- Street address
- Postal code (5 digits)
- City

This tells the app where you live so it can find nearby stores and relevant delivery options.

You can start typing your address to get autocomplete suggestions from OpenStreetMap. However, **always double-check the postal code** — OpenStreetMap frequently returns an incorrect postal code for Swedish addresses. If the postal code is wrong, your e-commerce store selections on the Stores page won't match your actual delivery area.

### Step 3: Enable recipe sources

Go to the **Recipes** page. You'll see a list of Swedish recipe websites (ICA, Coop, Köket, etc.). Click the **arrow button** to move sources from "Inactive" to "Active". Active sources are used when generating meal suggestions.

Then fetch recipes from at least one source (see [Fetching Recipes](#43-fetching-recipes) below).

### Step 4: Add a store and fetch offers

Go to the **Stores** page. Pick a store (Willys, ICA, Coop, etc.), choose your location type, and click **Fetch Offers** (see [Scraping a Store](#32-scraping-a-store) below).

### Step 5: Browse your suggestions

Go back to the **Home** page. Your personalized recipe suggestions based on current deals will be ready!

### First-run warm-up

After you have recipes and store offers, Deal Meals needs one successful recipe
matching rebuild before the Home page can show the full current suggestion set.
Right after a first setup, recipe fetch, or offer fetch, the Home page may
briefly show fewer suggestions, old suggestions, or no suggestions while the
matching cache is rebuilt.

There is also a small performance warm-up: the fastest optimized cache path is
enabled after 3 consecutive clean verified cache refreshes. Until then the app
still works, but it does extra safety verification and can feel slower.
Scheduling recipe and store fetches lets this happen in the background.

The start guide disappears automatically once all steps are complete.

---

## 2. Home Page - Your Weekly Meals

The home page is where you'll spend most of your time. It has three main views, accessible via the buttons at the top:

### 2.1 Weekly deal recipes (default view)

This is the main feature. It shows recipe suggestions organized into four color-coded categories:

| Category | Color | What it includes |
|----------|-------|-----------------|
| Meat & Poultry | Red | Recipes with meat-based deals |
| Fish & Seafood | Blue | Recipes with fish and seafood deals |
| Vegetarian | Green | Recipes with vegetarian deals |
| Smart buys | Yellow | Best value — recipes where the most ingredients are on sale |

**Each recipe card shows:**
- Recipe image
- Recipe name
- Source website
- Estimated savings (how much you save using current deals)
- Prep time
- Number of matching offers

**Clicking a recipe card** opens the original recipe on the source website in a new tab.

**Clicking "Show offers"** on a card opens a detailed popup showing:
- All matched store offers with prices and discounts
- Which ingredient each offer matches
- Links to the products in the store's webshop
- The full ingredient list (with a copy button for easy shopping list creation)

#### Refreshing suggestions

Click the **refresh button** (circular arrow) next to "Weekly deal recipes" to rebuild your suggestions. This is useful after fetching new store offers.

#### Adjusting the category balance

Click the **gear icon** next to "Weekly deal recipes" to go to Settings where you can adjust how many recipes from each category you want to see.

### 2.2 Search Recipes

Click **Search Recipes** to search across all your downloaded recipes by name or ingredient.

- Type at least 2 characters and press Enter or click the search button
- Results show recipe cards with name, source, prep time, and servings
- Click a card to open the recipe on the source website

**Filter by recipe source:** Next to the search button there is a dropdown menu listing all active recipe sources (e.g. ICA.se, Mathem.se, Javligtgott.se). Select a source and click **Search** to browse all recipes from that source — no search term needed. You can also combine a search term with a source filter to search within a specific source. The list updates dynamically: new scrapers appear automatically and disabled ones disappear.

**Hiding recipes:** If you see a recipe you never want to see again, click the **eye icon** on the card to hide it. Hidden recipes won't appear in suggestions or search results.

**Restoring hidden recipes:** In the search view, click **"Show Hidden Recipes"** to see all recipes you've hidden. Click **"Restore"** on any recipe to bring it back.

### 2.3 What Can I Cook? (Pantry Match)

Already have ingredients at home? Click **What Can I Cook?** and enter what you have (comma-separated).

Example: `chicken, rice, garlic, tomato`

The app searches all your recipes and shows:
- **Full matches** - recipes where you have all (or almost all) ingredients
- **Partial matches** - recipes where you're only missing a few items, with a list of what's missing

Each result shows a **coverage percentage** - how many of the recipe's ingredients you already have.

### 2.4 Status Cards

Below the main navigation buttons, two status cards show a quick overview:

- **Latest Offers** - which stores have active offers, how many items, and when they were last updated (with a warning if data is more than 9 days old)
- **Recipe Sources** - how many sources are active, total recipe count, and sync status

---

## 3. Stores - Managing Your Grocery Stores

The Stores page lets you configure which grocery stores to track and fetch their current offers.

### 3.1 Store Configuration

Each store card shows the store logo, name, and configuration options. Most stores offer two location types:

- **E-commerce** (truck icon) - Online delivery offers. Select your local delivery store from a dropdown (uses your postal code from Settings).
- **Physical store** (shop icon) - In-store offers. Search for your nearby store by name or city.

Select your preferred location type and choose your specific store. The configuration saves automatically.

**Good to know:**
- **E-commerce delivery fees** are not included in the deal prices shown. Most stores charge a separate delivery fee for home delivery orders.
- **Membership prices** — Many deals are exclusive to store loyalty members (e.g., Willys Plus, ICA Stammis, Coop Medlem). Deal Meals assumes you are a member. Membership is free to sign up for at all major Swedish grocery chains.

### 3.2 Scraping a Store

Once a store is configured, click the green **"Fetch Offers"** button to download current deals.

**What happens:**
1. The button becomes disabled and a progress bar appears
2. You'll see status messages like "Fetching products..." and "Saving 145 products..."
3. When complete, a popup shows how many offers were found
4. The progress bar disappears and the button re-enables

**Important notes:**
- Only one store can be scraped at a time. If you try to start another while one is running, you'll see a message asking you to wait.
- You can safely switch browser tabs or navigate to other pages while scraping runs. If you come back, the progress will resume.
- After scraping, your recipe suggestions on the home page will refresh automatically.

### 3.3 Store Schedules

Below the store cards, there's a **Scheduling** section where you can automate offer fetching.

**To create a schedule:**
1. Select a store from the dropdown
2. Choose a frequency: **Daily**, **Weekly**, or **Monthly**
3. For weekly: pick a day of the week
4. For monthly: pick a day of the month (1-28, not 29-31 since February only has 28 days)
5. Select the hour (24-hour format)
6. Click **Save**

**The schedule overview table** shows all your active schedules with:
- Store name and location
- Schedule description (e.g., "Every Monday at 06:00")
- Next scheduled run
- Last completed run

Click any row in the table to edit that schedule. To remove a schedule, select the store and set frequency to **"Off"**, or click the **delete button**.

---

## 4. Recipes - Managing Recipe Sources

The Recipes page lets you manage where your recipes come from and keep them up to date.

### 4.1 Recipe Sources

Sources are displayed in two columns:

- **Active** (green border) - These sources are used when generating your weekly meal suggestions
- **Inactive** (gray border) - Available but not currently used

**Each source card shows:**
- Source name (clickable link to the website)
- Brief description
- Number of recipes in your database
- Database size
- When it was last updated

**Actions:**
- **Arrow button** - Move between active and inactive
- **Star button** - Mark as favorite (starred sources get priority in suggestions)
- **Trash button** (inactive only) - Delete all recipes from this source

### 4.2 Configure Fetch Limits

Each recipe source has a **gear button** (gear icon) next to the arrow button. Click it to configure how many recipes to fetch:

- **Full fetch** — Number of recipes for "Full" mode. "Fetch all" = no limit.
- **Incremental fetch** — Number of recipes for "Incremental" mode. "All new" = all new recipes since last fetch.

The configured values are shown in the source description text (e.g., "Recept from coop.se (500 / all new)").

### 4.3 Fetching Recipes

Use the **Fetch Recipes** section to download recipes from your sources.

**Recommendation:** Download several thousand recipes, preferably from multiple
sources. The app can work with a smaller collection, but with only a few hundred
recipes the chance that this week's store offers happen to match a high-savings
recipe is much lower. Test mode with 20 recipes is only for checking that a
source works.

**Controls:**
1. **Source selector** - Pick a specific source, or "All active sources" to update everything
2. **Run mode:**
   - **Incremental** (recommended) - Only fetches new recipes since last run. Fast.
   - **Full** - Re-downloads everything. Slow but thorough. Use if data seems incomplete.
   - **Test** - Downloads only 20 recipes without saving. Good for checking if a source works.
3. Click **Fetch Recipes** to start

**During the fetch:**
- A spinner shows with the source name and progress (recipes found so far)
- You can **cancel** at any time with the red cancel button

**After completion:**
- A summary shows new recipes found and total in database
- Recipe suggestions on the home page will refresh

**Time estimates** appear below the source selector showing approximately how long each mode takes for the selected source.

### 4.4 Recipe Schedules

Just like store schedules, you can automate recipe fetching.

The scheduling section works the same way as on the Stores page: pick a source, set frequency and time, and save. The overview table shows all recipe schedules with last run results.

### 4.5 My Recipes — Add Your Own Recipes via URL

In addition to the built-in recipe sources, you can add individual recipes from **any recipe website** that supports the schema.org/Recipe standard (most major recipe sites do).

**Important:** Each recipe must have a **unique URL**. This is the only supported method — you cannot paste recipe text or upload images manually.

**How to use it:**

1. On the **Recipes** page, find **"My Recipes"** among your recipe sources
2. Click the **gear icon** (⚙) on the My Recipes card
3. In the modal that opens, paste a recipe URL and click **Add**
4. The URL is added with status ⏳ (not yet fetched)
5. **Run the scraper** (incremental or full) to fetch recipe data from the URLs

**Statuses:**
- ⏳ **Pending** — URL added but not yet fetched
- ✅ **OK** — Recipe fetched successfully (recipe name is shown)
- ❌ **Error** — Fetch failed (retried automatically, up to 5 times)
- ⚠️ **No recipe** — Page was found but contained no recipe data

**Good to know:**
- The universal scraper is by nature somewhat limited but should work with an estimated 70–80% of all recipes that have a URL. If a specific site doesn't work, it's due to that site's design — unfortunately a custom site-specific scraper would be needed for that site.
- JavaScript-rendered pages are handled automatically via browser fallback
- You can remove a URL via the 🗑 button in the modal — this also removes the fetched recipe
- Duplicates are rejected automatically (the same URL cannot be added twice)

### 4.6 About Run Modes

Below the fetch section, there's an explanation of each mode:
- **Incremental** - Fast, fetches only new content. Best for regular updates.
- **Test** - Quick test with 20 recipes, nothing saved. Use to verify a source works.
- **Full** - Complete re-scrape. Use occasionally if you suspect missing data.

---

## 5. Settings

The Settings page has several sections for customizing your experience.

### 5.1 Appearance

- **Theme** - Switch between Light and Dark mode
- **Font Size** - Adjust text size (12-24px) using a slider
- **High Contrast** - Enable for improved readability (WCAG AAA compliant)

Changes apply immediately and are remembered across sessions.

### 5.2 Sorting Method

Choose how recipes are ranked:

- **Money saved** (default) — Recipes are sorted by total savings in kronor. Best if you want to maximize the absolute size of the discount.
- **Percentage saved** — Recipes are sorted by average percentage discount, weighted by how many of the recipe's ingredients have offers. This prevents expensive ingredients with large absolute discounts from dominating the list.

When percentage mode is active, savings are displayed as percentages on the recipe cards and in the offer detail popup.

### 5.3 Home Address

Your home address, used to find nearby stores and delivery options.

- You can type an address to get autocomplete suggestions (powered by OpenStreetMap)
- Or fill in the fields manually: street, postal code (5 digits), and city
- Saves automatically when you make changes

**Note:** If you change your postal code, any e-commerce store selections may need to be re-configured on the Stores page, since delivery areas depend on your location.

### 5.4 Recipe Matching Preferences

This is where you fine-tune which recipes appear in your suggestions.

#### Ingredient Count

Filter recipes by number of ingredients. Use the sliders to set a minimum and maximum (1–30). Check **"No limit"** to remove the maximum and show all recipes regardless of ingredient count.

Fewer ingredients = simpler recipes. Useful if you want to avoid complex weeknight meals, or conversely if you want to filter out recipes that are too simple.

#### Category Exclusions
Toggle switches to completely hide categories:
- **Exclude meat** - No meat recipes at all
- **Exclude fish** - No fish/seafood recipes
- **Dairy products with lactose** - When enabled, dairy products that contain lactose are filtered out, but lactose-free alternatives (like Laktosfri mjölk) are still included.

#### Local Meat Only
When checked, imported meat is filtered out from offer matching. Products with origin in other countries (e.g. "Brasilien", "Nya Zeeland") or from known import brands are hidden. Specialty charcuterie that is inherently imported — such as prosciutto, chorizo, salami and salsiccia — is always shown regardless of this setting.

#### Category Balance
Four rows of buttons (0-4) control the distribution of recipe suggestions across categories:

| Setting | Effect |
|---------|--------|
| 0 | Category hidden entirely |
| 1 | Minimal - very few recipes from this category |
| 2 | Below average |
| 3 | Default - balanced |
| 4 | Maximum - prioritize this category |

A visual preview shows how 12 recipe slots would be distributed based on your current settings. Click **"Balance"** to reset all categories to the default (3-3-3-3).

#### Excluded Brands
Enter brand names you want to avoid (one per line or comma-separated). Offers from these brands won't be matched to recipes.

#### Excluded Ingredients
Enter ingredient keywords you want to avoid. Recipes containing these ingredients won't appear in suggestions.

#### Filtered Products
Enter product types to exclude from offer matching (e.g., "juice concentrate", "instant noodles").

#### Show Unmatched Offers
Click this button to see a diagnostic view of why certain store offers weren't matched to any recipe. Useful for understanding the matching system. Shows filter reasons like "non-food item", "brand excluded", "no recipe match", etc.

#### Ingredients That Never Match

Some ingredients are so common in recipes that they would create hundreds of matches without providing useful value. These **staple items are intentionally ignored** during recipe matching:

| Category | Ingredients |
|----------|-------------|
| Basic seasoning | salt, pepper, black pepper, white pepper, lemon pepper, garlic pepper |
| Cooking liquids | water, oil |
| Sugar types | sugar (generic) |

**What does this mean in practice?** If e.g. "Ground Black Pepper" is on sale, it won't appear as a match in recipe suggestions — even though many recipes contain black pepper. However, specific spices (cumin, cinnamon, paprika, etc.) are matched as usual.

In addition to staple items, the following are also ignored:
- **Cooking methods** as product descriptors (frozen, grilled, marinated, smoked, etc.)
- **Packaging words** (can, pack, bottle, etc.)
- **Brand names** and marketing words (organic, premium, classic, etc.)
- **Dietary labels** (gluten-free, lactose-free, vegan — diet descriptors, not ingredients)

### 5.5 Advanced Settings

#### Recipe Management

Manage duplicates, permanently excluded recipes, unmatched products, and spell check.

- **Find recipe duplicates** — Scans all recipes to find pairs with identical ingredient lists but different names or URLs. A popup shows both recipes side by side with image, name, source, URL, and ingredients.
  - **Hide** — Hides the recipe (can be restored via "Hidden recipes"). The recipe stays in the database but won't appear in search results or matching.
  - **Delete permanently** — Deletes the recipe from the database and adds its URL to an exclusion list so it won't be re-scraped.

- **Excluded recipes** — Shows all permanently excluded recipes with name, source, and date. You can remove individual exclusions (so the recipe can be re-scraped next time) or remove all exclusions at once.

- **Show unmatched products** — Shows store offers that didn't match any recipe, grouped by reason (excluded category, non-food, processed product, no keywords, no recipe match). Useful for finding gaps in the matching logic.

- **Spell check** — Shows all automatic spelling corrections made to recipe ingredients. Corrections happen automatically during recipe scraping using Levenshtein distance (max 1 character difference). The number of active corrections is shown in the button.
  - Corrections are displayed grouped by word pair (e.g., "scharlottenlökar → schalottenlökar") with all affected recipes listed under each group. Each recipe has a link to the source.
  - **Revert** (yellow button, per recipe) — Undoes the correction for that specific recipe and prevents it from being applied again for that recipe.
  - **Never correct this word** (red button, per group) — Undoes the correction in all recipes and prevents the word pair from being corrected again, regardless of recipe.
  - **Show blocked** — Shows blocked corrections (both per-recipe and global). From here you can allow them again.
  - A badge appears on the Configuration tab in the navbar when there are new unreviewed corrections.

#### Recipe Images

Control how recipe images are stored and managed.

- **Save images locally** - Cache images on the server for faster loading
- **Auto-download on scrape** - Automatically download images when fetching new recipes

**Image management buttons:**
- **Download missing images** - Start a background download of all missing images. Shows real-time progress with percentage and time estimate. Can be cancelled at any time.
- **Clear all images** - Delete all locally cached images (they'll be loaded from source websites instead)

**Failed image indicator:**
- Green checkmark: All images are fine
- Yellow warning: Some images are retrying (temporary failures)
- Red X: Some images permanently failed after 5 attempts

Click the indicator to manage failed images: retry them individually, delete the recipe, or bulk-delete all failed recipes.

#### SSL/HTTPS

Manage the app's HTTPS certificate:

- **Status badge** shows whether SSL is enabled, disabled, or overridden
- **Certificate details** show subject, expiry date, and days remaining
- **Upload** a new certificate and private key
- **Enable/Disable** SSL (requires container restart)
- **Delete** existing certificates

#### Reverse Proxy (optional)

The app works fine without a reverse proxy. If you put it behind one (Nginx Proxy Manager, Traefik, Caddy, etc.), configure these in `.env`:

1. Add the proxy's hostname/domain to `ALLOWED_HOSTS` so origin validation passes
2. Set `TRUSTED_PROXY` to the proxy's internal IP so rate limiting sees the real client IP

```
ALLOWED_HOSTS=localhost,127.0.0.1,my-domain.example.com
TRUSTED_PROXY=172.18.0.1
```

Find your proxy's IP with: `docker network inspect bridge | grep Gateway`

Then recreate the web container with `docker compose up -d web` (restart does NOT reload `.env`).

**Without `TRUSTED_PROXY`:** Rate limiting uses the proxy's IP for all requests, meaning all users share one rate limit bucket. This is safe but less precise.

---

## 6. Tips & FAQ

### Should I schedule or run manually?

**Scheduling is recommended.** When offers or recipes are fetched, the recipe matching cache is automatically rebuilt. With a normal number of offers this only takes a few seconds, but the actual fetching from the store's website can take a bit longer. If you schedule your fetches (e.g. overnight or early morning), everything happens in the background and your suggestions are ready when you open the app.

You can run fetches manually too — but you'll need to wait while the offers download and the matching recalculates.

### How often should I fetch offers?

Store offers typically change weekly. Setting up a **weekly schedule** is ideal. Pick a day when your store usually updates their offers (often Monday or Wednesday).

### How often should I fetch recipes?

Recipe sources don't change as frequently. A **monthly** or **weekly** schedule in incremental mode is usually enough to catch new recipes.

### Why are some recipes not showing?

There are several reasons:

**Your settings:**
- Category exclusions might be hiding them
- Category balance might be set to 0 for some categories
- Excluded brands, ingredients, or products might be filtering them out
- The recipe might have been manually hidden (check "Show Hidden Recipes" in Search)

**Seasonal filtering:**
Recipes with clear seasonal words in their name are automatically hidden from the homepage when out of season. They can always be found via **Search Recipes**. The seasons are:

| Holiday/Season | Keywords | Shown |
|----------------|----------|-------|
| Christmas | jul, pepparkak, glögg, lussebulle, advent | Dec 1 – Jan 6 |
| New Year's | nyår, nyårs | Dec 27 – Jan 2 |
| Semlor | semla, semlor, fettisdag | ~2 weeks around fettisdagen |
| Easter | påsk, påsklamm | 2 weeks before – 1 week after Easter |
| Midsummer | midsommar | 1 week before midsommarafton |
| Crayfish party | kräftskiva, surströmmingsskiva | all of August |
| Halloween | halloween | Oct 24 – Nov 3 |
| Summer recipes | sommar... (sommargryta, sommarsallad) | Jun – Aug |
| Autumn recipes | höst... (höstsoppa, höstgryta) | Sep – Nov |
| Winter recipes | vinter... (vintervärmare) | Dec – Feb |

**Buffets and party menus:**
Recipes that are buffets, multi-course dinners, or large party menus (30+ ingredients) are hidden from weekly suggestions. They tend to dominate rankings due to their size but are rarely useful for everyday cooking. These can still be found via **Search Recipes**.

### Why does a recipe match "wrong" products?

Matching is intentionally broad — the goal is to show which store offers are relevant, not to provide a perfect shopping list. A few things to know:

**Generic product categories:** Some ingredients are matched as a group rather than exactly:
- **Pasta** — "penne", "tagliatelle", "fusilli" etc. all match any pasta product. Reason: most recipes work with any pasta type, and you want to see that pasta is on sale regardless of shape. Exception: "spaghetti" only matches long pasta (not e.g. farfalle).
- **Rice** — "basmati rice" and "jasmine rice" match all rice products, since most dishes work with any rice type. Exception: "arborio rice" only matches itself — it's specific to risotto and not interchangeable.
- **Cheese** — "ost" (cheese) matches all cheese types. Specific cheeses like "västerbottensost" or "mozzarella" match more precisely.

**Noise matches:** An ingredient like "garlic" may match products like "Bruschetta Garlic & Parsley" — a product *containing* garlic, not garlic itself. These appear to give a complete picture, but you're expected to pick the appropriate product.

### Can I find seasonal recipes out of season?

Yes. Use **Search Recipes** and search for e.g. "julskinka" or "semlor" — they remain in the database and can always be found via search. Only the homepage's automatic suggestions hide them out of season.

### Can I use Deal Meals on my phone?

Yes! The interface is fully responsive and works on mobile browsers. All features are available on smaller screens.

### What does the star on a recipe source do?

Starred sources get slight priority when generating suggestions. If you prefer recipes from a particular website, star that source.

### How are recipes sorted in each category?

**Meat & Poultry, Fish & Seafood, and Vegetarian** are sorted by default by total savings in kronor — the recipe with the biggest discount appears first. If you've selected "Percentage saved" under **Settings > Sorting Method**, these are instead sorted by average percentage discount, weighted by how many ingredients have offers.

**Smart buys** uses a different approach. Instead of just looking at the discount amount, it favors recipes where you can buy almost everything on sale — not just a couple of expensive ingredients with a big discount, but the whole recipe at reasonable discounts.

**Example:**

| Recipe | Ingredients on sale | Savings | Shown as |
|--------|---------------------|---------|----------|
| A | 3 of 6 (50%) | 80 kr | Meat & Poultry (high discount) |
| B | 5 of 7 (75%) | 40 kr | Smart buys (good coverage) |
| C | 6 of 7 (90%) | 30 kr | Smart buys (best coverage) |

Recipe C ranks highest in Smart buys despite having the lowest savings, because almost all its ingredients are on sale.

### How accurate is the ingredient matching?

The matching is meant to be practical, not magical. For Swedish recipes and Swedish store offers, the goal is roughly **95-97% useful matches** for recipe ingredients that can reasonably be connected to a real grocery product.

100% accuracy is not realistic. Stores rename products, recipes can use vague wording, package names include brands and marketing text, and some ingredients simply do not map cleanly to this week's offers. The aim is "good enough to be useful" while keeping obviously wrong matches rare.

Some simplifications are intentional. For example, pasta is grouped into broad families such as regular pasta and long pasta, some common rice varieties are treated as interchangeable, cheese is often grouped broadly, and the matcher is usually not overly strict about everyday variants of products such as cream cheese or mustard.

This gives you room to choose the exact product you prefer, and it increases the chance that a real offer is shown for the ingredient family instead of hiding useful deals because the recipe wording and the store wording were slightly different.

### What's the difference between e-commerce and physical store?

- **E-commerce** shows online delivery offers (what you'd see when shopping on the store's website for home delivery)
- **Physical store** shows in-store offers (what you'd find in the actual store near you)

The offers can differ significantly between these two options, even for the same store chain.

### My suggestions seem stale - what do I do?

1. Go to **Stores** and re-fetch offers for your stores
2. Go back to **Home** and click the **refresh button** next to "Weekly deal recipes"
3. If that doesn't help, re-fetch the relevant recipe sources and wait for the cache rebuild to finish

### How do I change the language?

Click the **flag icon** in the top navigation bar and select your preferred language. The page will reload in the new language. Currently available: Swedish and English (United Kingdom).

### How do I switch between light and dark mode?

Go to **Settings** and use the theme toggle at the top of the page. The change applies immediately across all pages.

### Can I add my own recipes?

Yes! Use the **My Recipes** source to add recipes from any website via URL. Click the gear icon on the My Recipes card, paste a recipe URL, and run the scraper. The recipe must have a unique URL — you cannot paste recipe text directly. See [My Recipes](#45-my-recipes--add-your-own-recipes-via-url) for details.

### Why isn't store X or recipe site Y available?

Deal Meals is built with a **modular plugin system** — each store and recipe source is a self-contained plugin. The stores and recipe sites currently included are the ones that have been implemented so far, but the system is designed to be extended.

If you're comfortable with Python, you can write your own scraper plugin for any store or recipe website. Each plugin lives in its own folder and follows a simple template. See [HOW_TO_ADD_SCRAPERS.md](HOW_TO_ADD_SCRAPERS.md) for a step-by-step guide on adding new stores and recipe sources.

### Is there login or password protection?

No. The application has no built-in authentication — it is designed to run on a trusted local network and should not be exposed directly to the internet. If you need external access, use a reverse proxy with an identity provider in front of it, such as Nginx Proxy Manager, Traefik, or Caddy combined with Authentik or a similar authentication solution.
