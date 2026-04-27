// Home page behavior. Jinja-provided i18n and page data are bootstrapped in home.html.
const i18n = window.DealMealsHomeI18n || {};
const pageConfig = window.DealMealsHomePage || {};
const HOME_LOCALE = pageConfig.locale || undefined;

const t = window.DealMeals.createTranslator(i18n, { escapeParams: true });

function displayRecipeSource(source) {
    const cleaned = String(source || '').replace(/ [Rr]ecept$/, '');
    if (cleaned === 'My Recipes') return i18n['myrecipes.scraper_name'];
    return cleaned;
}

// Safe sessionStorage wrapper (ignores QuotaExceededError)
function safeSessionSet(key, value) {
    try { sessionStorage.setItem(key, value); }
    catch (e) { dbg.warn('sessionStorage full, skipping:', key); }
}

// ============================================
// Security: HTML entity decoding
// NOTE: escapeHtml() is defined in dealmeals-core.js
// ============================================

// Decode HTML entities (e.g., &amp; -> &) and then safely escape for HTML display
// Use this for text that may have been HTML-encoded in the database
function decodeHtmlEntities(str) {
    if (str == null) return '';
    const textarea = document.createElement('textarea');
    textarea.innerHTML = String(str);
    return textarea.value;
}

// ============================================
// Category constants (shared across functions)
// ============================================
const CATEGORY_ORDER = ['meat', 'fish', 'vegetarian', 'smart_buy'];
const CATEGORY_INFO = {
    'meat': { name: i18n['category.meat'], icon: 'bi-egg-fried' },
    'fish': { name: i18n['category.fish'], icon: 'bi-water' },
    'vegetarian': { name: i18n['category.vegetarian'], icon: 'bi-tree' },
    'smart_buy': { name: i18n['category.smart_buy'], icon: 'bi-piggy-bank' }
};

// Encode JSON for use in HTML attributes (escapes double quotes)
function encodeJsonAttr(jsonStr) {
    return jsonStr.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}

function formatPrepTime(minutes) {
    if (!minutes || minutes <= 0) return '';
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    if (hours > 0 && mins > 0) {
        return i18n['home.time_hours_minutes'].replace('{h}', hours).replace('{m}', mins);
    } else if (hours > 0) {
        return i18n['home.time_hours'].replace('{h}', hours);
    } else {
        return i18n['home.time_minutes'].replace('{m}', mins);
    }
}

// ============================================
// Toggle functions with mutual exclusivity
// ============================================

function closeAllSections() {
    const suggestionsSection = document.getElementById('recipe-suggestions-section');
    const searchSection = document.getElementById('search-section');
    const pantrySection = document.getElementById('pantry-section');
    const suggestionsHeader = document.getElementById('suggestions-header-sticky');
    const categoryHeaders = document.getElementById('category-headers-sticky');
    const stickyBlock = document.getElementById('sticky-header-block');

    if (suggestionsSection.classList.contains('show')) {
        bootstrap.Collapse.getOrCreateInstance(suggestionsSection).hide();
    }
    if (searchSection.classList.contains('show')) {
        bootstrap.Collapse.getOrCreateInstance(searchSection).hide();
    }
    if (pantrySection.classList.contains('show')) {
        bootstrap.Collapse.getOrCreateInstance(pantrySection).hide();
    }

    suggestionsHeader.style.display = 'none';
    categoryHeaders.style.display = 'none';
    stickyBlock.classList.remove('has-shadow');

    // Stop listening for background scrape events (not needed on search/pantry)
    disconnectCacheEvents();

    // Remove active state from all nav buttons
    document.querySelectorAll('#quick-actions-row .main-nav-active').forEach(
        btn => btn.classList.remove('main-nav-active')
    );
}

function toggleSuggestions() {
    const suggestionsSection = document.getElementById('recipe-suggestions-section');
    const suggestionsHeader = document.getElementById('suggestions-header-sticky');
    const stickyBlock = document.getElementById('sticky-header-block');
    const isAlreadyOpen = suggestionsSection.classList.contains('show');

    // DISABLED: reload empty section on re-click — unreachable in practice
    // (button is already active/selected, user won't click again)
    // Kept for quick restore if needed.
    if (isAlreadyOpen) {
        // if (allSuggestions.length === 0) {
        //     suggestionsLoaded = false;
        //     loadRecipeSuggestions();
        // }
        return;
    }

    // Close other sections first
    closeAllSections();

    bootstrap.Collapse.getOrCreateInstance(suggestionsSection).show();
    suggestionsHeader.style.display = 'flex';
    stickyBlock.classList.add('has-shadow');
    document.getElementById('btn-suggestions').classList.add('main-nav-active');
    localStorage.setItem('activeSection', 'suggestions');

    // Listen for background scrape completions while viewing suggestions
    connectCacheEvents();

    // Category headers will be shown by renderSuggestions() after content is ready
    loadRecipeSuggestions();
}

function toggleSearch() {
    const searchSection = document.getElementById('search-section');
    const isAlreadyOpen = searchSection.classList.contains('show');

    // If already open, do nothing
    if (isAlreadyOpen) return;

    // Close other sections first
    closeAllSections();

    bootstrap.Collapse.getOrCreateInstance(searchSection).show();
    document.getElementById('btn-search').classList.add('main-nav-active');
    localStorage.setItem('activeSection', 'search');
    // Focus on input field
    setTimeout(() => document.getElementById('search-input').focus(), 100);

    // Update hidden recipes button visibility
    updateHiddenRecipesButton();

    // Reset hidden recipes section state when reopening
    hiddenRecipesVisible = false;
    const hiddenSection = document.getElementById('hidden-recipes-section');
    if (hiddenSection) hiddenSection.style.display = 'none';
}

function togglePantry() {
    const pantrySection = document.getElementById('pantry-section');
    const isAlreadyOpen = pantrySection.classList.contains('show');

    // If already open, do nothing
    if (isAlreadyOpen) return;

    // Close other sections first
    closeAllSections();

    bootstrap.Collapse.getOrCreateInstance(pantrySection).show();
    document.getElementById('btn-pantry').classList.add('main-nav-active');
    localStorage.setItem('activeSection', 'pantry');
    // Focus on input field
    setTimeout(() => document.getElementById('pantry-input').focus(), 100);
}

// Disable browser's automatic scroll restoration
if ('scrollRestoration' in history) {
    history.scrollRestoration = 'manual';
}

// Setup guide - check completion and show/hide
async function loadSetupGuide() {
    try {
        const resp = await fetch('/api/setup/status');
        if (!resp.ok) return;
        const data = await resp.json();
        if (!data.success || data.guide_dismissed) return;

        const steps = data.steps;
        const allDone = Object.values(steps).every(v => v);

        if (allDone) {
            // All steps done - auto-dismiss permanently
            fetch('/api/ui-preferences', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({setup_guide_dismissed: true})
            });
            return;
        }

        // Mark completed steps
        const mapping = {allowed_hosts: 'hosts', delivery_address: 'address', recipes: 'recipes', offers: 'offers'};
        for (const [key, id] of Object.entries(mapping)) {
            if (steps[key]) {
                const li = document.getElementById('step-' + id);
                li.classList.add('step-done');
                li.querySelector('i').className = 'bi bi-check-circle-fill text-success';
            }
        }

        // Show detected hostname hint if ALLOWED_HOSTS not configured
        if (!steps.allowed_hosts && data.detected_host) {
            const hint = document.getElementById('step-hosts-hint');
            hint.innerHTML = i18n['setup.step_hosts_detected'].replace('{host}', escapeHtml(data.detected_host));
            hint.style.display = 'block';
        }

        document.getElementById('setup-guide').style.display = 'block';
        document.body.classList.add('setup-guide-active');
    } catch (e) {
        // Guide is non-critical - silently skip on error
    }
}

// Load status on page load and restore active section
document.addEventListener('DOMContentLoaded', function() {
    loadSetupGuide();
    loadOfferStatus();
    loadRecipeStatus();
    updateHiddenRecipesButton();

    // Restore previously active section (instant, no animation)
    const saved = localStorage.getItem('activeSection');
    if (saved === 'suggestions') {
        // restoreSuggestions() IIFE handles expanding if cached data exists.
        // If no cached data (e.g. cleared by store scraper), open section and load fresh.
        document.getElementById('btn-suggestions').classList.add('main-nav-active');
        const sugSection = document.getElementById('recipe-suggestions-section');
        if (!sugSection.classList.contains('show')) {
            // restoreSuggestions() didn't open it (no cached data) — do it now
            const sugHeader = document.getElementById('suggestions-header-sticky');
            const stickyBlock = document.getElementById('sticky-header-block');
            sugSection.classList.add('show');
            if (sugHeader) sugHeader.style.display = 'flex';
            if (stickyBlock) stickyBlock.classList.add('has-shadow');
            loadRecipeSuggestions();
        }
        // Listen for background scrape completions
        connectCacheEvents();
    } else if (saved === 'search') {
        document.getElementById('search-section').classList.add('show');
        document.getElementById('btn-search').classList.add('main-nav-active');
        restoreSearchState();
    } else if (saved === 'pantry') {
        document.getElementById('pantry-section').classList.add('show');
        document.getElementById('btn-pantry').classList.add('main-nav-active');
        restorePantryState();
    }

    // Scroll to top on page load
    window.scrollTo(0, 0);
});

function restoreSearchState() {
    const cached = sessionStorage.getItem('searchState');
    if (!cached) return;
    try {
        const data = JSON.parse(cached);
        const input = document.getElementById('search-input');
        const gridDiv = document.getElementById('search-results-grid');
        const resultsDiv = document.getElementById('search-results');
        if (input && gridDiv && resultsDiv && data.html) {
            input.value = data.query;
            gridDiv.innerHTML = data.html;
            resultsDiv.style.display = 'block';
            document.getElementById('search-loading').style.display = 'none';
            searchQuery = data.query;
            searchOffset = data.offset;
            searchTotalShown = data.totalShown;
        }
    } catch(e) { console.error('Error restoring search state:', e); }
}

function restorePantryState() {
    const cached = sessionStorage.getItem('pantryState');
    if (!cached) return;
    try {
        const data = JSON.parse(cached);
        const input = document.getElementById('pantry-input');
        const resultsDiv = document.getElementById('pantry-results');
        const fullMatchDiv = document.getElementById('pantry-full-match');
        const partialMatchDiv = document.getElementById('pantry-partial-match');
        if (input && fullMatchDiv && data.fullHtml) {
            input.value = data.input;
            fullMatchDiv.innerHTML = data.fullHtml;
            partialMatchDiv.innerHTML = data.partialHtml || '';
            resultsDiv.style.display = 'block';
            document.getElementById('pantry-loading').style.display = 'none';
            allPantryFullMatch = data.fullData || [];
            allPantryPartialMatch = data.partialData || [];
            pantryFullShown = data.fullShown || 0;
            pantryPartialShown = data.partialShown || 0;
            updatePantryLoadMoreButton();
        }
    } catch(e) { console.error('Error restoring pantry state:', e); }
}

async function loadOfferStatus() {
    try {
        const response = await fetch('/api/status/offers');
        if (!response.ok) return;
        const data = await response.json();

        const container = document.getElementById('offers-status');

        if (data.success && data.stores.length > 0) {
            const storesWithOffers = data.stores.filter(s => s.offer_count > 0);

            if (storesWithOffers.length > 0) {
                let html = '<table class="table table-sm mb-0">';
                html += `<thead><tr><th>${t('table.store')}</th><th>${t('table.type')}</th><th>${t('table.items')}</th><th>${t('table.last_scraped')}</th></tr></thead>`;
                html += '<tbody>';

                for (const store of storesWithOffers) {
                    let typeLabel;
                    if (store.location_type === 'ehandel') {
                        typeLabel = `<small>${t('status.ecommerce')}</small>`;
                    } else if (store.location_name) {
                        typeLabel = `<small>${escapeHtml(store.location_name)}</small>`;
                    } else {
                        typeLabel = `<small>${t('status.local_store')}</small>`;
                    }

                    let lastDateHtml;
                    if (store.last_scraped_at) {
                        const scraped = new Date(store.last_scraped_at);
                        const daysAgo = Math.floor((Date.now() - scraped.getTime()) / 86400000);
                        const dateStr = scraped.toLocaleDateString(HOME_LOCALE);
                        if (daysAgo > 9) {
                            const tooltip = t('home.stale_data_warning', {days: daysAgo});
                            lastDateHtml = `${dateStr} <span style="cursor:help" title="${tooltip}">&#9888;&#65039;</span> <small style="opacity:0.7">${tooltip}</small>`;
                        } else {
                            lastDateHtml = dateStr;
                        }
                    } else {
                        lastDateHtml = `<span class="text-muted">${t('common.never')}</span>`;
                    }

                    html += `<tr>
                        <td><strong>${escapeHtml(store.store_name)}</strong></td>
                        <td>${typeLabel}</td>
                        <td>${parseInt(store.offer_count) || 0}</td>
                        <td><small>${lastDateHtml}</small></td>
                    </tr>`;
                }

                html += '</tbody></table>';
                container.innerHTML = html;
            } else {
                container.innerHTML = `<p class="text-muted mb-0 no-offers-hint">${t('home.no_offers')} <a href="/stores">${t('home.fetch_from_stores')}</a></p>`;
            }
        } else {
            container.innerHTML = `<p class="text-muted mb-0 no-offers-hint">${t('home.no_offers')} <a href="/stores">${t('home.fetch_from_stores')}</a></p>`;
        }
    } catch (error) {
        document.getElementById('offers-status').innerHTML =
            `<p class="text-danger mb-0">${t('home.could_not_load')}</p>`;
    }
}

async function loadRecipeStatus() {
    try {
        const response = await fetch('/api/status/recipes');
        if (!response.ok) return;
        const data = await response.json();

        const container = document.getElementById('recipes-status');

        if (data.success) {
            // Show green checkmark if all synced, otherwise show count as text
            const syncDisplay = data.synced_last_month ?
                '<i class="bi bi-check-circle-fill text-success"></i>' :
                `${data.synced_sources}/${data.active_source_count}`;

            container.innerHTML = `
                <div class="row text-center">
                    <div class="col-4">
                        <h3 class="mb-0">${data.source_count}</h3>
                        <small class="text-muted">${t('home.active_sources')}</small>
                    </div>
                    <div class="col-4">
                        <h3 class="mb-0">${data.total_recipes.toLocaleString(HOME_LOCALE)}</h3>
                        <small class="text-muted">${t('home.recipes_active')}</small>
                    </div>
                    <div class="col-4">
                        <h3 class="mb-0">${syncDisplay}</h3>
                        <small class="text-muted">${t('home.synced_last_month')}</small>
                    </div>
                </div>
            `;
        } else {
            container.innerHTML = `<p class="text-muted mb-0">${t('home.no_sources')}</p>`;
        }
    } catch (error) {
        document.getElementById('recipes-status').innerHTML =
            `<p class="text-danger mb-0">${t('home.could_not_load')}</p>`;
    }
}

// ============================================
// Pantry Match Functions
// ============================================

let allPantryFullMatch = [];
let allPantryPartialMatch = [];
let pantryFullShown = 0;
let pantryPartialShown = 0;
const PANTRY_BATCH_SIZE = 12;

async function searchPantryRecipes() {
    const input = document.getElementById('pantry-input').value;

    if (!input.trim()) {
        Swal.fire({
            icon: 'warning',
            title: t('home.pantry_enter'),
            text: t('home.pantry_min')
        });
        return;
    }

    const resultsDiv = document.getElementById('pantry-results');
    const loadingDiv = document.getElementById('pantry-loading');
    const fullMatchDiv = document.getElementById('pantry-full-match');
    const partialMatchDiv = document.getElementById('pantry-partial-match');
    const loadMoreDiv = document.getElementById('pantry-load-more');
    const loadMoreBtn = document.getElementById('load-more-pantry-btn');

    // Reset pagination state
    allPantryFullMatch = [];
    allPantryPartialMatch = [];
    pantryFullShown = 0;
    pantryPartialShown = 0;

    resultsDiv.style.display = 'block';
    loadingDiv.style.display = 'block';
    fullMatchDiv.innerHTML = '';
    partialMatchDiv.innerHTML = '';
    if (loadMoreDiv) loadMoreDiv.style.display = 'none';

    try {
        const response = await fetch('/api/pantry-match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ingredients: input })
        });
        if (!response.ok) { loadingDiv.style.display = 'none'; return; }

        const data = await response.json();
        loadingDiv.style.display = 'none';

        if (!data.success) {
            fullMatchDiv.innerHTML = `<p class="text-danger">${t(data.message_key, data.message_params)}</p>`;
            return;
        }

        // Store all results for pagination
        allPantryFullMatch = data.full_match || [];
        allPantryPartialMatch = data.partial_match || [];

        // Show user keywords
        fullMatchDiv.innerHTML = `
            <p class="text-muted mb-3">
                <small>${t('home.pantry_searched', {keywords: data.user_keywords.map(k => escapeHtml(k)).join(', '), count: parseInt(data.total_searched).toLocaleString(HOME_LOCALE)})}</small>
            </p>
        `;

        // Full matches - show first batch
        if (allPantryFullMatch.length > 0) {
            let html = `<h6 class="text-success"><i class="bi bi-check-circle"></i> ${t('home.pantry_full_match')}</h6>`;
            html += '<div class="category-column full-width" id="pantry-full-row">';
            const fullBatch = allPantryFullMatch.slice(0, PANTRY_BATCH_SIZE);
            for (const recipe of fullBatch) {
                html += renderPantryRecipeCard(recipe, 'success');
            }
            html += '</div>';
            fullMatchDiv.innerHTML += html;
            pantryFullShown = fullBatch.length;
        } else {
            fullMatchDiv.innerHTML += `<p class="text-muted">${t('home.pantry_no_full')}</p>`;
        }

        // Partial matches - show first batch
        if (allPantryPartialMatch.length > 0) {
            let html = `<hr><h6 class="mt-3"><i class="bi bi-basket text-warning"></i> ${t('home.pantry_partial_match')}</h6>`;
            html += '<div class="category-column full-width" id="pantry-partial-row">';
            const partialBatch = allPantryPartialMatch.slice(0, PANTRY_BATCH_SIZE);
            for (const recipe of partialBatch) {
                html += renderPantryRecipeCard(recipe, 'warning');
            }
            html += '</div>';
            partialMatchDiv.innerHTML = html;
            pantryPartialShown = partialBatch.length;
        }

        // Show "Load more" button if there are more results
        updatePantryLoadMoreButton();

        // Attach event delegation for recipe card clicks (popup + URL open)
        if (!resultsDiv.dataset.listenersAttached) {
            resultsDiv.addEventListener('click', function(e) {
                const card = e.target.closest('.recipe-card');
                if (!card) return;
                if (e.target.closest('.show-offers-btn')) {
                    e.stopPropagation();
                    e.preventDefault();
                    const recipeId = card.dataset.recipeId;
                    const recipeName = card.dataset.recipeName;
                    const matchedOffers = JSON.parse(card.dataset.matchedOffers || '[]');
                    const ingredients = JSON.parse(card.dataset.ingredients || '[]');
                    const servings = parseInt(card.dataset.servings) || 0;
                    const cardIsCapped = card.dataset.isCapped === 'true';
                    const cardCappedSavings = parseInt(card.dataset.cappedSavings) || 0;
                    showMatchedOffers(recipeId, recipeName, matchedOffers, ingredients, servings, cardIsCapped, cardCappedSavings);
                    return;
                }
                const url = card.dataset.recipeUrl;
                if (url) window.open(url, '_blank');
            });
            resultsDiv.dataset.listenersAttached = 'true';
        }

        // Cache pantry state to sessionStorage
        safeSessionSet('pantryState', JSON.stringify({
            input: input,
            fullHtml: fullMatchDiv.innerHTML,
            partialHtml: partialMatchDiv.innerHTML,
            fullData: allPantryFullMatch,
            partialData: allPantryPartialMatch,
            fullShown: pantryFullShown,
            partialShown: pantryPartialShown
        }));

    } catch (error) {
        loadingDiv.style.display = 'none';
        fullMatchDiv.innerHTML = `<p class="text-danger">${i18n['common.error']}: ${escapeHtml(error.message)}</p>`;
    }
}

function loadMorePantryRecipes() {
    const loadMoreBtn = document.getElementById('load-more-pantry-btn');

    // Show spinner on button
    if (loadMoreBtn) {
        loadMoreBtn.disabled = true;
        loadMoreBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> ${i18n['common.loading']}`;
    }

    // Small delay for visual feedback
    setTimeout(() => {
        let addedAny = false;

        // Add more full matches
        if (pantryFullShown < allPantryFullMatch.length) {
            const fullRow = document.getElementById('pantry-full-row');
            if (fullRow) {
                const nextBatch = allPantryFullMatch.slice(pantryFullShown, pantryFullShown + PANTRY_BATCH_SIZE);
                let html = '';
                for (const recipe of nextBatch) {
                    html += renderPantryRecipeCard(recipe, 'success');
                }
                fullRow.insertAdjacentHTML('beforeend', html);
                pantryFullShown += nextBatch.length;
                addedAny = true;
            }
        }

        // Add more partial matches
        if (pantryPartialShown < allPantryPartialMatch.length) {
            const partialRow = document.getElementById('pantry-partial-row');
            if (partialRow) {
                const nextBatch = allPantryPartialMatch.slice(pantryPartialShown, pantryPartialShown + PANTRY_BATCH_SIZE);
                let html = '';
                for (const recipe of nextBatch) {
                    html += renderPantryRecipeCard(recipe, 'warning');
                }
                partialRow.insertAdjacentHTML('beforeend', html);
                pantryPartialShown += nextBatch.length;
                addedAny = true;
            }
        }

        updatePantryLoadMoreButton();

        // Update cache
        const fullMatchDiv = document.getElementById('pantry-full-match');
        const partialMatchDiv = document.getElementById('pantry-partial-match');
        safeSessionSet('pantryState', JSON.stringify({
            input: document.getElementById('pantry-input').value,
            fullHtml: fullMatchDiv.innerHTML,
            partialHtml: partialMatchDiv.innerHTML,
            fullData: allPantryFullMatch,
            partialData: allPantryPartialMatch,
            fullShown: pantryFullShown,
            partialShown: pantryPartialShown
        }));
    }, 100);
}

function updatePantryLoadMoreButton() {
    const loadMoreDiv = document.getElementById('pantry-load-more');
    const loadMoreBtn = document.getElementById('load-more-pantry-btn');

    const hasMoreFull = pantryFullShown < allPantryFullMatch.length;
    const hasMorePartial = pantryPartialShown < allPantryPartialMatch.length;
    const totalShown = pantryFullShown + pantryPartialShown;
    const totalAvailable = allPantryFullMatch.length + allPantryPartialMatch.length;

    if (loadMoreDiv && loadMoreBtn) {
        if (hasMoreFull || hasMorePartial) {
            loadMoreDiv.style.display = 'block';
            loadMoreBtn.innerHTML = `<i class="bi bi-plus-circle"></i> ${i18n['home.load_more']}`;
            loadMoreBtn.disabled = false;
        } else if (totalShown > PANTRY_BATCH_SIZE * 2) {
            loadMoreDiv.style.display = 'block';
            loadMoreBtn.innerHTML = `<i class="bi bi-check-circle"></i> ${i18n['home.no_more']}`;
            loadMoreBtn.disabled = true;
        } else {
            loadMoreDiv.style.display = 'none';
        }
    }
}

// ============================================
// Recipe Search Functions
// ============================================

let searchOffset = 0;
let searchQuery = '';
let searchTotalShown = 0;

async function searchRecipes(isLoadMore = false) {
    const input = document.getElementById('search-input').value.trim();
    const sourceFilter = document.getElementById('search-source-filter').value;

    if ((!input || input.length < 2) && !sourceFilter) {
        Swal.fire({
            icon: 'warning',
            title: i18n['home.search_title'],
            text: i18n['home.search_min_chars']
        });
        return;
    }

    const resultsDiv = document.getElementById('search-results');
    const loadingDiv = document.getElementById('search-loading');
    const emptyDiv = document.getElementById('search-empty');
    const gridDiv = document.getElementById('search-results-grid');
    const loadMoreDiv = document.getElementById('search-load-more');
    const loadMoreBtn = document.getElementById('load-more-search-btn');

    // Reset for new search
    if (!isLoadMore) {
        searchOffset = 0;
        searchQuery = input || '';
        searchTotalShown = 0;
        gridDiv.innerHTML = '';
    }

    if (isLoadMore) {
        // Only show spinner on the button - don't touch any other elements
        if (loadMoreBtn) {
            loadMoreBtn.disabled = true;
            loadMoreBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> ${i18n['common.loading']}`;
        }
    } else {
        // Initial search - show loading indicator
        resultsDiv.style.display = 'block';
        loadingDiv.style.display = 'block';
        emptyDiv.style.display = 'none';
        if (loadMoreDiv) loadMoreDiv.style.display = 'none';
    }

    try {
        let searchUrl = `/api/recipe-search?q=${encodeURIComponent(searchQuery)}&limit=50&offset=${searchOffset}`;
        if (sourceFilter) searchUrl += `&source=${encodeURIComponent(sourceFilter)}`;
        const response = await fetch(searchUrl);
        if (!response.ok) { loadingDiv.style.display = 'none'; return; }
        const data = await response.json();

        if (!isLoadMore) {
            loadingDiv.style.display = 'none';
        }

        if (!data.success) {
            gridDiv.innerHTML = `<p class="text-danger">${escapeHtml(t(data.message_key, data.message_params))}</p>`;
            return;
        }

        if (data.recipes.length === 0 && !isLoadMore) {
            emptyDiv.style.display = 'block';
            return;
        }

        // Update offset for next page
        searchOffset += data.recipes.length;
        searchTotalShown += data.recipes.length;

        // Build HTML
        let html = '';
        if (!isLoadMore) {
            const displayQuery = data.query || sourceFilter;
            html += `<p class="text-muted mb-3 search-count">
                <small>${t('home.showing_results', {count: searchTotalShown, query: escapeHtml(displayQuery)})}</small>
            </p>`;
            html += '<div class="category-column full-width" id="search-cards-row">';
        }

        for (const recipe of data.recipes) {
            html += renderRecipeCard(recipe);
        }

        if (!isLoadMore) {
            html += '</div>';
            gridDiv.innerHTML = html;
        } else {
            // Append to existing row
            const cardsRow = document.getElementById('search-cards-row');
            if (cardsRow) {
                cardsRow.insertAdjacentHTML('beforeend', html);
            }
            // Update count
            const countEl = gridDiv.querySelector('.search-count small');
            if (countEl) {
                countEl.textContent = t('home.showing_results', {count: searchTotalShown, query: data.query});
            }
        }

        // Show/hide "Load more" button
        if (loadMoreDiv && loadMoreBtn) {
            if (data.has_more) {
                loadMoreDiv.style.display = 'block';
                loadMoreBtn.innerHTML = `<i class="bi bi-plus-circle"></i> ${i18n['home.load_more']}`;
                loadMoreBtn.disabled = false;
            } else {
                if (searchTotalShown > 50) {
                    loadMoreDiv.style.display = 'block';
                    loadMoreBtn.innerHTML = `<i class="bi bi-check-circle"></i> ${i18n['home.no_more']}`;
                    loadMoreBtn.disabled = true;
                } else {
                    loadMoreDiv.style.display = 'none';
                }
            }
        }

        // Attach event delegation for recipe card clicks (popup + URL open)
        if (!gridDiv.dataset.listenersAttached) {
            gridDiv.addEventListener('click', function(e) {
                const card = e.target.closest('.recipe-card');
                if (!card) return;
                if (e.target.closest('.show-offers-btn')) {
                    e.stopPropagation();
                    e.preventDefault();
                    const recipeId = card.dataset.recipeId;
                    const recipeName = card.dataset.recipeName;
                    const matchedOffers = JSON.parse(card.dataset.matchedOffers || '[]');
                    const ingredients = JSON.parse(card.dataset.ingredients || '[]');
                    const servings = parseInt(card.dataset.servings) || 0;
                    const cardIsCapped = card.dataset.isCapped === 'true';
                    const cardCappedSavings = parseInt(card.dataset.cappedSavings) || 0;
                    showMatchedOffers(recipeId, recipeName, matchedOffers, ingredients, servings, cardIsCapped, cardCappedSavings);
                    return;
                }
                const url = card.dataset.recipeUrl;
                if (url) window.open(url, '_blank');
            });
            gridDiv.dataset.listenersAttached = 'true';
        }

        // Cache search state to sessionStorage
        safeSessionSet('searchState', JSON.stringify({
            query: searchQuery,
            html: gridDiv.innerHTML,
            offset: searchOffset,
            totalShown: searchTotalShown
        }));

    } catch (error) {
        if (!isLoadMore) {
            loadingDiv.style.display = 'none';
        }
        gridDiv.innerHTML = `<p class="text-danger">${i18n['common.error']}: ${escapeHtml(error.message)}</p>`;
        if (loadMoreBtn) {
            loadMoreBtn.innerHTML = `<i class="bi bi-plus-circle"></i> ${i18n['home.load_more']}`;
            loadMoreBtn.disabled = false;
        }
    }
}

function loadMoreSearchResults() {
    searchRecipes(true);
}

// Hidden recipes functionality
let hiddenRecipesVisible = false;

async function updateHiddenRecipesButton() {
    const btn = document.getElementById('show-hidden-btn');
    const badge = document.getElementById('hidden-recipes-badge');
    const countEl = document.getElementById('hidden-recipes-count');

    try {
        const response = await fetch('/api/recipes/excluded');
        if (!response.ok) return;
        const data = await response.json();

        if (data.success && data.recipes && data.recipes.length > 0) {
            if (btn) {
                btn.style.display = 'inline-block';
                btn.innerHTML = `<i class="bi bi-eye-slash"></i> ${escapeHtml(i18n['home.show_hidden_recipes'])} (${data.recipes.length})`;
            }
            if (badge && countEl) {
                countEl.textContent = data.recipes.length;
                badge.style.display = '';
            }
        } else {
            if (btn) btn.style.display = 'none';
            if (badge) badge.style.display = 'none';
        }
    } catch (error) {
        console.error('Error checking hidden recipes:', error);
        if (btn) btn.style.display = 'none';
        if (badge) badge.style.display = 'none';
    }
}

async function toggleHiddenRecipes() {
    const section = document.getElementById('hidden-recipes-section');
    const btn = document.getElementById('show-hidden-btn');

    if (hiddenRecipesVisible) {
        // Hide the section
        section.style.display = 'none';
        hiddenRecipesVisible = false;
        btn.innerHTML = `<i class="bi bi-eye-slash"></i> ${escapeHtml(i18n['home.show_hidden_recipes'])}`;
        return;
    }

    // Show and load hidden recipes
    section.style.display = 'block';
    hiddenRecipesVisible = true;
    btn.innerHTML = `<i class="bi bi-eye"></i> ${escapeHtml(i18n['home.hide_hidden_recipes'])}`;

    await loadHiddenRecipes();
}

async function loadHiddenRecipes() {
    const loading = document.getElementById('hidden-recipes-loading');
    const list = document.getElementById('hidden-recipes-list');
    const empty = document.getElementById('hidden-recipes-empty');

    loading.style.display = 'block';
    list.innerHTML = '';
    empty.style.display = 'none';

    try {
        const response = await fetch('/api/recipes/excluded');
        if (!response.ok) { loading.style.display = 'none'; return; }
        const data = await response.json();

        loading.style.display = 'none';

        if (data.success && data.recipes && data.recipes.length > 0) {
            let html = '<div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-2">';
            for (const recipe of data.recipes) {
                const recipeName = escapeHtml(recipe.name || '');
                const recipeSource = escapeHtml(displayRecipeSource(recipe.source_name));
                html += `
                    <div class="col">
                        <div class="card h-100 border-secondary">
                            <div class="card-body py-2 px-3">
                                <div class="d-flex justify-content-between align-items-start">
                                    <div>
                                        <h6 class="card-title mb-1" style="font-size: 0.9rem;">${recipeName}</h6>
                                        <small class="text-muted">${recipeSource}</small>
                                    </div>
                                    <button class="btn btn-sm btn-outline-success" data-action="restoreRecipe" data-arg="${escapeAttr(recipe.id)}" title="${escapeAttr(i18n['home.restore_recipe'])}">
                                        <i class="bi bi-eye"></i>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }
            html += '</div>';
            list.innerHTML = html;
        } else {
            empty.style.display = 'block';
        }
    } catch (error) {
        loading.style.display = 'none';
        list.innerHTML = `<p class="text-danger">${i18n['common.error']}: ${escapeHtml(error.message)}</p>`;
    }
}

async function restoreRecipe(recipeId) {
    try {
        const response = await fetch(`/api/recipes/${recipeId}/restore`, { method: 'PATCH' });
        if (!response.ok) return;
        const data = await response.json();

        if (data.success) {
            // Reload hidden recipes list
            await loadHiddenRecipes();
            // Update button count
            await updateHiddenRecipesButton();
        } else {
            Swal.fire({ icon: 'error', title: i18n['common.error'], text: t(data.message_key, data.message_params) });
        }
    } catch (error) {
        Swal.fire({ icon: 'error', title: i18n['common.error'], text: error.message });
    }
}


function renderPantryRecipeCard(recipe, colorClass) {
    const recipeUrl = safeUrl(recipe.url);
    const imageUrl = safeUrl(recipe.image_url);
    const recipeUrlAttr = escapeAttr(recipeUrl);
    const imageUrlAttr = escapeAttr(imageUrl);
    const recipeName = escapeHtml(decodeHtmlEntities(recipe.name || ''));
    const recipeNameAttr = escapeAttr(decodeHtmlEntities(recipe.name || ''));
    const recipeSource = escapeHtml(displayRecipeSource(recipe.source));
    const numMatches = parseInt(recipe.num_matches) || 0;
    const prepTime = recipe.prep_time_minutes;
    const matchedOffers = recipe.matched_offers || [];

    // Use capped total_savings from backend (same as renderRecipeCard)
    let cappedSavings = parseFloat(recipe.total_savings) || 0;
    let uncappedSavings = 0;
    const byKeyword = {};
    matchedOffers.forEach(o => {
        const kw = o.matched_keyword || 'unknown';
        const savings = parseFloat(o.savings) || 0;
        if (!byKeyword[kw] || savings > byKeyword[kw]) {
            byKeyword[kw] = savings;
        }
    });
    uncappedSavings = Object.values(byKeyword).reduce((sum, s) => sum + s, 0);
    if (!cappedSavings && uncappedSavings > 0) cappedSavings = uncappedSavings;
    const isCapped = uncappedSavings > 0 && Math.round(cappedSavings) < Math.round(uncappedSavings);
    let savingsText = '';
    if (cappedSavings > 0) {
        savingsText = t('home.save_approx', {amount: Math.round(cappedSavings)});
        if (isCapped) savingsText += '*';
    }

    // Pantry-specific badges
    const missingText = recipe.missing_count > 0 ?
        `<span class="badge bg-${colorClass} text-dark">${i18n['home.pantry_missing']} ${recipe.missing_preview.map(m => escapeHtml(m)).join(', ')}</span>` :
        `<span class="badge bg-success">${i18n['home.pantry_complete']}</span>`;

    // Store data for popup
    const offersData = JSON.stringify(matchedOffers);
    const ingredientsData = JSON.stringify(recipe.ingredients || []);
    const servings = recipe.servings || 0;

    return `
        <div class="recipe-card"
             data-recipe-id="${escapeAttr(recipe.id || '')}"
             data-recipe-url="${recipeUrlAttr}"
             data-recipe-name="${recipeNameAttr}"
             data-matched-offers="${encodeJsonAttr(offersData)}"
             data-ingredients="${encodeJsonAttr(ingredientsData)}"
             data-servings="${servings}"
             data-capped-savings="${Math.round(cappedSavings)}"
             data-is-capped="${isCapped}">
            <div class="recipe-card-image">
                ${imageUrl ?
                    `<img src="${imageUrlAttr}" alt="${recipeNameAttr}" loading="lazy">` :
                    '<div class="recipe-card-placeholder"><i class="bi bi-image"></i></div>'
                }
            </div>
            <div class="recipe-card-body">
                <h6 class="recipe-card-title">${recipeName}</h6>
                <div class="recipe-card-meta">
                    <div class="recipe-card-info-row">
                        ${missingText}
                        <span class="badge bg-light text-dark">${t('home.pantry_coverage', {pct: parseInt(recipe.coverage_pct) || 0})}</span>
                    </div>
                    <div class="recipe-card-info-row">
                        <small class="recipe-card-source">${recipeSource}</small>
                        ${savingsText ? `<span class="recipe-card-savings"><i class="bi bi-piggy-bank"></i> ${savingsText}</span>` : ''}
                        ${prepTime ? `<span class="recipe-card-time"><i class="bi bi-clock"></i> ${formatPrepTime(prepTime)}</span>` : ''}
                    </div>
                    <button class="btn btn-outline-${numMatches > 0 ? 'success' : 'secondary'} btn-sm show-offers-btn">
                        ${numMatches > 0 ? t('home.offers_show', {count: numMatches}) : i18n['home.no_offers_show_recipe']}
                    </button>
                </div>
            </div>
        </div>
    `;
}

// ============================================
// Recipe Suggestions Functions
// ============================================

let allSuggestions = [];
let suggestionsLoaded = false;
let currentBalance = { 'meat': 3, 'fish': 3, 'vegetarian': 3, 'smart_buy': 3 };
let currentRecipeId = null;  // For modal exclude button

// Exclude (hide) a recipe - called from card trash button
async function excludeRecipeFromCard(recipeId, recipeName, event) {
    event.stopPropagation();
    event.preventDefault();

    const result = await Swal.fire({
        icon: 'question',
        title: i18n['home.hide_title'],
        text: i18n['home.hide_text'].replace('{name}', recipeName),
        showCancelButton: true,
        confirmButtonText: i18n['home.hide_confirm'],
        cancelButtonText: i18n['home.hide_cancel'],
        confirmButtonColor: '#dc3545'
    });

    if (!result.isConfirmed) return;

    try {
        const response = await fetch(`/api/recipes/${recipeId}/exclude`, { method: 'PATCH' });
        if (!response.ok) return;
        const data = await response.json();

        if (data.success) {
            // Remove the card from DOM
            const card = document.querySelector(`.recipe-card[data-recipe-id="${recipeId}"]`);
            if (card) {
                card.style.transition = 'opacity 0.3s, transform 0.3s';
                card.style.opacity = '0';
                card.style.transform = 'scale(0.8)';
                setTimeout(() => {
                    card.remove();
                    updateCategoryHeaders();
                    // Update count display
                    const countEl = document.querySelector('.suggestions-count');
                    if (countEl) {
                        const remaining = document.querySelectorAll('.recipe-card').length;
                        countEl.textContent = t('home.showing_recipes', {count: remaining});
                    }
                }, 300);
            }

            // Update hidden recipes button and badge
            await updateHiddenRecipesButton();

            // Also remove from allSuggestions array and update sessionStorage
            allSuggestions = allSuggestions.filter(r => String(r.id) !== String(recipeId));
            renderedRecipeIds.delete(String(recipeId));

            // Update sessionStorage so "load more" continues to work
            safeSessionSet('recipeSuggestions', JSON.stringify({
                recipes: allSuggestions,
                noMore: false
            }));
        } else {
            Swal.fire({ icon: 'error', title: i18n['common.error'], text: t(data.message_key, data.message_params) });
        }
    } catch (error) {
        Swal.fire({ icon: 'error', title: i18n['common.error'], text: error.message });
    }
}

// Exclude recipe from modal
async function excludeCurrentRecipe() {
    if (!currentRecipeId) return;

    const modal = bootstrap.Modal.getInstance(document.getElementById('matchedOffersModal'));
    if (modal) modal.hide();

    // Get recipe name from the modal
    const recipeName = document.getElementById('modalRecipeName')?.textContent || '';

    await excludeRecipeFromCard(currentRecipeId, recipeName, { stopPropagation: () => {}, preventDefault: () => {} });
}

// Restore suggestions from sessionStorage on page load
(function restoreSuggestions() {
    // Check if cache was rebuilt (e.g., after toggling favorites on recipes page)
    if (sessionStorage.getItem('suggestionsNeedRefresh') === 'true') {
        sessionStorage.removeItem('suggestionsNeedRefresh');
        sessionStorage.removeItem('recipeSuggestions');
        sessionStorage.removeItem('recipeBalance');
        sessionStorage.removeItem('cacheGeneration');
        dbg.log('[Suggestions] Cache invalidated after favorites change');
        return; // Skip restore, will load fresh on demand
    }

    // Auto-invalidate if server cache was rebuilt since last load
    const serverGeneration = pageConfig.cacheGeneration == null ? '' : String(pageConfig.cacheGeneration);
    const storedGeneration = sessionStorage.getItem('cacheGeneration');
    if (serverGeneration && storedGeneration && serverGeneration !== storedGeneration) {
        sessionStorage.removeItem('recipeSuggestions');
        sessionStorage.removeItem('recipeBalance');
        sessionStorage.removeItem('cacheGeneration');
        dbg.log(`[Suggestions] Server cache rebuilt (${storedGeneration} → ${serverGeneration}), auto-cleared`);
        return;
    }

    const cached = sessionStorage.getItem('recipeSuggestions');
    const cachedBalance = sessionStorage.getItem('recipeBalance');
    if (cachedBalance) {
        try { currentBalance = JSON.parse(cachedBalance); } catch(e) {}
    }
    if (cached) {
        try {
            const data = JSON.parse(cached);
            allSuggestions = data.recipes || [];
            if (allSuggestions.length > 0) {
                suggestionsLoaded = true;

                // Only auto-expand if suggestions is the active section (or no section saved)
                const activeSection = localStorage.getItem('activeSection');
                if (activeSection && activeSection !== 'suggestions') {
                    // Data restored but don't show — the DOMContentLoaded handler
                    // will open the correct section
                    return;
                }

                // Wait for DOM to be ready
                setTimeout(() => {
                    const collapseSection = document.getElementById('recipe-suggestions-section');
                    const pantrySection = document.getElementById('pantry-section');
                    const results = document.getElementById('suggestions-results');
                    const loading = document.getElementById('suggestions-loading');
                    const loadMoreDiv = document.getElementById('suggestions-load-more');
                    const loadMoreBtn = document.getElementById('load-more-suggestions-btn');
                    const suggestionsHeader = document.getElementById('suggestions-header-sticky');
                    const stickyBlock = document.getElementById('sticky-header-block');

                    if (results && loading && collapseSection) {
                        // Expand suggestions, ensure pantry is closed
                        collapseSection.classList.add('show');
                        if (pantrySection) pantrySection.classList.remove('show');

                        // Show sticky header elements
                        if (suggestionsHeader) suggestionsHeader.style.display = 'flex';
                        if (stickyBlock) stickyBlock.classList.add('has-shadow');

                        // Mark button active
                        document.getElementById('btn-suggestions').classList.add('main-nav-active');
                        localStorage.setItem('activeSection', 'suggestions');

                        loading.style.display = 'none';
                        results.style.display = 'block';
                        if (loadMoreDiv) loadMoreDiv.style.display = 'block';
                        renderSuggestions(allSuggestions);
                        // Update button state
                        if (loadMoreBtn && data.noMore) {
                            loadMoreBtn.innerHTML = `<i class="bi bi-check-circle"></i> ${i18n['home.no_more']}`;
                            loadMoreBtn.disabled = true;
                        }
                    }
                }, 100);
            }
        } catch (e) {
            console.error('Error restoring suggestions:', e);
        }
    }
})();

async function loadRecipeSuggestions() {
    // If already loaded, just re-render to show categories
    if (suggestionsLoaded && allSuggestions.length > 0) {
        const results = document.getElementById('suggestions-results');
        const loading = document.getElementById('suggestions-loading');
        const loadMoreDiv = document.getElementById('suggestions-load-more');

        loading.style.display = 'none';
        results.style.display = 'block';
        if (loadMoreDiv) loadMoreDiv.style.display = 'block';

        // Re-render to ensure category headers are shown
        renderSuggestions(allSuggestions);
        return;
    }

    allSuggestions = [];
    await loadMoreSuggestions(true);
}

/// Force refresh: rebuild cache and reload from scratch
async function refreshRecipeSuggestions() {
    // Clear local state
    sessionStorage.removeItem('recipeSuggestions');
    sessionStorage.removeItem('recipeBalance');
    sessionStorage.removeItem('cacheGeneration');
    suggestionsLoaded = false;
    allSuggestions = [];
    renderedRecipeIds = new Set();

    // Show loading popup while cache rebuilds
    Swal.fire({
        title: i18n['home.rebuild_title'],
        html: `<div class="mb-2">${i18n['home.rebuild_text']}</div><small class="text-muted">${i18n['home.rebuild_wait']}</small>`,
        allowOutsideClick: false,
        allowEscapeKey: false,
        showConfirmButton: false,
        didOpen: () => {
            Swal.showLoading();
        }
    });

    try {
        // Trigger cache rebuild
        await fetch('/api/cache/reset', { method: 'POST' });

        // Poll for completion (max 5 minutes — large DBs take 2-3 min)
        const maxWait = 300000;
        const pollInterval = 500;
        const startTime = Date.now();

        while (Date.now() - startTime < maxWait) {
            await new Promise(resolve => setTimeout(resolve, pollInterval));

            try {
                const statusResponse = await fetch('/api/cache/status');
                if (!statusResponse.ok) continue;
                const status = await statusResponse.json();

                if (status.ready) {
                    dbg.log(`[Cache] Rebuilt in ${Date.now() - startTime}ms, ${status.total_matches} recipes`);
                    break;
                }
            } catch (e) {
                // Ignore polling errors, keep waiting
            }
        }
    } catch (e) {
        console.error('Cache reset failed:', e);
    }

    // Close popup and load fresh recipes
    Swal.close();
    cacheResetTriggered = false;  // Reset flag so page-leave will trigger again
    loadMoreSuggestions(true);
}

async function loadMoreSuggestions(isInitialLoad = false) {
    const loading = document.getElementById('suggestions-loading');
    const empty = document.getElementById('suggestions-empty');
    const results = document.getElementById('suggestions-results');
    const loadMoreDiv = document.getElementById('suggestions-load-more');
    const loadMoreBtn = document.getElementById('load-more-suggestions-btn');

    if (isInitialLoad) {
        loading.style.display = 'block';
        empty.style.display = 'none';
        results.style.display = 'none';
        loadMoreDiv.style.display = 'none';
    } else {
        loadMoreBtn.disabled = true;
        loadMoreBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> ${i18n['common.loading']}`;
    }

    try {
        // Check cache status FIRST on initial load — don't attempt heavy live
        // computation if cache is in error state
        if (isInitialLoad) {
            try {
                const statusResp = await fetch('/api/cache/status');
                if (statusResp.ok) {
                    const cacheStatus = await statusResp.json();
                    if (cacheStatus.status === 'error') {
                        loading.style.display = 'none';
                        const warnDiv = document.createElement('div');
                        warnDiv.className = 'alert alert-warning fade show mx-3 mt-2';
                        warnDiv.innerHTML = `<i class="bi bi-exclamation-triangle-fill"></i> <strong>${i18n['home.cache_error_title']}:</strong> ${i18n['home.cache_error_text']}`;
                        const container = document.getElementById('suggestions-results')?.parentNode;
                        if (container) container.insertBefore(warnDiv, container.firstChild);
                        return;
                    }
                }
            } catch (e) { /* ignore status check errors, proceed normally */ }
        }

        // Send already-shown recipe IDs so server skips them (POST to avoid URL length limits)
        const excludeIds = allSuggestions.map(r => r.id);
        const response = await fetch('/api/matching/preview', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({exclude_ids: excludeIds, max_results: 12})
        });
        if (!response.ok) return;
        const data = await response.json();

        loading.style.display = 'none';

        if (data.success && data.recipes && data.recipes.length > 0) {
            // Check if server cache was rebuilt (different generation than what we have stored)
            const storedGeneration = sessionStorage.getItem('cacheGeneration');
            const serverGeneration = data.cache_generation;
            let generationChanged = false;

            if (storedGeneration && serverGeneration && storedGeneration !== serverGeneration) {
                // Cache was rebuilt on server - clear client state and start fresh
                dbg.log(`[Suggestions] Cache rebuilt on server (${storedGeneration} → ${serverGeneration}), clearing client state`);
                allSuggestions = [];
                renderedRecipeIds.clear();
                generationChanged = true;
            }

            // Store the current cache generation
            if (serverGeneration) {
                safeSessionSet('cacheGeneration', serverGeneration);
            }

            // Deduplicate: only add recipes we don't already have
            const existingIds = new Set(allSuggestions.map(r => String(r.id)));
            const newRecipes = data.recipes.filter(r => !existingIds.has(String(r.id)));

            allSuggestions = allSuggestions.concat(newRecipes);
            suggestionsLoaded = true;

            dbg.log(`[Suggestions] Received ${data.recipes.length} from API, ${newRecipes.length} were new`);

            // Store balance for dynamic layout
            if (data.balance) {
                currentBalance = data.balance;
                safeSessionSet('recipeBalance', JSON.stringify(data.balance));
            }

            // Cache in sessionStorage for tab persistence
            const noMore = data.recipes.length < 12;
            safeSessionSet('recipeSuggestions', JSON.stringify({
                recipes: allSuggestions,
                noMore: noMore
            }));

            // Use appendOnly=true when loading more (not initial load)
            // Force full re-render if cache generation changed (DOM is stale)
            const appendOnly = !isInitialLoad && !generationChanged;
            renderSuggestions(allSuggestions, appendOnly);
            results.style.display = 'block';
            loadMoreDiv.style.display = 'block';

            // Disable button if no more
            if (noMore) {
                loadMoreBtn.innerHTML = `<i class="bi bi-check-circle"></i> ${i18n['home.no_more']}`;
                loadMoreBtn.disabled = true;
            } else {
                loadMoreBtn.innerHTML = `<i class="bi bi-plus-circle"></i> ${i18n['home.load_more']}`;
                loadMoreBtn.disabled = false;
            }
        } else if (isInitialLoad) {
            empty.style.display = 'block';
        } else {
            // Load more returned empty batch - no more recipes in cache
            // Re-enable button and show "no more" state
            if (loadMoreBtn) {
                loadMoreBtn.innerHTML = `<i class="bi bi-check-circle"></i> ${i18n['home.no_more']}`;
                loadMoreBtn.disabled = true;
            }
            dbg.log('[Suggestions] Empty batch received - cache exhausted');
        }
    } catch (error) {
        loading.style.display = 'none';
        console.error('Error loading suggestions:', error);

        if (isInitialLoad) {
            empty.style.display = 'block';
        } else {
            // Re-enable button on error so user can retry
            if (loadMoreBtn) {
                loadMoreBtn.innerHTML = `<i class="bi bi-exclamation-circle"></i> ${i18n['common.retry']}`;
                loadMoreBtn.disabled = false;
            }
        }
    }
}

// Track rendered recipe IDs to avoid duplicates
let renderedRecipeIds = new Set();

function renderSuggestions(recipes, appendOnly = false) {
    const container = document.getElementById('suggestions-results');
    const categoryHeadersEl = document.getElementById('category-headers-sticky');

    // Use shared constants (defined at top of script)
    const categoryOrder = CATEGORY_ORDER;
    const categoryInfo = CATEGORY_INFO;

    // Calculate dynamic layout based on balance (raw counts 0-4)
    // Active = count > 0
    // Wide = normalized weight >= 0.5 (50%), BUT only if some category is hidden (0%)
    // This prevents 5-column layouts when all 4 categories are active
    const totalWeight = categoryOrder.reduce((sum, cat) => sum + (currentBalance[cat] || 0), 0);
    const activeCategories = [];
    const potentialWideCategories = [];
    for (const cat of categoryOrder) {
        const count = currentBalance[cat] || 0;
        if (count > 0) {
            activeCategories.push(cat);
            // Check if normalized weight >= 50%
            const normalizedWeight = totalWeight > 0 ? count / totalWeight : 0;
            if (normalizedWeight >= 0.5) potentialWideCategories.push(cat);
        }
    }

    // Only allow wide categories if there's at least one hidden category
    const hasHiddenCategory = activeCategories.length < 4;
    // Single active category: use full-width (4 columns) instead of wide (2 columns)
    const isSingleCategory = activeCategories.length === 1;
    const wideCategories = (hasHiddenCategory && !isSingleCategory) ? new Set(potentialWideCategories) : new Set();
    const fullWidthCategory = isSingleCategory ? activeCategories[0] : null;

    // Build grid template: single category = 1fr (full width), wide = 2fr, normal = 1fr
    const gridParts = activeCategories.map(cat => {
        if (fullWidthCategory === cat) return '1fr';
        return wideCategories.has(cat) ? '2fr' : '1fr';
    });
    const gridTemplate = gridParts.join(' ') || 'repeat(4, 1fr)';

    // Apply grid to headers and rows
    categoryHeadersEl.style.setProperty('--category-grid', gridTemplate);
    container.style.setProperty('--category-grid', gridTemplate);

    // Group recipes by category (with deduplication by ID)
    const byCategory = { 'meat': [], 'fish': [], 'vegetarian': [], 'smart_buy': [] };
    const seenIds = new Set();
    recipes.forEach(recipe => {
        // Skip duplicates (same recipe ID)
        if (recipe.id && seenIds.has(recipe.id)) return;
        if (recipe.id) seenIds.add(recipe.id);

        let cat = recipe.category || 'vegetarian';
        if (byCategory[cat]) byCategory[cat].push(recipe);
    });

    // Update category headers in sticky section (only active categories)
    let headersHtml = '';
    for (const cat of activeCategories) {
        const info = categoryInfo[cat];
        const count = byCategory[cat].length;
        const isWide = wideCategories.has(cat);
        headersHtml += `
            <div class="category-header ${cat}${isWide ? ' wide' : ''}">
                <i class="bi ${info.icon}"></i> ${info.name}: ${count}
            </div>
        `;
    }
    categoryHeadersEl.innerHTML = headersHtml;
    categoryHeadersEl.style.display = activeCategories.length > 0 ? 'grid' : 'none';

    // Check if we should append or rebuild
    const existingColumns = container.querySelector('.category-columns');

    // Calculate expected total (sum of byCategory for active categories)
    const expectedTotal = activeCategories.reduce((sum, cat) => sum + byCategory[cat].length, 0);

    // Only use append mode if columns exist AND have correct structure
    const canAppend = appendOnly && existingColumns &&
        activeCategories.every(cat => existingColumns.querySelector(`.category-column[data-category="${cat}"]`));

    if (canAppend) {
        // APPEND MODE: Add new recipes to existing columns
        // ALWAYS sync renderedRecipeIds with DOM (not just when sizes differ)
        // This ensures consistency even if there were type mismatches before
        const domCardIds = new Set();
        container.querySelectorAll('.recipe-card[data-recipe-id]').forEach(card => {
            domCardIds.add(card.dataset.recipeId);  // Always strings from DOM
        });
        renderedRecipeIds = domCardIds;

        let cardsAdded = 0;
        for (const cat of activeCategories) {
            const columnEl = existingColumns.querySelector(`.category-column[data-category="${cat}"]`);
            if (!columnEl) continue;

            // Add any recipe not already rendered (don't use index-based logic)
            for (const recipe of byCategory[cat]) {
                if (!recipe || !recipe.id) continue;

                // Skip if already rendered (use String for consistent type comparison)
                const recipeIdStr = String(recipe.id);
                if (renderedRecipeIds.has(recipeIdStr)) continue;

                const cardWrapper = document.createElement('div');
                cardWrapper.innerHTML = renderRecipeCard(recipe);
                columnEl.appendChild(cardWrapper.firstElementChild);
                renderedRecipeIds.add(recipeIdStr);
                cardsAdded++;
            }
        }

        // Update total count (count actual DOM cards, not array length)
        const totalCards = container.querySelectorAll('.recipe-card').length;
        const countEl = container.querySelector('.suggestions-count');
        if (countEl) countEl.textContent = t('home.showing_recipes', {count: totalCards});

        dbg.log(`[Suggestions] Append: added ${cardsAdded} cards, total now ${totalCards}/${expectedTotal}`);

        // If we expected more cards but couldn't add them AND we added nothing, force rebuild
        if (cardsAdded === 0 && totalCards < expectedTotal) {
            dbg.warn(`[Suggestions] Append failed (${totalCards}/${expectedTotal}), forcing rebuild`);
            renderedRecipeIds = new Set();
            renderSuggestions(recipes, false);
            return;
        }

    } else {
        // FRESH BUILD: Create columns from scratch
        renderedRecipeIds = new Set();

        let html = '<div class="category-columns">';
        let totalRendered = 0;

        for (const cat of activeCategories) {
            const isWide = wideCategories.has(cat);
            const isFullWidth = fullWidthCategory === cat;
            const colClass = isFullWidth ? ' full-width' : (isWide ? ' wide' : '');
            html += `<div class="category-column${colClass}" data-category="${cat}">`;

            for (const recipe of byCategory[cat]) {
                html += renderRecipeCard(recipe);
                renderedRecipeIds.add(String(recipe.id));  // Use String for consistent type
                totalRendered++;
            }

            html += '</div>';
        }

        html += '</div>';
        html += `<p class="text-muted text-center mt-3 suggestions-count">${t('home.showing_recipes', {count: totalRendered})}</p>`;

        container.innerHTML = html;
    }

    // Add event delegation for recipe cards (safer than inline onclick)
    // Use event delegation on container to handle dynamically added cards
    if (!container.dataset.listenersAttached) {
        container.addEventListener('click', function(e) {
            const card = e.target.closest('.recipe-card');
            if (!card) return;

            // Don't open URL if clicking the "show offers" button
            if (e.target.closest('.show-offers-btn')) {
                e.stopPropagation();
                e.preventDefault();
                const recipeId = card.dataset.recipeId;
                const recipeName = card.dataset.recipeName;
                const matchedOffers = JSON.parse(card.dataset.matchedOffers || '[]');
                const ingredients = JSON.parse(card.dataset.ingredients || '[]');
                const servings = parseInt(card.dataset.servings) || 0;
                const cardIsCapped = card.dataset.isCapped === 'true';
                const cardCappedSavings = parseInt(card.dataset.cappedSavings) || 0;
                showMatchedOffers(recipeId, recipeName, matchedOffers, ingredients, servings, cardIsCapped, cardCappedSavings);
                return;
            }
            const url = card.dataset.recipeUrl;
            if (url) window.open(url, '_blank');
        });
        container.dataset.listenersAttached = 'true';
    }

    // Equalize card heights across columns (delay to ensure DOM is rendered)
    requestAnimationFrame(() => {
        requestAnimationFrame(equalizeCardHeights);
    });
}

// Update category headers after a recipe is removed
function updateCategoryHeaders() {
    const categoryHeadersEl = document.getElementById('category-headers-sticky');
    const container = document.getElementById('suggestions-results');
    if (!categoryHeadersEl || !container) return;

    // Use shared constant (defined at top of script)
    const categoryInfo = CATEGORY_INFO;

    // Count actual cards in each column
    const columns = container.querySelectorAll('.category-column');
    let headersHtml = '';
    columns.forEach(col => {
        const cat = col.dataset.category;
        if (!cat || !categoryInfo[cat]) return;
        const count = col.querySelectorAll('.recipe-card').length;
        const isWide = col.classList.contains('wide');
        headersHtml += `
            <div class="category-header ${cat}${isWide ? ' wide' : ''}">
                <i class="bi ${categoryInfo[cat].icon}"></i> ${categoryInfo[cat].name}: ${count}
            </div>
        `;
    });
    categoryHeadersEl.innerHTML = headersHtml;
}

// Update the "Showing X recipes" display
function updateRecipeCountDisplay() {
    const container = document.getElementById('suggestions-results');
    if (!container) return;
    const totalCards = container.querySelectorAll('.recipe-card').length;
    const countEl = container.querySelector('.suggestions-count');
    if (countEl) countEl.textContent = t('home.showing_recipes', {count: totalCards});
}

// Equalize card heights so cards in the same "row" across columns have the same height
function equalizeCardHeights() {
    const columns = document.querySelectorAll('.category-column');
    if (!columns.length) return;

    // Get all cards from each column
    const cardsByColumn = Array.from(columns).map(col =>
        Array.from(col.querySelectorAll('.recipe-card'))
    );

    // Find max number of cards in any column
    const maxCards = Math.max(...cardsByColumn.map(cards => cards.length));
    if (maxCards === 0) return;

    // For each row index, equalize heights
    for (let rowIdx = 0; rowIdx < maxCards; rowIdx++) {
        const cardsInRow = cardsByColumn
            .map(cards => cards[rowIdx])
            .filter(card => card);

        if (cardsInRow.length <= 1) continue;

        // Reset heights first to get natural height
        cardsInRow.forEach(card => card.style.height = 'auto');

        // Find max height in this row
        const maxHeight = Math.max(...cardsInRow.map(card => card.offsetHeight));

        // Apply to all cards in this row
        cardsInRow.forEach(card => card.style.height = maxHeight + 'px');
    }
}

// Re-equalize on window resize (debounced)
let resizeTimeout;
window.addEventListener('resize', function() {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(equalizeCardHeights, 150);
});

function renderRecipeCard(recipe) {
    const recipeUrl = safeUrl(recipe.url);
    const imageUrl = safeUrl(recipe.image_url);
    const recipeUrlAttr = escapeAttr(recipeUrl);
    const imageUrlAttr = escapeAttr(imageUrl);
    // Decode HTML entities first (e.g., &amp; -> &), then escape for safe HTML display
    const recipeName = escapeHtml(decodeHtmlEntities(recipe.name || ''));
    const recipeNameAttr = escapeAttr(decodeHtmlEntities(recipe.name || ''));
    // Remove " Recept" suffix for cleaner display (Mathem Recept -> Mathem, etc.)
    const recipeSource = escapeHtml(displayRecipeSource(recipe.source));
    const numMatches = parseInt(recipe.num_matches) || 0;
    const prepTime = recipe.prep_time_minutes;
    const matchedOffers = recipe.matched_offers || [];

    // Use capped total_savings from backend for card display (sorted value)
    // Fall back to calculating from offers if not available (search/pantry)
    let cappedSavings = parseFloat(recipe.total_savings) || 0;
    let uncappedSavings = 0;
    const byKeyword = {};
    matchedOffers.forEach(o => {
        const kw = o.matched_keyword || 'unknown';
        const savings = parseFloat(o.savings) || 0;
        if (!byKeyword[kw] || savings > byKeyword[kw]) {
            byKeyword[kw] = savings;
        }
    });
    uncappedSavings = Object.values(byKeyword).reduce((sum, s) => sum + s, 0);
    if (!cappedSavings && uncappedSavings > 0) cappedSavings = uncappedSavings;
    const isCapped = uncappedSavings > 0 && Math.round(cappedSavings) < Math.round(uncappedSavings);

    // Format savings text (show capped value on card)
    let savingsText = '';
    if (cappedSavings > 0) {
        if (i18n['home.ranking_mode'] === 'percentage' && recipe.avg_savings_pct > 0) {
            const numItems = parseInt(recipe.num_matches) || 1;
            const pct = Math.round(recipe.avg_savings_pct);
            savingsText = numItems === 1
                ? t('home.save_pct_item', {pct})
                : t('home.save_pct_items', {pct, count: numItems});
        } else {
            savingsText = t('home.save_approx', {amount: Math.round(cappedSavings)});
            if (isCapped) savingsText += '*';
        }
    }

    // Store matched_offers, ingredients and servings as data attributes
    const offersData = JSON.stringify(matchedOffers);
    const ingredientsData = JSON.stringify(recipe.ingredients || []);
    const servings = recipe.servings || 0;

    return `
        <div class="recipe-card"
             data-recipe-id="${escapeAttr(recipe.id || '')}"
             data-recipe-url="${recipeUrlAttr}"
             data-recipe-name="${recipeNameAttr}"
             data-matched-offers="${encodeJsonAttr(offersData)}"
             data-ingredients="${encodeJsonAttr(ingredientsData)}"
             data-servings="${servings}"
             data-capped-savings="${Math.round(cappedSavings)}"
             data-is-capped="${isCapped}">
            <div class="recipe-card-image">
                ${imageUrl ?
                    `<img src="${imageUrlAttr}" alt="${recipeNameAttr}" loading="lazy">` :
                    '<div class="recipe-card-placeholder"><i class="bi bi-image"></i></div>'
                }
            </div>
            <div class="recipe-card-body">
                <h6 class="recipe-card-title">${recipeName}</h6>
                <div class="recipe-card-meta">
                    <div class="recipe-card-info-row">
                        <small class="recipe-card-source">${recipeSource}</small>
                        ${savingsText ? `<span class="recipe-card-savings"><i class="bi bi-piggy-bank"></i> ${savingsText}</span>` : ''}
                        ${prepTime ? `<span class="recipe-card-time"><i class="bi bi-clock"></i> ${formatPrepTime(prepTime)}</span>` : ''}
                    </div>
                    <button class="btn btn-outline-${numMatches > 0 ? 'success' : 'secondary'} btn-sm show-offers-btn">
                        ${numMatches > 0 ? t('home.offers_show', {count: numMatches}) : i18n['home.no_offers_show_recipe']}
                    </button>
                </div>
            </div>
        </div>
    `;
}

// Clean up ingredient text - collapse whitespace, round decimals, decode HTML entities
function formatIngredient(text) {
    if (!text) return '';
    // Collapse whitespace
    let clean = text.replace(/\s+/g, ' ').trim();
    // Decode HTML entities (&amp; -> &)
    const textarea = document.createElement('textarea');
    textarea.innerHTML = clean;
    clean = textarea.value;
    // Round ugly decimals like "100.000002" -> "100", "1.999998" -> "2"
    clean = clean.replace(/(\d+)\.(\d{4,})/g, (match, whole, decimals) => {
        const num = parseFloat(match);
        // If very close to whole number, round it
        if (Math.abs(num - Math.round(num)) < 0.01) {
            return Math.round(num).toString();
        }
        // Otherwise round to 1 decimal
        return num.toFixed(1).replace(/\.0$/, '');
    });
    return clean;
}

// Process ingredient array - merge "eller"/"och" items with previous
function processIngredients(ingredients) {
    if (!ingredients || !ingredients.length) return [];

    const result = [];
    for (let i = 0; i < ingredients.length; i++) {
        let item = formatIngredient(ingredients[i]);
        if (!item) continue;

        // Check if this item starts with "eller" or "och" (connector word)
        const startsWithConnector = /^(eller|och)\s/i.test(item);

        if (startsWithConnector && result.length > 0) {
            // Merge with previous item
            result[result.length - 1] += ' ' + item;
        } else {
            result.push(item);
        }
    }
    return result;
}

// Helper: Extract weight in grams from recipe ingredient (e.g., "50 g Cheddar" -> 50)
function parseIngredientWeight(ingredientText) {
    if (!ingredientText) return null;
    const text = ingredientText.toLowerCase();

    // Pattern: "50 g", "100 gram", "1,5 kg", "500g"
    const kgMatch = text.match(/(\d+(?:[,\.]\d+)?)\s*kg\b/);
    if (kgMatch) return parseFloat(kgMatch[1].replace(',', '.')) * 1000;

    const gMatch = text.match(/(\d+(?:[,\.]\d+)?)\s*(?:g|gram)\b/);
    if (gMatch) return parseFloat(gMatch[1].replace(',', '.'));

    // Volume-to-weight conversion for dry goods commonly sold by kg
    // 1 msk = 0.15 dl, 1 tsk = 0.05 dl
    const volumeConversions = {
        // Approximate grams per dl for common dry goods
        'mjöl':       60,   // wheat flour, all types
        'vetemjöl':   60,
        'dinkel':     60,
        'rågsikt':    60,
        'grahamsmjöl':65,
        'socker':     85,
        'strösocker': 85,
        'florsocker': 65,
        'muscovado':  85,
        'havregryn':  40,
        'havre':      40,
        'grynmjöl':   70,
        'mannagryn':  70,
        'majzena':    65,   // corn starch
        'majsstärkelse': 65,
        'potatismjöl':65,
        'bakpulver':  75,
        'cacao':      50,   // cocoa powder
        'kakao':      50,
        'ris':        90,
        // Liquids (density ~0.9-1.0 g/ml → ~90-100 g/dl)
        'olja':       90,   // all oils (rapsolja, olivolja, matolja etc.)
        'rapsolja':   90,
        'olivolja':   90,
        'matolja':    90,
        'kokosolja':  90,
        'sesamolja':  90,
        'solrosolja': 90,
        'vinäger':    100,  // vinegar ≈ water density
        'ättika':     100,
        'balsamico':  100,
        'soja':       100,  // soy sauce
        'sojasås':    100,
        'sirap':      140,  // syrup (denser)
        'honung':     140,
        'sylt':       130,  // jam/preserves (~1.3 g/ml)
        'lingonsylt': 130,
        'jordgubbssylt': 130,
        'marmelad':   130,
        'ketchup':    120,
        'senap':      110,
        'majonnäs':   95,
        'majonnas':   95,
        'grädde':     100,  // cream ≈ water density
        'gradde':     100,
        'gräddfil':   100,
        'graddfil':   100,
        'crème fraîche': 100,
        'creme fraiche': 100,
        'filmjölk':   100,
        'mjölk':      100,
        'kokosmjölk': 100,
    };

    // Check for dl, msk, tsk volume units
    const dlMatch = text.match(/(\d+(?:[,\.]\d+)?)\s*dl\b/);
    const mskMatch = text.match(/(\d+(?:[,\.]\d+)?)\s*msk\b/);
    const tskMatch = text.match(/(\d+(?:[,\.]\d+)?)\s*tsk\b/);

    let volumeDl = null;
    if (dlMatch) {
        volumeDl = parseFloat(dlMatch[1].replace(',', '.'));
    } else if (mskMatch) {
        volumeDl = parseFloat(mskMatch[1].replace(',', '.')) * 0.15;
    } else if (tskMatch) {
        volumeDl = parseFloat(tskMatch[1].replace(',', '.')) * 0.05;
    }

    if (volumeDl !== null) {
        for (const [ingredient, gramsPerDl] of Object.entries(volumeConversions)) {
            if (text.includes(ingredient)) {
                return volumeDl * gramsPerDl;
            }
        }
    }

    return null;
}

// Helper: Extract weight in grams from product name (e.g., "ca 1,4kg" -> 1400)
function parseProductWeight(productName) {
    if (!productName) return null;
    const text = productName.toLowerCase();

    // Pattern: "ca 1,4kg", "ca 500g", "1,4 kg"
    const kgMatch = text.match(/(?:ca\s+)?(\d+(?:[,\.]\d+)?)\s*kg\b/);
    if (kgMatch) return parseFloat(kgMatch[1].replace(',', '.')) * 1000;

    const gMatch = text.match(/(?:ca\s+)?(\d+(?:[,\.]\d+)?)\s*(?:g|gram)\b/);
    if (gMatch) return parseFloat(gMatch[1].replace(',', '.'));

    // Volumes (ml ≈ grams for water-based, close enough for oversized detection)
    const lMatch = text.match(/(\d+(?:[,\.]\d+)?)\s*(?:l|liter)\b/);
    if (lMatch) return parseFloat(lMatch[1].replace(',', '.')) * 1000;

    const clMatch = text.match(/(\d+(?:[,\.]\d+)?)\s*cl\b/);
    if (clMatch) return parseFloat(clMatch[1].replace(',', '.')) * 10;

    const mlMatch = text.match(/(\d+(?:[,\.]\d+)?)\s*ml\b/);
    if (mlMatch) return parseFloat(mlMatch[1].replace(',', '.'));

    return null;
}

// Helper: Find the matching ingredient from recipe list
function findMatchingIngredient(ingredients, keyword) {
    if (!ingredients || !keyword) return null;
    const kwLower = keyword.toLowerCase();
    return ingredients.find(ing => ing && ing.toLowerCase().includes(kwLower));
}

// Helper: Check if product is significantly larger than recipe needs (>5x) OR expensive (>200kr)
// Expensive items (except meat/fish/cheese) get a warning as they may be bulk packages
function isOversizedProduct(productName, ingredientText, price = 0, weightGrams = null) {
    // Check weight-based oversizing (prefer API weight, fallback to name parsing)
    const productWeight = weightGrams || parseProductWeight(productName);
    const ingredientWeight = parseIngredientWeight(ingredientText);

    if (productWeight && ingredientWeight && ingredientWeight > 0) {
        if (productWeight > ingredientWeight * 5) {
            return true;
        }
    }

    // Check price-based warning (>200 kr, except meat/fish/cheese)
    if (price > 200) {
        const nameLower = (productName || '').toLowerCase();
        const exemptPatterns = /(kött|fläsk|biff|entrecote|ryggbiff|oxfilé|lammkött|kalv|bacon|skinka|fisk|lax|torsk|räk|sej|sill|tonfisk|ost|cheese|brie|cheddar|parmesan|gorgonzola|gruyère|manchego)/;
        if (!exemptPatterns.test(nameLower)) {
            return true;
        }
    }

    // Bulk product: >=4kg/4L is likely restaurant/wholesale packaging
    const bulkWeight = weightGrams || parseProductWeight(productName);
    if (bulkWeight && bulkWeight >= 4000) {
        return true;
    }

    return false;
}

function formatSavingsBadge(savings, offer) {
    if (i18n['home.ranking_mode'] === 'percentage') {
        const origPrice = parseFloat(offer.original_price) || parseFloat(offer.price) || 0;
        if (origPrice > 0 && savings > 0) {
            const pct = Math.round((savings / origPrice) * 100);
            return `-${pct}%`;
        }
    }
    return `-${savings.toFixed(1).replace('.', ',')} kr`;
}

function showMatchedOffers(recipeId, recipeName, matchedOffers, ingredients, servings, isCapped, cappedSavings) {
    // Store recipe ID and show exclude button for regular recipes
    currentRecipeId = recipeId;
    const excludeBtn = document.getElementById('excludeRecipeBtn');
    if (excludeBtn) {
        excludeBtn.style.display = recipeId ? 'inline-block' : 'none';
    }

    document.getElementById('modalRecipeName').textContent = recipeName;
    ingredients = ingredients || [];
    servings = servings || 0;

    // Group by ingredient line (not keyword) — multiple keywords from the same
    // ingredient line (e.g., "örter ex. basilika/timjan/oregano") should merge
    // into one group. Falls back to keyword grouping when _matched_ing_idx missing.
    const grouped = {};
    matchedOffers.forEach(offer => {
        const ingIdx = offer._matched_ing_idx;
        const keyword = offer.matched_keyword || i18n['common.unknown'];
        // Use ingredient index as group key when available, else keyword
        const groupKey = (ingIdx !== undefined && ingIdx !== null) ? `_ing_${ingIdx}` : keyword;
        if (!grouped[groupKey]) grouped[groupKey] = { keywords: new Set(), offers: [] };
        grouped[groupKey].keywords.add(keyword);
        grouped[groupKey].offers.push(offer);
    });
    // Convert to keyword-keyed format for display (join keywords with " / ")
    const groupedByKeyword = {};
    Object.values(grouped).forEach(g => {
        const displayKeyword = [...g.keywords].sort().join(' / ');
        groupedByKeyword[displayKeyword] = g.offers;
    });
    // Replace grouped for rest of code
    const groupedFinal = groupedByKeyword;

    const tbody = document.getElementById('offersTableBody');
    tbody.innerHTML = '';

    let totalSavings = 0;
    let pctSum = 0;
    let pctCount = 0;
    let uniqueIngredients = Object.keys(groupedFinal).length;

    Object.entries(groupedFinal).sort((a, b) => a[0].localeCompare(b[0], HOME_LOCALE)).forEach(([keyword, offers]) => {
        // Find the matching recipe ingredient (needed for frozen context check and oversized detection)
        const matchingIngredient = findMatchingIngredient(ingredients, keyword);

        // Sort by savings descending (best deals first)
        // Check if ingredient refers to a frozen product context
        const ingLower = (matchingIngredient || '').toLowerCase();
        const isFrozenContext = /\b(fryst|frysta|frosen|smoothie)\b/.test(ingLower);
        const sorted = [...offers].sort((a, b) => {
            // Exact qualifier-specific matches first (e.g. kalamata before generic black olives)
            const qsA = parseInt(a.qualifier_specificity_rank) || 0;
            const qsB = parseInt(b.qualifier_specificity_rank) || 0;
            if (qsA !== qsB) return qsB - qsA;
            // Qualifier matches first (exact flavor match), then context, then by savings
            const qA = a.qualifier_match ? 1 : 0;
            const qB = b.qualifier_match ? 1 : 0;
            if (qA !== qB) return qB - qA;
            // Context matches next (e.g., gratängost for gratäng recipes)
            const cA = a.context_match ? 1 : 0;
            const cB = b.context_match ? 1 : 0;
            if (cA !== cB) return cB - cA;
            const sD = (parseFloat(b.savings) || 0) - (parseFloat(a.savings) || 0);
            if (sD !== 0) return sD;
            // When ingredient is a frozen product, prefer frozen offers over drinks
            if (isFrozenContext) {
                const fA = a.category === 'frozen' ? 1 : 0;
                const fB = b.category === 'frozen' ? 1 : 0;
                if (fA !== fB) return fB - fA;
            }
            return 0;
        });
        const bestSavings = Math.max(...sorted.map(o => parseFloat(o.savings) || 0));
        totalSavings += bestSavings;

        // Track percentage for best offer per ingredient
        if (bestSavings > 0) {
            const bestOffer = sorted[0];
            const origPrice = parseFloat(bestOffer.original_price) || parseFloat(bestOffer.price) || 0;
            if (origPrice > 0) {
                pctSum += (bestSavings / origPrice) * 100;
                pctCount++;
            }
        }

        const displayKw = offers[0].display_keyword || keyword;
        const keywordEsc = escapeHtml(displayKw);

        if (offers.length === 1) {
            const offer = offers[0];
            const offerName = escapeHtml(offer.name || '');
            const storeName = escapeHtml(offer.store_name || '?');
            const price = parseFloat(offer.price) || 0;
            const savings = parseFloat(offer.savings) || 0;
            const productUrl = safeUrl(offer.product_url);
            const isMultiBuy = offer.is_multi_buy || false;
            const multiBuyQty = offer.multi_buy_quantity || 2;
            const isOversized = isOversizedProduct(offer.name, matchingIngredient, price, offer.weight_grams);

            const row = document.createElement('tr');
            if (isMultiBuy) row.classList.add('table-warning');
            row.innerHTML = `
                <td>
                    <strong>${offerName}</strong>
                    ${isOversized ? `<span class="ms-1" title="${i18n['home.modal_quantity_warning']}">📦</span>` : ''}
                    <br><small class="text-muted">${keywordEsc}</small>
                </td>
                <td class="text-center">
                    <small class="badge bg-secondary">${storeName}</small>
                </td>
                <td class="text-end" style="white-space:nowrap"><strong>${price.toFixed(2).replace('.', ',')} kr</strong></td>
                <td class="text-center">
                    <span class="badge bg-success">${savings ? formatSavingsBadge(savings, offer) : '-'}</span>
                </td>
                <td class="text-center">
                    ${isMultiBuy ? `<span class="badge bg-warning text-dark" title="${t('home.modal_multi_buy', {qty: multiBuyQty})}"><i class="bi bi-exclamation-triangle"></i> ${multiBuyQty}st</span>` : ''}
                </td>
                <td class="text-center">
                    ${productUrl ?
                        `<a href="${escapeAttr(productUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-outline-primary" aria-label="${escapeAttr(t('home.modal_open_product'))}"><i class="bi bi-box-arrow-up-right"></i></a>` :
                        '-'
                    }
                </td>
            `;
            tbody.appendChild(row);
        } else {
            const firstName = escapeHtml(sorted[0].name || '');
            const minPrice = parseFloat(sorted[0].price) || 0;
            const maxPrice = parseFloat(sorted[sorted.length-1].price) || 0;

            // Check if all offers are from the same store
            const storeNames = [...new Set(offers.map(o => o.store_name || '?'))];
            const storeDisplay = storeNames.length === 1
                ? `<small class="badge bg-secondary">${escapeHtml(storeNames[0])}</small>`
                : `<small class="text-muted">${i18n['home.modal_multiple_stores']}</small>`;

            // Check if any offer is multibuy
            const hasMultiBuy = offers.some(o => o.is_multi_buy);

            // Check if the best offer (first after sorting) is oversized or expensive
            const hasOversized = sorted.slice(0, 4).some(o => isOversizedProduct(o.name, matchingIngredient, parseFloat(o.price) || 0, o.weight_grams));

            // Build safe links with savings info (max 4 links)
            const links = sorted.slice(0, 4).map((o, i) => {
                const url = safeUrl(o.product_url);
                const oPrice = parseFloat(o.price) || 0;
                const mbIcon = o.is_multi_buy ? '⚠' : '';
                const osIcon = isOversizedProduct(o.name, matchingIngredient, oPrice, o.weight_grams) ? '📦' : '';
                const priceStr = oPrice.toFixed(2).replace('.', ',');
                const savingsStr = parseFloat(o.savings).toFixed(2).replace('.', ',');
                const osTitle = isOversizedProduct(o.name, matchingIngredient, oPrice, o.weight_grams) ? ` (${i18n['home.modal_quantity_warning']})` : '';
                const tooltip = t('home.modal_offer_tooltip', {price: priceStr, savings: savingsStr}) + (o.is_multi_buy ? ` (${i18n['home.modal_multi_buy_short']})` : '') + osTitle;
                return url ? `<a href="${escapeAttr(url)}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-outline-primary me-1" title="${escapeAttr(tooltip)}">${osIcon}${mbIcon}${i+1}</a>` : '';
            }).join('');

            // Show individual savings with decimals (max 4)
            const savingsArr = sorted.slice(0, 4).map(o => formatSavingsBadge(parseFloat(o.savings) || 0, o));
            const savingsDisplay = savingsArr.join(' / ');

            const row = document.createElement('tr');
            row.classList.add('table-info');
            row.innerHTML = `
                <td>
                    <strong>${firstName}</strong> ${i18n['home.modal_and_more']}
                    <span class="badge bg-primary ms-2">${t('home.modal_alternatives', {count: offers.length})}</span>
                    ${hasOversized ? `<span class="ms-1" title="${i18n['home.modal_quantity_warning']}">📦</span>` : ''}
                    <br><small class="text-muted">${keywordEsc}</small>
                </td>
                <td class="text-center">${storeDisplay}</td>
                <td class="text-end" style="white-space:nowrap">
                    <strong>${minPrice.toFixed(2).replace('.', ',')} kr</strong>
                    <small class="text-muted">- ${maxPrice.toFixed(2).replace('.', ',')} kr</small>
                </td>
                <td class="text-center">
                    <span class="badge bg-success">${savingsDisplay}</span>
                </td>
                <td class="text-center">
                    ${hasMultiBuy ? `<span class="badge bg-warning text-dark" title="${i18n['home.modal_some_multi']}"><i class="bi bi-exclamation-triangle"></i></span>` : ''}
                </td>
                <td class="text-center" style="white-space:nowrap">${links}</td>
            `;
            tbody.appendChild(row);
        }
    });

    const cappedNote = isCapped
        ? `<small class="text-muted d-block mt-1"><i class="bi bi-info-circle"></i> ${i18n['home.modal_savings_capped'].replace('{capped}', cappedSavings).replace('{cap}', 50)}</small>`
        : '';

    document.getElementById('offersSummary').innerHTML = `
        <div class="d-flex justify-content-between align-items-center">
            <span>${i18n['home.modal_ingredients_matched'].replace('{count}', `<strong>${escapeHtml(String(uniqueIngredients))}</strong>`)}</span>
            <span>${i18n['home.ranking_mode'] === 'percentage' && pctCount > 0
                ? t('home.modal_save_avg_pct', {pct: Math.round(pctSum / pctCount), count: pctCount})
                : t('home.modal_save_up_to', {amount: totalSavings.toFixed(1).replace('.', ',')})
            }</span>
        </div>
        ${cappedNote}
        <small class="text-muted d-block mt-2"><i class="bi bi-exclamation-triangle text-warning"></i> ${i18n['home.modal_quantity_note']}</small>
        <small class="text-muted d-block mt-1">${i18n['home.modal_quantity_note2']}</small>
        <small class="text-muted d-block mt-1">${i18n['home.modal_quantity_note3']}</small>
    `;

    // Display full ingredient list (copy/paste friendly)
    const ingredientListEl = document.getElementById('ingredientList');
    const ingredientHeaderEl = document.getElementById('ingredientListHeader');
    if (ingredients && ingredients.length > 0) {
        // Process ingredients - merge "eller/och", round decimals, decode entities
        const formattedIngredients = processIngredients(ingredients);
        ingredientListEl.textContent = formattedIngredients.join('\n');
        ingredientListEl.parentElement.parentElement.style.display = '';
        // Update header with servings if available
        if (ingredientHeaderEl) {
            ingredientHeaderEl.innerHTML = servings > 0
                ? `<i class="bi bi-list-check"></i> ${t('home.modal_full_recipe_servings', {n: servings})}`
                : `<i class="bi bi-list-check"></i> ${i18n['home.modal_full_recipe']}`;
        }
    } else {
        ingredientListEl.parentElement.parentElement.style.display = 'none';
    }

    const modal = new bootstrap.Modal(document.getElementById('matchedOffersModal'));
    modal.show();

    // Setup copy button for ingredient list
    const copyBtn = document.getElementById('copyIngredientsBtn');
    if (copyBtn && ingredientListEl) {
        copyBtn.onclick = async function() {
            try {
                await navigator.clipboard.writeText(ingredientListEl.textContent);
                // Show feedback - change icon temporarily
                const icon = copyBtn.querySelector('i');
                icon.className = 'bi bi-clipboard-check';
                setTimeout(() => {
                    icon.className = 'bi bi-clipboard';
                }, 1500);
            } catch (err) {
                console.error('Failed to copy:', err);
            }
        };
    }
}

// ============================================
// Background Scraper Notification (SSE)
// ============================================
// Listen for server-sent events when a background scrape completes.
// Replaces 30s polling — the server pushes events instantly.

let cacheEventSource = null;

async function handleCacheEvent(event) {
    const data = JSON.parse(event.data);

    // Silent invalidation (e.g. new recipes scraped) — just clear client cache
    if (data.type === 'cache_invalidated') {
        dbg.log('[SSE] Cache invalidated (silent) — will refresh on next load');
        sessionStorage.removeItem('recipeSuggestions');
        sessionStorage.removeItem('recipeBalance');
        sessionStorage.removeItem('cacheGeneration');
        return;
    }

    if (data.type !== 'cache_rebuilt') return;

    dbg.log(`[SSE] Cache rebuilt: ${data.source}`);

    // Close recipe modal if open (offers are no longer valid)
    const openModal = bootstrap.Modal.getInstance(document.getElementById('matchedOffersModal'));
    if (openModal) openModal.hide();

    // Show notification
    const storeName = data.source || i18n['home.store'];
    await Swal.fire({
        icon: 'info',
        title: i18n['home.new_offers_available'],
        html: `${escapeHtml(i18n['home.background_scraper_complete'])}<br><strong>${escapeHtml(storeName)}</strong>`,
        timer: 5000,
        timerProgressBar: true,
        showConfirmButton: true,
        confirmButtonText: 'OK'
    });

    // Clear active scrapes from localStorage so the stores page
    // won't show a duplicate "scrape complete" popup
    localStorage.removeItem('deal_meals_active_scrapes');

    // Remove cache error banner if present (cache just recovered)
    document.querySelectorAll('.alert-warning').forEach(el => {
        if (el.textContent.includes(i18n['home.cache_error_title'])) el.remove();
    });

    // Soft refresh: update data without losing user state
    sessionStorage.removeItem('recipeSuggestions');
    sessionStorage.removeItem('recipeBalance');
    sessionStorage.removeItem('cacheGeneration');

    // Refresh status cards
    loadOfferStatus();
    loadRecipeStatus();

    // If suggestions section is open, reload recipes
    const sugSection = document.getElementById('recipe-suggestions-section');
    if (sugSection && sugSection.classList.contains('show')) {
        suggestionsLoaded = false;
        allSuggestions = [];
        renderedRecipeIds.clear();
        loadRecipeSuggestions();
    }
}

function connectCacheEvents() {
    if (cacheEventSource) return;
    cacheEventSource = new EventSource('/api/events/cache');
    cacheEventSource.onmessage = handleCacheEvent;
    cacheEventSource.onerror = () => {
        // EventSource auto-reconnects; close explicitly only if page is hidden
        dbg.warn('[SSE] Connection error (will auto-reconnect)');
    };
}

function disconnectCacheEvents() {
    if (cacheEventSource) {
        cacheEventSource.close();
        cacheEventSource = null;
    }
}

// Only connect when suggestions section is active (not needed for search/pantry)
// Connection is managed by toggleSuggestions/closeAllSections/visibilitychange.

function isSuggestionsOpen() {
    const s = document.getElementById('recipe-suggestions-section');
    return s && s.classList.contains('show');
}

// Disconnect when page is hidden, reconnect when visible IF suggestions are open
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
        disconnectCacheEvents();
    } else if (isSuggestionsOpen()) {
        connectCacheEvents();
    }
});

// ============================================
// Event delegation
// ============================================
document.addEventListener('click', function(e) {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    switch (el.dataset.action) {
        case 'toggleSuggestions': toggleSuggestions(); break;
        case 'toggleSearch': toggleSearch(); break;
        case 'togglePantry': togglePantry(); break;
        case 'refreshRecipeSuggestions': refreshRecipeSuggestions(); break;
        case 'loadMoreSuggestions': loadMoreSuggestions(); break;
        case 'searchRecipes': searchRecipes(); break;
        case 'toggleHiddenRecipes': toggleHiddenRecipes(); break;
        case 'loadMoreSearchResults': loadMoreSearchResults(); break;
        case 'searchPantryRecipes': searchPantryRecipes(); break;
        case 'loadMorePantryRecipes': loadMorePantryRecipes(); break;
        case 'excludeCurrentRecipe': excludeCurrentRecipe(); break;
        case 'restoreRecipe': restoreRecipe(el.dataset.arg); break;
    }
});

document.addEventListener('keydown', function(e) {
    const el = e.target.closest('[data-enter-action]');
    if (el && e.key === 'Enter') {
        switch (el.dataset.enterAction) {
            case 'searchRecipes': searchRecipes(); break;
            case 'searchPantryRecipes': searchPantryRecipes(); break;
        }
    }
});

// Global image error handler (replaces inline onerror)
document.addEventListener('error', function(e) {
    if (e.target.tagName === 'IMG') {
        const parent = e.target.parentElement;
        if (parent && parent.classList.contains('recipe-card-image')) {
            parent.innerHTML = '<div class="recipe-card-placeholder"><i class="bi bi-image"></i></div>';
        }
    }
}, true);
