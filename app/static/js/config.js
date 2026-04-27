// Config page behavior. Jinja-provided i18n and page data are bootstrapped in config.html.
const i18n = window.DealMealsConfigI18n || {};
const pageConfig = window.DealMealsConfigPage || {};

const translateMessage = window.DealMeals.createTranslator(i18n);

// Resolve API response message (message_key with params, or fallback)
const resolveMsg = data => window.DealMeals.resolveMessage(data, { messages: i18n });

// Auto-resize textarea to fit content
function autoResizeTextarea(el) {
    el.style.height = 'auto';
    el.style.height = el.scrollHeight + 'px';
}

// Initialize all auto-resize textareas
function initAutoResizeTextareas() {
    document.querySelectorAll('.auto-resize').forEach(el => {
        autoResizeTextarea(el);
    });
}

// Debounce timer for slider changes
let matchingSaveTimeout = null;

// Load settings when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Theme radio buttons are server-rendered with correct checked state

    // Load delivery address
    loadDeliveryAddress();

    // Load matching preferences (will trigger auto-resize after loading)
    loadMatchingPreferences();

    // Load image preferences and status
    loadImagePreferences();
    loadImageStatus();

    // Load SSL status
    loadSSLStatus();

    // Load cache settings (from same endpoint as matching preferences)
    loadCacheSettings();

    // Load spell check badge count
    loadSpellCheckBadge();
});

// Load delivery address
async function loadDeliveryAddress() {
    try {
        const response = await fetch('/api/preferences/delivery-address');
        if (!response.ok) return;
        const data = await response.json();

        if (data.success) {
            document.getElementById('delivery-street-input').value = data.street_address || '';
            document.getElementById('delivery-postal-input').value = data.postal_code || '';
            document.getElementById('delivery-city-input').value = data.city || '';
        }
    } catch (error) {
        console.error('Error loading delivery address:', error);
    }
}

// Address autocomplete variables
let addressSearchTimeout = null;
const APP_LANGUAGE = pageConfig.appLanguage || 'sv';

// Locale → Country code mapping for address search.
// In this app the selected language also implies the market/country profile.
const LOCALE_COUNTRY_MAP = {
    'sv': 'se',
    'en_gb': 'gb',
};

function normalizePostalCode(postalCode) {
    const value = (postalCode || '').trim();
    if (APP_LANGUAGE === 'en_gb') {
        const compact = value.toUpperCase().replace(/\s+/g, '');
        return compact.replace(/^(.+)(\d[A-Z]{2})$/, '$1 $2').trim();
    }
    return value.replace(/\s/g, '');
}

function isValidPostalCode(postalCode) {
    if (APP_LANGUAGE === 'en_gb') {
        const normalized = normalizePostalCode(postalCode);
        return /^(GIR 0AA|[A-Z]{1,2}\d[A-Z\d]?\s\d[A-Z]{2})$/.test(normalized);
    }
    return postalCode.length === 5 && /^\d+$/.test(postalCode);
}

function formatStreetAddress(addr) {
    const road = addr.road || addr.street || addr.pedestrian || '';
    const houseNumber = addr.house_number || '';

    if (APP_LANGUAGE === 'en_gb') {
        return [houseNumber, road].filter(Boolean).join(' ');
    }
    return [road, houseNumber].filter(Boolean).join(' ');
}

function extractPostTown(addr) {
    return addr.city || addr.town || addr.village || addr.municipality || addr.county || '';
}

// Search address using OpenStreetMap Nominatim
async function searchAddress() {
    const query = document.getElementById('delivery-search-input').value.trim();
    const suggestionsDiv = document.getElementById('address-suggestions');

    if (query.length < 3) {
        suggestionsDiv.style.display = 'none';
        return;
    }

    // Debounce - wait 500ms after last keystroke
    clearTimeout(addressSearchTimeout);
    addressSearchTimeout = setTimeout(async () => {
        try {
            // OpenStreetMap Nominatim API (free, only requires User-Agent)
            const countryCode = LOCALE_COUNTRY_MAP[APP_LANGUAGE] || 'se';

            const url = `https://nominatim.openstreetmap.org/search?` +
                `q=${encodeURIComponent(query)}&` +
                `format=json&` +
                `countrycodes=${countryCode}&` +
                `addressdetails=1&` +
                `limit=10`;

            const response = await fetch(url, {
                headers: {
                    'User-Agent': 'DealMeals/1.0'
                }
            });

            if (!response.ok) {
                throw new Error(i18n.delivery_search_error);
            }

            const results = await response.json();

            if (results && results.length > 0) {
                // Show suggestions
                suggestionsDiv.innerHTML = results.map(result => {
                    const addr = result.address || {};
                    const postcode = normalizePostalCode(addr.postcode || '');
                    const city = extractPostTown(addr);
                    const fullAddress = formatStreetAddress(addr);

                    return `
                        <button type="button"
                                class="list-group-item list-group-item-action"
                                data-action="selectAddress" data-street="${escapeAttr(fullAddress)}" data-postal="${escapeAttr(postcode)}" data-city="${escapeAttr(city)}" >
                            <strong>${escapeHtml(fullAddress)}</strong><br>
                            <small class="text-muted">${escapeHtml(postcode)} ${escapeHtml(city)}</small>
                        </button>
                    `;
                }).join('');
                suggestionsDiv.style.display = 'block';
            } else {
                suggestionsDiv.innerHTML = `<div class="list-group-item">${i18n.delivery_no_results}</div>`;
                suggestionsDiv.style.display = 'block';
            }
        } catch (error) {
            console.error('Address search error:', error);
            suggestionsDiv.innerHTML = `<div class="list-group-item text-danger">${i18n.delivery_search_error}</div>`;
            suggestionsDiv.style.display = 'block';
        }
    }, 500);
}

// Select address from suggestions
function selectAddress(street, postcode, city) {
    document.getElementById('delivery-street-input').value = street;
    document.getElementById('delivery-postal-input').value = normalizePostalCode(postcode);
    document.getElementById('delivery-city-input').value = city;
    document.getElementById('delivery-search-input').value = '';
    document.getElementById('address-suggestions').style.display = 'none';
}

// Clear address search
function clearAddressSearch() {
    document.getElementById('delivery-search-input').value = '';
    document.getElementById('address-suggestions').style.display = 'none';
}

// Save delivery address with debounce
let addressSaveTimeout = null;

function debouncedSaveAddress() {
    if (addressSaveTimeout) clearTimeout(addressSaveTimeout);
    addressSaveTimeout = setTimeout(saveDeliveryAddress, 800);
}

async function saveDeliveryAddress() {
    const street = document.getElementById('delivery-street-input').value.trim();
    const postal = normalizePostalCode(document.getElementById('delivery-postal-input').value);
    const city = document.getElementById('delivery-city-input').value.trim();
    const messageDiv = document.getElementById('delivery-address-message');

    // Silent validation - only save if all fields are valid
    if (!street || !postal || !city) {
        return; // Don't save incomplete address, but don't show error either
    }

    if (!isValidPostalCode(postal)) {
        return; // Invalid postal code, wait for correction
    }

    document.getElementById('delivery-postal-input').value = postal;

    try {
        const response = await fetch('/api/preferences/delivery-address', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                street_address: street,
                postal_code: postal,
                city: city
            })
        });
        if (!response.ok) throw new Error(i18n.error);

        const data = await response.json();

        if (!data.success) {
            throw new Error(resolveMsg(data) || i18n.error);
        }
        // Success - silently saved, no popup needed
        messageDiv.style.display = 'none';
    } catch (error) {
        messageDiv.className = 'alert alert-danger py-2 small';
        messageDiv.innerHTML = '❌ ' + escapeHtml(error.message);
        messageDiv.style.display = 'block';
    }
}

// ============================================
// Matching Preferences Functions
// ============================================

// Load matching preferences from server
async function loadMatchingPreferences() {
    try {
        const response = await fetch('/api/matching/preferences');
        if (!response.ok) return;
        const data = await response.json();

        if (data.success) {
            const prefs = data.preferences;

            // Set checkboxes
            document.getElementById('exclude-meat').checked = prefs.exclude_meat;
            document.getElementById('exclude-fish').checked = prefs.exclude_fish;
            document.getElementById('exclude-dairy').checked = prefs.exclude_dairy;
            document.getElementById('local-meat-only').checked = prefs.local_meat_only;

            // Set exclude keywords
            const keywords = prefs.exclude_keywords || [];
            document.getElementById('exclude-keywords').value = keywords.join(', ');

            // Set filtered products
            const filteredProducts = prefs.filtered_products || [];
            document.getElementById('filtered-products').value = filteredProducts.join(', ');

            // Set excluded brands
            const excludedBrands = prefs.excluded_brands || [];
            document.getElementById('excluded-brands').value = excludedBrands.join(', ');

            // Auto-resize textareas after loading content
            initAutoResizeTextareas();

            // Balance is now stored as raw counts (0-4)
            // Backward compatibility: if total <= 4, it's new format (counts)
            // If total is ~1.0, it's old format (normalized ratios)
            const total = prefs.balance_meat + prefs.balance_fish + prefs.balance_veg + prefs.balance_budget;

            let meatCount, fishCount, vegCount, budgetCount;
            if (total <= 0) {
                // No data - use defaults
                meatCount = fishCount = vegCount = budgetCount = 3;
            } else if (total <= 4) {
                // Old format (normalized ratios sum to ~1.0)
                // Convert to counts by multiplying by 12 and distributing
                meatCount = Math.round(prefs.balance_meat * 4);
                fishCount = Math.round(prefs.balance_fish * 4);
                vegCount = Math.round(prefs.balance_veg * 4);
                budgetCount = Math.round(prefs.balance_budget * 4);
                // Ensure at least something if non-zero
                if (meatCount === 0 && prefs.balance_meat > 0) meatCount = 1;
                if (fishCount === 0 && prefs.balance_fish > 0) fishCount = 1;
                if (vegCount === 0 && prefs.balance_veg > 0) vegCount = 1;
                if (budgetCount === 0 && prefs.balance_budget > 0) budgetCount = 1;
            } else {
                // New format - raw counts (0-4), clamped to valid range
                meatCount = Math.min(4, Math.max(0, Math.round(prefs.balance_meat)));
                fishCount = Math.min(4, Math.max(0, Math.round(prefs.balance_fish)));
                vegCount = Math.min(4, Math.max(0, Math.round(prefs.balance_veg)));
                budgetCount = Math.min(4, Math.max(0, Math.round(prefs.balance_budget)));
            }

            // Apply the counts (this also updates button states)
            // Skip save during load to avoid circular updates
            isLoadingPreferences = true;
            setBalance('meat', meatCount, true);
            setBalance('fish', fishCount, true);
            setBalance('veg', vegCount, true);
            setBalance('budget', budgetCount, true);
            isLoadingPreferences = false;

            updateBalancePreview();

            // Ranking mode
            const rankingMode = prefs.ranking_mode || 'absolute';
            const radio = document.getElementById(rankingMode === 'percentage' ? 'ranking-percentage' : 'ranking-absolute');
            if (radio) radio.checked = true;

            // Ingredient count filter
            loadIngredientFilter(prefs.min_ingredients || 0, prefs.max_ingredients || 0);
        }
    } catch (error) {
        console.error('Error loading matching preferences:', error);
    }
}

// ==================== Cache Settings ====================

async function loadCacheSettings() {
    try {
        const response = await fetch('/api/matching/preferences');
        if (!response.ok) return;
        const data = await response.json();
        if (data.success) {
            const prefs = data.preferences;
            const useMemory = prefs.cache_use_memory || false;
            const maxMemory = prefs.cache_max_memory_mb || 150;

            document.getElementById('cache-use-memory').checked = useMemory;
            document.getElementById('cache-max-memory').value = maxMemory;
            updateMemoryLabel(maxMemory);
            toggleMemorySettings(useMemory);
            updateCacheModeStatus(useMemory);
        }
    } catch (error) {
        console.error('Error loading cache settings:', error);
    }
}

function updateMemoryLabel(value) {
    document.getElementById('cache-memory-label').textContent = value + ' MB';
}

function toggleMemorySettings(enabled) {
    document.getElementById('cache-memory-settings').style.display = enabled ? 'block' : 'none';
}

function updateCacheModeStatus(useMemory) {
    const icon = document.getElementById('cache-mode-status').querySelector('i');
    const text = document.getElementById('cache-mode-text');
    if (useMemory) {
        icon.className = 'bi bi-memory';
        text.textContent = i18n.cache_mode_memory;
    } else {
        icon.className = 'bi bi-database';
        text.textContent = i18n.cache_mode_db;
    }
}

async function saveCacheSettings() {
    const useMemory = document.getElementById('cache-use-memory').checked;
    const maxMemory = parseInt(document.getElementById('cache-max-memory').value);

    toggleMemorySettings(useMemory);
    updateCacheModeStatus(useMemory);

    // Load current preferences and merge cache settings
    try {
        const getResp = await fetch('/api/matching/preferences');
        if (!getResp.ok) return;
        const getData = await getResp.json();
        if (!getData.success) return;

        const prefs = getData.preferences;
        prefs.cache_use_memory = useMemory;
        prefs.cache_max_memory_mb = maxMemory;

        const response = await fetch('/api/matching/preferences', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(prefs)
        });
        if (!response.ok) {
            Swal.fire({ icon: 'error', title: i18n.error });
            return;
        }

        const data = await response.json();
    } catch (error) {
        console.error('Error saving cache settings:', error);
    }
}

// Flag to prevent saving during load
let isLoadingPreferences = false;

// Set balance count for a category
function setBalance(category, value, skipSave = false) {
    // Update hidden input
    document.getElementById(`balance-${category}`).value = value;

    // Update button active state
    const group = document.getElementById(`balance-${category}-group`);
    group.querySelectorAll('.btn').forEach(btn => {
        btn.classList.remove('active');
        if (parseInt(btn.dataset.value) === value) {
            btn.classList.add('active');
        }
    });

    // Update preview
    updateBalancePreview();

    // Save (debounced) unless loading or explicitly skipped
    if (!isLoadingPreferences && !skipSave) {
        saveMatchingPreferencesDebounced();
    }
}

// Update balance preview with boxes using largest remainder method
function updateBalancePreview() {
    const meat = parseInt(document.getElementById('balance-meat').value);
    const fish = parseInt(document.getElementById('balance-fish').value);
    const veg = parseInt(document.getElementById('balance-veg').value);
    const budget = parseInt(document.getElementById('balance-budget').value);

    const total = meat + fish + veg + budget;
    if (total === 0) {
        document.getElementById('balance-preview').innerHTML =
            `<span class="text-muted">${i18n.balance_set_one}</span>`;
        return;
    }

    // Distribute 12 boxes using largest remainder method (fair distribution)
    const totalBoxes = 12;
    const counts = [
        { key: 'meat', weight: meat, name: i18n.category_meat, color: 'danger', icon: 'bi-egg-fried' },
        { key: 'fish', weight: fish, name: i18n.category_fish, color: 'primary', icon: 'bi-water' },
        { key: 'veg', weight: veg, name: i18n.category_vegetarian, color: 'success', icon: 'bi-tree' },
        { key: 'budget', weight: budget, name: i18n.category_budget, color: 'warning', icon: 'bi-piggy-bank' }
    ];

    // Calculate exact proportions and floor values
    let allocated = 0;
    counts.forEach(c => {
        c.exact = (c.weight / total) * totalBoxes;
        c.boxes = Math.floor(c.exact);
        c.remainder = c.exact - c.boxes;
        allocated += c.boxes;
    });

    // Distribute remaining boxes to categories with largest remainders
    // Tie-break: prefer category with higher original weight
    let remaining = totalBoxes - allocated;
    const sortedByRemainder = [...counts].sort((a, b) => b.remainder - a.remainder || b.weight - a.weight);
    for (let i = 0; i < remaining; i++) {
        sortedByRemainder[i].boxes++;
    }

    // Fairness fix: equal-weight categories should get equal counts.
    // If 3+ categories share the same weight but got unequal counts,
    // move the excess to the highest-weight category instead.
    const byWeight = {};
    counts.forEach(c => {
        if (c.weight > 0) {
            if (!byWeight[c.weight]) byWeight[c.weight] = [];
            byWeight[c.weight].push(c);
        }
    });
    for (const group of Object.values(byWeight)) {
        if (group.length < 3) continue;
        const minBoxes = Math.min(...group.map(c => c.boxes));
        let excess = 0;
        group.forEach(c => { excess += c.boxes - minBoxes; c.boxes = minBoxes; });
        if (excess > 0) {
            // Give excess to highest-weight category
            const highest = counts.reduce((a, b) => (a.weight > b.weight ? a : b));
            highest.boxes += excess;
        }
    }

    let html = '';
    counts.forEach(cat => {
        for (let i = 0; i < cat.boxes; i++) {
            html += `<span class="badge bg-${cat.color} py-2 px-2" title="${cat.name}">
                <i class="bi ${cat.icon}"></i>
            </span>`;
        }
    });

    document.getElementById('balance-preview').innerHTML = html;
}

// Save with debounce for button changes
function saveMatchingPreferencesDebounced() {
    clearTimeout(matchingSaveTimeout);
    matchingSaveTimeout = setTimeout(() => saveMatchingPreferences(true), 500);
}

// Reset all balance to count 3 (default)
function resetBalance() {
    setBalance('meat', 3);
    setBalance('fish', 3);
    setBalance('veg', 3);
    setBalance('budget', 3);
    saveMatchingPreferences(true);
}

// ============================================
// Ingredient Count Filter
// ============================================

function getIngredientValue(type) {
    const slider = document.getElementById(type + '-ingredients-slider');
    if (type === 'min') {
        const val = parseInt(slider.value);
        return val <= 1 ? 0 : val;
    }
    const cb = document.getElementById('max-ingredients-nolimit');
    if (cb.checked) return 0;
    return parseInt(slider.value);
}

function updateIngredientLabel() {
    const minSlider = document.getElementById('min-ingredients-slider');
    const maxSlider = document.getElementById('max-ingredients-slider');
    const minLabel = document.getElementById('min-ingredients-label');
    const maxLabel = document.getElementById('max-ingredients-label');
    const maxCb = document.getElementById('max-ingredients-nolimit');

    minLabel.textContent = minSlider.value;

    if (maxCb.checked) {
        maxLabel.textContent = '-';
        maxSlider.disabled = true;
    } else {
        maxLabel.textContent = maxSlider.value;
        maxSlider.disabled = false;
    }
}

function loadIngredientFilter(minVal, maxVal) {
    const minSlider = document.getElementById('min-ingredients-slider');
    const maxSlider = document.getElementById('max-ingredients-slider');
    const maxCb = document.getElementById('max-ingredients-nolimit');

    minSlider.value = minVal > 0 ? minVal : 1;

    if (maxVal === 0) {
        maxCb.checked = true;
        maxSlider.value = 30;
    } else {
        maxCb.checked = false;
        maxSlider.value = maxVal;
    }

    updateIngredientLabel();
}

// Save matching preferences to server
async function saveMatchingPreferences(silent = false) {
    // Parse exclude keywords
    const keywordsText = document.getElementById('exclude-keywords').value;
    const keywords = keywordsText
        .split(',')
        .map(k => k.trim().toLowerCase())
        .filter(k => k.length > 0);

    // Parse filtered products
    const filteredProductsText = document.getElementById('filtered-products').value;
    const filteredProducts = filteredProductsText
        .split(',')
        .map(k => k.trim().toLowerCase())
        .filter(k => k.length > 0);

    // Parse excluded brands (keep original case, backend normalizes for comparison)
    const excludedBrandsText = document.getElementById('excluded-brands').value;
    const excludedBrands = excludedBrandsText
        .split(',')
        .map(k => k.trim())
        .filter(k => k.length > 0);

    // Get counts (0-4) - store raw counts, backend normalizes internally
    const meatCount = parseInt(document.getElementById('balance-meat').value);
    const fishCount = parseInt(document.getElementById('balance-fish').value);
    const vegCount = parseInt(document.getElementById('balance-veg').value);
    const budgetCount = parseInt(document.getElementById('balance-budget').value);

    const prefs = {
        exclude_meat: document.getElementById('exclude-meat').checked,
        exclude_fish: document.getElementById('exclude-fish').checked,
        exclude_dairy: document.getElementById('exclude-dairy').checked,
        local_meat_only: document.getElementById('local-meat-only').checked,
        exclude_keywords: keywords,
        filtered_products: filteredProducts,
        excluded_brands: excludedBrands,
        balance_meat: meatCount,
        balance_fish: fishCount,
        balance_veg: vegCount,
        balance_budget: budgetCount,
        ranking_mode: document.querySelector('input[name="ranking-mode"]:checked')?.value || 'absolute',
        min_ingredients: getIngredientValue('min'),
        max_ingredients: getIngredientValue('max')
    };

    try {
        const response = await fetch('/api/matching/preferences', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(prefs)
        });
        if (!response.ok) throw new Error(i18n.error);

        const data = await response.json();
        const messageDiv = document.getElementById('matching-message');

        if (data.success) {
            // Clear home page recipe cache so it reloads with new settings
            sessionStorage.removeItem('recipeSuggestions');
            sessionStorage.removeItem('recipeBalance');
            sessionStorage.removeItem('cacheGeneration');
        } else {
            messageDiv.className = 'alert alert-danger py-2';
            messageDiv.innerHTML = '❌ ' + i18n.settings_save_error + ' ' + escapeHtml(resolveMsg(data));
            messageDiv.style.display = 'block';
        }
    } catch (error) {
        console.error('Error saving matching preferences:', error);
        const messageDiv = document.getElementById('matching-message');
        messageDiv.className = 'alert alert-danger py-2';
        messageDiv.innerHTML = '❌ ' + i18n.error + ': ' + escapeHtml(error.message);
        messageDiv.style.display = 'block';
    }
}

// ============================================
// Recipe Images Functions
// ============================================

// Load image preferences from server
async function loadImagePreferences() {
    try {
        const response = await fetch('/api/images/preferences');
        if (!response.ok) return;
        const data = await response.json();

        if (data.success) {
            document.getElementById('images-save-local').checked = data.save_local || false;
            document.getElementById('images-auto-download').checked = data.auto_download || false;
        }
    } catch (error) {
        console.error('Error loading image preferences:', error);
    }
}

// Load image status (count and disk usage)
async function loadImageStatus() {
    try {
        const response = await fetch('/api/images/status');
        if (!response.ok) return;
        const data = await response.json();

        const statusEl = document.getElementById('images-status');
        if (data.success) {
            if (data.downloaded > 0) {
                statusEl.textContent = i18n.images_status
                    .replace('{downloaded}', data.downloaded)
                    .replace('{total}', data.total)
                    .replace('{size}', data.size);
            } else {
                statusEl.textContent = i18n.images_status_none;
            }

            // Update download status indicator (three states)
            const failedIcon = document.getElementById('images-failed-icon');
            const failedText = document.getElementById('images-failed-text');

            if (data.permanently_failed > 0) {
                // Red state - permanent failures (5 attempts, won't retry)
                failedIcon.className = 'bi bi-x-circle text-danger';
                failedText.textContent = i18n.images_failed_permanent.replace('{count}', data.permanently_failed);
            } else if (data.retrying_count > 0) {
                // Yellow state - retrying (1-4 attempts, will retry)
                failedIcon.className = 'bi bi-exclamation-triangle text-warning';
                failedText.textContent = i18n.images_failed_retrying.replace('{count}', data.retrying_count);
            } else {
                // Green state - no failures
                failedIcon.className = 'bi bi-check-circle text-success';
                failedText.textContent = i18n.images_failed_ok;
            }
        }

        // Check if a download is currently running and restore progress UI
        await checkAndRestoreDownloadProgress();

    } catch (error) {
        console.error('Error loading image status:', error);
    }
}

// Check if download is running and restore progress UI if needed
async function checkAndRestoreDownloadProgress() {
    // Don't check if we're already polling
    if (downloadPollingInterval) return;

    try {
        const response = await fetch('/api/images/download/status');
        if (!response.ok) return;
        const data = await response.json();

        if (data.status === 'running') {
            // Download is running - restore progress UI
            const btn = document.getElementById('btn-download-images');
            const messageDiv = document.getElementById('images-message');

            btn.disabled = true;
            messageDiv.className = 'alert alert-info py-2 small';
            const progressMsg = translateMessage(data.message_key, data.message_params) || i18n.images_downloading;
            messageDiv.innerHTML = `
                <div class="d-flex align-items-center justify-content-between">
                    <div>
                        <span class="spinner-border spinner-border-sm me-2"></span>
                        <span id="download-progress-text">${escapeHtml(progressMsg)}</span>
                    </div>
                    <button class="btn btn-outline-danger btn-sm py-0 px-2" data-action="cancelImageDownload">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
                <div class="progress mt-2" style="height: 6px;">
                    <div class="progress-bar progress-bar-striped progress-bar-animated" id="download-progress-bar" role="progressbar" aria-valuenow="${data.total > 0 ? Math.round((data.processed / data.total) * 100) : 0}" aria-valuemin="0" aria-valuemax="100" style="width: ${data.total > 0 ? Math.round((data.processed / data.total) * 100) : 0}%"></div>
                </div>
            `;
            messageDiv.style.display = 'block';

            // Start polling for progress
            downloadPollingInterval = setInterval(pollDownloadProgress, 1000);
        }
    } catch (error) {
        console.error('Error checking download status:', error);
    }
}

// Save image preferences
async function saveImagePreferences() {
    const prefs = {
        save_local: document.getElementById('images-save-local').checked,
        auto_download: document.getElementById('images-auto-download').checked
    };

    try {
        const response = await fetch('/api/images/preferences', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(prefs)
        });
        if (!response.ok) throw new Error(i18n.error);

        const data = await response.json();
        const messageDiv = document.getElementById('images-message');

        if (!data.success) {
            throw new Error(resolveMsg(data) || i18n.error);
        }
        // Success - no message needed, auto-save is expected
    } catch (error) {
        const messageDiv = document.getElementById('images-message');
        messageDiv.className = 'alert alert-danger py-2 small';
        messageDiv.innerHTML = '❌ ' + escapeHtml(error.message);
        messageDiv.style.display = 'block';
    }
}

// Download missing images (async with progress)
let downloadPollingInterval = null;

async function downloadMissingImages() {
    const btn = document.getElementById('btn-download-images');
    const messageDiv = document.getElementById('images-message');

    // Start the download
    try {
        const response = await fetch('/api/images/download', { method: 'POST' });
        if (!response.ok) throw new Error(i18n.error);
        const data = await response.json();

        if (!data.success) {
            throw new Error(resolveMsg(data) || i18n.error);
        }

        // Show progress UI
        btn.disabled = true;
        messageDiv.className = 'alert alert-info py-2 small';
        messageDiv.innerHTML = `
            <div class="d-flex align-items-center justify-content-between">
                <div>
                    <span class="spinner-border spinner-border-sm me-2"></span>
                    <span id="download-progress-text">${i18n.images_downloading}</span>
                </div>
                <button class="btn btn-outline-danger btn-sm py-0 px-2" data-action="cancelImageDownload">
                    <i class="bi bi-x"></i>
                </button>
            </div>
            <div class="progress mt-2" style="height: 6px;">
                <div class="progress-bar progress-bar-striped progress-bar-animated" id="download-progress-bar" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" style="width: 0%"></div>
            </div>
        `;
        messageDiv.style.display = 'block';

        // Start polling for progress
        downloadPollingInterval = setInterval(pollDownloadProgress, 1000);

    } catch (error) {
        messageDiv.className = 'alert alert-danger py-2 small';
        messageDiv.innerHTML = '❌ ' + i18n.images_download_error + ': ' + escapeHtml(error.message);
        messageDiv.style.display = 'block';
    }
}

async function pollDownloadProgress() {
    const btn = document.getElementById('btn-download-images');
    const messageDiv = document.getElementById('images-message');

    try {
        const response = await fetch('/api/images/download/status');
        if (!response.ok) return;
        const data = await response.json();

        if (!data.success) return;

        // Update progress bar and text
        const progressBar = document.getElementById('download-progress-bar');
        const progressText = document.getElementById('download-progress-text');

        if (progressBar) {
            progressBar.style.width = data.progress + '%';
            progressBar.setAttribute('aria-valuenow', Math.round(data.progress));
        }
        if (progressText) progressText.textContent = translateMessage(data.message_key, data.message_params);

        // Check if complete
        if (!data.running) {
            clearInterval(downloadPollingInterval);
            downloadPollingInterval = null;
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-cloud-download"></i> ' + escapeHtml(i18n.images_download_missing);

            const finalMsg = translateMessage(data.message_key, data.message_params);

            if (data.status === 'complete') {
                messageDiv.className = 'alert alert-success py-2 small';
                messageDiv.innerHTML = '✅ ' + escapeHtml(finalMsg);
                setTimeout(() => { messageDiv.style.display = 'none'; }, 5000);
            } else if (data.status === 'cancelled') {
                messageDiv.className = 'alert alert-warning py-2 small';
                messageDiv.innerHTML = '⚠️ ' + escapeHtml(finalMsg);
                setTimeout(() => { messageDiv.style.display = 'none'; }, 3000);
            } else if (data.status === 'error') {
                messageDiv.className = 'alert alert-danger py-2 small';
                const errorMsg = data.message_params?.error || finalMsg;
                messageDiv.innerHTML = '❌ ' + escapeHtml(errorMsg);
            }

            loadImageStatus();
        }
    } catch (error) {
        console.error('Error polling download status:', error);
    }
}

async function cancelImageDownload() {
    const messageDiv = document.getElementById('images-message');
    const btn = document.getElementById('btn-download-images');

    try {
        // Stop polling immediately
        if (downloadPollingInterval) {
            clearInterval(downloadPollingInterval);
            downloadPollingInterval = null;
        }

        // Update UI immediately
        messageDiv.className = 'alert alert-warning py-2 small';
        messageDiv.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>' + escapeHtml(i18n.images_cancelling);

        const response = await fetch('/api/images/download/cancel', { method: 'POST' });
        if (!response.ok) {
            messageDiv.className = 'alert alert-danger py-2 small';
            messageDiv.innerHTML = '❌ ' + i18n.error;
            messageDiv.style.display = 'block';
            return;
        }
        const data = await response.json();

        // Show final status
        messageDiv.innerHTML = '⚠️ ' + escapeHtml(i18n.images_cancelled);
        setTimeout(() => {
            messageDiv.style.display = 'none';
            btn.disabled = false;
            loadImageStatus();
        }, 2000);

    } catch (error) {
        console.error('Error cancelling download:', error);
        messageDiv.className = 'alert alert-danger py-2 small';
        messageDiv.innerHTML = '❌ ' + i18n.images_cancel_error + ': ' + escapeHtml(error.message);
        btn.disabled = false;
    }
}

// Confirm and clear all images
async function confirmClearImages() {
    // Get current count for the confirmation message
    let count = 0;
    try {
        const response = await fetch('/api/images/status');
        if (!response.ok) return;
        const data = await response.json();
        if (data.success) count = data.downloaded;
    } catch (e) { /* ignore */ }

    const confirmText = i18n.images_clear_confirm.replace('{count}', count);

    Swal.fire({
        title: i18n.images_clear_title,
        text: confirmText,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#dc3545',
        cancelButtonColor: '#6c757d',
        confirmButtonText: i18n.common_delete,
        cancelButtonText: i18n.common_cancel
    }).then(async (result) => {
        if (result.isConfirmed) {
            try {
                const response = await fetch('/api/images/clear', { method: 'POST' });
                if (!response.ok) {
                    Swal.fire({ icon: 'error', title: i18n.error });
                    return;
                }
                const data = await response.json();

                if (data.success) {
                    Swal.fire({
                        title: '✅',
                        text: i18n.images_cleared,
                        icon: 'success',
                        timer: 2000,
                        showConfirmButton: false
                    });
                    loadImageStatus();
                } else {
                    throw new Error(resolveMsg(data));
                }
            } catch (error) {
                Swal.fire({
                    title: i18n.error,
                    text: error.message,
                    icon: 'error'
                });
            }
        }
    });
}

// ============================================
// ============================================
// UNMATCHED OFFERS ANALYSIS
// ============================================

let unmatchedOffersModal = null;

function showUnmatchedOffers() {
    if (!unmatchedOffersModal) {
        unmatchedOffersModal = new bootstrap.Modal(document.getElementById('unmatchedOffersModal'));
    }

    // Show spinner while loading
    document.getElementById('unmatched-offers-body').innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-2">${i18n.loading}</p>
        </div>`;

    unmatchedOffersModal.show();

    fetch('/api/matching/unmatched-offers')
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                document.getElementById('unmatched-offers-body').innerHTML =
                    `<div class="alert alert-danger">${escapeHtml(resolveMsg(data) || i18n.error)}</div>`;
                return;
            }

            if (data.total === 0) {
                document.getElementById('unmatched-offers-body').innerHTML =
                    `<div class="alert alert-info">${i18n.unmatched_no_offers}</div>`;
                return;
            }

            const reasonLabels = {
                category_excluded: i18n.unmatched_reason_category_excluded,
                local_meat: i18n.unmatched_reason_local_meat,
                keyword_excluded: i18n.unmatched_reason_keyword_excluded,
                filtered_product: i18n.unmatched_reason_filtered_product,
                brand_excluded: i18n.unmatched_reason_brand_excluded,
                processed: i18n.unmatched_reason_processed,
                junk_food: i18n.unmatched_reason_junk_food,
                non_food: i18n.unmatched_reason_non_food,
                no_keywords: i18n.unmatched_reason_no_keywords,
                no_recipe_match: i18n.unmatched_reason_no_recipe_match
            };

            const reasonColors = {
                category_excluded: 'secondary',
                local_meat: 'info',
                keyword_excluded: 'warning text-dark',
                filtered_product: 'warning text-dark',
                brand_excluded: 'warning text-dark',
                processed: 'secondary',
                junk_food: 'secondary',
                non_food: 'dark',
                no_keywords: 'danger',
                no_recipe_match: 'primary'
            };

            // Stats summary
            let statsHtml = `<div class="mb-3 p-2 bg-body-tertiary rounded">
                <div class="row text-center small">
                    <div class="col"><strong>${i18n.unmatched_total.replace('{total}', data.total)}</strong></div>
                    <div class="col"><span class="badge bg-success">${i18n.unmatched_matched.replace('{count}', data.matched)}</span></div>
                    <div class="col"><span class="badge bg-secondary">${i18n.unmatched_filtered_count.replace('{count}', data.filtered.length)}</span></div>
                    <div class="col"><span class="badge bg-primary">${i18n.unmatched_unmatched_count.replace('{count}', data.unmatched.length)}</span></div>
                </div>`;

            // Stats per reason
            if (Object.keys(data.stats).length > 0) {
                statsHtml += `<div class="mt-2 d-flex flex-wrap gap-1 justify-content-center">`;
                for (const [reason, count] of Object.entries(data.stats)) {
                    const label = reasonLabels[reason] || reason;
                    const color = reasonColors[reason] || 'secondary';
                    statsHtml += `<span class="badge bg-${color}">${label}: ${count}</span>`;
                }
                statsHtml += `</div>`;
            }
            statsHtml += `</div>`;

            // Build table rows
            let rows = '';

            // Filtered offers
            for (const item of data.filtered) {
                const label = reasonLabels[item.reason] || item.reason;
                const color = reasonColors[item.reason] || 'secondary';
                rows += `<tr>
                    <td class="small">${escapeHtml(item.name)}</td>
                    <td class="small text-end">${item.price.toFixed(0)} kr</td>
                    <td><span class="badge bg-${color}">${label}</span></td>
                    <td class="small text-muted">${escapeHtml(item.detail)}</td>
                </tr>`;
            }

            // Unmatched offers (passed filters but no recipe)
            for (const item of data.unmatched) {
                const label = reasonLabels[item.reason] || item.reason;
                const color = reasonColors[item.reason] || 'primary';
                rows += `<tr>
                    <td class="small">${escapeHtml(item.name)}</td>
                    <td class="small text-end">${item.price.toFixed(0)} kr</td>
                    <td><span class="badge bg-${color}">${label}</span></td>
                    <td class="small text-muted">${escapeHtml(item.detail)}</td>
                </tr>`;
            }

            document.getElementById('unmatched-offers-body').innerHTML = `
                ${statsHtml}
                <table class="table table-sm table-hover mb-0">
                    <thead>
                        <tr>
                            <th>${i18n.unmatched_product}</th>
                            <th class="text-end">${i18n.unmatched_price}</th>
                            <th>${i18n.unmatched_reason}</th>
                            <th>${i18n.unmatched_detail}</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>`;
        })
        .catch(err => {
            document.getElementById('unmatched-offers-body').innerHTML =
                `<div class="alert alert-danger">${i18n.error}: ${escapeHtml(err.message)}</div>`;
        });
}

// FAILED IMAGES MANAGEMENT
// ============================================

let failedImagesLoaded = false;
let failedImagesModal = null;

function showFailedImagesModal() {
    // Initialize modal if not already done
    if (!failedImagesModal) {
        failedImagesModal = new bootstrap.Modal(document.getElementById('failedImagesModal'));
    }

    // Load data and show modal
    loadFailedImages();
    failedImagesModal.show();
}

async function loadFailedImages() {
    const tbody = document.getElementById('images-failed-list');
    tbody.innerHTML = `<tr><td colspan="5" class="text-center"><span class="spinner-border spinner-border-sm"></span> ${i18n.loading}</td></tr>`;

    try {
        const response = await fetch('/api/images/failures');
        if (!response.ok) return;
        const data = await response.json();

        if (!data.success) {
            throw new Error(resolveMsg(data) || 'Failed to load');
        }

        if (data.failures.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">${i18n.images_failed_none}</td></tr>`;
            return;
        }

        tbody.innerHTML = data.failures.map(f => {
            const recipeName = String(f.recipe_name || '');
            const recipeNameShort = recipeName.substring(0, 35) + (recipeName.length > 35 ? '...' : '');
            const lastError = String(f.last_error || '');
            const lastErrorShort = lastError ? lastError.substring(0, 25) + (lastError.length > 25 ? '...' : '') : '-';
            return `
                <tr>
                    <td title="${escapeAttr(recipeName)}">
                        ${f.permanently_failed ? '<i class="bi bi-x-circle text-danger me-1"></i>' : '<i class="bi bi-arrow-repeat text-muted me-1"></i>'}
                        ${escapeHtml(recipeNameShort)}
                    </td>
                    <td class="text-muted">${escapeHtml(f.recipe_source || '-')}</td>
                    <td class="text-muted small" title="${escapeAttr(lastError)}">${escapeHtml(lastErrorShort)}</td>
                    <td class="text-center">${escapeHtml(f.attempt_count)}/5</td>
                    <td class="text-end">
                        <button class="btn btn-outline-secondary btn-sm py-0 px-1" data-action="resetFailedRecipe" data-arg="${escapeAttr(f.recipe_id)}" title="${escapeAttr(i18n.images_failed_reset_title)}">
                            <i class="bi bi-arrow-clockwise"></i>
                        </button>
                        <button class="btn btn-outline-danger btn-sm py-0 px-1" data-action="deleteFailedRecipe" data-arg1="${escapeAttr(f.recipe_id)}" data-arg2="${escapeAttr(recipeName)}" title="${escapeAttr(i18n.images_failed_delete_title)}">
                            <i class="bi bi-trash"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        failedImagesLoaded = true;

    } catch (error) {
        console.error('Error loading failed images:', error);
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">${i18n.error}: ${escapeHtml(error.message)}</td></tr>`;
    }
}

async function deleteFailedRecipe(recipeId, recipeName) {
    const confirmMsg = i18n.images_failed_delete_confirm.replace('{name}', recipeName);
    const result = await Swal.fire({
        title: i18n.images_failed_delete_all_title,
        text: confirmMsg,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#dc3545',
        confirmButtonText: i18n.common_delete,
        cancelButtonText: i18n.common_cancel
    });
    if (!result.isConfirmed) return;

    try {
        const response = await fetch(`/api/images/failures/${recipeId}`, { method: 'DELETE' });
        if (!response.ok) {
            Swal.fire({ icon: 'error', title: i18n.error });
            return;
        }
        const data = await response.json();

        if (data.success) {
            failedImagesLoaded = false;
            loadFailedImages();
            loadImageStatus();
        } else {
            Swal.fire({ icon: 'error', title: i18n.error, text: resolveMsg(data) });
        }
    } catch (error) {
        Swal.fire({ icon: 'error', title: i18n.error, text: error.message });
    }
}

async function deleteAllFailedRecipes() {
    // Extract count from the text span
    const failedText = document.getElementById('images-failed-text').textContent;
    const countMatch = failedText.match(/\d+/);
    const count = countMatch ? countMatch[0] : '?';

    Swal.fire({
        title: i18n.images_failed_delete_all_title,
        text: i18n.images_failed_delete_all_text.replace('{count}', count),
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#dc3545',
        cancelButtonColor: '#6c757d',
        confirmButtonText: i18n.images_failed_delete_all,
        cancelButtonText: i18n.common_cancel
    }).then(async (result) => {
        if (result.isConfirmed) {
            try {
                const response = await fetch('/api/images/failures', { method: 'DELETE' });
                if (!response.ok) {
                    Swal.fire({ icon: 'error', title: i18n.error });
                    return;
                }
                const data = await response.json();

                if (data.success) {
                    Swal.fire({
                        title: '✅',
                        text: i18n.images_failed_deleted.replace('{count}', data.deleted),
                        icon: 'success',
                        timer: 2000,
                        showConfirmButton: false
                    });
                    failedImagesLoaded = false;
                    if (failedImagesModal) failedImagesModal.hide();
                    loadImageStatus();
                } else {
                    throw new Error(resolveMsg(data));
                }
            } catch (error) {
                Swal.fire({
                    title: i18n.error,
                    text: error.message,
                    icon: 'error'
                });
            }
        }
    });
}

async function resetFailedRecipe(recipeId) {
    try {
        const response = await fetch(`/api/images/failures/${recipeId}/reset`, { method: 'POST' });
        if (!response.ok) {
            Swal.fire({ icon: 'error', title: i18n.error });
            return;
        }
        const data = await response.json();

        if (data.success) {
            failedImagesLoaded = false;
            loadFailedImages();
            loadImageStatus();
        } else {
            Swal.fire({ icon: 'error', title: i18n.error, text: resolveMsg(data) });
        }
    } catch (error) {
        Swal.fire({ icon: 'error', title: i18n.error, text: error.message });
    }
}

// ============================================
// SSL/HTTPS Functions
// ============================================

async function loadSSLStatus() {
    try {
        const response = await fetch('/api/ssl/status');
        if (!response.ok) return;
        const data = await response.json();

        if (!data.success) {
            console.error('Failed to load SSL status');
            return;
        }

        const status = data.status;
        const statusIcon = document.getElementById('ssl-status-icon');
        const statusText = document.getElementById('ssl-status-text');
        const certInfo = document.getElementById('ssl-cert-info');
        const enableSwitch = document.getElementById('ssl-enabled');
        const deleteBtn = document.getElementById('ssl-delete-btn');

        // Update enable switch
        enableSwitch.checked = status.ssl_enabled;
        enableSwitch.disabled = !status.has_certificates;

        // Update delete button
        deleteBtn.disabled = !status.has_certificates;

        // Update status display
        if (status.force_http_override) {
            statusIcon.className = 'badge bg-warning';
            statusIcon.innerHTML = '<i class="bi bi-shield-exclamation"></i>';
            statusText.textContent = i18n.ssl_status_force_http;
        } else if (status.effective_ssl) {
            statusIcon.className = 'badge bg-success';
            statusIcon.innerHTML = '<i class="bi bi-shield-check"></i>';
            statusText.textContent = i18n.ssl_status_enabled;
        } else if (status.has_certificates && !status.ssl_enabled) {
            statusIcon.className = 'badge bg-secondary';
            statusIcon.innerHTML = '<i class="bi bi-shield-x"></i>';
            statusText.textContent = i18n.ssl_status_disabled;
        } else {
            statusIcon.className = 'badge bg-secondary';
            statusIcon.innerHTML = '<i class="bi bi-shield-x"></i>';
            statusText.textContent = i18n.ssl_status_no_cert;
        }

        // Show certificate info if available
        if (status.certificate && status.certificate.exists && status.certificate.details_available) {
            const cert = status.certificate;
            let certHtml = `<strong>${escapeHtml(cert.subject)}</strong><br>`;

            if (cert.is_expired) {
                certHtml += `<span class="text-danger"><i class="bi bi-exclamation-circle"></i> ${i18n.ssl_cert_expired}</span>`;
            } else {
                certHtml += escapeHtml(
                    i18n.ssl_cert_expires
                        .replace('{days}', cert.days_until_expiry)
                        .replace('{date}', cert.not_valid_after.split('T')[0])
                );
            }

            certInfo.innerHTML = certHtml;
            certInfo.style.display = 'block';
        } else {
            certInfo.style.display = 'none';
        }

    } catch (error) {
        console.error('Error loading SSL status:', error);
    }
}

async function toggleSSL() {
    const enableSwitch = document.getElementById('ssl-enabled');
    const enabled = enableSwitch.checked;
    const messageDiv = document.getElementById('ssl-message');

    try {
        const response = await fetch('/api/ssl/enable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enabled })
        });
        if (!response.ok) {
            messageDiv.className = 'alert alert-danger py-2 small';
            messageDiv.innerHTML = i18n.error;
            messageDiv.style.display = 'block';
            return;
        }

        const data = await response.json();

        if (data.success) {
            messageDiv.className = 'alert alert-success py-2 small';
            messageDiv.innerHTML = enabled ? i18n.ssl_enabled_msg : i18n.ssl_disabled_msg;
            messageDiv.style.display = 'block';
            setTimeout(() => { messageDiv.style.display = 'none'; }, 5000);
            loadSSLStatus();
        } else {
            throw new Error(resolveMsg(data));
        }
    } catch (error) {
        // Revert switch on error
        enableSwitch.checked = !enabled;
        messageDiv.className = 'alert alert-danger py-2 small';
        messageDiv.innerHTML = i18n.error + ': ' + escapeHtml(error.message);
        messageDiv.style.display = 'block';
    }
}

function updateSSLFileLabel(input) {
    const label = document.getElementById(`${input.id}-name`);
    if (!label) return;
    label.textContent = input.files && input.files.length
        ? input.files[0].name
        : i18n.ssl_no_file_chosen;
}

function resetSSLFilePickers() {
    ['ssl-cert-file', 'ssl-key-file'].forEach(id => {
        const input = document.getElementById(id);
        if (!input) return;
        input.value = '';
        updateSSLFileLabel(input);
    });
}

async function uploadSSLCertificates() {
    const certFile = document.getElementById('ssl-cert-file').files[0];
    const keyFile = document.getElementById('ssl-key-file').files[0];
    const messageDiv = document.getElementById('ssl-message');

    if (!certFile || !keyFile) {
        messageDiv.className = 'alert alert-warning py-2 small';
        messageDiv.innerHTML = escapeHtml(i18n.ssl_select_files);
        messageDiv.style.display = 'block';
        return;
    }

    try {
        // Read files as text
        const certData = await certFile.text();
        const keyData = await keyFile.text();

        const response = await fetch('/api/ssl/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                cert: certData,
                key: keyData
            })
        });
        if (!response.ok) {
            messageDiv.className = 'alert alert-danger py-2 small';
            messageDiv.innerHTML = i18n.error;
            messageDiv.style.display = 'block';
            return;
        }

        const data = await response.json();

        if (data.success) {
            // Clear file inputs
            resetSSLFilePickers();

            // Auto-enable HTTPS now that we have certificates
            await fetch('/api/ssl/enable', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: true })
            });

            Swal.fire({
                title: '✅',
                text: i18n.ssl_upload_success,
                icon: 'success',
                timer: 5000,
                timerProgressBar: true,
                confirmButtonText: i18n.common_ok
            });

            // Reload status
            loadSSLStatus();
        } else {
            throw new Error(resolveMsg(data));
        }
    } catch (error) {
        messageDiv.className = 'alert alert-danger py-2 small';
        messageDiv.innerHTML = i18n.ssl_upload_error + ': ' + escapeHtml(error.message);
        messageDiv.style.display = 'block';
    }
}

async function deleteSSLCertificates() {
    Swal.fire({
        title: i18n.ssl_delete_title,
        text: i18n.ssl_delete_confirm,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#dc3545',
        cancelButtonColor: '#6c757d',
        confirmButtonText: i18n.common_delete,
        cancelButtonText: i18n.common_cancel
    }).then(async (result) => {
        if (result.isConfirmed) {
            const messageDiv = document.getElementById('ssl-message');

            try {
                const response = await fetch('/api/ssl/certificates', { method: 'DELETE' });
                if (!response.ok) {
                    Swal.fire({ icon: 'error', title: i18n.error });
                    return;
                }
                const data = await response.json();

                if (data.success) {
                    Swal.fire({
                        title: '✅',
                        text: i18n.ssl_deleted,
                        icon: 'success',
                        timer: 2000,
                        showConfirmButton: false
                    });
                    loadSSLStatus();
                } else {
                    throw new Error(resolveMsg(data));
                }
            } catch (error) {
                Swal.fire({
                    title: i18n.error,
                    text: error.message,
                    icon: 'error'
                });
            }
        }
    });
}

// ============================================================================
// RECIPE DEDUPLICATION & EXCLUSION
// ============================================================================

let duplicatesModalInstance = null;
let duplicatePairs = [];
let currentDupIndex = 0;

function showDuplicatesModal() {
    if (!duplicatesModalInstance) {
        duplicatesModalInstance = new bootstrap.Modal(document.getElementById('duplicatesModal'));
    }

    document.getElementById('duplicatesBody').innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-2">${i18n.find_duplicates_searching}</p>
        </div>`;
    document.getElementById('dup-counter').textContent = '';
    document.getElementById('dup-prev').disabled = true;
    document.getElementById('dup-next').disabled = true;

    duplicatesModalInstance.show();

    fetch('/api/recipes/duplicates')
        .then(r => r.json())
        .then(data => {
            if (!data.success) throw new Error(resolveMsg(data));
            duplicatePairs = data.pairs;
            currentDupIndex = 0;
            if (duplicatePairs.length === 0) {
                document.getElementById('duplicatesBody').innerHTML = `
                    <div class="text-center py-4">
                        <i class="bi bi-check-circle text-success fs-1"></i>
                        <p class="mt-2">${i18n.no_duplicates}</p>
                    </div>`;
                document.getElementById('dup-counter').textContent = '';
            } else {
                renderDuplicatePair();
            }
        })
        .catch(err => {
            document.getElementById('duplicatesBody').innerHTML = `
                <div class="alert alert-danger">${escapeHtml(err.message)}</div>`;
        });
}

function showDuplicatePair(delta) {
    if (delta !== undefined) {
        currentDupIndex += delta;
    }
    renderDuplicatePair();
}

function renderDuplicatePair() {
    if (duplicatePairs.length === 0) return;

    const pair = duplicatePairs[currentDupIndex];
    const a = pair.recipe_a;
    const b = pair.recipe_b;

    document.getElementById('dup-counter').textContent =
        i18n.duplicates_found.replace('{current}', currentDupIndex + 1).replace('{total}', duplicatePairs.length);
    document.getElementById('dup-prev').disabled = currentDupIndex === 0;
    document.getElementById('dup-next').disabled = currentDupIndex >= duplicatePairs.length - 1;

    const namesDiffer = a.name !== b.name;
    const urlsDiffer = a.url !== b.url;

    function recipeCard(recipe, side) {
        const rawImgSrc = recipe.image_url || '';
        const imgSrc = rawImgSrc ? safeUrl(rawImgSrc.startsWith('/') ? rawImgSrc : '/static/recipe_images/' + rawImgSrc) : '';
        const recipeName = escapeHtml(recipe.name || '');
        const recipeNameAttr = escapeAttr(recipe.name || '');
        const sourceName = escapeHtml(recipe.source_name || '');
        const recipeUrl = safeUrl(recipe.url);
        const recipeUrlText = escapeHtml(recipe.url || '');
        const recipeUrlAttr = escapeAttr(recipe.url || '');
        const linkPrefix = urlsDiffer ? '<i class="bi bi-exclamation-triangle-fill text-warning me-1 small"></i>' : '';
        const urlHtml = recipeUrl
            ? `<a href="${escapeAttr(recipeUrl)}" target="_blank" rel="noopener noreferrer" class="d-block small text-truncate mb-2" title="${recipeUrlAttr}">${linkPrefix}${recipeUrlText}</a>`
            : `<span class="d-block small text-truncate mb-2" title="${recipeUrlAttr}">${linkPrefix}${recipeUrlText}</span>`;
        const imgHtml = imgSrc
            ? `<img src="${escapeAttr(imgSrc)}" alt="${recipeNameAttr}" class="img-fluid rounded mb-2" style="max-height: 180px; object-fit: cover; width: 100%;">`
            : '<div class="bg-light rounded mb-2 d-flex align-items-center justify-content-center" style="height: 120px;"><i class="bi bi-image text-muted fs-1"></i></div>';

        const ingList = recipe.ingredients || [];
        const ingredients = ingList.map(ing => {
            const text = typeof ing === 'string' ? ing : (ing.name || JSON.stringify(ing));
            return `<li class="small">${escapeHtml(text)}</li>`;
        }).join('');
        const scrollStyle = ingList.length > 20 ? ' style="max-height: 400px; overflow-y: auto;"' : '';

        return `
            <div class="col-md-6">
                ${imgHtml}
                <h6 class="mb-1">${namesDiffer ? '<i class="bi bi-exclamation-triangle-fill text-warning me-1 small"></i>' : ''}${recipeName}</h6>
                <span class="badge bg-secondary mb-1">${sourceName}</span>
                ${urlHtml}
                <p class="small text-muted mb-1">${i18n.ingredients} (${ingList.length})</p>
                <div${scrollStyle}>
                    <ul class="list-unstyled ms-2">${ingredients}</ul>
                </div>
                <div class="mt-2 d-flex gap-2">
                    <button class="btn btn-outline-warning btn-sm" data-action="hideRecipeFromDup" data-arg1="${escapeAttr(recipe.id)}" data-arg2="${escapeAttr(side)}">
                        <i class="bi bi-eye-slash"></i> ${i18n.hide_recipe}
                    </button>
                    <button class="btn btn-outline-danger btn-sm" data-action="deleteRecipePermanent" data-arg1="${escapeAttr(recipe.id)}" data-arg2="${escapeAttr(side)}">
                        <i class="bi bi-trash"></i> ${i18n.delete_permanent}
                    </button>
                </div>
            </div>`;
    }

    document.getElementById('duplicatesBody').innerHTML = `
        <div class="row g-3">
            ${recipeCard(a, 'a')}
            ${recipeCard(b, 'b')}
        </div>`;
}

async function hideRecipeFromDup(recipeId, side) {
    try {
        const resp = await fetch(`/api/recipes/${recipeId}/exclude`, {
            method: 'PATCH',
            headers: { 'Origin': window.location.origin }
        });
        const data = await resp.json();
        if (!data.success) throw new Error(resolveMsg(data));

        removeDuplicatePair();
        updateExcludedUrlCount();
    } catch (err) {
        Swal.fire({ title: i18n.error, text: err.message, icon: 'error' });
    }
}

async function deleteRecipePermanent(recipeId, side) {
    const result = await Swal.fire({
        title: i18n.delete_permanent,
        text: i18n.delete_permanent_confirm,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#dc3545',
        confirmButtonText: i18n.delete_permanent
    });
    if (!result.isConfirmed) return;

    try {
        const resp = await fetch(`/api/recipes/${recipeId}/permanent`, {
            method: 'DELETE',
            headers: { 'Origin': window.location.origin }
        });
        const data = await resp.json();
        if (!data.success) throw new Error(resolveMsg(data));

        removeDuplicatePair();
        updateExcludedUrlCount();
    } catch (err) {
        Swal.fire({ title: i18n.error, text: err.message, icon: 'error' });
    }
}

function removeDuplicatePair() {
    duplicatePairs.splice(currentDupIndex, 1);
    updateDuplicatesCount();
    if (duplicatePairs.length === 0) {
        document.getElementById('duplicatesBody').innerHTML = `
            <div class="text-center py-4">
                <i class="bi bi-check-circle text-success fs-1"></i>
                <p class="mt-2">${i18n.no_duplicates}</p>
            </div>`;
        document.getElementById('dup-counter').textContent = '';
        document.getElementById('dup-prev').disabled = true;
        document.getElementById('dup-next').disabled = true;
    } else {
        if (currentDupIndex >= duplicatePairs.length) currentDupIndex = duplicatePairs.length - 1;
        renderDuplicatePair();
    }
}

// --- Excluded URLs modal ---

let excludedUrlsModalInstance = null;

function showExcludedUrlsModal() {
    if (!excludedUrlsModalInstance) {
        excludedUrlsModalInstance = new bootstrap.Modal(document.getElementById('excludedUrlsModal'));
    }

    document.getElementById('excludedUrlsBody').innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-2">${i18n.loading}</p>
        </div>`;
    document.getElementById('remove-all-exclusions-btn').style.display = 'none';

    excludedUrlsModalInstance.show();

    loadExcludedUrls();
}

function loadExcludedUrls() {
    fetch('/api/recipes/excluded-urls')
        .then(r => r.json())
        .then(data => {
            if (!data.success) throw new Error(resolveMsg(data));

            if (data.count === 0) {
                document.getElementById('excludedUrlsBody').innerHTML = `
                    <div class="text-center py-4 text-muted">${i18n.no_exclusions}</div>`;
                document.getElementById('remove-all-exclusions-btn').style.display = 'none';
                return;
            }

            document.getElementById('remove-all-exclusions-btn').style.display = '';

            const rows = data.urls.map(u => {
                const href = safeUrl(u.url);
                const urlText = escapeHtml(u.url || '');
                const urlHtml = href
                    ? `<a href="${escapeAttr(href)}" target="_blank" rel="noopener noreferrer" class="text-truncate d-inline-block" style="max-width: 300px;">${urlText}</a>`
                    : `<span class="text-truncate d-inline-block" style="max-width: 300px;">${urlText}</span>`;
                return `
                    <tr>
                        <td class="small">${escapeHtml(u.recipe_name || '-')}</td>
                        <td><span class="badge bg-secondary">${escapeHtml(u.source_name || '-')}</span></td>
                        <td class="small">${urlHtml}</td>
                        <td class="small text-muted">${u.excluded_at ? escapeHtml(new Date(u.excluded_at).toLocaleDateString()) : '-'}</td>
                        <td>
                            <button class="btn btn-outline-danger btn-sm py-0 px-1" data-action="removeExclusion" data-kind="${escapeAttr(u.kind || 'url')}" data-arg="${escapeAttr(u.id)}">
                                <i class="bi bi-x"></i>
                            </button>
                        </td>
                    </tr>`;
            }).join('');

            document.getElementById('excludedUrlsBody').innerHTML = `
                <table class="table table-sm table-hover">
                    <thead>
                        <tr>
                            <th>${i18n.col_recipe}</th>
                            <th>${i18n.col_source}</th>
                            <th>${i18n.col_url}</th>
                            <th>${i18n.col_date}</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>`;
        })
        .catch(err => {
            document.getElementById('excludedUrlsBody').innerHTML = `
                <div class="alert alert-danger">${escapeHtml(err.message)}</div>`;
        });
}

async function removeExclusion(kind, exclusionId) {
    try {
        const isHiddenRecipe = kind === 'recipe';
        const resp = await fetch(
            isHiddenRecipe
                ? `/api/recipes/${exclusionId}/restore`
                : `/api/recipes/excluded-urls/${exclusionId}`,
            {
                method: isHiddenRecipe ? 'PATCH' : 'DELETE',
                headers: { 'Origin': window.location.origin }
            }
        );
        const data = await resp.json();
        if (!data.success) throw new Error(resolveMsg(data));

        loadExcludedUrls();
        updateExcludedUrlCount();
    } catch (err) {
        Swal.fire({ title: i18n.error, text: err.message, icon: 'error' });
    }
}

async function removeAllExclusions() {
    const result = await Swal.fire({
        title: i18n.remove_all_exclusions,
        text: i18n.remove_all_confirm,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#dc3545',
        confirmButtonText: i18n.remove_all_exclusions
    });
    if (!result.isConfirmed) return;

    try {
        const resp = await fetch('/api/recipes/excluded-urls', {
            method: 'DELETE',
            headers: { 'Origin': window.location.origin }
        });
        const data = await resp.json();
        if (!data.success) throw new Error(resolveMsg(data));

        loadExcludedUrls();
        updateExcludedUrlCount();
    } catch (err) {
        Swal.fire({ title: i18n.error, text: err.message, icon: 'error' });
    }
}

function updateExcludedUrlCount() {
    fetch('/api/recipes/excluded-urls')
        .then(r => r.json())
        .then(data => {
            const btn = document.getElementById('excluded-urls-btn-text');
            if (data.success && data.count > 0) {
                btn.textContent = i18n.excluded_urls_count.replace('{count}', data.count);
            } else {
                btn.textContent = i18n.excluded_urls;
            }
        });
}

// Load excluded URL count on page load
document.addEventListener('DOMContentLoaded', () => { updateExcludedUrlCount(); });

// ==================== DUPLICATES COUNT ====================

function setCountButtonText(spanId, baseLabel, countData) {
    const span = document.getElementById(spanId);
    const button = span?.closest('button');
    if (!span) return;

    if (countData?.success) {
        const count = Number.isFinite(Number(countData.count)) ? Number(countData.count) : 0;
        span.textContent = `${baseLabel} (${count})`;
        if (button) {
            button.removeAttribute('title');
            button.removeAttribute('aria-label');
        }
        return;
    }

    span.textContent = `${baseLabel} (?)`;
    const reason = countData ? resolveMsg(countData) : '';
    const tooltip = reason || i18n.count_unavailable;
    if (button) {
        button.title = tooltip;
        button.setAttribute('aria-label', tooltip);
    }
}

function updateDuplicatesCount() {
    fetch('/api/recipes/duplicates/count')
        .then(r => r.json())
        .then(data => {
            setCountButtonText('duplicates-btn-text', i18n.find_duplicates, data);
        })
        .catch(() => {
            setCountButtonText('duplicates-btn-text', i18n.find_duplicates, null);
        });
}

document.addEventListener('DOMContentLoaded', () => { updateDuplicatesCount(); });

// ==================== UNMATCHED OFFERS COUNT ====================

function updateUnmatchedCount() {
    fetch('/api/matching/unmatched-offers/count')
        .then(r => r.json())
        .then(data => {
            setCountButtonText('unmatched-btn-text', i18n.show_unmatched, data);
        })
        .catch(() => {
            setCountButtonText('unmatched-btn-text', i18n.show_unmatched, null);
        });
}

document.addEventListener('DOMContentLoaded', () => { updateUnmatchedCount(); });

// ==================== SPELL CHECK ====================

let spellCheckData = [];
let spellGlobalExclusions = [];
let showExcluded = false;

function loadSpellCheckBadge() {
    fetch('/api/spell-corrections/count')
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                const total = data.total || 0;
                const unreviewed = data.count || 0;
                if (total > 0) {
                    updateSpellCheckButtonText(total, unreviewed > 0);
                }
            }
        })
        .catch(() => {});
}

function updateSpellCheckButtonText(count, pulse) {
    const btnText = document.getElementById('spellcheck-btn-text');
    const btn = document.getElementById('spellcheck-btn');
    if (btnText && count > 0) {
        btnText.textContent = `${i18n.spellcheck} (${count})`;
        if (pulse && btn) {
            btn.classList.add('spell-pulse');
        }
    } else if (btnText) {
        btnText.textContent = i18n.spellcheck;
    }
}

async function showSpellCheckModal() {
    const btn = document.getElementById('spellcheck-btn');
    if (btn) btn.classList.remove('spell-pulse');

    const body = document.getElementById('spellCheckBody');
    body.innerHTML = `<div class="text-center py-4"><div class="spinner-border spinner-border-sm"></div> ${i18n.loading}</div>`;

    const modal = new bootstrap.Modal(document.getElementById('spellCheckModal'));
    modal.show();

    try {
        const resp = await fetch('/api/spell-corrections');
        const data = await resp.json();

        if (!data.success) {
            body.innerHTML = `<div class="text-center py-4 text-danger">${i18n.error}</div>`;
            return;
        }

        spellCheckData = data.corrections || [];
        spellGlobalExclusions = data.global_exclusions || [];

        const activeCount = spellCheckData.filter(c => !c.excluded).length;
        updateSpellCheckButtonText(activeCount, false);

        if (data.unreviewed_count > 0) {
            fetch('/api/spell-corrections/review', { method: 'POST', headers: { 'Origin': location.origin } })
                .then(() => {
                    const navBadge = document.getElementById('spell-badge');
                    if (navBadge) navBadge.style.display = 'none';
                })
                .catch(() => {});
        }

        renderSpellCheckGrouped();

    } catch (err) {
        body.innerHTML = `<div class="text-center py-4 text-danger">${i18n.error}</div>`;
    }
}

function renderSpellCheckGrouped() {
    const body = document.getElementById('spellCheckBody');
    const toggleBtn = document.getElementById('spellcheck-toggle-excluded');

    const active = spellCheckData.filter(c => !c.excluded);
    const perRecipeExcluded = spellCheckData.filter(c => c.excluded);
    const hasExcluded = perRecipeExcluded.length > 0 || spellGlobalExclusions.length > 0;

    if (hasExcluded) {
        toggleBtn.style.display = '';
        toggleBtn.innerHTML = showExcluded
            ? `${i18n.spellcheck_hide_excluded}`
            : `${i18n.spellcheck_show_excluded}`;
    } else {
        toggleBtn.style.display = 'none';
    }

    if (active.length === 0 && !showExcluded) {
        body.innerHTML = `<div class="text-center py-4 text-muted">${i18n.spellcheck_no_corrections}</div>`;
        return;
    }

    // Group active corrections by word pair
    const groups = {};
    for (const c of active) {
        const key = `${c.original_word}|${c.corrected_word}`;
        if (!groups[key]) {
            groups[key] = { original: c.original_word, corrected: c.corrected_word, recipes: [] };
        }
        groups[key].recipes.push(c);
    }

    let html = '';

    // Render active groups (new/unreviewed groups first)
    const sortedGroups = Object.values(groups).sort((a, b) => {
        const aNew = a.recipes.some(c => !c.reviewed);
        const bNew = b.recipes.some(c => !c.reviewed);
        if (aNew !== bNew) return aNew ? -1 : 1;
        return a.original.localeCompare(b.original);
    });
    for (const group of sortedGroups) {
        const countText = i18n.spellcheck_recipes_count.replace('{count}', group.recipes.length);
        const hasNew = group.recipes.some(c => !c.reviewed);
        html += `<div class="border rounded mb-2">`;
        html += `<div class="d-flex align-items-center justify-content-between px-3 py-2 bg-body-tertiary">`;
        html += `<span>`;
        if (hasNew) html += `<span class="badge bg-info me-1">${i18n.new_badge}</span>`;
        html += `<span style="text-decoration: line-through; opacity: 0.6;">${escapeHtml(group.original)}</span>`;
        html += ` <i class="bi bi-arrow-right text-muted small"></i> `;
        html += `<span class="fw-medium">${escapeHtml(group.corrected)}</span>`;
        html += `<span class="text-muted small ms-2">(${countText})</span>`;
        html += `</span>`;
        html += `<button class="btn btn-outline-danger btn-sm py-0 px-2" data-action="excludeWordGlobal" data-arg1="${escapeAttr(group.original)}" data-arg2="${escapeAttr(group.corrected)}" title="${escapeAttr(i18n.spellcheck_exclude_word_tooltip)}">`;
        html += `<i class="bi bi-x-circle"></i> ${i18n.spellcheck_exclude_word}`;
        html += `</button>`;
        html += `</div>`;

        html += `<div class="px-3 py-1">`;
        for (const c of group.recipes) {
            const recipeUrl = safeUrl(c.recipe_url);
            const linkIcon = recipeUrl
                ? `<a href="${escapeAttr(recipeUrl)}" target="_blank" rel="noopener noreferrer" style="color: #8b5cf6;" class="me-1"><i class="bi bi-box-arrow-up-right small"></i></a>`
                : '';
            const newBadge = !c.reviewed ? ` <span class="badge bg-info ms-1">${i18n.new_badge}</span>` : '';
            html += `<div class="d-flex align-items-center justify-content-between py-1 border-bottom" style="border-color: var(--bs-border-color-translucent) !important;">`;
            html += `<span class="small">${linkIcon}${escapeHtml(c.recipe_name)}${newBadge}</span>`;
            html += `<button class="btn btn-outline-warning btn-sm py-0 px-1" data-action="revertCorrection" data-arg="${escapeAttr(c.id)}" title="${escapeAttr(i18n.spellcheck_revert_tooltip)}">`;
            html += `<i class="bi bi-arrow-counterclockwise"></i>`;
            html += `</button>`;
            html += `</div>`;
        }
        html += `</div></div>`;
    }

    // Render excluded section
    if (showExcluded && (spellGlobalExclusions.length > 0 || perRecipeExcluded.length > 0)) {
        html += `<hr class="my-3">`;

        // Global exclusions
        for (const ex of spellGlobalExclusions) {
            html += `<div class="d-flex align-items-center justify-content-between px-3 py-2 mb-1 border rounded bg-body-tertiary text-muted">`;
            html += `<span>`;
            html += `<span>${escapeHtml(ex.original_word)}</span>`;
            html += ` <i class="bi bi-arrow-right small"></i> `;
            html += `<span style="text-decoration: line-through;">${escapeHtml(ex.corrected_word)}</span>`;
            html += `</span>`;
            html += `<button class="btn btn-outline-success btn-sm py-0 px-2" data-action="resetWordExclusion" data-arg1="${escapeAttr(ex.original_word)}" data-arg2="${escapeAttr(ex.corrected_word)}" title="${escapeAttr(i18n.spellcheck_allow_again)}">`;
            html += `<i class="bi bi-arrow-counterclockwise"></i> ${i18n.spellcheck_allow_again}`;
            html += `</button>`;
            html += `</div>`;
        }

        // Per-recipe exclusions
        for (const c of perRecipeExcluded) {
            html += `<div class="d-flex align-items-center justify-content-between px-3 py-2 mb-1 border rounded bg-body-tertiary text-muted">`;
            html += `<span class="small">`;
            html += `${escapeHtml(c.original_word)} <i class="bi bi-arrow-right small"></i> `;
            html += `<span style="text-decoration: line-through;">${escapeHtml(c.corrected_word)}</span>`;
            html += ` — ${escapeHtml(c.recipe_name)}`;
            html += `</span>`;
            html += `<button class="btn btn-outline-success btn-sm py-0 px-1" data-action="resetExclusion" data-arg="${escapeAttr(c.id)}" title="${escapeAttr(i18n.spellcheck_allow_again)}">`;
            html += `<i class="bi bi-arrow-counterclockwise"></i>`;
            html += `</button>`;
            html += `</div>`;
        }
    }

    if (!html) {
        body.innerHTML = `<div class="text-center py-4 text-muted">${i18n.spellcheck_no_corrections}</div>`;
        return;
    }

    body.innerHTML = html;
}

function toggleExcludedCorrections() {
    showExcluded = !showExcluded;
    renderSpellCheckGrouped();
}

function updateSpellBtnCount() {
    const activeCount = spellCheckData.filter(c => !c.excluded).length;
    updateSpellCheckButtonText(activeCount, false);
}

async function revertCorrection(id) {
    try {
        const resp = await fetch('/api/spell-corrections/revert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Origin': location.origin },
            body: JSON.stringify({ id })
        });
        const data = await resp.json();
        if (data.success) {
            const c = spellCheckData.find(c => c.id === id);
            if (c) { c.excluded = true; c.reviewed = true; }
            renderSpellCheckGrouped();
            updateSpellBtnCount();
        } else {
            Swal.fire({ icon: 'error', text: resolveMsg(data) });
        }
    } catch (err) {
        Swal.fire({ icon: 'error', text: i18n.error });
    }
}

async function excludeWordGlobal(originalWord, correctedWord) {
    try {
        const resp = await fetch('/api/spell-corrections/exclude-word', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Origin': location.origin },
            body: JSON.stringify({ original_word: originalWord, corrected_word: correctedWord })
        });
        const data = await resp.json();
        if (data.success) {
            // Remove all corrections for this word pair from local data
            spellCheckData = spellCheckData.filter(c =>
                !(c.original_word === originalWord && c.corrected_word === correctedWord)
            );
            // Add to global exclusions list
            spellGlobalExclusions.push({ original_word: originalWord, corrected_word: correctedWord });
            renderSpellCheckGrouped();
            updateSpellBtnCount();
        } else {
            Swal.fire({ icon: 'error', text: resolveMsg(data) });
        }
    } catch (err) {
        Swal.fire({ icon: 'error', text: i18n.error });
    }
}

async function resetExclusion(id) {
    try {
        const resp = await fetch('/api/spell-corrections/reset-exclusion', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Origin': location.origin },
            body: JSON.stringify({ id })
        });
        const data = await resp.json();
        if (data.success) {
            spellCheckData = spellCheckData.filter(c => c.id !== id);
            renderSpellCheckGrouped();
            updateSpellBtnCount();
        } else {
            Swal.fire({ icon: 'error', text: resolveMsg(data) });
        }
    } catch (err) {
        Swal.fire({ icon: 'error', text: i18n.error });
    }
}

async function resetWordExclusion(originalWord, correctedWord) {
    try {
        const resp = await fetch('/api/spell-corrections/reset-word-exclusion', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Origin': location.origin },
            body: JSON.stringify({ original_word: originalWord, corrected_word: correctedWord })
        });
        const data = await resp.json();
        if (data.success) {
            spellGlobalExclusions = spellGlobalExclusions.filter(e =>
                !(e.original_word === originalWord && e.corrected_word === correctedWord)
            );
            renderSpellCheckGrouped();
        } else {
            Swal.fire({ icon: 'error', text: resolveMsg(data) });
        }
    } catch (err) {
        Swal.fire({ icon: 'error', text: i18n.error });
    }
}

// ============================================
// Event delegation
// ============================================
document.addEventListener('click', function(e) {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    switch (el.dataset.action) {
        case 'setBalance': setBalance(el.dataset.category, parseInt(el.dataset.value)); break;
        case 'showDuplicatePair': showDuplicatePair(parseInt(el.dataset.dir)); break;
        case 'clearAddressSearch': clearAddressSearch(); break;
        case 'resetBalance': resetBalance(); break;
        case 'showDuplicatesModal': showDuplicatesModal(); break;
        case 'showExcludedUrlsModal': showExcludedUrlsModal(); break;
        case 'showSpellCheckModal': showSpellCheckModal(); break;
        case 'showUnmatchedOffers': showUnmatchedOffers(); break;
        case 'removeAllExclusions': removeAllExclusions(); break;
        case 'toggleExcludedCorrections': toggleExcludedCorrections(); break;
        case 'downloadMissingImages': downloadMissingImages(); break;
        case 'confirmClearImages': confirmClearImages(); break;
        case 'showFailedImagesModal': showFailedImagesModal(); break;
        case 'deleteAllFailedRecipes': deleteAllFailedRecipes(); break;
        case 'pickSSLFile': document.getElementById(el.dataset.target)?.click(); break;
        case 'uploadSSLCertificates': uploadSSLCertificates(); break;
        case 'deleteSSLCertificates': deleteSSLCertificates(); break;
        case 'cancelImageDownload': cancelImageDownload(); break;
        case 'selectAddress': selectAddress(el.dataset.street, el.dataset.postal, el.dataset.city); break;
        case 'resetFailedRecipe': resetFailedRecipe(el.dataset.arg); break;
        case 'deleteFailedRecipe': deleteFailedRecipe(el.dataset.arg1, el.dataset.arg2); break;
        case 'hideRecipeFromDup': hideRecipeFromDup(el.dataset.arg1, el.dataset.arg2); break;
        case 'deleteRecipePermanent': deleteRecipePermanent(el.dataset.arg1, el.dataset.arg2); break;
        case 'removeExclusion': removeExclusion(el.dataset.kind, el.dataset.arg); break;
        case 'excludeWordGlobal': excludeWordGlobal(el.dataset.arg1, el.dataset.arg2); break;
        case 'revertCorrection': revertCorrection(parseInt(el.dataset.arg)); break;
        case 'resetWordExclusion': resetWordExclusion(el.dataset.arg1, el.dataset.arg2); break;
        case 'resetExclusion': resetExclusion(parseInt(el.dataset.arg)); break;
    }
});

document.addEventListener('change', function(e) {
    const el = e.target;
    const action = el.dataset.change;
    if (!action) return;
    const actions = action.split(',');
    for (const a of actions) {
        switch (a.trim()) {
            case 'setTheme': setTheme(el.dataset.value); break;
            case 'setHighContrast': setHighContrast(el.checked); break;
            case 'saveMatchingPreferences': saveMatchingPreferences(); break;
            case 'saveImagePreferences': saveImagePreferences(); break;
            case 'saveCacheSettings': saveCacheSettings(); break;
            case 'toggleSSL': toggleSSL(); break;
            case 'updateSSLFileLabel': updateSSLFileLabel(el); break;
            case 'updateIngredientLabel': updateIngredientLabel(); break;
            case 'saveMatchingPreferencesDebounced': saveMatchingPreferencesDebounced(); break;
        }
    }
});

document.addEventListener('input', function(e) {
    const el = e.target;
    const action = el.dataset.input;
    if (!action) return;
    const actions = action.split(',');
    for (const a of actions) {
        switch (a.trim()) {
            case 'setFontSize': setFontSize(parseInt(el.value)); break;
            case 'searchAddress': searchAddress(); break;
            case 'debouncedSaveAddress': debouncedSaveAddress(); break;
            case 'updateIngredientLabel': updateIngredientLabel(); break;
            case 'saveMatchingPreferencesDebounced': saveMatchingPreferencesDebounced(); break;
            case 'autoResize': autoResizeTextarea(el); break;
            case 'saveMatchingPreferences': saveMatchingPreferences(); break;
            case 'updateMemoryLabel': updateMemoryLabel(el.value); break;
        }
    }
});

// Image error handler (replaces inline onerror on dup preview images)
document.addEventListener('error', function(e) {
    if (e.target.tagName === 'IMG') {
        e.target.style.display = 'none';
    }
}, true);
