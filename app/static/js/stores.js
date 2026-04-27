// Stores page behavior. Jinja-provided i18n data is bootstrapped in stores.html.
const i18n = window.DealMealsStoresI18n || {};
const pageConfig = window.DealMealsStoresPage || {};
const STORE_LOCALE = pageConfig.locale || undefined;
const t = window.DealMeals.createTranslator(i18n);

const STORE_CONFIG_ERROR_KEYS = [
    'stores.missing_delivery_address',
    'stores.missing_ehandel_store',
    'stores.missing_store_location',
    'stores.invalid_store_config'
];

function isStoreConfigErrorKey(key) {
    return STORE_CONFIG_ERROR_KEYS.includes(key);
}

// NOTE: escapeHtml() is defined in dealmeals-core.js

function fetchedProductsText(data, displayName) {
    if (data.message_key === 'ws.fetch_empty_success') {
        return t(data.message_key, { ...(data.message_params || {}), store: displayName });
    }
    if (data.base !== undefined && data.variants !== undefined && data.variants > 0) {
        return t('fetched_products_with_variants', { base: data.base, variants: data.variants, store: displayName });
    }
    return t('fetched_products', { count: data.count, store: displayName });
}

// Format store name for display (ICA stays uppercase, others get capitalized)
function formatStoreName(storeId) {
    const names = {
        'ica': 'ICA',
        'hemkop': 'Hemköp',
    };
    return names[storeId.toLowerCase()] || storeId.charAt(0).toUpperCase() + storeId.slice(1);
}

// Fetch selected location for a store
async function loadSelectedLocation(storeId) {
    try {
        // Fetch store config (location info)
        const response = await fetch(`/api/store-config?store=${storeId}`);
        if (!response.ok) return;

        const data = await response.json();

        const locationDiv = document.getElementById(`${storeId}-location`);
        const locationNameEl = document.getElementById(`${storeId}-location-name`);

        if (!locationDiv || !locationNameEl) return;

        // Show location card
        locationDiv.style.display = 'block';

        // Show location based on API data
        if (data.location_type === 'ehandel') {
            locationNameEl.innerHTML = '<i class="bi bi-truck"></i> ' + i18n.home_delivery;
        } else if (data.location_name) {
            locationNameEl.innerHTML = `<i class="bi bi-shop"></i> ${escapeHtml(data.location_name)}`;
        } else if (data.location_type === 'butik') {
            locationNameEl.innerHTML = '<i class="bi bi-shop"></i> ' + i18n.store_selected;
        } else {
            // Hide if no location exists
            locationDiv.style.display = 'none';
        }
    } catch (error) {
        console.error(`Could not load location for ${storeId}:`, error);
    }
}

// Load store config and location info
async function checkStoreStatus(storeId) {
    loadStoreConfig(storeId);
    loadSelectedLocation(storeId);
}

// ============================================
// Generic Store Config System
// Works for any store plugin with config fields
// ============================================

// Store config state - holds current config for each store
const storeConfigs = {};

// Load store config and render UI
async function loadStoreConfig(storeId) {
    try {
        // Fetch config fields from plugin
        const fieldsResponse = await fetch(`/api/stores/${storeId}/config-fields`);
        if (!fieldsResponse.ok) return;
        const fieldsData = await fieldsResponse.json();

        // Fetch saved config values
        const configResponse = await fetch(`/api/stores/${storeId}/config`);
        if (!configResponse.ok) return;
        const configData = await configResponse.json();

        storeConfigs[storeId] = configData.config || {};

        // If plugin has config fields, render them
        if (fieldsData.success && fieldsData.fields && fieldsData.fields.length > 0) {
            renderStoreConfigUI(storeId, fieldsData.fields, storeConfigs[storeId]);
        }
    } catch (error) {
        console.error(`Error loading config for ${storeId}:`, error);
    }
}

// Render config UI dynamically based on field definitions
function renderStoreConfigUI(storeId, fields, config) {
    const container = document.getElementById(`${storeId}-config-container`);
    if (!container) return;

    let html = '';
    const locationType = config.location_type || 'ehandel';

    // Separate fields into groups: independent and dependent
    const independentFields = fields.filter(f => !f.depends_on);
    const dependentFields = fields.filter(f => f.depends_on);

    // Render independent fields first (e.g., radio buttons)
    for (const field of independentFields) {
        const value = config[field.key] || field.default;

        if (field.field_type === 'radio' && field.options) {
            for (const opt of field.options) {
                const checked = value === opt.value ? 'checked' : '';
                const radioId = `${storeId}-${field.key}-${opt.value}`;

                // Get store name for this option type
                // ehandel uses ehandel_store_name, butik uses location_name
                let storeName = '';
                if (opt.value === 'ehandel') {
                    storeName = config.ehandel_store_name || '';
                } else if (opt.value === 'butik') {
                    storeName = config.location_name || '';
                }

                // Description: show store name OR original description
                let descriptionHtml = '';
                if (storeName) {
                    descriptionHtml = `<br><small class="text-muted"><i class="bi bi-shop"></i> ${escapeHtml(storeName)}</small>`;
                } else {
                    descriptionHtml = opt.description ? `<br><small class="text-muted">${escapeHtml(opt.description)}</small>` : '';
                }

                html += `
                    <div class="form-check mb-2">
                        <input class="form-check-input" type="radio" name="${storeId}-${field.key}"
                               id="${radioId}" value="${escapeHtml(opt.value)}" ${checked}
                               data-change="updateStoreConfigField" data-store="${storeId}" data-field="${field.key}" data-value="${opt.value}">
                        <label class="form-check-label" for="${radioId}">
                            <strong>${escapeHtml(opt.label)}</strong>${opt.suffix ? ` <span class="fw-normal">${escapeHtml(opt.suffix)}</span>` : ''}
                            ${descriptionHtml}
                        </label>
                    </div>
                `;
            }
        }
    }

    // Render dependent fields in a stacked wrapper (prevents layout shift when switching)
    if (dependentFields.length > 0) {
        html += `<div class="store-field-stack">`;
        for (const field of dependentFields) {
            const shouldShow = config[field.depends_on.field] === field.depends_on.value;

            if (field.field_type === 'async_select') {
                const savedStoreId = config[`${field.key}_id`] || '';
                const savedStoreName = config[`${field.key}_name`] || '';

                html += `
                    <div id="${storeId}-${field.key}-container" class="mb-2" style="display: ${shouldShow ? 'block' : 'none'};">
                        <label class="form-label">${escapeHtml(field.label)}</label>
                        <select class="form-select" id="${storeId}-${field.key}"
                                data-invalidate-on-postal-change="${field.invalidate_on_postal_change ? 'true' : 'false'}"
                                data-change="selectAsyncOption" data-store="${storeId}" data-field="${field.key}">
                            <option value="">${escapeHtml(field.placeholder || i18n.select_placeholder)}</option>
                            ${savedStoreId ? `<option value="${escapeHtml(savedStoreId)}" selected>${escapeHtml(savedStoreName)}</option>` : ''}
                        </select>
                    </div>
                `;
            } else if (field.field_type === 'search') {
                html += `
                    <div id="${storeId}-${field.key}-container" class="mb-2" style="display: ${shouldShow ? 'block' : 'none'};">
                        <label class="form-label">${escapeHtml(field.label)}</label>
                        <div class="store-search-wrapper">
                            <div class="input-group">
                                <input type="text" class="form-control" id="${storeId}-${field.key}"
                                       placeholder="${escapeHtml(field.placeholder || '')}"
                                       data-keyup="handleStoreSearchKeyup" data-store="${storeId}">
                                <button class="btn btn-outline-primary" type="button" data-action="searchStoreLocations" data-arg="${storeId}">
                                    <i class="bi bi-search"></i>
                                </button>
                            </div>
                            <div id="${storeId}-location-results" class="list-group store-location-dropdown" style="display: none;"></div>
                        </div>
                    </div>
                `;
            }
        }
        html += `</div>`;
    }

    // Handle any remaining non-dependent, non-radio fields (text, display)
    for (const field of independentFields) {
        const value = config[field.key] || field.default;

        if (field.field_type === 'text') {
            html += `
                <div class="mb-3">
                    <label class="form-label" for="${storeId}-${field.key}">${escapeHtml(field.label)}</label>
                    <input type="text" class="form-control" id="${storeId}-${field.key}"
                           value="${escapeHtml(value || '')}"
                           placeholder="${escapeHtml(field.placeholder || '')}"
                           data-change="updateStoreConfigField" data-store="${storeId}" data-field="${field.key}" data-use-value="true">
                </div>
            `;
        } else if (field.field_type === 'display') {
            // Static display field (read-only info text, styled like a selected radio option)
            const opt = field.options && field.options[0] ? field.options[0] : {};
            html += `
                <div class="form-check mb-2">
                    <input class="form-check-input" type="radio" checked readonly style="pointer-events: none;">
                    <label class="form-check-label">
                        <strong>${escapeHtml(field.label)}</strong>${opt.suffix ? ` <span class="fw-normal">${escapeHtml(opt.suffix)}</span>` : ''}
                        ${opt.description ? `<br><small class="text-muted">${escapeHtml(opt.description)}</small>` : ''}
                    </label>
                </div>
            `;
        }
    }

    container.innerHTML = html;

    // Load async_select options after rendering
    loadAsyncSelectOptions(storeId, fields, config);
}

// Load options for async_select fields
async function loadAsyncSelectOptions(storeId, fields, config) {
    for (const field of fields) {
        if (field.field_type !== 'async_select') continue;

        // Always load options (even for hidden fields) so they're ready when user switches
        const select = document.getElementById(`${storeId}-${field.key}`);
        if (!select) continue;

        try {
            // Fetch options from API
            const response = await fetch(`/api/stores/${storeId}/ehandel-stores`);
            if (!response.ok) continue;
            const data = await response.json();

            if (data.success && data.stores) {
                // Only check postal code changes for fields that explicitly require it
                // (e.g., ICA e-handel depends on postal code, Willys/Mathem do not)
                let postalCodeChanged = false;
                const currentPostalCode = data.postal_code || '';

                if (field.invalidate_on_postal_change) {
                    const savedPostalCode = config._postal_code_used;
                    postalCodeChanged = savedPostalCode && currentPostalCode && savedPostalCode !== currentPostalCode;

                    if (postalCodeChanged) {
                        // Postal code changed - clear saved store selection silently
                        dbg.log(`Postal code changed: ${savedPostalCode} -> ${currentPostalCode}, clearing ${storeId} store selection`);
                        storeConfigs[storeId][`${field.key}_id`] = '';
                        storeConfigs[storeId][`${field.key}_name`] = '';
                        storeConfigs[storeId][`${field.key}_address`] = '';
                        storeConfigs[storeId]._postal_code_used = '';
                        // Save the cleared config
                        saveStoreConfig(storeId);
                    }
                }

                // Keep current selection only if postal code hasn't changed
                const currentValue = postalCodeChanged ? '' : select.value;

                // Build options HTML
                let optionsHtml = `<option value="">${i18n.select_store_placeholder}</option>`;
                for (const store of data.stores) {
                    const selected = store.id === currentValue ? 'selected' : '';
                    // Only include postal code in data attribute if field invalidates on change
                    const postalAttr = field.invalidate_on_postal_change ? `data-postal="${escapeHtml(currentPostalCode)}"` : '';
                    optionsHtml += `<option value="${escapeHtml(store.id)}" data-name="${escapeHtml(store.name)}" data-address="${escapeHtml(store.address)}" ${postalAttr} ${selected}>${escapeHtml(store.name)} - ${escapeHtml(store.address)}</option>`;
                }
                select.innerHTML = optionsHtml;

                // Restore selection if valid and postal code unchanged
                if (currentValue) {
                    select.value = currentValue;
                }

                // If postal code changed, re-render UI to reflect cleared selection
                if (postalCodeChanged) {
                    const fieldsResponse = await fetch(`/api/stores/${storeId}/config-fields`);
                    if (!fieldsResponse.ok) return;
                    const fieldsData = await fieldsResponse.json();
                    if (fieldsData.success && fieldsData.fields) {
                        renderStoreConfigUI(storeId, fieldsData.fields, storeConfigs[storeId]);
                    }
                    return; // Exit early - re-render will handle options
                }
            } else if (data.message_key || data.error) {
                select.innerHTML = `<option value="">${escapeHtml(data.message_key ? t(data.message_key, data.message_params) : data.error)}</option>`;
            }
        } catch (error) {
            console.error(`Error loading async options for ${storeId}-${field.key}:`, error);
            select.innerHTML = `<option value="">${i18n.could_not_load_stores}</option>`;
        }
    }
}

// Handle async_select option selection
async function selectAsyncOption(storeId, fieldKey, selectElement) {
    const selectedOption = selectElement.options[selectElement.selectedIndex];
    const storeIdValue = selectedOption.value;
    const storeName = selectedOption.dataset.name || selectedOption.textContent;
    const storeAddress = selectedOption.dataset.address || '';
    const postalCode = selectedOption.dataset.postal || '';
    const invalidateOnPostalChange = selectElement.dataset.invalidateOnPostalChange === 'true';

    if (!storeIdValue) return;

    // Update config with the selected store (saved per field key)
    if (!storeConfigs[storeId]) storeConfigs[storeId] = {};
    storeConfigs[storeId].location_type = 'ehandel';
    storeConfigs[storeId][`${fieldKey}_id`] = storeIdValue;
    storeConfigs[storeId][`${fieldKey}_name`] = storeName;
    storeConfigs[storeId][`${fieldKey}_address`] = storeAddress;

    // Save postal code if this field invalidates on postal change (e.g., ICA e-handel)
    // This allows detecting when user changes postal code and needs to re-select store
    if (invalidateOnPostalChange && postalCode) {
        storeConfigs[storeId]._postal_code_used = postalCode;
    }

    await saveStoreConfig(storeId);

    // Re-render to show selected store in radio button description
    const fieldsResponse = await fetch(`/api/stores/${storeId}/config-fields`);
    if (!fieldsResponse.ok) return;
    const fieldsData = await fieldsResponse.json();
    if (fieldsData.success && fieldsData.fields) {
        renderStoreConfigUI(storeId, fieldsData.fields, storeConfigs[storeId]);
    }
}

// Update a config field and save
async function updateStoreConfigField(storeId, fieldKey, value) {
    if (!storeConfigs[storeId]) storeConfigs[storeId] = {};
    storeConfigs[storeId][fieldKey] = value;

    // Handle location_type changes - toggle display without full re-render
    if (fieldKey === 'location_type') {
        // Toggle field display based on new value
        const ehandelContainer = document.getElementById(`${storeId}-ehandel_store-container`);
        const searchContainer = document.getElementById(`${storeId}-location_search-container`);

        if (ehandelContainer) {
            ehandelContainer.style.display = value === 'ehandel' ? 'block' : 'none';
        }
        if (searchContainer) {
            searchContainer.style.display = value === 'butik' ? 'block' : 'none';
        }

        // Save in background (don't wait)
        saveStoreConfig(storeId);
    }
}

// Handle Enter key in search
function handleStoreSearchKeyup(event, storeId) {
    if (event.key === 'Enter') {
        searchStoreLocations(storeId);
    }
}

// Search for store locations using generic endpoint
async function searchStoreLocations(storeId) {
    const searchInput = document.getElementById(`${storeId}-location_search`);
    const query = (searchInput?.value || '').trim();
    if (query.length < 2) return;

    // Get current location_type from config
    const locationType = storeConfigs[storeId]?.location_type || 'ehandel';

    try {
        const response = await fetch(`/api/stores/${storeId}/locations?q=${encodeURIComponent(query)}&location_type=${locationType}`);
        if (!response.ok) return;
        const data = await response.json();

        const resultsDiv = document.getElementById(`${storeId}-location-results`);
        if (!resultsDiv) return;

        if (data.stores && data.stores.length > 0) {
            resultsDiv.style.display = 'block';
            resultsDiv.innerHTML = data.stores.map(store => `
                <button type="button" class="list-group-item list-group-item-action py-2 store-location-btn"
                        data-store-id="${storeId}"
                        data-location-id="${escapeHtml(store.storeId)}"
                        data-location-name="${escapeHtml(store.displayName)}"
                        data-location-address="${escapeHtml(store.address)}">
                    <strong>${escapeHtml(store.displayName)}</strong><br>
                    <small class="text-muted">${escapeHtml(store.address)}</small>
                </button>
            `).join('');

            // Add click handlers
            resultsDiv.querySelectorAll('.store-location-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    selectStoreLocation(
                        this.dataset.storeId,
                        this.dataset.locationId,
                        this.dataset.locationName,
                        this.dataset.locationAddress
                    );
                });
            });
        } else {
            resultsDiv.style.display = 'block';
            resultsDiv.innerHTML = '<div class="list-group-item text-muted">' + i18n.no_stores_found + '</div>';
        }
    } catch (error) {
        console.error(`Error searching locations for ${storeId}:`, error);
    }
}

// Select a store location
async function selectStoreLocation(storeId, locationId, locationName, locationAddress) {
    // Clear search results and input
    const resultsDiv = document.getElementById(`${storeId}-location-results`);
    const searchInput = document.getElementById(`${storeId}-location_search`);
    if (resultsDiv) {
        resultsDiv.innerHTML = '';
        resultsDiv.style.display = 'none';
    }
    if (searchInput) searchInput.value = '';

    // Update config and save - keep current location_type (don't override to 'butik')
    if (!storeConfigs[storeId]) storeConfigs[storeId] = {};
    storeConfigs[storeId].location_type = 'butik';
    storeConfigs[storeId].location_id = locationId;
    storeConfigs[storeId].location_name = locationName;
    storeConfigs[storeId].location_address = locationAddress;

    await saveStoreConfig(storeId);

    // Re-render the config UI to show the selected store properly
    // This ensures the store name replaces the description text
    const fieldsResponse = await fetch(`/api/stores/${storeId}/config-fields`);
    if (!fieldsResponse.ok) return;
    const fieldsData = await fieldsResponse.json();
    if (fieldsData.success && fieldsData.fields) {
        renderStoreConfigUI(storeId, fieldsData.fields, storeConfigs[storeId]);
    }
}

// Save store config to database
async function saveStoreConfig(storeId) {
    try {
        await fetch(`/api/stores/${storeId}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config: storeConfigs[storeId] })
        });
    } catch (error) {
        console.error(`Error saving config for ${storeId}:`, error);
    }
}

// ============================================
// Active Scrape State Persistence
// ============================================

const ACTIVE_SCRAPES_KEY = 'deal_meals_active_scrapes';
let backendRunningScrape = null;
let backendScrapeStatusTimer = null;

function getActiveScrapes() {
    try {
        return JSON.parse(localStorage.getItem(ACTIVE_SCRAPES_KEY) || '{}');
    } catch (e) {
        return {};
    }
}

function setActiveScrape(storeId, state) {
    const scrapes = getActiveScrapes();
    scrapes[storeId] = { ...state, updatedAt: Date.now() };
    localStorage.setItem(ACTIVE_SCRAPES_KEY, JSON.stringify(scrapes));
}

function clearActiveScrape(storeId) {
    const scrapes = getActiveScrapes();
    delete scrapes[storeId];
    localStorage.setItem(ACTIVE_SCRAPES_KEY, JSON.stringify(scrapes));
}

function getStoreIdsFromPage() {
    return Array.from(document.querySelectorAll('[id$="-config-container"]'))
        .map(container => container.id.replace('-config-container', ''))
        .filter(Boolean);
}

function setBackendScrapeLock(status) {
    backendRunningScrape = status?.active ? status : null;
    const runningStore = backendRunningScrape?.store_id;
    const localScrapes = getActiveScrapes();

    for (const storeId of getStoreIdsFromPage()) {
        const btn = document.getElementById(`${storeId}-scrape-btn`);
        const progressDiv = document.getElementById(`${storeId}-progress`);
        const progressBar = document.getElementById(`${storeId}-progress-bar`);
        const progressText = document.getElementById(`${storeId}-progress-text`);
        const localActive = localScrapes[storeId] && !localScrapes[storeId].completed;

        if (!btn) continue;

        if (backendRunningScrape) {
            if (localActive && storeId === runningStore && backendRunningScrape.source === 'manual') {
                continue;
            }

            btn.disabled = true;
            btn.textContent = i18n.scrape_in_progress;
            btn.classList.remove('btn-success', 'btn-danger');
            btn.classList.add('btn-secondary');
            btn.onclick = null;

            if (storeId === runningStore && progressDiv && progressBar && progressText) {
                const progress = backendRunningScrape.progress || 0;
                progressBar.style.width = progress + '%';
                progressBar.setAttribute('aria-valuenow', Math.round(progress));
                progressText.textContent = (backendRunningScrape.message_key
                    ? t(backendRunningScrape.message_key, backendRunningScrape.message_params)
                    : null) || i18n.working;
                progressDiv.style.visibility = 'visible';
            } else if (progressDiv && !localActive) {
                progressDiv.style.visibility = 'hidden';
            }
        } else if (!localActive) {
            resetScrapeButton(btn, storeId);
            if (progressDiv) progressDiv.style.visibility = 'hidden';
        }
    }
}

async function pollBackendScrapeStatus() {
    try {
        const response = await fetch('/api/scrape-status');
        if (!response.ok) return;
        const data = await response.json();
        setBackendScrapeLock(data);
    } catch (e) {
        // Keep the current button state on transient status failures.
    }
}

function restoreActiveScrapes() {
    const scrapes = getActiveScrapes();
    const now = Date.now();
    const maxAge = 15 * 60 * 1000; // 15 minutes max

    for (const [storeId, state] of Object.entries(scrapes)) {
        // Skip stale entries (older than 15 minutes)
        if (now - state.updatedAt > maxAge) {
            clearActiveScrape(storeId);
            continue;
        }

        // Restore UI for active scrape
        const btn = document.getElementById(`${storeId}-scrape-btn`);
        const progressDiv = document.getElementById(`${storeId}-progress`);
        const progressBar = document.getElementById(`${storeId}-progress-bar`);
        const progressText = document.getElementById(`${storeId}-progress-text`);

        if (btn && progressDiv && progressBar && progressText) {
            // Show cancel button instead of disabled fetch button
            btn.disabled = false;
            btn.textContent = i18n['stores.cancel_scrape'];
            btn.classList.remove('btn-success', 'btn-secondary');
            btn.classList.add('btn-danger');
            btn.onclick = (event) => {
                event.stopPropagation();
                cancelScrape(storeId);
            };
            // Disable transition when restoring to prevent animation
            progressBar.style.transition = 'none';
            progressBar.style.width = (state.progress ?? 0) + '%';
            progressBar.setAttribute('aria-valuenow', state.progress ?? 0);
            progressBar.offsetHeight; // Force reflow
            progressBar.style.transition = '';
            progressDiv.style.visibility = 'visible';
            progressText.textContent = (state.message_key ? t(state.message_key, state.message_params) : null) || state.message || i18n.checking_status;

            // Try to reconnect to WebSocket
            reconnectToScrape(storeId);
        }
    }
}

async function reconnectToScrape(store) {
    const btn = document.getElementById(`${store}-scrape-btn`);
    const progressDiv = document.getElementById(`${store}-progress`);
    const progressBar = document.getElementById(`${store}-progress-bar`);
    const progressText = document.getElementById(`${store}-progress-text`);

    // Check server for active scrape status
    try {
        const response = await fetch(`/api/scrape-status/${store}`);
        if (!response.ok) return;
        const data = await response.json();

        if (data.active) {
            if (data.source === 'scheduled') {
                clearActiveScrape(store);
                resetScrapeButton(btn, store);
                setBackendScrapeLock({ ...data, store_id: store });
                return;
            }

            // Scrape is still running - update UI with server-calculated progress
            // Server calculates progress based on elapsed time, so it's accurate even after tab switch
            let currentProgress = data.progress || 0;
            progressBar.style.width = currentProgress + '%';
            progressBar.setAttribute('aria-valuenow', Math.round(currentProgress));
            progressText.textContent = (data.message_key ? t(data.message_key, data.message_params) : null) || data.message || i18n.working;
            setActiveScrape(store, { progress: currentProgress, message_key: data.message_key, message_params: data.message_params });

            // Continue simulating progress locally between polls
            const estTime = data.est_time || 300;
            const targetProgress = 95;
            let simulatedProgress = setInterval(() => {
                if (currentProgress < targetProgress) {
                    // Increment smoothly towards target (about 0.5% per 500ms at default rate)
                    currentProgress += (targetProgress / (estTime * 2));
                    currentProgress = Math.min(currentProgress, targetProgress);
                    progressBar.style.width = currentProgress + '%';
                    progressBar.setAttribute('aria-valuenow', Math.round(currentProgress));
                }
            }, 500);

            // Poll for updates every 3 seconds
            let pollFailCount = 0;
            const pollInterval = setInterval(async () => {
                try {
                    const pollResponse = await fetch(`/api/scrape-status/${store}`);
                    if (!pollResponse.ok) {
                        if (++pollFailCount >= 5) {
                            // 5 consecutive failures (15s) — give up
                            if (simulatedProgress) {
                                clearInterval(simulatedProgress);
                                simulatedProgress = null;
                            }
                            clearInterval(pollInterval);
                            progressText.innerHTML = `
                                <span class="text-warning">${i18n.could_not_get_status}</span>
                                <br><a href="#" data-action="resetScrapeUI" data-arg="${store}" class="small">${i18n.reset}</a>
                            `;
                        }
                        return;
                    }
                    pollFailCount = 0;
                    const pollData = await pollResponse.json();

                    if (pollData.active) {
                        // Use server's time-based progress (more accurate)
                        currentProgress = pollData.progress || currentProgress;
                        progressBar.style.width = currentProgress + '%';
                        progressBar.setAttribute('aria-valuenow', Math.round(currentProgress));
                        progressText.textContent = (pollData.message_key ? t(pollData.message_key, pollData.message_params) : null) || pollData.message || i18n.working;
                        setActiveScrape(store, { progress: currentProgress, message_key: pollData.message_key, message_params: pollData.message_params });
                    } else {
                        // Stop local simulation
                        if (simulatedProgress) {
                            clearInterval(simulatedProgress);
                            simulatedProgress = null;
                        }
                        // Scrape finished
                        clearInterval(pollInterval);
                        progressDiv.style.visibility = 'hidden';
                        resetScrapeButton(btn, store);
                        clearActiveScrape(store);
                        pollBackendScrapeStatus();

                        // Show success message with count if available
                        const storeName = store.charAt(0).toUpperCase() + store.slice(1);
                        const displayName = pollData.location_name || storeName;
                        const countText = (pollData.count !== undefined && pollData.count !== null)
                            ? fetchedProductsText(pollData, displayName)
                            : t('scrape_complete', { store: displayName });
                        const autoClose = trackScrapeCompletion();
                        Swal.fire({
                            icon: 'success',
                            title: i18n.success,
                            text: countText,
                            confirmButtonText: i18n.ok,
                            confirmButtonColor: '#28a745',
                            timer: autoClose ? 8000 : undefined,
                            timerProgressBar: autoClose
                        });
                    }
                } catch (e) {
                    // Stop local simulation on error
                    if (simulatedProgress) {
                        clearInterval(simulatedProgress);
                        simulatedProgress = null;
                    }
                    clearInterval(pollInterval);
                    progressText.innerHTML = `
                        <span class="text-warning">${i18n.could_not_get_status}</span>
                        <br><a href="#" data-action="resetScrapeUI" data-arg="${store}" class="small">${i18n.reset}</a>
                    `;
                }
            }, 3000);
        } else {
            // Scrape not running - clean up
            progressDiv.style.visibility = 'hidden';
            resetScrapeButton(btn, store);
            clearActiveScrape(store);
            pollBackendScrapeStatus();

            // If scrape just completed (with count), show success message
            if (data.completed && data.count !== undefined) {
                const storeName = store.charAt(0).toUpperCase() + store.slice(1);
                const displayName = data.location_name || storeName;
                const autoClose2 = trackScrapeCompletion();
                Swal.fire({
                    icon: 'success',
                    title: i18n.success,
                    text: fetchedProductsText(data, displayName),
                    confirmButtonText: i18n.ok,
                    confirmButtonColor: '#28a745',
                    timer: autoClose2 ? 8000 : undefined,
                    timerProgressBar: autoClose2
                });
            }
        }
    } catch (e) {
        // API error - show manual reset option
        progressText.innerHTML = `
            <span class="text-warning">${i18n.could_not_connect}</span>
            <br><a href="#" data-action="resetScrapeUI" data-arg="${store}" class="small">${i18n.reset}</a>
        `;
    }
}

function resetScrapeUI(store) {
    const btn = document.getElementById(`${store}-scrape-btn`);
    const progressDiv = document.getElementById(`${store}-progress`);

    if (progressDiv) progressDiv.style.visibility = 'hidden';
    if (btn) resetScrapeButton(btn, store);
    clearActiveScrape(store);
}

// Check if any scrape is currently running
function isAnyScrapeRunning() {
    const scrapes = getActiveScrapes();
    const now = Date.now();
    const maxAge = 15 * 60 * 1000; // 15 minutes max

    for (const [storeId, state] of Object.entries(scrapes)) {
        // Skip stale entries
        if (now - state.updatedAt > maxAge) continue;
        // Skip entries we already know are completed
        if (state.completed) continue;
        // Found an active scrape
        return storeId;
    }
    return null;
}

async function resolveRunningScrape() {
    try {
        const response = await fetch('/api/scrape-status');
        if (response.ok) {
            const data = await response.json();
            setBackendScrapeLock(data);
            if (data.active) {
                return data.store_id || 'store';
            }
        }
    } catch (e) {
        // Fall back to local state below.
    }

    const runningStore = isAnyScrapeRunning();
    if (!runningStore) return null;

    try {
        const response = await fetch(`/api/scrape-status/${runningStore}`);
        if (!response.ok) {
            return runningStore;
        }

        const data = await response.json();
        if (data.active) {
            return runningStore;
        }

        clearActiveScrape(runningStore);
        return null;
    } catch (e) {
        // On network/API failure, keep the safer behavior and assume it may still run
        return runningStore;
    }
}

// Reset scrape button to default state
function resetScrapeButton(btn, store) {
    btn.disabled = false;
    btn.textContent = i18n.fetch_offers;
    btn.classList.remove('btn-danger', 'btn-secondary');
    btn.classList.add('btn-success');
    btn.onclick = null;
}

// Cancel a running scrape
async function cancelScrape(store) {
    const btn = document.getElementById(`${store}-scrape-btn`);
    if (btn) {
        btn.disabled = true;
        btn.textContent = i18n['stores.scrape_cancelling'];
    }

    try {
        const response = await fetch(`/api/scrape/${store}/cancel`, {
            method: 'POST',
            headers: {
                'Origin': window.location.origin
            }
        });
        if (!response.ok) {
            const data = await response.json();
            console.warn('Cancel failed:', data);
        }
        // The WebSocket will receive the cancelled status and reset the UI
    } catch (e) {
        // If cancel request fails, reset button anyway
        if (btn) resetScrapeButton(btn, store);
    }
}

// Scrape store - using SweetAlert2 for popups
async function scrapeStore(store) {
    const btn = document.getElementById(`${store}-scrape-btn`);
    const progressDiv = document.getElementById(`${store}-progress`);
    const progressBar = document.getElementById(`${store}-progress-bar`);
    const progressText = document.getElementById(`${store}-progress-text`);

    if (!btn || !progressDiv || !progressBar || !progressText) {
        Swal.fire({
            icon: 'error',
            title: i18n.error,
            text: i18n.ui_missing,
            confirmButtonColor: '#dc3545'
        });
        return;
    }

    // Check if another scrape is already running
    const runningScrape = await resolveRunningScrape();
    if (runningScrape) {
        const runningStoreName = formatStoreName(runningScrape);
        Swal.fire({
            icon: 'warning',
            title: i18n.scrape_in_progress,
            text: `${runningStoreName} ${i18n.scrape_wait}`,
            confirmButtonText: i18n.ok,
            confirmButtonColor: '#ffc107'
        });
        return;
    }

    // Switch button to cancel mode
    btn.disabled = false;
    btn.textContent = i18n['stores.cancel_scrape'];
    btn.classList.remove('btn-success', 'btn-secondary');
    btn.classList.add('btn-danger');
    btn.onclick = (event) => {
        event.stopPropagation();
        cancelScrape(store);
    };
    // Temporarily disable transition to prevent animation from previous value to 0%
    progressBar.style.transition = 'none';
    progressBar.style.width = '0%';
    progressBar.setAttribute('aria-valuenow', 0);
    // Force reflow to apply the width change immediately
    progressBar.offsetHeight;
    // Re-enable transition for smooth progress updates
    progressBar.style.transition = '';
    progressText.textContent = i18n.starting;
    progressDiv.style.visibility = 'visible';

    // Save config before starting scrape to ensure latest values are persisted
    const checkedLocationType = document.querySelector(`input[name="${store}-location_type"]:checked`);
    if (!storeConfigs[store]) storeConfigs[store] = {};
    if (checkedLocationType?.value) {
        storeConfigs[store].location_type = checkedLocationType.value;
    }
    await saveStoreConfig(store);

    // Save initial state to localStorage
    setActiveScrape(store, { progress: 0, message: i18n.starting });
    setBackendScrapeLock({
        active: true,
        store_id: store,
        progress: 0,
        message_key: 'ws.fetching_offers',
        message_params: { store: formatStoreName(store) },
        source: 'manual'
    });

    // Simulated progress timer
    let simulatedProgress = null;
    let currentProgress = 0;

    // Connect to WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/scrape/${store}`);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        // Start simulated progress if requested
        if (data.simulate_progress && !simulatedProgress) {
            const maxTime = data.max_time || 120;
            const startProgress = 0;
            const targetProgress = 95;  // Stop at 95% - jumps to 100% when actually complete
            currentProgress = startProgress;
            progressBar.style.width = currentProgress + '%';
            progressBar.setAttribute('aria-valuenow', Math.round(currentProgress));

            // Calculate increment: go from 0% to 95% over maxTime seconds
            const totalIncrements = maxTime * 2; // Update every 500ms
            const increment = (targetProgress - startProgress) / totalIncrements;

            simulatedProgress = setInterval(() => {
                if (currentProgress < targetProgress) {
                    currentProgress += increment;
                    progressBar.style.width = currentProgress + '%';
                    progressBar.setAttribute('aria-valuenow', Math.round(currentProgress));
                }
            }, 500);
        }

        // Real progress from server (not the simulate_progress message)
        if (data.progress !== undefined && !data.simulate_progress) {
            if (simulatedProgress) {
                clearInterval(simulatedProgress);
                simulatedProgress = null;
            }
            currentProgress = data.progress;
            progressBar.style.width = data.progress + '%';
            progressBar.setAttribute('aria-valuenow', Math.round(data.progress));
        }

        if (data.message_key || data.message) {
            progressText.textContent = (data.message_key ? t(data.message_key, data.message_params) : null) || data.message;
            // Update localStorage with current state
            setActiveScrape(store, { progress: currentProgress, message_key: data.message_key, message_params: data.message_params });
        }

        if (data.status === 'complete') {
            if (simulatedProgress) {
                clearInterval(simulatedProgress);
                simulatedProgress = null;
            }
            // Clear from localStorage
            clearActiveScrape(store);

            // Clear cached recipes so home page resets to initial state
            // (user will need to click "Weekly deal recipes" to load fresh results)
            sessionStorage.removeItem('recipeSuggestions');
            sessionStorage.removeItem('recipeBalance');

            setTimeout(() => {
                resetScrapeButton(btn, store);
                progressDiv.style.visibility = 'hidden';
                pollBackendScrapeStatus();

                // Success popup with SweetAlert2
                // Use location_name from server if available, otherwise fall back to store name
                const storeName = store.charAt(0).toUpperCase() + store.slice(1);
                const displayName = data.location_name || storeName;
                Swal.fire({
                    icon: 'success',
                    title: i18n.success,
                    text: fetchedProductsText(data, displayName),
                    confirmButtonText: i18n.ok,
                    confirmButtonColor: '#28a745',
                    timer: 4000,
                    timerProgressBar: true
                });
            }, 1000);
        }

        if (data.status === 'error') {
            if (simulatedProgress) {
                clearInterval(simulatedProgress);
                simulatedProgress = null;
            }
            // Clear from localStorage
            clearActiveScrape(store);

            resetScrapeButton(btn, store);
            progressDiv.style.visibility = 'hidden';
            pollBackendScrapeStatus();

            const isStoreConfigError = isStoreConfigErrorKey(data.message_key);
            Swal.fire({
                icon: isStoreConfigError ? 'warning' : 'error',
                title: isStoreConfigError ? i18n['stores.store_config_incomplete_title'] : i18n.error_occurred,
                text: (data.message_key ? t(data.message_key, data.message_params) : null) || data.message,
                confirmButtonColor: isStoreConfigError ? '#ffc107' : '#dc3545'
            });
        }

        if (data.status === 'cancelled') {
            if (simulatedProgress) {
                clearInterval(simulatedProgress);
                simulatedProgress = null;
            }
            clearActiveScrape(store);
            resetScrapeButton(btn, store);
            progressDiv.style.visibility = 'hidden';
            pollBackendScrapeStatus();

            Swal.fire({
                icon: 'info',
                title: i18n['stores.scrape_cancelled'],
                confirmButtonText: i18n.ok,
                confirmButtonColor: '#6c757d',
                timer: 3000,
                timerProgressBar: true
            });
        }
    };

    ws.onerror = () => {
        // WebSocket error - could be tab switch, network issue, etc.
        // DON'T clear localStorage or show error - scrape may still be running on server
        // ws.onclose will fire after this and handle reconnection
        if (simulatedProgress) {
            clearInterval(simulatedProgress);
            simulatedProgress = null;
        }
    };

    ws.onclose = (event) => {
        // WebSocket closed - could be normal close after complete, or disconnect
        // If we already handled 'complete' or 'error' status, this is fine
        // If not, the scrape might still be running - don't clear state
        if (simulatedProgress) {
            clearInterval(simulatedProgress);
            simulatedProgress = null;
        }
        // Only reconnect if a scrape was active (btn disabled + progress visible)
        if (btn.disabled && progressDiv.style.visibility !== 'hidden') {
            // Delay reconnect to avoid hammering a restarting server
            setTimeout(() => reconnectToScrape(store), 3000);
        }
    };
}

let completedScrapes = 0;

function trackScrapeCompletion() {
    completedScrapes++;
    fetch('/api/ui-preferences', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ completed_scrapes: completedScrapes })
    }).catch(() => {});
    return completedScrapes > 3;
}

// Check status on page load - for all stores dynamically
document.addEventListener('DOMContentLoaded', () => {
    // Load completed scrapes count from DB
    fetch('/api/ui-preferences').then(r => r.json()).then(data => {
        if (data.success) completedScrapes = data.preferences.completed_scrapes || 0;
    }).catch(() => {});

    // Restore any active scrapes first (before loading configs)
    restoreActiveScrapes();
    pollBackendScrapeStatus();
    if (!backendScrapeStatusTimer) {
        backendScrapeStatusTimer = setInterval(pollBackendScrapeStatus, 5000);
    }

    // Find all store config containers on the page and load their config
    document.querySelectorAll('[id$="-config-container"]').forEach(container => {
        const storeId = container.id.replace('-config-container', '');
        if (storeId) {
            checkStoreStatus(storeId);
        }
    });
});

// ============================================
// Store Scheduling Functions
// ============================================

let loggedInStores = [];

// Initialize scheduling fields on page load
document.addEventListener('DOMContentLoaded', function() {
    initStoreScheduleFields();
    loadLoggedInStores();
    loadAllStoreSchedules();
});

function initStoreScheduleFields() {
    // Populate day of month (1-28)
    const dayOfMonthSelect = document.getElementById('store-schedule-day-of-month');
    for (let i = 1; i <= 28; i++) {
        const option = document.createElement('option');
        option.value = i;
        option.textContent = i;
        dayOfMonthSelect.appendChild(option);
    }

    // Populate hours (0-23 in 24h format)
    const hourSelect = document.getElementById('store-schedule-hour');
    for (let i = 0; i <= 23; i++) {
        const option = document.createElement('option');
        option.value = i;
        option.textContent = i.toString().padStart(2, '0') + ':00';
        hourSelect.appendChild(option);
    }
    // Default to 06:00
    hourSelect.value = '6';
}

async function loadLoggedInStores() {
    // Dynamically get stores from the page (from config containers)
    const storeIds = [];
    document.querySelectorAll('[id$="-config-container"]').forEach(container => {
        const storeId = container.id.replace('-config-container', '');
        if (storeId) storeIds.push(storeId);
    });

    const select = document.getElementById('store-schedule-select');
    const previousSelection = select.value; // Preserve current selection
    select.innerHTML = '<option value="">' + i18n.select_store + '</option>';

    loggedInStores = [];

    for (const storeId of storeIds) {
        try {
            const response = await fetch(`/api/store-config?store=${storeId}`);
            if (!response.ok) continue;
            const data = await response.json();

            loggedInStores.push({
                id: storeId,
                name: formatStoreName(storeId),
                location_type: data.location_type,
                location_name: data.location_name,
                ehandel_store_name: data.ehandel_store_name
            });
        } catch (error) {
            console.error(`Error checking ${storeId} status:`, error);
        }
    }

    // Populate dropdown with available stores
    // Format: "Store - E-handel - [ehandel store]" or "Store - [butik name]"
    for (const store of loggedInStores) {
        const option = document.createElement('option');
        option.value = store.id;
        let label = store.name;
        if (store.location_type === 'ehandel') {
            // E-handel: show "Store - E-handel" + optional ehandel store name
            label += ' - ' + i18n.ecommerce;
            if (store.ehandel_store_name) {
                label += ' - ' + store.ehandel_store_name;
            }
        } else if (store.location_name) {
            // Butik: show "Store - butik name" (no "Butik" label needed)
            label += ' - ' + store.location_name;
        }
        option.textContent = label;
        select.appendChild(option);
    }

    if (loggedInStores.length === 0) {
        select.innerHTML = '<option value="">' + i18n.no_store_available + '</option>';
    }

    // Restore previous selection if still valid
    if (previousSelection) {
        select.value = previousSelection;
    }
}

function updateStoreScheduleFields() {
    const frequency = document.getElementById('store-schedule-frequency').value;
    const dayOfWeekContainer = document.getElementById('store-day-of-week-container');
    const dayOfMonthContainer = document.getElementById('store-day-of-month-container');
    const hourContainer = document.getElementById('store-hour-container');
    const saveBtn = document.getElementById('save-store-schedule-btn');
    const storeSelect = document.getElementById('store-schedule-select');

    // Hide all optional fields first
    dayOfWeekContainer.style.display = 'none';
    dayOfMonthContainer.style.display = 'none';
    hourContainer.style.display = 'none';

    if (frequency === '') {
        saveBtn.disabled = !storeSelect.value;
        return;
    }

    // Show hour for all frequencies
    hourContainer.style.display = 'block';

    if (frequency === 'weekly') {
        dayOfWeekContainer.style.display = 'block';
    } else if (frequency === 'monthly') {
        dayOfMonthContainer.style.display = 'block';
    }

    saveBtn.disabled = !storeSelect.value;
}

async function loadStoreSchedule() {
    const storeId = document.getElementById('store-schedule-select').value;
    const scheduleInfo = document.getElementById('store-schedule-info');

    // Enable/disable save button
    document.getElementById('save-store-schedule-btn').disabled = !storeId;

    if (!storeId) {
        // Reset fields
        document.getElementById('store-schedule-frequency').value = '';
        updateStoreScheduleFields();
        scheduleInfo.style.display = 'none';
        return;
    }

    try {
        const response = await fetch(`/api/store-schedules/${storeId}`);
        if (!response.ok) return;
        const data = await response.json();

        if (data.success && data.schedule) {
            const schedule = data.schedule;

            // Populate fields
            document.getElementById('store-schedule-frequency').value = schedule.frequency;
            updateStoreScheduleFields();

            if (schedule.frequency === 'weekly' && schedule.day_of_week !== null) {
                document.getElementById('store-schedule-day-of-week').value = schedule.day_of_week;
            }
            if (schedule.frequency === 'monthly' && schedule.day_of_month !== null) {
                document.getElementById('store-schedule-day-of-month').value = schedule.day_of_month;
            }
            document.getElementById('store-schedule-hour').value = schedule.hour;

            // Show schedule info
            scheduleInfo.style.display = 'block';
            document.getElementById('store-schedule-description').textContent = formatStoreScheduleDescription(schedule);

            let runInfo = '';
            const runInfoEl = document.getElementById('store-schedule-run-info');
            if (schedule.last_run_failed) {
                runInfo = i18n.last_run_failed;
                runInfoEl.textContent = runInfo;
            } else {
                if (schedule.last_run_at) {
                    runInfo += i18n.last_completed + ': ' + new Date(schedule.last_run_at).toLocaleString(STORE_LOCALE) + ' | ';
                }
                if (schedule.next_run_at) {
                    runInfo += i18n.next_run + ': ' + new Date(schedule.next_run_at).toLocaleString(STORE_LOCALE);
                }
                runInfoEl.textContent = runInfo;
            }
        } else {
            // No schedule - reset fields
            document.getElementById('store-schedule-frequency').value = '';
            updateStoreScheduleFields();
            scheduleInfo.style.display = 'none';
        }
    } catch (error) {
        console.error('Error loading store schedule:', error);
    }
}

function formatStoreScheduleDescription(schedule) {
    const hour = schedule.hour.toString().padStart(2, '0') + ':00';

    if (schedule.frequency === 'daily') {
        return t('every_day_at', { hour: hour });
    } else if (schedule.frequency === 'weekly') {
        return t('every_weekday_at', { day: i18n.days[schedule.day_of_week], hour: hour });
    } else if (schedule.frequency === 'monthly') {
        return t('monthly_at', { day: schedule.day_of_month, hour: hour });
    }
    return i18n.unknown_frequency;
}

async function saveStoreSchedule() {
    const storeId = document.getElementById('store-schedule-select').value;
    const frequency = document.getElementById('store-schedule-frequency').value;

    if (!storeId) {
        Swal.fire({
            icon: 'warning',
            title: i18n.select_store,
            text: i18n.select_store_first
        });
        return;
    }

    // If frequency is empty, delete the schedule
    if (!frequency) {
        await deleteStoreSchedule();
        return;
    }

    const hour = parseInt(document.getElementById('store-schedule-hour').value);
    let dayOfWeek = null;
    let dayOfMonth = null;

    if (frequency === 'weekly') {
        dayOfWeek = parseInt(document.getElementById('store-schedule-day-of-week').value);
    } else if (frequency === 'monthly') {
        dayOfMonth = parseInt(document.getElementById('store-schedule-day-of-month').value);
    }

    try {
        const response = await fetch(`/api/store-schedules/${storeId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                frequency: frequency,
                hour: hour,
                day_of_week: dayOfWeek,
                day_of_month: dayOfMonth,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
            })
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            const isHourConflict = data.message_key === 'scheduler.store_hour_conflict';
            const isStoreConfigError = isStoreConfigErrorKey(data.message_key);
            Swal.fire({
                icon: (isHourConflict || isStoreConfigError) ? 'warning' : 'error',
                title: isHourConflict
                    ? i18n['scheduler.store_hour_conflict_title']
                    : isStoreConfigError
                        ? i18n['stores.store_config_incomplete_title']
                        : i18n.error,
                text: data.message_key ? t(data.message_key, data.message_params) : i18n.could_not_save
            });
            return;
        }

        const data = await response.json();

        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: i18n.schedule_saved,
                text: data.message_key ? t(data.message_key, data.message_params) : '',
                timer: 2000,
                showConfirmButton: false
            });
            // Reload to show updated info
            loadStoreSchedule();
            loadAllStoreSchedules();
        } else {
            Swal.fire({
                icon: 'error',
                title: i18n.error,
                text: data.message_key ? t(data.message_key, data.message_params) : ''
            });
        }
    } catch (error) {
        Swal.fire({
            icon: 'error',
            title: i18n.error,
            text: i18n.could_not_save + ': ' + error.message
        });
    }
}

async function deleteStoreSchedule() {
    const storeId = document.getElementById('store-schedule-select').value;
    if (!storeId) return;
    await deleteStoreScheduleById(storeId);
}

async function deleteStoreScheduleById(storeId) {
    try {
        const response = await fetch(`/api/store-schedules/${storeId}`, {
            method: 'DELETE'
        });
        if (!response.ok) {
            Swal.fire({ icon: 'error', title: i18n.error });
            return;
        }

        const data = await response.json();

        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: i18n.schedule_removed,
                timer: 1500,
                showConfirmButton: false
            });
            // Reset form if this store is currently selected
            const select = document.getElementById('store-schedule-select');
            if (select.value === storeId) {
                document.getElementById('store-schedule-frequency').value = '';
                updateStoreScheduleFields();
                document.getElementById('store-schedule-info').style.display = 'none';
            }
            loadAllStoreSchedules();
        } else {
            Swal.fire({
                icon: 'error',
                title: i18n.error,
                text: data.message_key ? t(data.message_key, data.message_params) : ''
            });
        }
    } catch (error) {
        Swal.fire({
            icon: 'error',
            title: i18n.error,
            text: i18n.could_not_delete + ': ' + error.message
        });
    }
}

async function loadAllStoreSchedules() {
    const container = document.getElementById('store-all-schedules-list');

    try {
        const response = await fetch('/api/store-schedules');
        if (!response.ok) return;
        const data = await response.json();

        if (!data.success || !data.schedules || data.schedules.length === 0) {
            container.innerHTML = '<p class="text-muted small mb-0"><i class="bi bi-info-circle me-1"></i>' + i18n.no_schedules + '</p>';
            return;
        }

        // Build table
        let html = `
            <table class="table table-sm table-hover mb-0 schedule-table">
                <thead>
                    <tr>
                        <th>${i18n.store}</th>
                        <th>${i18n.schedule}</th>
                        <th>${i18n.next_run}</th>
                        <th>${i18n.last_completed}</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
        `;

        // Sort by next_run_at
        const sortedSchedules = [...data.schedules].sort((a, b) => {
            if (!a.next_run_at) return 1;
            if (!b.next_run_at) return -1;
            return new Date(a.next_run_at) - new Date(b.next_run_at);
        });

        for (const schedule of sortedSchedules) {
            // Build store label: "Store - E-handel - [ehandel store]" or "Store - [butik name]"
            let storeName = formatStoreName(schedule.store_id);
            if (schedule.location_type === 'ehandel') {
                // E-handel: show "Store - E-handel" + optional ehandel store name
                storeName += ' - ' + i18n.ecommerce;
                if (schedule.ehandel_store_name) {
                    storeName += ' - ' + schedule.ehandel_store_name;
                }
            } else if (schedule.location_name) {
                // Butik: show "Store - butik name" (no "Butik" label needed)
                storeName += ' - ' + schedule.location_name;
            }

            const description = formatStoreScheduleDescription(schedule);
            const nextRun = schedule.next_run_at
                ? new Date(schedule.next_run_at).toLocaleString(STORE_LOCALE)
                : '-';
            const lastRun = schedule.last_run_failed
                ? i18n.last_run_failed
                : schedule.last_run_at
                    ? new Date(schedule.last_run_at).toLocaleString(STORE_LOCALE)
                    : i18n.never;

            html += `
                <tr style="cursor: pointer;" data-action="selectStoreSchedule" data-arg="${schedule.store_id}">
                    <td><strong>${storeName}</strong></td>
                    <td>${description}</td>
                    <td><small>${nextRun}</small></td>
                    <td><small class="text-muted">${lastRun}</small></td>
                    <td><button class="btn btn-sm btn-outline-danger border-0" data-action="deleteStoreScheduleById" data-arg="${schedule.store_id}" data-stop-prop="true" title="${i18n.remove_schedule}"><i class="bi bi-x-lg"></i></button></td>
                </tr>
            `;
        }

        html += '</tbody></table>';
        container.innerHTML = html;

    } catch (error) {
        container.innerHTML = '<p class="text-danger small mb-0">' + i18n.could_not_load + '</p>';
        console.error('Error loading store schedules:', error);
    }
}

function selectStoreSchedule(storeId) {
    // Select the store in dropdown and load its schedule
    document.getElementById('store-schedule-select').value = storeId;
    loadStoreSchedule();
}

// ============================================
// Event delegation
// ============================================
document.addEventListener('click', function(e) {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    if (el.dataset.stopProp === 'true') e.stopPropagation();
    if (el.tagName === 'A') e.preventDefault();
    switch (el.dataset.action) {
        case 'scrapeStore': scrapeStore(el.dataset.arg); break;
        case 'saveStoreSchedule': saveStoreSchedule(); break;
        case 'deleteStoreSchedule': deleteStoreSchedule(); break;
        case 'searchStoreLocations': searchStoreLocations(el.dataset.store); break;
        case 'resetScrapeUI': resetScrapeUI(el.dataset.arg); break;
        case 'selectStoreSchedule': selectStoreSchedule(el.dataset.arg); break;
        case 'deleteStoreScheduleById': e.stopPropagation(); deleteStoreScheduleById(el.dataset.arg); break;
    }
});

document.addEventListener('change', function(e) {
    const el = e.target;
    const action = el.dataset.change;
    if (!action) return;
    switch (action) {
        case 'loadStoreSchedule': loadStoreSchedule(); break;
        case 'updateStoreScheduleFields': updateStoreScheduleFields(); break;
        case 'updateStoreConfigField':
            updateStoreConfigField(el.dataset.store, el.dataset.field,
                el.dataset.useValue === 'true' ? el.value : (el.dataset.value || el.value));
            break;
        case 'selectAsyncOption': selectAsyncOption(el.dataset.store, el.dataset.field, el); break;
    }
});

document.addEventListener('focus', function(e) {
    const el = e.target;
    if (el.dataset.focus === 'loadLoggedInStores') {
        loadLoggedInStores();
    }
}, true);

document.addEventListener('keyup', function(e) {
    const el = e.target.closest('[data-keyup]');
    if (el && el.dataset.keyup === 'handleStoreSearchKeyup') {
        handleStoreSearchKeyup(e, el.dataset.store);
    }
});
