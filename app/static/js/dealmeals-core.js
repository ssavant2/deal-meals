// Shared Deal Meals browser helpers. Loaded as a classic script so existing
// templates can keep using the current global helper names during stabilization.

window.DealMeals = window.DealMeals || {};

// Debug logger: silent by default, enable with localStorage.setItem('debug','1')
const _dbg = localStorage.getItem('debug');
const _noop = () => {};
const dbg = {
    log: _dbg ? console.log.bind(console) : _noop,
    warn: _dbg ? console.warn.bind(console) : _noop
};

function escapeHtml(str) {
    if (str == null) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

function escapeAttr(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function safeUrl(url) {
    if (!url) return '';
    const str = String(url).trim();
    if (!str || /[\u0000-\u001F\u007F]/.test(str)) return '';

    // Allow app-local absolute paths, but not protocol-relative URLs.
    if (str.startsWith('/')) {
        return str.startsWith('//') ? '' : str;
    }

    try {
        const parsed = new URL(str);
        return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? str : '';
    } catch {
        return '';
    }
}

function dmInterpolateMessage(template, params = {}, options = {}) {
    let str = template == null ? '' : String(template);
    const transformParam = options.transformParam || ((_, value) => value);
    const escapeParams = Boolean(options.escapeParams);

    for (const [key, value] of Object.entries(params || {})) {
        let replacement = transformParam(key, value);
        if (replacement == null) replacement = '';
        replacement = String(replacement);
        if (escapeParams) replacement = escapeHtml(replacement);
        str = str.replace(`{${key}}`, replacement);
    }
    return str;
}

function dmTranslateMessage(key, params = {}, options = {}) {
    const messages = options.messages || window.DealMealsI18n || {};
    const template = Object.prototype.hasOwnProperty.call(messages, key)
        ? messages[key]
        : key;
    return dmInterpolateMessage(template, params, options);
}

function dmCreateTranslator(messages, options = {}) {
    return function translateWithMessages(key, params = {}) {
        return dmTranslateMessage(key, params, { ...options, messages });
    };
}

function dmResolveMessage(data, options = {}) {
    if (!data) return options.fallback || '';
    if (data.message_key) {
        return dmTranslateMessage(data.message_key, data.message_params || {}, options);
    }
    return data.message || data.error || options.fallback || '';
}

function getTheme() {
    const match = document.cookie.match(/(?:^|; )theme=([^;]*)/);
    return match ? match[1] : 'light';
}

function setTheme(theme) {
    const expires = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toUTCString();
    document.cookie = `theme=${theme}; expires=${expires}; path=/; SameSite=Lax`;
    document.documentElement.setAttribute('data-bs-theme', theme);
    updateThemeIcon();
    updateThemeRadios();
}

function toggleTheme() {
    const current = getTheme();
    setTheme(current === 'light' ? 'dark' : 'light');
}

function updateThemeIcon() {
    const icon = document.getElementById('theme-icon');
    if (icon) {
        const theme = getTheme();
        icon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    }
}

function updateThemeRadios() {
    const theme = getTheme();
    const lightRadio = document.getElementById('theme-light');
    const darkRadio = document.getElementById('theme-dark');
    if (lightRadio) lightRadio.checked = (theme === 'light');
    if (darkRadio) darkRadio.checked = (theme === 'dark');
}

function getFontSize() {
    const match = document.cookie.match(/(?:^|; )fontSize=([^;]*)/);
    return match ? parseInt(match[1]) : 16;
}

function setFontSize(size) {
    size = Math.max(12, Math.min(24, size));
    const expires = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toUTCString();
    document.cookie = `fontSize=${size}; expires=${expires}; path=/; SameSite=Lax`;
    document.documentElement.style.fontSize = size + 'px';

    const slider = document.getElementById('font-size-slider');
    if (slider) slider.value = size;
    const label = document.getElementById('font-size-label');
    if (label) label.textContent = size + 'px';
}

function getHighContrast() {
    const match = document.cookie.match(/(?:^|; )highContrast=([^;]*)/);
    return match ? match[1] === 'true' : false;
}

function setHighContrast(enabled) {
    const expires = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toUTCString();
    document.cookie = `highContrast=${enabled}; expires=${expires}; path=/; SameSite=Lax`;
    if (enabled) {
        document.documentElement.setAttribute('data-contrast', 'high');
    } else {
        document.documentElement.removeAttribute('data-contrast');
    }

    const cb = document.getElementById('high-contrast-toggle');
    if (cb) cb.checked = enabled;
}

function getLanguage() {
    const match = document.cookie.match(/(?:^|; )language=([^;]*)/);
    return match ? match[1] : 'sv';
}

function setLanguage(lang) {
    const expires = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toUTCString();
    document.cookie = `language=${lang}; expires=${expires}; path=/; SameSite=Lax`;
    window.location.reload();
}

function highlightActiveNavLink() {
    const currentPath = window.location.pathname;
    document.querySelectorAll('.navbar-nav .nav-link').forEach(link => {
        if (link.classList.contains('dropdown-toggle')) return;
        const href = link.getAttribute('href');
        if (href === currentPath || (currentPath === '/' && href === '/')) {
            link.classList.add('active');
        }
    });
}

function updateSpellCheckBadge() {
    fetch('/api/spell-corrections/count')
        .then(r => r.json())
        .then(data => {
            if (data.success && data.count > 0) {
                const badge = document.getElementById('spell-badge');
                if (badge) {
                    badge.textContent = data.count;
                    badge.style.display = '';
                }
            }
        })
        .catch(() => {});
}

document.addEventListener('DOMContentLoaded', function() {
    highlightActiveNavLink();
    updateThemeIcon();
    updateThemeRadios();
    updateSpellCheckBadge();
});

document.addEventListener('click', function(e) {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    if (el.dataset.action === 'setLanguage') {
        e.preventDefault();
        setLanguage(el.dataset.arg);
    }
});

Object.assign(window.DealMeals, {
    dbg,
    escapeHtml,
    escapeAttr,
    safeUrl,
    interpolateMessage: dmInterpolateMessage,
    translateMessage: dmTranslateMessage,
    createTranslator: dmCreateTranslator,
    resolveMessage: dmResolveMessage,
    getTheme,
    setTheme,
    toggleTheme,
    updateThemeIcon,
    updateThemeRadios,
    getFontSize,
    setFontSize,
    getHighContrast,
    setHighContrast,
    getLanguage,
    setLanguage,
    highlightActiveNavLink,
    updateSpellCheckBadge,
});
