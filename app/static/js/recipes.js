// Recipes page behavior. Jinja-provided i18n and page data are bootstrapped in recipes.html.
const i18n = window.DealMealsRecipesI18n || {};
const pageConfig = window.DealMealsRecipesPage || {};
const RECIPE_LOCALE = pageConfig.locale || undefined;

const modeNames = { incremental: 'mode_incremental', full: 'mode_full', test: 'mode_test' };

// Scraper name overrides (English code names → i18n display names)
const scraperNameOverrides = {
    'My Recipes': () => i18n.myrecipes_scraper_name,
};

const t = window.DealMeals.createTranslator(i18n, {
    transformParam: (k, v) => {
        let translated = v;
        if (k === 'mode' && modeNames[v]) translated = i18n[modeNames[v]] || v;
        if (k === 'name' && scraperNameOverrides[v]) translated = scraperNameOverrides[v]();
        if (typeof translated === 'string' && i18n[translated]) translated = i18n[translated];
        return translated;
    }
});

function formatDuration(seconds) {
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    const remainMin = minutes % 60;
    return remainMin > 0 ? `${hours}h ${remainMin} min` : `${hours}h`;
}

let scrapers = [];
let pollingInterval = null;
let currentScraperId = null;
let completedScrapes = 0;
let runAllQueue = null;  // { scrapers: [], index: 0, totalNew: 0 } when running all active
let imageDownloadRunning = Boolean(pageConfig.image_download_running);
let imageDownloadLockInterval = null;
let imageDownloadPollDelay = null;
let imageAutoDownloadEnabled = false;
let runButtonDefaultHtml = '';
let runButtonRecipeLocked = false;
let postRecipeImageLockInterval = null;
let postRecipeImageLockTimeout = null;
let pendingAutoImageCompletion = null;
let pendingAutoImageStarted = false;
let pendingAutoImageFallbackTimeout = null;
const IMAGE_DOWNLOAD_RUNNING_POLL_MS = 1000;
const POST_RECIPE_IMAGE_LOCK_WATCH_MS = 30000;
const AUTO_IMAGE_FALLBACK_POPUP_MS = 5000;

// Load scrapers on page load
document.addEventListener('DOMContentLoaded', function() {
    initScheduleFields();
    initRecipeRunButtonState();
    refreshImageAutoDownloadPreference();
    refreshImageDownloadLock();
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            stopImageDownloadLockPolling();
            stopPostRecipeImageLockWatch();
        } else {
            refreshImageAutoDownloadPreference();
            refreshImageDownloadLock();
        }
    });

    // Load UI preferences first (for onboarding state), then scrapers
    fetch('/api/ui-preferences').then(r => r.json()).then(data => {
        if (data.success) completedScrapes = data.preferences.completed_scrapes || 0;
    }).catch(() => {}).finally(() => {
        loadScrapers().then(() => {
            checkRunningScrapers();
            loadAllSchedules();
        });
    });
});

function initRecipeRunButtonState() {
    const btn = document.getElementById('run-scraper-btn');
    if (btn && !runButtonDefaultHtml) {
        const label = btn.dataset.defaultLabel || i18n.fetch_recipes || 'Fetch recipes';
        runButtonDefaultHtml = `<i class="bi bi-play-fill"></i> ${escapeHtml(label)}`;
    }
    updateRecipeRunButtonState();
}

function setRecipeRunButtonLocked(locked) {
    runButtonRecipeLocked = locked;
    updateRecipeRunButtonState();
}

function updateRecipeRunButtonState() {
    const btn = document.getElementById('run-scraper-btn');
    if (!btn) return;
    if (!runButtonDefaultHtml) {
        const label = btn.dataset.defaultLabel || i18n.fetch_recipes || 'Fetch recipes';
        runButtonDefaultHtml = `<i class="bi bi-play-fill"></i> ${escapeHtml(label)}`;
    }

    if (imageDownloadRunning) {
        const label = i18n.image_download_in_progress_button || t('recipes.wait_for_image_download');
        btn.disabled = true;
        btn.classList.remove('btn-info');
        btn.classList.add('btn-primary', 'image-download-lock');
        btn.innerHTML = escapeHtml(label);
        btn.title = t('recipes.wait_for_image_download');
        btn.setAttribute('aria-disabled', 'true');
        return;
    }

    btn.disabled = runButtonRecipeLocked;
    btn.classList.remove('btn-info', 'image-download-lock');
    btn.classList.add('btn-primary');
    btn.innerHTML = runButtonDefaultHtml;
    btn.title = '';
    if (!runButtonRecipeLocked) btn.removeAttribute('aria-disabled');
}

function translateImageDownloadStatus(data) {
    const key = data?.message_key;
    if (key) {
        const message = t(key, data.message_params || {});
        if (message && message !== key) return message;
    }
    return i18n.images_downloading || i18n.image_download_in_progress_button || '';
}

function setProgressCancelAction(action) {
    const cancelBtn = document.getElementById('cancel-scraper-btn');
    if (!cancelBtn) return;

    cancelBtn.dataset.action = action;
    cancelBtn.disabled = false;
    cancelBtn.innerHTML = `<i class="bi bi-x-circle me-1"></i>${escapeHtml(i18n.cancel || 'Cancel')}`;
}

function setProgressPanelRecipeMode() {
    const progressWrap = document.getElementById('image-download-progress-container');
    if (progressWrap) {
        progressWrap.classList.add('invisible');
    }
    const progressBar = document.getElementById('recipe-image-download-progress-bar');
    if (progressBar) {
        progressBar.style.width = '0%';
        progressBar.setAttribute('aria-valuenow', '0');
    }
    setProgressCancelAction('cancelScraper');
}

function setPendingAutoImageCompletion(pending) {
    pendingAutoImageCompletion = pending;
    pendingAutoImageStarted = false;

    if (pendingAutoImageFallbackTimeout) {
        clearTimeout(pendingAutoImageFallbackTimeout);
    }

    pendingAutoImageFallbackTimeout = setTimeout(() => {
        if (pendingAutoImageCompletion && !pendingAutoImageStarted) {
            finishPendingAutoImageCompletion();
        }
    }, AUTO_IMAGE_FALLBACK_POPUP_MS);
}

function clearPendingAutoImageFallback() {
    if (pendingAutoImageFallbackTimeout) {
        clearTimeout(pendingAutoImageFallbackTimeout);
        pendingAutoImageFallbackTimeout = null;
    }
}

function showRunAllCompletePopup({ count, summaryHtml, autoClose }) {
    Swal.fire({
        icon: 'success',
        title: t('all_complete', { count: count }),
        html: summaryHtml,
        confirmButtonText: i18n.ok,
        heightAuto: false,
        scrollbarPadding: false,
        timer: autoClose ? 8000 : undefined,
        timerProgressBar: autoClose,
        didOpen: () => {
            document.getElementById('progress-container').classList.remove('active');
            setRecipeRunButtonLocked(false);
        },
        didClose: () => {
            loadScrapers();
            loadAllSchedules();
        }
    });
}

function finishPendingAutoImageCompletion() {
    const pending = pendingAutoImageCompletion;
    if (!pending) return;

    pendingAutoImageCompletion = null;
    pendingAutoImageStarted = false;
    clearPendingAutoImageFallback();
    stopPostRecipeImageLockWatch();

    document.getElementById('progress-container')?.classList.remove('active');
    setProgressPanelRecipeMode();
    setRecipeRunButtonLocked(false);

    if (pending.type === 'single') {
        showDetailedResult(pending.data, {
            didOpen: () => {
                document.getElementById('progress-container').classList.remove('active');
                setRecipeRunButtonLocked(false);
            },
            didClose: () => {
                loadScrapers();
                loadAllSchedules();
            }
        });
        return;
    }

    if (pending.type === 'runAll') {
        showRunAllCompletePopup(pending);
    }
}

function updateRecipeImageDownloadStatus(data = null, options = {}) {
    const progressContainer = document.getElementById('progress-container');
    if (!progressContainer) return;

    const running = data ? Boolean(data.running) : imageDownloadRunning;
    if (!running) {
        if (pendingAutoImageCompletion && pendingAutoImageStarted) {
            finishPendingAutoImageCompletion();
            return;
        }
        if (options.keepProgressWhenIdle) return;
        const recipeProgressActive = Boolean(currentScraperId || pollingInterval || runAllQueue || runButtonRecipeLocked);
        if (!recipeProgressActive) {
            progressContainer.classList.remove('active');
            setProgressPanelRecipeMode();
        }
        return;
    }

    const resultContainer = document.getElementById('result-container');
    const title = document.getElementById('progress-title');
    const progressText = document.getElementById('progress-message');
    const progressWrap = document.getElementById('image-download-progress-container');
    const progressBar = document.getElementById('recipe-image-download-progress-bar');

    if (pendingAutoImageCompletion) {
        pendingAutoImageStarted = true;
    }
    progressContainer.classList.add('active');
    if (resultContainer) resultContainer.style.display = 'none';
    setProgressCancelAction('cancelImageDownloadFromRecipes');
    if (title) title.textContent = i18n.images_downloading || i18n.image_download_in_progress_button || '';
    if (progressText) progressText.textContent = translateImageDownloadStatus(data);
    if (progressWrap) progressWrap.classList.remove('invisible');

    if (progressBar) {
        const rawProgress = data?.progress;
        const progress = Number.isFinite(Number(rawProgress))
            ? Math.max(0, Math.min(100, Number(rawProgress)))
            : 0;
        progressBar.style.width = `${progress}%`;
        progressBar.setAttribute('aria-valuenow', Math.round(progress));
    }
}

async function refreshImageDownloadLock(options = {}) {
    try {
        const response = await fetch('/api/images/download/status');
        if (!response.ok) return imageDownloadRunning;
        const data = await response.json();
        if (!data.success) return imageDownloadRunning;
        imageDownloadRunning = Boolean(data.running);
        updateRecipeRunButtonState();
        updateRecipeImageDownloadStatus(data, options);
        syncImageDownloadLockPolling();
        return imageDownloadRunning;
    } catch (error) {
        console.error('Error checking image download status:', error);
        return imageDownloadRunning;
    }
}

async function refreshImageAutoDownloadPreference() {
    try {
        const response = await fetch('/api/images/preferences');
        if (!response.ok) return imageAutoDownloadEnabled;
        const data = await response.json();
        if (!data.success) return imageAutoDownloadEnabled;
        imageAutoDownloadEnabled = Boolean(data.auto_download);
        return imageAutoDownloadEnabled;
    } catch (error) {
        console.error('Error checking image preferences:', error);
        return imageAutoDownloadEnabled;
    }
}

async function refreshImageDownloadLockAfterRecipeComplete() {
    if (!(await refreshImageAutoDownloadPreference())) {
        return false;
    }

    stopPostRecipeImageLockWatch();
    const startedAt = Date.now();
    const checkForImageDownload = async () => {
        const running = await refreshImageDownloadLock({ keepProgressWhenIdle: true });
        const timedOut = Date.now() - startedAt >= POST_RECIPE_IMAGE_LOCK_WATCH_MS;
        if (running || timedOut) {
            stopPostRecipeImageLockWatch();
            if (timedOut && !running) updateRecipeImageDownloadStatus({ running: false });
        }
        return running;
    };

    await checkForImageDownload();
    if (!imageDownloadRunning) {
        postRecipeImageLockInterval = setInterval(
            checkForImageDownload,
            IMAGE_DOWNLOAD_RUNNING_POLL_MS
        );
        postRecipeImageLockTimeout = setTimeout(
            stopPostRecipeImageLockWatch,
            POST_RECIPE_IMAGE_LOCK_WATCH_MS + IMAGE_DOWNLOAD_RUNNING_POLL_MS
        );
    }
    return true;
}

function syncImageDownloadLockPolling() {
    if (document.hidden || !imageDownloadRunning) {
        stopImageDownloadLockPolling();
        return;
    }

    const delay = IMAGE_DOWNLOAD_RUNNING_POLL_MS;
    if (imageDownloadLockInterval && imageDownloadPollDelay === delay) {
        return;
    }

    if (imageDownloadLockInterval) {
        clearInterval(imageDownloadLockInterval);
    }

    imageDownloadPollDelay = delay;
    imageDownloadLockInterval = setInterval(refreshImageDownloadLock, delay);
}

function stopImageDownloadLockPolling() {
    if (imageDownloadLockInterval) {
        clearInterval(imageDownloadLockInterval);
        imageDownloadLockInterval = null;
    }
    imageDownloadPollDelay = null;
}

function stopPostRecipeImageLockWatch() {
    if (postRecipeImageLockInterval) {
        clearInterval(postRecipeImageLockInterval);
        postRecipeImageLockInterval = null;
    }
    if (postRecipeImageLockTimeout) {
        clearTimeout(postRecipeImageLockTimeout);
        postRecipeImageLockTimeout = null;
    }
}

async function shouldContinueToAutoImageDownload(data) {
    if (!data || data.mode === 'test') return false;
    if (!Number(data.new_recipes || 0)) return false;
    return Boolean(await refreshImageAutoDownloadPreference());
}

async function cancelImageDownloadFromRecipes() {
    const progressText = document.getElementById('progress-message');
    const cancelBtn = document.getElementById('cancel-scraper-btn');

    if (cancelBtn) cancelBtn.disabled = true;
    if (progressText) progressText.textContent = i18n.images_cancelling || t('images.download_cancelling');

    try {
        const response = await fetch('/api/images/download/cancel', { method: 'POST' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
            throw new Error(window.DealMeals.resolveMessage(data, {
                messages: i18n,
                fallback: i18n.error || 'Error'
            }));
        }
        await refreshImageDownloadLock();
    } catch (error) {
        if (progressText) {
            progressText.textContent = `${i18n.images_cancel_error || i18n.error}: ${error.message}`;
        }
        if (cancelBtn) cancelBtn.disabled = false;
    }
}

async function checkRunningScrapers() {
    try {
        // Check queue first — if a "run all" was active it takes priority
        const [runningResp, queueResp] = await Promise.all([
            fetch('/api/recipe-scrapers/running'),
            fetch('/api/recipe-scrapers/queue'),
        ]);
        const runningData = await runningResp.json();
        const queueData = await queueResp.json();

        if (queueData.success && queueData.active) {
            // Restore the run-all queue from server state
            const scrapersById = {};
            scrapers.forEach(s => { scrapersById[s.id] = s; });
            const restoredScrapers = queueData.scraper_ids
                .map(id => scrapersById[id])
                .filter(s => s);

            if (restoredScrapers.length === 0) {
                // All scrapers vanished — clear stale queue
                await fetch('/api/recipe-scrapers/queue', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'cancel' })
                });
                return;
            }

            runAllQueue = {
                scrapers: restoredScrapers,
                index: queueData.index,
                totalNew: queueData.total_new,
            };

            // Show progress UI
            setRecipeRunButtonLocked(true);
            setProgressPanelRecipeMode();
            document.getElementById('progress-container').classList.add('active');
            document.getElementById('result-container').style.display = 'none';

            if (runningData.success && runningData.running && runningData.scraper_id) {
                // A scraper is running — resume polling with the queue callback
                const scraperId = runningData.scraper_id;
                currentScraperId = scraperId;
                const scraper = scrapersById[scraperId];
                const scraperName = scraper ? scraper.name : scraperId;
                const total = restoredScrapers.length;
                const current = queueData.index + 1;
                document.getElementById('progress-title').textContent =
                    t('running_all_progress', { name: scraperName, current: current, total: total });
                document.getElementById('progress-message').textContent =
                    (runningData.message_key ? t(runningData.message_key, runningData.message_params) : runningData.message) || i18n.fetching;
                startPolling(scraperId, _makeQueueCallback());
                dbg.log(`Resumed run-all queue at index ${queueData.index}, polling ${scraperId}`);
            } else {
                // No scraper running — current index already finished or page reloaded between scrapers
                dbg.log(`Restored run-all queue at index ${queueData.index}, starting next`);
                runNextInQueue();
            }
            return;
        }

        // No queue — check for a single running scraper
        if (runningData.success && runningData.running && runningData.scraper_id) {
            const scraperId = runningData.scraper_id;
            currentScraperId = scraperId;

            const select = document.getElementById('scraper-select');
            select.value = scraperId;
            updateTimeEstimates();

            const modeSelect = document.getElementById('mode-select');
            if (runningData.mode) {
                modeSelect.value = runningData.mode;
            }

            setRecipeRunButtonLocked(true);
            setProgressPanelRecipeMode();

            const progressContainer = document.getElementById('progress-container');
            const resultContainer = document.getElementById('result-container');
            progressContainer.classList.add('active');
            resultContainer.style.display = 'none';

            const scraper = scrapers.find(s => s.id === scraperId);
            const scraperName = scraper ? scraper.name : scraperId;
            document.getElementById('progress-title').textContent = `${scraperName}...`;
            document.getElementById('progress-message').textContent =
                (runningData.message_key ? t(runningData.message_key, runningData.message_params) : runningData.message) || i18n.fetching;

            startPolling(scraperId);
            dbg.log(`Resumed polling for running scraper: ${scraperId}`);
        }
    } catch (error) {
        console.error('Error checking running scrapers:', error);
    }
}

// Returns a callback for startPolling that advances the server-side queue and moves to next scraper.
function _makeQueueCallback() {
    return async (result) => {
        if (!runAllQueue) {
            document.getElementById('progress-container').classList.remove('active');
            setRecipeRunButtonLocked(false);
            loadScrapers();
            loadAllSchedules();
            return;
        }

        if (result.status === 'complete' && result.new_recipes !== undefined) {
            runAllQueue.totalNew += result.new_recipes;
        }

        runAllQueue.index++;

        // Sync updated index + totalNew to server before starting next
        try {
            await fetch('/api/recipe-scrapers/queue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'advance', index: runAllQueue.index, total_new: runAllQueue.totalNew })
            });
        } catch (error) {
            console.error('Failed to advance queue on server:', error);
        }

        runNextInQueue();
    };
}

async function loadScrapers() {
    try {
        const response = await fetch('/api/recipe-scrapers');
        const data = await response.json();

        if (data.success) {
            scrapers = data.scrapers;
            renderScrapers();
            populateSelect();
            populateScheduleSelect();
        } else {
            showError(i18n.could_not_load + ': ' + (t(data.message_key, data.message_params) || data.message));
        }
    } catch (error) {
        showError(i18n.error_loading + ': ' + error.message);
    }
}

function renderScrapers() {
    const activeContainer = document.getElementById('active-scrapers');
    const inactiveContainer = document.getElementById('inactive-scrapers');
    const activeEmpty = document.getElementById('active-empty');
    const inactiveEmpty = document.getElementById('inactive-empty');

    // Clear existing cards (but keep empty placeholders)
    activeContainer.querySelectorAll('.scraper-card').forEach(el => el.remove());
    inactiveContainer.querySelectorAll('.scraper-card').forEach(el => el.remove());

    let hasActive = false;
    let hasInactive = false;

    // Sort scrapers alphabetically by name
    const sortedScrapers = [...scrapers].sort((a, b) => a.name.localeCompare(b.name, RECIPE_LOCALE));

    sortedScrapers.forEach(scraper => {
        const card = createScraperCard(scraper);

        if (scraper.enabled) {
            activeContainer.appendChild(card);
            hasActive = true;
        } else {
            inactiveContainer.appendChild(card);
            hasInactive = true;
        }
    });

    // Show/hide empty placeholders
    activeEmpty.style.display = hasActive ? 'none' : 'block';
    inactiveEmpty.style.display = hasInactive ? 'none' : 'block';

    // Update unscraped sources banner
    updateUnscrapedBanner();
}

function updateUnscrapedBanner() {
    const banner = document.getElementById('unscraped-banner');
    const bannerText = document.getElementById('unscraped-banner-text');
    const fetchSection = document.getElementById('fetch-section');
    const activeSources = scrapers.filter(s => s.enabled && s.id !== 'myrecipes');
    const scraped = activeSources.filter(s => s.recipe_count > 0);
    const unscraped = activeSources.filter(s => s.recipe_count === 0);

    // Hide banner and pulse after user has completed 3+ scrapes (they know how it works)
    const isOnboarding = completedScrapes < 3;

    if (isOnboarding && unscraped.length > 0 && activeSources.length > 0) {
        const text = i18n.unscraped_banner
            .replace('{count}', unscraped.length)
            .replace('{total}', activeSources.length);
        bannerText.innerHTML = `<strong>${text}</strong> — ${i18n.unscraped_banner_action}`;
        banner.classList.remove('d-none');
    } else {
        banner.classList.add('d-none');
    }

    // Pulse the fetch section during onboarding (stop once all active sources have recipes)
    if (fetchSection && isOnboarding && unscraped.length > 0) {
        fetchSection.classList.remove('attention-pulse');
        void fetchSection.offsetWidth;
        fetchSection.classList.add('attention-pulse');
    }
}

function buildDescription(scraper) {
    // Strip old hardcoded "(hämtar ~X)" / "(hämtar ~X senaste)" from description
    let base = scraper.description.replace(/\s*\(hämtar[^)]*\)\s*$/, '').trim();

    const full = scraper.max_recipes_full;
    const incr = scraper.max_recipes_incremental;

    let fullText = full ? full.toLocaleString(RECIPE_LOCALE) : i18n.config_all_full.toLowerCase();
    let incrText = incr ? incr.toLocaleString(RECIPE_LOCALE) : i18n.config_all_incremental.toLowerCase();

    return `${base} (${fullText} / ${incrText})`;
}

function createScraperCard(scraper) {
    const card = document.createElement('div');
    card.className = `card scraper-card mb-3 ${scraper.enabled ? '' : 'disabled-scraper'}`;
    const scraperId = String(scraper.id || '');
    const scraperIdAttr = escapeAttr(scraperId);
    card.id = `scraper-${scraperId}`;
    let sourceUrl = safeUrl(scraper.source_url);

    // i18n: translate scraper name and description
    if (scraper.id === 'myrecipes') {
        scraper.name = i18n.myrecipes_scraper_name;
        scraper.description = i18n.description_prefix.replace('{source}', i18n.myrecipes_source_label);
    } else if (sourceUrl && !sourceUrl.startsWith('/')) {
        // "Recipes from koket.se" — extract domain as source
        const domain = new URL(sourceUrl).hostname.replace('www.', '');
        scraper.description = i18n.description_prefix.replace('{source}', domain);
    }
    const scraperNameText = escapeHtml(scraper.name || '');
    const scraperNameAttr = escapeAttr(scraper.name || '');
    const descriptionText = escapeHtml(buildDescription(scraper));

    // Format last run date
    let lastRunText = i18n.never_run;
    if (scraper.last_run_at) {
        const date = new Date(scraper.last_run_at);
        lastRunText = date.toLocaleString(RECIPE_LOCALE);
    }

    // Format database size
    let sizeText = '0 KB';
    if (scraper.database_size_kb > 1024) {
        sizeText = (scraper.database_size_kb / 1024).toFixed(1) + ' MB';
    } else {
        sizeText = Math.round(scraper.database_size_kb) + ' KB';
    }

    // Star button (favorite) - same size as move button but borderless
    const starIcon = scraper.is_starred ? 'bi-star-fill' : 'bi-star';
    const starColor = scraper.is_starred ? 'text-warning' : 'text-muted';
    const starTitle = scraper.is_starred ? i18n.remove_favorite : i18n.mark_favorite;
    const starButton = `
        <button class="star-btn mt-2" data-action="toggleStar" data-arg="${scraperIdAttr}" title="${escapeAttr(starTitle)}">
            <i class="bi ${starIcon} ${starColor}"></i>
        </button>`;

    // Config button (settings) - standard for all scrapers
    const hasConfig = scraper.max_recipes_full !== null || scraper.max_recipes_incremental !== null;
    const isMyRecipes = scraper.id === 'myrecipes';
    const configButton = `
        <button class="btn btn-outline-secondary btn-sm move-btn ${hasConfig ? 'config-active' : ''}" data-action="openScraperConfig" data-id="${scraperIdAttr}" data-name="${scraperNameAttr}" data-max-full="${scraper.max_recipes_full}" data-max-incr="${scraper.max_recipes_incremental}" title="${escapeAttr(i18n.config_settings)}">
            <i class="bi bi-gear"></i>
        </button>`;

    // URL management button (only for myrecipes)
    const urlButton = isMyRecipes ? `
        <button class="btn btn-outline-secondary btn-sm move-btn" data-action="openMyRecipesConfig" title="${escapeAttr(i18n.myrecipes_manage_urls)}">
            <i class="bi bi-link-45deg"></i>
        </button>` : '';

    // Build action buttons based on enabled status
    let actionButtons = '';
    if (scraper.enabled) {
        actionButtons = `
            <div class="d-flex align-items-start gap-2">
                ${urlButton}
                ${configButton}
                <div class="d-flex flex-column align-items-center">
                    <button class="btn btn-outline-secondary btn-sm move-btn" data-action="moveScraper" data-arg="${scraperIdAttr}" data-enable="false" title="${escapeAttr(i18n.deactivate)}">
                        <i class="bi bi-arrow-right"></i>
                    </button>
                    ${starButton}
                </div>
            </div>`;
    } else {
        actionButtons = `
            <div class="d-flex align-items-start gap-2">
                ${urlButton}
                ${configButton}
                <div class="d-flex flex-column align-items-center">
                    <button class="btn btn-outline-success btn-sm move-btn" data-action="moveScraper" data-arg="${scraperIdAttr}" data-enable="true" title="${escapeAttr(i18n.activate)}">
                        <i class="bi bi-arrow-left"></i>
                    </button>
                    ${starButton}
                    ${scraper.recipe_count > 0 ? `
                    <button class="btn btn-outline-danger btn-sm move-btn mt-2" data-action="clearScraperData" data-id="${scraperIdAttr}" data-name="${scraperNameAttr}" data-count="${scraper.recipe_count}" title="${escapeAttr(i18n.clear_database)}">
                        <i class="bi bi-trash"></i>
                    </button>` : ''}
                </div>
            </div>`;
    }

    card.innerHTML = `
        <div class="card-body">
            <div class="d-flex justify-content-between align-items-start">
                <div class="flex-grow-1">
                    <h6 class="card-title mb-1">
                        ${sourceUrl
                            ? `<a href="${escapeAttr(sourceUrl)}" target="_blank" rel="noopener noreferrer" class="text-decoration-none">${scraperNameText} <i class="bi bi-box-arrow-up-right small"></i></a>`
                            : `<span class="text-decoration-none" style="color: var(--bs-link-color)">${scraperNameText}</span>`}
                    </h6>
                    <p class="card-text small text-muted mb-2">${descriptionText}</p>
                    <div class="stats-row">
                        <span class="me-3" title="${i18n.recipes}">
                            <i class="bi bi-journal-text"></i> ${scraper.recipe_count.toLocaleString(RECIPE_LOCALE)} ${i18n.recipes_fetched}
                        </span>
                        <span class="me-3" title="${i18n.database_size}">
                            <i class="bi bi-database"></i> ${sizeText}
                        </span>
                        <br class="d-md-none">
                        <span title="${i18n.last_run}">
                            <i class="bi bi-clock"></i> ${lastRunText}
                        </span>
                    </div>
                </div>
                <div class="ms-3">
                    ${actionButtons}
                </div>
            </div>
        </div>
    `;

    return card;
}

function populateSelect() {
    const select = document.getElementById('scraper-select');
    select.innerHTML = '<option value="">' + i18n.select_source_placeholder + '</option>';

    // Sort alphabetically by name
    const sortedScrapers = scrapers.filter(s => s.enabled).sort((a, b) => a.name.localeCompare(b.name, RECIPE_LOCALE));

    // Add "all active" option + separator (only if 2+ sources)
    if (sortedScrapers.length >= 2) {
        const allOption = document.createElement('option');
        allOption.value = '__all_active__';
        allOption.textContent = i18n.all_active_sources;
        select.appendChild(allOption);

        const separator = document.createElement('option');
        separator.disabled = true;
        separator.textContent = '─────────────';
        select.appendChild(separator);
    }

    sortedScrapers.forEach(scraper => {
        const option = document.createElement('option');
        option.value = scraper.id;
        option.textContent = scraper.name;
        select.appendChild(option);
    });

    // Clear time estimates when repopulating
    updateTimeEstimates();
}

function updateTimeEstimates() {
    const scraperId = document.getElementById('scraper-select').value;
    const container = document.getElementById('time-estimates-container');
    const estimatesText = document.getElementById('time-estimates-text');
    const warningContainer = document.getElementById('scraper-warning-container');
    const warningText = document.getElementById('scraper-warning-text');
    const modeSelect = document.getElementById('mode-select');

    // Lock mode to incremental when "all active" is selected
    if (scraperId === '__all_active__') {
        modeSelect.value = 'incremental';
        modeSelect.disabled = true;
        container.style.display = 'none';
        warningContainer.style.display = 'none';
        return;
    } else {
        modeSelect.disabled = false;
    }

    if (!scraperId) {
        container.style.display = 'none';
        warningContainer.style.display = 'none';
        return;
    }

    const scraper = scrapers.find(s => s.id === scraperId);

    // Show warning if present
    if (scraper && scraper.warning) {
        warningText.textContent = scraper.warning;
        warningContainer.style.display = 'block';
    } else {
        warningContainer.style.display = 'none';
    }

    if (!scraper || !scraper.time_estimates) {
        container.style.display = 'none';
        return;
    }

    const estimates = scraper.time_estimates;
    const parts = [];

    const modeLabels = {
        'full': i18n.mode_full,
        'incremental': i18n.mode_incremental,
        'test': i18n.mode_test
    };

    // Build estimate string for each mode that has data (include all modes here)
    for (const mode of ['full', 'incremental', 'test']) {
        if (estimates[mode]) {
            const formatted = estimates[mode].formatted || i18n.unknown;
            parts.push(`${modeLabels[mode]}: ${i18n.approx} ${formatted}`);
        }
    }

    if (parts.length === 0) {
        container.style.display = 'none';
        return;
    }

    estimatesText.textContent = parts.join(' • ');
    container.style.display = 'block';
}

async function moveScraper(scraperId, enable) {
    try {
        const endpoint = enable ? 'enable' : 'disable';
        const response = await fetch(`/api/recipe-scrapers/${scraperId}/${endpoint}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            // Update local state
            const scraper = scrapers.find(s => s.id === scraperId);
            if (scraper) {
                scraper.enabled = enable;
            }
            renderScrapers();
            populateSelect();
            // Signal home page to reset (cache is being rebuilt with new source list)
            sessionStorage.setItem('suggestionsNeedRefresh', 'true');
        } else {
            showError(i18n.could_not_change + ': ' + (t(data.message_key, data.message_params) || data.message));
        }
    } catch (error) {
        showError(i18n.error + ': ' + error.message);
    }
}

async function toggleStar(scraperId, event) {
    // Prevent event bubbling
    if (event) event.stopPropagation();

    try {
        const response = await fetch(`/api/recipe-scrapers/${scraperId}/star`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            // Update local state and re-render (no popup)
            const scraper = scrapers.find(s => s.id === scraperId);
            if (scraper) {
                scraper.is_starred = data.is_starred;
            }
            renderScrapers();
            // Signal home page to reset (cache is being rebuilt with new starred status)
            sessionStorage.setItem('suggestionsNeedRefresh', 'true');
        } else {
            showError(t(data.message_key, data.message_params) || data.message);
        }
    } catch (error) {
        showError(i18n.error + ': ' + error.message);
    }
}

async function openScraperConfig(scraperId, scraperName, maxFull, maxIncr) {
    // Build radio + input HTML for each mode
    const fullIsAll = (maxFull === null || maxFull === undefined || isNaN(maxFull));
    const incrIsAll = (maxIncr === null || maxIncr === undefined || isNaN(maxIncr));

    const html = `
        <div style="text-align: left;">
            <h6 class="mb-2">${i18n.config_full_label}</h6>
            <div class="form-check">
                <input class="form-check-input" type="radio" name="fullMode" id="fullAll" value="all" ${fullIsAll ? 'checked' : ''}>
                <label class="form-check-label" for="fullAll">${i18n.config_all_full}</label>
            </div>
            <div class="form-check mt-1">
                <input class="form-check-input" type="radio" name="fullMode" id="fullMax" value="max" ${!fullIsAll ? 'checked' : ''}>
                <label class="form-check-label" for="fullMax">
                    ${i18n.config_max}:
                    <input type="number" id="fullMaxValue" min="1" max="9999" value="${fullIsAll ? 500 : maxFull}"
                           style="width: 80px; margin-left: 6px;" class="form-control form-control-sm d-inline-block"
                           data-check-id="fullMax"
                           data-focus-check-id="fullMax">
                </label>
            </div>
            <hr class="my-3">
            <h6 class="mb-2">${i18n.config_incremental_label}</h6>
            <div class="form-check">
                <input class="form-check-input" type="radio" name="incrMode" id="incrAll" value="all" ${incrIsAll ? 'checked' : ''}>
                <label class="form-check-label" for="incrAll">${i18n.config_all_incremental}</label>
            </div>
            <div class="form-check mt-1">
                <input class="form-check-input" type="radio" name="incrMode" id="incrMax" value="max" ${!incrIsAll ? 'checked' : ''}>
                <label class="form-check-label" for="incrMax">
                    ${i18n.config_max}:
                    <input type="number" id="incrMaxValue" min="1" max="9999" value="${incrIsAll ? 50 : maxIncr}"
                           style="width: 80px; margin-left: 6px;" class="form-control form-control-sm d-inline-block"
                           data-check-id="incrMax"
                           data-focus-check-id="incrMax">
                </label>
            </div>
        </div>`;

    const result = await Swal.fire({
        title: i18n.config_title.replace('{name}', scraperName),
        html: html,
        showCancelButton: true,
        confirmButtonText: i18n.save,
        cancelButtonText: i18n.cancel,
        preConfirm: () => {
            const fullMode = document.querySelector('input[name="fullMode"]:checked').value;
            const incrMode = document.querySelector('input[name="incrMode"]:checked').value;
            const fullVal = fullMode === 'all' ? null : parseInt(document.getElementById('fullMaxValue').value);
            const incrVal = incrMode === 'all' ? null : parseInt(document.getElementById('incrMaxValue').value);

            if (fullVal !== null && (isNaN(fullVal) || fullVal < 1 || fullVal > 9999)) {
                Swal.showValidationMessage(i18n.config_invalid || 'Invalid (1-9999)');
                return false;
            }
            if (incrVal !== null && (isNaN(incrVal) || incrVal < 1 || incrVal > 9999)) {
                Swal.showValidationMessage(i18n.config_invalid || 'Invalid (1-9999)');
                return false;
            }
            return { max_recipes_full: fullVal, max_recipes_incremental: incrVal };
        }
    });

    if (!result.isConfirmed) return;

    try {
        const response = await fetch(`/api/recipe-scrapers/${scraperId}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(result.value)
        });
        const data = await response.json();
        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: i18n.config_saved,
                timer: 1500,
                showConfirmButton: false,
                backdrop: false,
            });
            // Update just this scraper's data without full reload
            const s = scrapers.find(sc => sc.id === scraperId);
            if (s) {
                s.max_recipes_full = data.max_recipes_full;
                s.max_recipes_incremental = data.max_recipes_incremental;
                const card = document.getElementById(`scraper-${scraperId}`);
                if (card) {
                    const desc = card.querySelector('.card-text');
                    if (desc) desc.textContent = buildDescription(s);
                    // Update gear button highlight
                    const gear = card.querySelector('.move-btn .bi-gear')?.closest('button');
                    if (gear) {
                        const hasConfig = data.max_recipes_full !== null || data.max_recipes_incremental !== null;
                        gear.classList.toggle('config-active', hasConfig);
                    }
                }
            }
        } else {
            showError(data.message || 'Error');
        }
    } catch (error) {
        showError(error.message);
    }
}

// ========== MINA RECEPT: Custom URL Management Modal ==========

function statusBadge(status, retryCount) {
    const map = {
        'pending': { cls: 'bg-secondary', text: i18n.myrecipes_status_pending },
        'ok': { cls: 'bg-success', text: i18n.myrecipes_status_ok },
        'error': { cls: 'bg-danger', text: i18n.myrecipes_status_error },
        'no_recipe': { cls: 'bg-warning text-dark', text: i18n.myrecipes_status_no_recipe },
        'gave_up': { cls: 'bg-danger', text: i18n.myrecipes_status_gave_up },
    };
    const s = map[status] || map['pending'];
    const retryInfo = retryCount > 0 && status !== 'ok' && status !== 'gave_up'
        ? ` <small>(${retryCount}/5)</small>` : '';
    return `<span class="badge ${s.cls}">${s.text}${retryInfo}</span>`;
}

function buildUrlList(urlList) {
    if (!urlList.length) {
        return `<p class="text-muted small mb-0">${i18n.myrecipes_no_urls}</p>`;
    }
    return `<div class="list-group list-group-flush" style="max-height: 350px; overflow-y: auto;">
        ${urlList.map(u => {
            const tooltip = u.last_error ? `title="${escapeAttr(u.last_error)}"` : '';
            const href = safeUrl(u.url);
            const displayUrl = escapeHtml(u.url || '');
            const urlHtml = href
                ? `<a href="${escapeAttr(href)}" target="_blank" rel="noopener noreferrer" class="text-decoration-none small">${displayUrl}</a>`
                : `<span class="text-decoration-none small">${displayUrl}</span>`;
            const labelHtml = u.label ? `<div class="text-muted" style="font-size: 0.7rem;">${escapeHtml(u.label)}</div>` : '';
            return `<div class="list-group-item d-flex justify-content-between align-items-center px-2 py-1" ${tooltip}>
                <div class="text-truncate me-2" style="min-width: 0;">
                    ${urlHtml}
                    ${labelHtml}
                </div>
                <div class="d-flex align-items-center gap-2 flex-shrink-0">
                    ${statusBadge(u.status, u.retry_count || 0)}
                    <button class="btn btn-outline-danger btn-sm py-0 px-1" data-action="deleteMyRecipeUrl" data-arg="${escapeAttr(u.id)}" title="${escapeAttr(i18n.myrecipes_confirm_delete)}">
                        <i class="bi bi-x-lg"></i>
                    </button>
                </div>
            </div>`;
        }).join('')}
    </div>`;
}

async function openMyRecipesConfig() {
    // Fetch current URLs and render list
    try {
        const resp = await fetch('/api/recipe-scrapers/custom/urls');
        const data = await resp.json();
        window._myRecipesUrls = data.success ? data.urls.sort((a, b) => a.url.localeCompare(b.url)) : [];
    } catch (e) {
        showError(e.message);
        return;
    }

    document.getElementById('myrecipes-url-list').innerHTML = buildUrlList(window._myRecipesUrls);

    const modalEl = document.getElementById('myRecipesModal');
    const modal = new bootstrap.Modal(modalEl);

    // Enter key adds URL
    const input = document.getElementById('newRecipeUrl');
    input.value = '';
    input.onkeydown = (e) => {
        if (e.key === 'Enter') { e.preventDefault(); addMyRecipeUrl(); }
    };

    // Refresh scraper list when modal closes
    modalEl.addEventListener('hidden.bs.modal', () => loadScrapers(), { once: true });

    modal.show();
    setTimeout(() => input.focus(), 300);
}

async function addMyRecipeUrl() {
    const input = document.getElementById('newRecipeUrl');
    const url = (input?.value || '').trim();
    if (!url) return;

    try {
        const resp = await fetch('/api/recipe-scrapers/custom/urls', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await resp.json();

        if (data.success) {
            input.value = '';
            window._myRecipesUrls.push(data.url_entry);
            window._myRecipesUrls.sort((a, b) => a.url.localeCompare(b.url));
            document.getElementById('myrecipes-url-list').innerHTML =
                buildUrlList(window._myRecipesUrls);
        } else {
            // Show inline error
            const msgKey = data.message_key || '';
            const msg = i18n[msgKey.replace(/\./g, '_')] || msgKey || 'Error';
            input.classList.add('is-invalid');
            let feedback = input.parentElement.querySelector('.invalid-feedback');
            if (!feedback) {
                feedback = document.createElement('div');
                feedback.className = 'invalid-feedback';
                input.parentElement.appendChild(feedback);
            }
            feedback.textContent = msg;
            setTimeout(() => input.classList.remove('is-invalid'), 3000);
        }
    } catch (e) {
        showError(e.message);
    }
}

async function deleteMyRecipeUrl(urlId) {
    try {
        const resp = await fetch(`/api/recipe-scrapers/custom/urls/${urlId}`, {
            method: 'DELETE'
        });
        const data = await resp.json();

        if (data.success) {
            window._myRecipesUrls = window._myRecipesUrls.filter(u => u.id !== urlId);
            document.getElementById('myrecipes-url-list').innerHTML =
                buildUrlList(window._myRecipesUrls);
            // Update scraper card count
            loadScrapers();
        }
    } catch (e) {
        showError(e.message);
    }
}

async function clearScraperData(scraperId, scraperName, recipeCount) {
    // Show confirmation dialog
    const confirmHtml = i18n.clear_db_confirm
        .replace('{count}', recipeCount.toLocaleString(RECIPE_LOCALE))
        .replace('{name}', scraperName);
    const result = await Swal.fire({
        icon: 'warning',
        title: i18n.clear_db_title,
        html: confirmHtml,
        showCancelButton: true,
        confirmButtonText: i18n.clear_db_yes,
        cancelButtonText: i18n.cancel,
        confirmButtonColor: '#dc3545'
    });

    if (!result.isConfirmed) {
        return;
    }

    try {
        const response = await fetch(`/api/recipe-scrapers/${scraperId}/recipes`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: i18n.cleared,
                text: t(data.message_key, data.message_params) || data.message,
                timer: 2000,
                showConfirmButton: false
            });
            // Reload scrapers to update stats
            loadScrapers();
        } else {
            showError(t(data.message_key, data.message_params) || data.message);
        }
    } catch (error) {
        showError(i18n.error + ': ' + error.message);
    }
}

async function runScraper() {
    const scraperId = document.getElementById('scraper-select').value;
    const mode = document.getElementById('mode-select').value;

    if (!scraperId) {
        Swal.fire({
            icon: 'warning',
            title: i18n.select_source,
            text: i18n.select_source_first
        });
        return;
    }

    if (await refreshImageDownloadLock()) {
        return;
    }

    // Route to sequential runner for "all active"
    if (scraperId === '__all_active__') {
        runAllActive();
        return;
    }

    // Check if any scraper is already running
    try {
        const runningResponse = await fetch('/api/recipe-scrapers/running');
        const runningData = await runningResponse.json();

        if (runningData.success && runningData.running) {
            const runningScraper = scrapers.find(s => s.id === runningData.scraper_id);
            const runningName = runningScraper ? runningScraper.name : runningData.scraper_id;

            Swal.fire({
                icon: 'warning',
                title: i18n.already_running,
                html: i18n.already_running_desc.replace('{name}', runningName)
            });
            return;
        }
    } catch (error) {
        console.error('Error checking running scrapers:', error);
        // Continue anyway if check fails
    }

    // Confirm if full mode
    if (mode === 'full') {
        const result = await Swal.fire({
            icon: 'warning',
            title: i18n.full_confirm_title,
            text: i18n.full_confirm_desc,
            showCancelButton: true,
            confirmButtonText: i18n.yes_run,
            cancelButtonText: i18n.cancel,
            confirmButtonColor: '#dc3545'
        });

        if (!result.isConfirmed) {
            return;
        }
    }

    // Disable button and show progress
    setRecipeRunButtonLocked(true);
    setProgressPanelRecipeMode();

    const progressContainer = document.getElementById('progress-container');
    const resultContainer = document.getElementById('result-container');
    progressContainer.classList.add('active');
    resultContainer.style.display = 'none';

    document.getElementById('progress-title').textContent = i18n.fetching;
    document.getElementById('progress-message').textContent = i18n.waiting_server;

    try {
        // Store current scraper ID for cancel button
        currentScraperId = scraperId;

        // Start the scraper
        const response = await fetch(`/api/recipe-scrapers/${scraperId}/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });

        const data = await response.json();

        if (data.success) {
            let msg = t('scraper_started', data.message_params || {});
            document.getElementById('progress-message').textContent = msg;
            // Start polling for status
            startPolling(scraperId);
        } else {
            showResult('error', t(data.message_key, data.message_params) || data.message);
            setRecipeRunButtonLocked(false);
            progressContainer.classList.remove('active');
        }
    } catch (error) {
        showResult('error', i18n.error + ': ' + error.message);
        setRecipeRunButtonLocked(false);
        progressContainer.classList.remove('active');
    }
}

function startPolling(scraperId, onComplete) {
    // Poll every 2 seconds
    let pollFailCount = 0;
    pollingInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/recipe-scrapers/${scraperId}/status`);
            if (!response.ok) {
                if (++pollFailCount >= 5) {
                    clearInterval(pollingInterval);
                    pollingInterval = null;
                    currentScraperId = null;
                    document.getElementById('progress-container').classList.remove('active');
                    setRecipeRunButtonLocked(false);
                    showResult('error', i18n.could_not_load);
                }
                return;
            }
            pollFailCount = 0;
            const data = await response.json();

            if (data.success) {
                // Show progress message with recipes found count if available
                let progressText = (data.message_key ? t(data.message_key, data.message_params) : data.message) || i18n.fetching;
                if (data.recipes_found !== undefined && data.recipes_found > 0) {
                    progressText += ` (${t('recipes_found', { count: data.recipes_found })})`;
                }
                document.getElementById('progress-message').textContent = progressText;

                if (!data.running) {
                    // Scraper finished
                    clearInterval(pollingInterval);
                    pollingInterval = null;
                    currentScraperId = null;

                    // If a custom onComplete callback is provided, use it instead of default behavior
                    if (onComplete) {
                        await onComplete(data);
                        return;
                    }

                    if (data.status === 'complete') {
                        if (await shouldContinueToAutoImageDownload(data)) {
                            setPendingAutoImageCompletion({ type: 'single', data });
                            setRecipeRunButtonLocked(false);
                            refreshImageDownloadLockAfterRecipeComplete();
                            loadScrapers();
                            loadAllSchedules();
                            return;
                        }

                        showDetailedResult(data, {
                            didOpen: () => {
                                document.getElementById('progress-container').classList.remove('active');
                                setRecipeRunButtonLocked(false);
                            },
                            didClose: () => {
                                loadScrapers();
                                loadAllSchedules();
                            }
                        });
                    } else if (data.status === 'cancelled') {
                        document.getElementById('progress-container').classList.remove('active');
                        setRecipeRunButtonLocked(false);
                        Swal.fire({
                            icon: 'info',
                            title: i18n.cancelled,
                            text: i18n.fetch_cancelled,
                            timer: 2000,
                            showConfirmButton: false
                        });
                    } else if (data.status === 'error') {
                        document.getElementById('progress-container').classList.remove('active');
                        setRecipeRunButtonLocked(false);
                        showResult('error', t(data.message_key, data.message_params) || data.message);
                    }
                }
            }
        } catch (error) {
            console.error('Polling error:', error);
            if (++pollFailCount >= 5) {
                clearInterval(pollingInterval);
                pollingInterval = null;
                currentScraperId = null;
                document.getElementById('progress-container').classList.remove('active');
                setRecipeRunButtonLocked(false);
                showResult('error', i18n.could_not_load);
            }
        }
    }, 2000);
}

async function cancelScraper() {
    // Stop the "run all" queue — both in memory and on server
    if (runAllQueue) {
        runAllQueue = null;
        fetch('/api/recipe-scrapers/queue', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'cancel' })
        }).catch(() => {});
    }

    if (!currentScraperId) {
        return;
    }

    const cancelBtn = document.getElementById('cancel-scraper-btn');
    cancelBtn.disabled = true;
    cancelBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>' + i18n.cancelling;

    try {
        const response = await fetch(`/api/recipe-scrapers/${currentScraperId}/cancel`, {
            method: 'POST'
        });

        const data = await response.json();

        if (!data.success) {
            showError(t(data.message_key, data.message_params) || data.message);
        }
        // Polling will pick up the cancelled status
    } catch (error) {
        showError(i18n.error_cancel + ': ' + error.message);
    } finally {
        cancelBtn.disabled = false;
        cancelBtn.innerHTML = '<i class="bi bi-x-circle me-1"></i>' + i18n.cancel;
    }
}

async function runAllActive() {
    // Get all enabled scrapers sorted alphabetically
    const activeScrapers = scrapers.filter(s => s.enabled).sort((a, b) => a.name.localeCompare(b.name, RECIPE_LOCALE));

    if (activeScrapers.length === 0) {
        Swal.fire({ icon: 'warning', title: i18n.select_source, text: i18n.select_source_first });
        return;
    }

    if (await refreshImageDownloadLock()) {
        return;
    }

    // Check if any scraper is already running
    try {
        const runningResponse = await fetch('/api/recipe-scrapers/running');
        const runningData = await runningResponse.json();
        if (runningData.success && runningData.running) {
            const runningScraper = scrapers.find(s => s.id === runningData.scraper_id);
            const runningName = runningScraper ? runningScraper.name : runningData.scraper_id;
            Swal.fire({ icon: 'warning', title: i18n.already_running, html: i18n.already_running_desc.replace('{name}', runningName) });
            return;
        }
    } catch (error) {
        console.error('Error checking running scrapers:', error);
    }

    // Estimate total time from incremental time estimates
    // Sources without history get ~2 min per 50 recipes as fallback
    let totalSeconds = 0;
    activeScrapers.forEach(s => {
        if (s.time_estimates && s.time_estimates.incremental) {
            totalSeconds += s.time_estimates.incremental.avg_seconds;
        } else {
            totalSeconds += 120;  // ~2 min fallback for first run
        }
    });
    const timeText = formatDuration(totalSeconds);

    // Confirm before starting
    const confirm = await Swal.fire({
        icon: 'info',
        title: t('run_all_confirm_title', { count: activeScrapers.length }),
        html: t('run_all_confirm_desc', { time: timeText }),
        showCancelButton: true,
        confirmButtonText: i18n.run_all_confirm_yes,
        cancelButtonText: i18n.cancel
    });

    if (!confirm.isConfirmed) return;

    // Register queue on server before starting (survives page reloads)
    try {
        await fetch('/api/recipe-scrapers/queue', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'start', scraper_ids: activeScrapers.map(s => s.id) })
        });
    } catch (error) {
        console.error('Failed to register queue on server:', error);
        // Continue anyway — worst case it won't survive a reload
    }

    // Initialize in-memory queue
    runAllQueue = { scrapers: activeScrapers, index: 0, totalNew: 0 };

    // Show progress UI
    setRecipeRunButtonLocked(true);
    setProgressPanelRecipeMode();
    const progressContainer = document.getElementById('progress-container');
    const resultContainer = document.getElementById('result-container');
    progressContainer.classList.add('active');
    resultContainer.style.display = 'none';

    // Start first scraper
    runNextInQueue();
}

async function runNextInQueue() {
    if (!runAllQueue || runAllQueue.index >= runAllQueue.scrapers.length) {
        // All done — show summary
        finishRunAll();
        return;
    }

    const queue = runAllQueue;
    const scraper = queue.scrapers[queue.index];
    const total = queue.scrapers.length;
    const current = queue.index + 1;

    // Update progress title with overall counter
    setProgressPanelRecipeMode();
    document.getElementById('progress-title').textContent =
        t('running_all_progress', { name: scraper.name, current: current, total: total });
    document.getElementById('progress-message').textContent = i18n.waiting_server;

    try {
        currentScraperId = scraper.id;

        const response = await fetch(`/api/recipe-scrapers/${scraper.id}/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: 'incremental' })
        });

        const data = await response.json();

        if (data.success) {
            document.getElementById('progress-message').textContent =
                t('scraper_started', data.message_params || {});

            startPolling(scraper.id, _makeQueueCallback());
        } else {
            // This scraper failed to start — skip to next
            dbg.warn(`Scraper ${scraper.name} failed to start:`, data);
            queue.index++;
            fetch('/api/recipe-scrapers/queue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'advance', index: queue.index, total_new: queue.totalNew })
            }).catch(() => {});
            runNextInQueue();
        }
    } catch (error) {
        console.error(`Error starting scraper ${scraper.name}:`, error);
        queue.index++;
        fetch('/api/recipe-scrapers/queue', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'advance', index: queue.index, total_new: queue.totalNew })
        }).catch(() => {});
        runNextInQueue();
    }
}

function wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitForCacheReady(timeoutMs = 10 * 60 * 1000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        try {
            const response = await fetch('/api/cache/status');
            if (response.ok) {
                const data = await response.json();
                if (data.status === 'ready') return true;
                if (data.status === 'error') return false;
            }
        } catch (error) {
            console.error('Failed to poll cache status:', error);
        }
        await wait(2000);
    }
    return false;
}

async function finishRunAll() {
    const queue = runAllQueue;
    runAllQueue = null;

    const totalNew = queue ? queue.totalNew : 0;
    let cacheRebuildStarted = false;
    let cacheReady = false;

    // Finish server-side queue and trigger one final cache rebuild for the whole batch.
    try {
        const response = await fetch('/api/recipe-scrapers/queue', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'finish', total_new: totalNew })
        });
        const data = await response.json();
        cacheRebuildStarted = Boolean(data.cache_rebuild_started);
    } catch (error) {
        console.error('Failed to finish queue on server:', error);
    }

    if (cacheRebuildStarted) {
        sessionStorage.setItem('suggestionsNeedRefresh', 'true');
        setProgressPanelRecipeMode();
        document.getElementById('progress-container').classList.add('active');
        document.getElementById('progress-title').textContent = t('recipes.cache_rebuild_started');
        document.getElementById('progress-message').textContent = i18n.waiting_server;
        cacheReady = await waitForCacheReady();
    }

    // Track completed scrapes (once for the whole batch)
    completedScrapes++;
    fetch('/api/ui-preferences', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ completed_scrapes: completedScrapes })
    }).catch(() => {});

    const count = queue ? queue.scrapers.length : 0;
    const autoClose = completedScrapes > 3;
    let summaryHtml = escapeHtml(t('all_complete_summary', { total: totalNew.toLocaleString(RECIPE_LOCALE) }));
    if (cacheRebuildStarted && !cacheReady) {
        summaryHtml += `<br><span class="text-muted">${escapeHtml(t('recipes.cache_rebuild_started'))}</span>`;
    }

    if (totalNew > 0 && await refreshImageAutoDownloadPreference()) {
        setPendingAutoImageCompletion({
            type: 'runAll',
            count,
            summaryHtml,
            autoClose
        });
        setRecipeRunButtonLocked(false);
        refreshImageDownloadLockAfterRecipeComplete();
        loadScrapers();
        loadAllSchedules();
        return;
    }

    showRunAllCompletePopup({ count, summaryHtml, autoClose });
}

function showDetailedResult(data, modalOptions = {}) {
    const silent = Boolean(modalOptions.silent);
    if (silent) {
        modalOptions = { ...modalOptions };
        delete modalOptions.silent;
    }

    // Build HTML content for detailed result popup
    // Map mode to translated label
    const modeLabelMap = {
        'full': i18n.mode_full,
        'incremental': i18n.mode_incremental,
        'test': i18n.mode_test
    };
    const modeLabel = modeLabelMap[data.mode] || data.mode_label || data.mode;
    const newRecipes = data.new_recipes !== undefined ? data.new_recipes : 0;
    const totalInDb = data.total_in_db !== undefined ? data.total_in_db : 0;
    const note = data.note_key ? t(data.note_key, data.note_params || {}) : (data.note || '');

    const spellCorrections = data.spell_corrections || 0;

    let html = `
        <div style="text-align: left; font-size: 1.1em;">
            <p><strong>${i18n.new_recipes_found}</strong> ${newRecipes.toLocaleString(RECIPE_LOCALE)}</p>
            <p><strong>${i18n.total_in_db}</strong> ${totalInDb.toLocaleString(RECIPE_LOCALE)}</p>
            ${spellCorrections > 0 ? `<p><i class="bi bi-spellcheck text-info"></i> ${i18n.spell_corrections_made.replace('{count}', spellCorrections)}</p>` : ''}
            ${note ? `<p class="text-muted small"><em>${note}</em></p>` : ''}
        </div>
    `;

    // Update spell check badge in nav immediately
    if (spellCorrections > 0) {
        const badge = document.getElementById('spell-badge');
        if (badge) {
            fetch('/api/spell-corrections/count')
                .then(r => r.json())
                .then(d => {
                    if (d.success && d.count > 0) {
                        badge.textContent = d.count;
                        badge.style.display = '';
                    }
                })
                .catch(() => {});
        }
    }

    // Track completed scrapes in DB — auto-close after 3rd
    completedScrapes++;
    fetch('/api/ui-preferences', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ completed_scrapes: completedScrapes })
    }).catch(() => {});

    if (silent) return;

    const autoClose = completedScrapes > 3;
    Swal.fire({
        icon: 'success',
        title: t('fetch_complete', { mode: modeLabel }),
        html: html,
        confirmButtonText: i18n.ok,
        heightAuto: false,
        scrollbarPadding: false,
        timer: autoClose ? 8000 : undefined,
        timerProgressBar: autoClose,
        ...modalOptions
    });
}

function showResult(type, message) {
    // Use SweetAlert with OK button so user doesn't miss the result
    Swal.fire({
        icon: type === 'success' ? 'success' : 'error',
        title: type === 'success' ? i18n.success : i18n.error,
        text: message,
        confirmButtonText: i18n.ok
    });
}

function showError(message) {
    Swal.fire({
        icon: 'error',
        title: i18n.error,
        text: message
    });
}

// ============== Scheduling Functions ==============

async function loadAllSchedules() {
    const container = document.getElementById('all-schedules-list');

    try {
        // Load saved sort preference first
        if (!window.currentScheduleSort) {
            try {
                const prefResponse = await fetch('/api/ui-preferences');
                const prefData = await prefResponse.json();
                if (prefData.success && prefData.preferences?.scheduleSort) {
                    window.currentScheduleSort = prefData.preferences.scheduleSort;
                } else {
                    window.currentScheduleSort = { column: 'next_run_at', ascending: true };
                }
            } catch (e) {
                window.currentScheduleSort = { column: 'next_run_at', ascending: true };
            }
        }

        const response = await fetch('/api/schedules');
        const data = await response.json();

        if (!data.success || !data.schedules || data.schedules.length === 0) {
            container.innerHTML = '<p class="text-muted small mb-0"><i class="bi bi-info-circle me-1"></i>' + i18n.no_schedules + '</p>';
            return;
        }

        // Store schedules globally for sorting
        window.schedulesData = data.schedules;

        renderScheduleTable();

    } catch (error) {
        container.innerHTML = '<p class="text-danger small mb-0">' + i18n.could_not_load_schedules + '</p>';
        console.error('Error loading schedules:', error);
    }
}

function renderScheduleTable() {
    const container = document.getElementById('all-schedules-list');
    if (!window.schedulesData) return;

    // Sort data
    const sortedSchedules = [...window.schedulesData].sort((a, b) => {
        const col = window.currentScheduleSort.column;
        const asc = window.currentScheduleSort.ascending;

        let valA, valB;

        if (col === 'scraper_id') {
            const scraperA = scrapers.find(s => s.id === a.scraper_id);
            const scraperB = scrapers.find(s => s.id === b.scraper_id);
            valA = (scraperA ? scraperA.name : a.scraper_id).toLowerCase();
            valB = (scraperB ? scraperB.name : b.scraper_id).toLowerCase();
        } else if (col === 'schedule') {
            // Sort by weekday (Monday=0 first, Sunday=6 last), then by hour
            // Combined value: day_of_week * 24 + hour
            const dayA = a.day_of_week !== null ? a.day_of_week : 7;
            const dayB = b.day_of_week !== null ? b.day_of_week : 7;
            valA = dayA * 24 + (a.hour || 0);
            valB = dayB * 24 + (b.hour || 0);
        } else if (col === 'next_run_at' || col === 'last_run_at') {
            valA = a[col] ? new Date(a[col]).getTime() : (asc ? Infinity : -Infinity);
            valB = b[col] ? new Date(b[col]).getTime() : (asc ? Infinity : -Infinity);
        } else if (col === 'last_run_recipes') {
            valA = a.last_run_recipes || 0;
            valB = b.last_run_recipes || 0;
        } else {
            valA = a[col] || '';
            valB = b[col] || '';
        }

        if (valA < valB) return asc ? -1 : 1;
        if (valA > valB) return asc ? 1 : -1;
        return 0;
    });

    // Build table with sortable headers
    const sortIcon = (col) => {
        if (window.currentScheduleSort.column !== col) return '<i class="bi bi-arrow-down-up text-muted ms-1"></i>';
        return window.currentScheduleSort.ascending
            ? '<i class="bi bi-sort-up ms-1"></i>'
            : '<i class="bi bi-sort-down ms-1"></i>';
    };

    let html = `
        <table class="table table-sm table-hover mb-0 schedule-table">
            <thead>
                <tr>
                    <th style="cursor: pointer;" data-action="sortScheduleTable" data-arg="scraper_id">${i18n.select_source}${sortIcon('scraper_id')}</th>
                    <th style="cursor: pointer;" data-action="sortScheduleTable" data-arg="schedule">${i18n.schedule}${sortIcon('schedule')}</th>
                    <th style="cursor: pointer;" data-action="sortScheduleTable" data-arg="next_run_at">${i18n.next_run}${sortIcon('next_run_at')}</th>
                    <th style="cursor: pointer;" data-action="sortScheduleTable" data-arg="last_run_at">${i18n.last_completed}${sortIcon('last_run_at')}</th>
                    <th style="cursor: pointer;" data-action="sortScheduleTable" data-arg="last_run_recipes">${i18n.last_run_recipes}${sortIcon('last_run_recipes')}</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
    `;

    for (const schedule of sortedSchedules) {
        // Find scraper name
        const scraper = scrapers.find(s => s.id === schedule.scraper_id);
        const scraperName = scraper ? scraper.name : schedule.scraper_id;

        const description = formatScheduleDescription(schedule);
        const nextRun = schedule.next_run_at
            ? new Date(schedule.next_run_at).toLocaleString(RECIPE_LOCALE)
            : '-';
        const lastRun = schedule.last_run_failed
            ? i18n.last_run_failed
            : schedule.last_run_at
                ? new Date(schedule.last_run_at).toLocaleString(RECIPE_LOCALE)
                : i18n.never;
        const lastRecipes = schedule.last_run_recipes || 0;

        html += `
            <tr style="cursor: pointer;" data-action="selectScheduleScraper" data-arg="${schedule.scraper_id}">
                <td><strong>${scraperName}</strong></td>
                <td>${description}</td>
                <td><small>${nextRun}</small></td>
                <td><small class="text-muted">${lastRun}</small></td>
                <td><small>${lastRecipes.toLocaleString(RECIPE_LOCALE)}</small></td>
                <td><button class="btn btn-sm btn-outline-danger border-0" data-action="deleteScheduleById" data-arg="${schedule.scraper_id}" data-stop-prop="true" title="${i18n.remove_schedule}"><i class="bi bi-x-lg"></i></button></td>
            </tr>
        `;
    }

    html += '</tbody></table>';
    container.innerHTML = html;
}

function sortScheduleTable(column) {
    if (window.currentScheduleSort.column === column) {
        window.currentScheduleSort.ascending = !window.currentScheduleSort.ascending;
    } else {
        window.currentScheduleSort.column = column;
        window.currentScheduleSort.ascending = true;
    }
    renderScheduleTable();

    // Save preference to database
    fetch('/api/ui-preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            scheduleSort: {
                column: window.currentScheduleSort.column,
                ascending: window.currentScheduleSort.ascending
            }
        })
    }).catch(e => dbg.warn('Could not save sort preference:', e));
}

function selectScheduleScraper(scraperId) {
    // Select the scraper in dropdown and load its schedule
    document.getElementById('schedule-scraper-select').value = scraperId;
    loadSchedule();
}

function initScheduleFields() {
    // Populate day of month (1-28)
    const dayOfMonthSelect = document.getElementById('schedule-day-of-month');
    for (let i = 1; i <= 28; i++) {
        const option = document.createElement('option');
        option.value = i;
        option.textContent = i;
        dayOfMonthSelect.appendChild(option);
    }

    // Populate hours (0-23 in 24h format)
    const hourSelect = document.getElementById('schedule-hour');
    for (let i = 0; i <= 23; i++) {
        const option = document.createElement('option');
        option.value = i;
        option.textContent = i.toString().padStart(2, '0') + ':00';
        hourSelect.appendChild(option);
    }
    // Default to 06:00
    hourSelect.value = '6';
}

function populateScheduleSelect() {
    const select = document.getElementById('schedule-scraper-select');
    select.innerHTML = '<option value="">' + i18n.select_source_placeholder + '</option>';

    // Sort alphabetically by name
    const sortedScrapers = scrapers.filter(s => s.enabled).sort((a, b) => a.name.localeCompare(b.name, RECIPE_LOCALE));
    sortedScrapers.forEach(scraper => {
        const option = document.createElement('option');
        option.value = scraper.id;
        option.textContent = scraper.name;
        select.appendChild(option);
    });
}

function updateScheduleFields() {
    const frequency = document.getElementById('schedule-frequency').value;
    const dayOfWeekContainer = document.getElementById('day-of-week-container');
    const dayOfMonthContainer = document.getElementById('day-of-month-container');
    const hourContainer = document.getElementById('hour-container');
    const saveBtn = document.getElementById('save-schedule-btn');
    const scraperSelect = document.getElementById('schedule-scraper-select');

    // Hide all optional fields first
    dayOfWeekContainer.style.display = 'none';
    dayOfMonthContainer.style.display = 'none';
    hourContainer.style.display = 'none';

    if (frequency === '') {
        saveBtn.disabled = !scraperSelect.value;
        return;
    }

    // Show hour for all frequencies
    hourContainer.style.display = 'block';

    if (frequency === 'weekly') {
        dayOfWeekContainer.style.display = 'block';
    } else if (frequency === 'monthly') {
        dayOfMonthContainer.style.display = 'block';
    }

    saveBtn.disabled = !scraperSelect.value;
}

async function loadSchedule() {
    const scraperId = document.getElementById('schedule-scraper-select').value;
    const scheduleInfo = document.getElementById('schedule-info');

    // Enable/disable save button
    document.getElementById('save-schedule-btn').disabled = !scraperId;

    if (!scraperId) {
        // Reset fields
        document.getElementById('schedule-frequency').value = '';
        updateScheduleFields();
        scheduleInfo.style.display = 'none';
        return;
    }

    try {
        const response = await fetch(`/api/schedules/${scraperId}`);
        const data = await response.json();

        if (data.success && data.schedule) {
            const schedule = data.schedule;

            // Populate fields
            document.getElementById('schedule-frequency').value = schedule.frequency;
            updateScheduleFields();

            if (schedule.frequency === 'weekly' && schedule.day_of_week !== null) {
                document.getElementById('schedule-day-of-week').value = schedule.day_of_week;
            }
            if (schedule.frequency === 'monthly' && schedule.day_of_month !== null) {
                document.getElementById('schedule-day-of-month').value = schedule.day_of_month;
            }
            document.getElementById('schedule-hour').value = schedule.hour;

            // Show schedule info
            scheduleInfo.style.display = 'block';
            document.getElementById('schedule-description').textContent = formatScheduleDescription(schedule);

            let runInfo = '';
            if (schedule.last_run_failed) {
                runInfo = i18n.last_run_failed;
            } else {
                if (schedule.last_run_at) {
                    runInfo += i18n.last_completed + ': ' + new Date(schedule.last_run_at).toLocaleString(RECIPE_LOCALE) + ' | ';
                }
                if (schedule.next_run_at) {
                    runInfo += i18n.next_run + ': ' + new Date(schedule.next_run_at).toLocaleString(RECIPE_LOCALE);
                }
            }
            document.getElementById('schedule-last-run').textContent = runInfo;
        } else {
            // No schedule - reset fields
            document.getElementById('schedule-frequency').value = '';
            updateScheduleFields();
            scheduleInfo.style.display = 'none';
        }
    } catch (error) {
        console.error('Error loading schedule:', error);
    }
}

function formatScheduleDescription(schedule) {
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

async function saveSchedule() {
    const scraperId = document.getElementById('schedule-scraper-select').value;
    const frequency = document.getElementById('schedule-frequency').value;

    if (!scraperId) {
        showError(i18n.select_source_first);
        return;
    }

    // If frequency is empty, delete the schedule
    if (!frequency) {
        await deleteSchedule();
        return;
    }

    const hour = parseInt(document.getElementById('schedule-hour').value);
    let dayOfWeek = null;
    let dayOfMonth = null;

    if (frequency === 'weekly') {
        dayOfWeek = parseInt(document.getElementById('schedule-day-of-week').value);
    } else if (frequency === 'monthly') {
        dayOfMonth = parseInt(document.getElementById('schedule-day-of-month').value);
    }

    try {
        const response = await fetch(`/api/schedules/${scraperId}`, {
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
            loadSchedule();
            loadAllSchedules();
        } else {
            showError(data.message_key ? t(data.message_key, data.message_params) : '');
        }
    } catch (error) {
        showError(i18n.error + ': ' + error.message);
    }
}

async function deleteSchedule() {
    const scraperId = document.getElementById('schedule-scraper-select').value;
    if (!scraperId) return;
    await deleteScheduleById(scraperId);
}

async function deleteScheduleById(scraperId) {
    try {
        const response = await fetch(`/api/schedules/${scraperId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: i18n.schedule_removed,
                timer: 1500,
                showConfirmButton: false
            });
            // Reset form if this scraper is currently selected
            const select = document.getElementById('schedule-scraper-select');
            if (select.value === scraperId) {
                document.getElementById('schedule-frequency').value = '';
                updateScheduleFields();
                document.getElementById('schedule-info').style.display = 'none';
            }
            loadAllSchedules();
        } else {
            showError(data.message_key ? t(data.message_key, data.message_params) : '');
        }
    } catch (error) {
        showError(i18n.error + ': ' + error.message);
    }
}

// ============================================
// Event delegation
// ============================================
document.addEventListener('click', function(e) {
    // data-check-id: click on number input checks associated radio
    const checkEl = e.target.closest('[data-check-id]');
    if (checkEl) {
        document.getElementById(checkEl.dataset.checkId).checked = true;
    }

    const el = e.target.closest('[data-action]');
    if (!el) return;
    if (el.dataset.stopProp === 'true') e.stopPropagation();
    switch (el.dataset.action) {
        case 'addMyRecipeUrl': addMyRecipeUrl(); break;
        case 'runScraper': runScraper(); break;
        case 'cancelScraper': cancelScraper(); break;
        case 'cancelImageDownloadFromRecipes': cancelImageDownloadFromRecipes(); break;
        case 'saveSchedule': saveSchedule(); break;
        case 'deleteSchedule': deleteSchedule(); break;
        case 'openMyRecipesConfig': openMyRecipesConfig(); break;
        case 'toggleStar': toggleStar(el.dataset.arg, e); break;
        case 'openScraperConfig':
            openScraperConfig(
                el.dataset.id, el.dataset.name,
                el.dataset.maxFull === 'null' ? null : parseInt(el.dataset.maxFull),
                el.dataset.maxIncr === 'null' ? null : parseInt(el.dataset.maxIncr)
            ); break;
        case 'moveScraper': moveScraper(el.dataset.arg, el.dataset.enable === 'true'); break;
        case 'clearScraperData': clearScraperData(el.dataset.id, el.dataset.name, parseInt(el.dataset.count)); break;
        case 'deleteMyRecipeUrl': deleteMyRecipeUrl(parseInt(el.dataset.arg)); break;
        case 'sortScheduleTable': sortScheduleTable(el.dataset.arg); break;
        case 'selectScheduleScraper': selectScheduleScraper(el.dataset.arg); break;
        case 'deleteScheduleById': e.stopPropagation(); deleteScheduleById(el.dataset.arg); break;
    }
});

document.addEventListener('change', function(e) {
    const el = e.target;
    if (el.dataset.change) {
        switch (el.dataset.change) {
            case 'updateTimeEstimates': updateTimeEstimates(); break;
            case 'loadSchedule': loadSchedule(); break;
            case 'updateScheduleFields': updateScheduleFields(); break;
        }
    }
});

// data-focus-check-id: focusing number input checks associated radio
document.addEventListener('focus', function(e) {
    const el = e.target.closest('[data-focus-check-id]');
    if (el) {
        document.getElementById(el.dataset.focusCheckId).checked = true;
    }
}, true);
