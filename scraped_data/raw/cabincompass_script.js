// Defer background image loading
document.addEventListener('DOMContentLoaded', () => {
    // Load background image after page content
    const bgImage = new Image();
    bgImage.src = 'p2.png';
    bgImage.onload = () => document.body.classList.add('bg-loaded');

    initializeGoogleAuth();
});

// Cache DOM elements
const elements = {
    appContainer: document.getElementById("app-container"),
    authGate: document.getElementById("auth-gate"),
    authError: document.getElementById("auth-error"),
    googleSignIn: document.getElementById("google-signin"),
    signOutButton: document.getElementById("sign-out-button"),
    teacherSearch: document.getElementById("teacher-search"),
    searchResults: document.getElementById("search-results"),
    getDirectionsButton: document.getElementById("get-directions"),
    directionsDisplay: document.getElementById("directions-display")
};

// API endpoints and helpers with multi-host fallback
let API_BASES = [];
function refreshApiBases() {
    const configuredApiBase = window.__APP_CONFIG__?.apiBase || null;
    API_BASES = Array.from(new Set(
        [configuredApiBase, window.location.origin].filter(Boolean)
    ));
}
refreshApiBases();

const API_PATHS = {
    search: '/api/search',
    directions: '/api/directions/',
    image: '/api/images/',
    log: '/api/log'
};

// State management
let state = {
    selectedTeacher: null,
    searchTimeout: null,
    idToken: null,
    isAuthenticated: false,
    user: null,
    apiBase: null
};

const authOptions = {
    emails: new Set(),
    domains: new Set()
};

function applyInlineAuthConfig(target) {
    if (!window.CABIN_COMPASS_CLIENT_ID) return target;
    const opts = window.CABIN_COMPASS_AUTH_OPTIONS || {};
    const allowedDomains = opts.allowedDomains || (opts.allowedDomain ? [opts.allowedDomain] : []);
    const allowedEmails = opts.allowedEmails || [];
    return {
        ...target,
        googleClientId: window.CABIN_COMPASS_CLIENT_ID,
        apiBase: opts.apiBase || target.apiBase,
        allowedDomains,
        allowedEmails
    };
}

function configureAuthOptions(config) {
    if (!config) return;
    const normalize = (value) => (value || '').toLowerCase().trim();
    const emails = (config.allowedEmails || []).map(normalize).filter(Boolean);
    const domains = (config.allowedDomains || []).map(normalize).filter(Boolean);
    authOptions.emails = new Set(emails);
    authOptions.domains = new Set(domains);
    window.AUTH_OPTIONS = {
        allowedEmails: emails,
        allowedDomains: domains
    };
}

function isEmailAllowed(email) {
    const normalized = (email || '').toLowerCase();
    const domain = normalized.split('@')[1] || '';
    const hasEmailRules = authOptions.emails.size > 0;
    const hasDomainRules = authOptions.domains.size > 0;
    if (!hasEmailRules && !hasDomainRules) {
        return true;
    }
    const emailAllowed = !hasEmailRules || authOptions.emails.has(normalized);
    const domainAllowed = !hasDomainRules || (domain && authOptions.domains.has(domain));
    return emailAllowed || domainAllowed;
}

function normalizePath(path) {
    if (!path.startsWith('/')) {
        return '/' + path;
    }
    return path;
}

function getCurrentApiBase() {
    return state.apiBase || sessionStorage.getItem(API_BASE_OVERRIDE_KEY) || API_BASES[0];
}

async function fetchWithFallback(path, options = {}) {
    const normalized = normalizePath(path);
    let lastError = null;
    for (const base of API_BASES) {
        try {
            const url = new URL(normalized, base).toString();
            const response = await fetch(url, options);
            if (response.ok) {
                state.apiBase = base;
                sessionStorage.setItem(API_BASE_OVERRIDE_KEY, base);
                response.usedBase = base;
                return response;
            }
            lastError = new Error(`Request failed with status ${response.status}`);
            continue;
        } catch (error) {
            lastError = error;
        }
    }
    throw lastError || new Error('All API endpoints failed');
}

const AUTH_STORAGE_KEY = 'cabincompass_id_token';
const API_BASE_OVERRIDE_KEY = 'API_BASE_OVERRIDE';

function showAuthGate(message) {
    if (elements.appContainer) {
        elements.appContainer.style.display = 'none';
    }
    if (elements.authGate) {
        elements.authGate.style.display = 'flex';
    }
    if (elements.signOutButton) {
        elements.signOutButton.style.display = 'none';
    }
    if (elements.authError) {
        if (message) {
            elements.authError.textContent = message;
            elements.authError.style.display = 'block';
        } else {
            elements.authError.textContent = '';
            elements.authError.style.display = 'none';
        }
    }
}

function hideAuthGate() {
    if (elements.authGate) {
        elements.authGate.style.display = 'none';
    }
    if (elements.appContainer) {
        elements.appContainer.style.display = 'block';
    }
    if (elements.signOutButton) {
        elements.signOutButton.style.display = 'inline-flex';
    }
    if (elements.authError) {
        elements.authError.style.display = 'none';
        elements.authError.textContent = '';
    }
}

function decodeIdToken(idToken) {
    try {
        const parts = idToken.split('.');
        if (parts.length !== 3) return null;
        const json = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
        return json || null;
    } catch (_e) { return null; }
}

async function updateAuthState({ idToken, user = null }) {
    state.idToken = idToken;
    state.isAuthenticated = true;
    state.user = user;
    sessionStorage.setItem(AUTH_STORAGE_KEY, idToken);
    hideAuthGate();
    try {
        // Probe backend to log login (and learn working API base)
        const headers = {
            'Authorization': `Bearer ${idToken}`,
            'Content-Type': 'application/json'
        };
        let logged = false;
        for (const base of API_BASES) {
            try {
                const url = new URL('/api/auth/me', base).toString();
                console.log('[frontend] Attempting to authenticate with:', base);
                const res = await fetch(url, {
                    method: 'GET',
                    headers: headers,
                    credentials: 'include',
                    mode: 'cors'
                });
                console.log('[frontend] Auth response status:', res.status, res.statusText);
                if (res.ok) {
                    const data = await res.json();
                    console.log('[frontend] Authentication successful:', data);
                    sessionStorage.setItem(API_BASE_OVERRIDE_KEY, base);
                    logged = true;
                    break;
                } else {
                    const errorText = await res.text();
                    console.error('[frontend] Auth failed:', res.status, errorText);
                }
            } catch (e) {
                console.error('[frontend] Auth request error:', e);
            }
        }
        if (!logged) {
            const payload = decodeIdToken(idToken) || {};
            const email = payload.email || null;
            const name = payload.name || null;
            for (const base of API_BASES) {
                try {
                    const url = new URL('/api/log', base).toString();
                    const res = await fetch(url, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ action: 'google_login_unverified', email, name })
                    });
                    if (res.ok) {
                        sessionStorage.setItem(API_BASE_OVERRIDE_KEY, base);
                        break;
                    }
                } catch (_e) { }
            }
        }
    } catch (_e) { }
}

function clearAuthentication({ message, suppressPrompt } = {}) {
    state.idToken = null;
    state.isAuthenticated = false;
    state.user = null;
    sessionStorage.removeItem(AUTH_STORAGE_KEY);
    showAuthGate(message);
    if (!suppressPrompt && window.google?.accounts?.id) {
        window.google.accounts.id.disableAutoSelect();
        window.google.accounts.id.prompt();
    }
}

async function handleCredentialResponse(response) {
    try {
        if (!response || !response.credential) {
            throw new Error('Missing credential response');
        }
        const payload = decodeIdToken(response.credential) || {};
        if (!isEmailAllowed(payload.email || '')) {
            showAuthGate('This Google account is not authorized for CabinCompass.');
            if (window.google?.accounts?.id) {
                window.google.accounts.id.disableAutoSelect();
            }
            return;
        }
        await updateAuthState({ idToken: response.credential });
    } catch (error) {
        console.error("Error handling Google credential:", error);
        showAuthGate('Unable to complete sign-in. Please try again.');
    }
}

async function loadAppConfig() {
    if (window.CABIN_COMPASS_CLIENT_ID) {
        window.__APP_CONFIG__ = applyInlineAuthConfig(window.__APP_CONFIG__ || {});
    }
    if (window.__APP_CONFIG__?.googleClientId) {
        refreshApiBases();
        configureAuthOptions(window.__APP_CONFIG__);
        return window.__APP_CONFIG__;
    }
    const candidates = [
        `${window.location.origin}/config.json`,
        `https://find-my-teacher.onrender.com/config.json`
    ];
    for (const url of candidates) {
        try {
            const res = await fetch(url, { cache: 'no-store' });
            if (!res.ok) continue;
            const json = await res.json();
            if (json && json.googleClientId) {
                window.__APP_CONFIG__ = applyInlineAuthConfig(json);
                refreshApiBases();
                configureAuthOptions(window.__APP_CONFIG__);
                return json;
            }
        } catch (_e) { }
    }
    // Fallback via dynamic script injection to bypass CORS
    const scriptCandidates = [
        `${window.location.origin}/config.js`,
        `https://find-my-teacher.onrender.com/config.js`
    ];
    for (const src of scriptCandidates) {
        try {
            await new Promise((resolve, reject) => {
                const s = document.createElement('script');
                s.src = src;
                s.async = true;
                s.onload = () => resolve();
                s.onerror = reject;
                document.head.appendChild(s);
            });
            if (window.__APP_CONFIG__?.googleClientId) {
                window.__APP_CONFIG__ = applyInlineAuthConfig(window.__APP_CONFIG__);
                refreshApiBases();
                configureAuthOptions(window.__APP_CONFIG__);
                return window.__APP_CONFIG__;
            }
        } catch (_e) { }
    }
    return null;
}

async function initializeGoogleAuth() {
    const loaded = await loadAppConfig();
    const config = (loaded || window.__APP_CONFIG__) || null;
    configureAuthOptions(config);
    const clientId = config?.googleClientId;
    if (!clientId) {
        console.error('Google client ID is not configured.');
        showAuthGate('Google sign-in is unavailable. Contact the administrator.');
        return;
    }

    const attemptInit = () => {
        if (!(window.google && window.google.accounts && window.google.accounts.id)) {
            setTimeout(attemptInit, 100);
            return;
        }

        window.google.accounts.id.initialize({
            client_id: clientId,
            callback: handleCredentialResponse,
            auto_select: true,
            ux_mode: 'popup'
        });

        if (elements.googleSignIn && elements.googleSignIn.children.length === 0) {
            window.google.accounts.id.renderButton(elements.googleSignIn, {
                theme: 'filled_blue',
                size: 'large',
                type: 'standard',
            });
        }

        const storedToken = sessionStorage.getItem(AUTH_STORAGE_KEY);
        if (storedToken) {
            updateAuthState({ idToken: storedToken });
        } else {
            showAuthGate();
            window.google.accounts.id.prompt();
        }
    };

    attemptInit();
}

if (elements.signOutButton) {
    elements.signOutButton.addEventListener('click', () => {
        clearAuthentication({ message: 'Signed out successfully.', suppressPrompt: true });
        sessionStorage.removeItem('API_BASE_OVERRIDE');
    });
}

// Debounce function
const debounce = (func, wait) => {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
};

// Add a loading spinner element to the DOM
const searchBox = document.getElementById('teacher-search');
let searchSpinner = document.getElementById('search-loading-spinner');
if (!searchSpinner && searchBox) {
    searchSpinner = document.createElement('span');
    searchSpinner.id = 'search-loading-spinner';
    searchSpinner.style.display = 'none';
    searchSpinner.style.position = 'absolute';
    searchSpinner.style.right = '18px';
    searchSpinner.style.top = '50%';
    searchSpinner.style.transform = 'translateY(-50%)';
    searchSpinner.innerHTML = `<svg width="22" height="22" viewBox="0 0 50 50"><circle cx="25" cy="25" r="20" fill="none" stroke="#007BFF" stroke-width="5" stroke-linecap="round" stroke-dasharray="31.4 31.4" transform="rotate(-90 25 25)"><animateTransform attributeName="transform" type="rotate" from="0 25 25" to="360 25 25" dur="1s" repeatCount="indefinite"/></circle></svg>`;
    searchBox.parentNode.style.position = 'relative';
    searchBox.parentNode.appendChild(searchSpinner);
}

if (elements.teacherSearch && elements.searchResults) {
    async function searchTeachers(query) {
        try {
            if (query.length < 2) {
                elements.searchResults.style.display = 'none';
                if (searchSpinner) searchSpinner.style.display = 'none';
                return;
            }
            if (searchSpinner) searchSpinner.style.display = 'inline-block';
            const response = await fetchWithFallback(`${API_PATHS.search}?query=${encodeURIComponent(query)}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            const filteredTeachers = data.teachers.filter(teacher =>
                teacher.name.toLowerCase().includes(query.toLowerCase())
            );
            displaySearchResults(filteredTeachers);
        } catch (error) {
            console.error("Error searching teachers:", error);
            elements.searchResults.innerHTML = '<div class="search-result-item">Failed to load teachers. Please check your connection or try again later.</div>';
            elements.searchResults.style.display = 'block';
        } finally {
            if (searchSpinner) searchSpinner.style.display = 'none';
        }
    }

    function displaySearchResults(teachers) {
        elements.searchResults.innerHTML = '';

        if (!teachers.length) {
            elements.searchResults.innerHTML = '<div class="search-result-item">No matching teachers found</div>';
        } else {
            const fragment = document.createDocumentFragment();
            teachers.forEach(teacher => {
                const div = document.createElement('div');
                div.className = 'search-result-item';

                // Highlight the matching text
                const teacherName = teacher.name || 'Unknown';
                const searchQuery = elements.teacherSearch.value.toLowerCase();
                const index = teacherName.toLowerCase().indexOf(searchQuery);

                let highlightedName = teacherName;
                if (index !== -1 && teacherName !== 'Unknown') {
                    const before = teacherName.substring(0, index);
                    const match = teacherName.substring(index, index + searchQuery.length);
                    const after = teacherName.substring(index + searchQuery.length);
                    highlightedName = `${before}<strong>${match}</strong>${after}`;
                }

                div.innerHTML = `
                    <div class="teacher-name">${highlightedName}</div>
                `;

                div.addEventListener('click', () => {
                    state.selectedTeacher = teacher;
                    elements.teacherSearch.value = teacher.name;
                    elements.searchResults.style.display = 'none';
                    fetchAndDisplayDirections();
                });
                fragment.appendChild(div);
            });
            elements.searchResults.appendChild(fragment);
        }

        elements.searchResults.style.display = 'block';
    }

    // Optimized event handlers with debouncing
    elements.teacherSearch.addEventListener('input', debounce((e) => {
        const query = e.target.value.trim();
        if (query.length < 2) {
            elements.searchResults.style.display = 'none';
            state.selectedTeacher = null;
            return;
        }
        searchTeachers(query);
    }, 300));

    elements.teacherSearch.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && state.selectedTeacher) {
            getDirections();
        }
    });

    // Use event delegation for document click
    document.addEventListener('click', (e) => {
        if (!elements.teacherSearch.contains(e.target) && !elements.searchResults.contains(e.target)) {
            elements.searchResults.style.display = 'none';
        }
    });
}

// Move these functions to top-level scope
async function fetchAndDisplayDirections() {
    if (!state.selectedTeacher) return;
    if (!state.isAuthenticated || !state.idToken) {
        showAuthGate();
        return;
    }
    try {
        elements.directionsDisplay.innerHTML = '';
        const response = await fetchWithFallback(`${API_PATHS.directions}${encodeURIComponent(state.selectedTeacher.name)}`);
        const data = await response.json();
        const directionsContent = document.createElement('div');
        directionsContent.id = 'directions-content';
        directionsContent.className = 'teacher-card';
        directionsContent.innerHTML = `
            <div class="teacher-info">
                <div class="info-item"><strong>👤 Name:</strong> <span>${state.selectedTeacher.name || 'Unknown'}</span></div>
                <div class="info-item"><strong>🏢 Branch:</strong> <span>${data.branch || 'N/A'}</span></div>
                <div class="info-item"><strong>🏬 Floor:</strong> <span>${data.floor || 'N/A'}</span></div>
            </div>
            <div class="info-item"><strong>🧭 Directions:</strong><br><span id="directions-text-content">${data.directions || 'N/A'}</span></div>
            <div id="directions-image-container" style="display:none"></div>
        `;
        elements.directionsDisplay.appendChild(directionsContent);
        const imageContainer = document.getElementById("directions-image-container");
        if (!data.error && data.imageUrl) {
            imageContainer.innerHTML = '';
            let imageUrl = data.imageUrl;
            const base = getCurrentApiBase();
            if (base) {
                try {
                    imageUrl = new URL(imageUrl, base).toString();
                } catch (error) {
                    console.warn('Unable to normalize image URL:', error.message);
                }
            }
            imageUrl += `?t=${Date.now()}`;
            const img = new Image();
            img.src = imageUrl;
            img.alt = state.selectedTeacher.name;
            img.className = 'teacher-image';
            img.onload = () => {
                imageContainer.style.display = 'block';
            };
            img.onerror = () => {
                imageContainer.innerHTML = '<p>Image unavailable</p>';
                imageContainer.style.display = 'block';
            };
            imageContainer.appendChild(img);
        } else if (data.error) {
            imageContainer.innerHTML = `<p style='color:red;'>${data.error}</p>`;
            imageContainer.style.display = 'block';
        }
        elements.directionsDisplay.style.display = "block";
    } catch (error) {
        console.error("Error fetching directions:", error);
        elements.directionsDisplay.innerHTML = '<p>Failed to fetch directions. Please try again.</p>';
        elements.directionsDisplay.style.display = "block";
    }
}

async function getDirections() {
    if (!state.selectedTeacher) {
        alert("Please select a teacher from the search results.");
        return;
    }
    try {
        elements.directionsDisplay.innerHTML = '';
        sessionStorage.setItem('selectedTeacher', JSON.stringify(state.selectedTeacher));
        window.location.reload();
    } catch (error) {
        console.error("Error:", error);
        alert("Failed to process request. Please try again.");
    }
}

// Handle page reload and auto-display directions
document.addEventListener('DOMContentLoaded', () => {
    // First clear any existing content
    if (elements.directionsDisplay) {
        elements.directionsDisplay.innerHTML = '';
    }

    const storedTeacher = sessionStorage.getItem('selectedTeacher');
    if (storedTeacher) {
        try {
            state.selectedTeacher = JSON.parse(storedTeacher);
            sessionStorage.removeItem('selectedTeacher');

            if (elements.teacherSearch) {
                elements.teacherSearch.value = state.selectedTeacher.name;
            }

            if (elements.getDirectionsButton && elements.directionsDisplay) {
                const attemptFetchDirections = () => {
                    if (state.isAuthenticated && state.idToken) {
                        fetchAndDisplayDirections();
                        return true;
                    }
                    return false;
                };

                if (!attemptFetchDirections()) {
                    const authInterval = setInterval(() => {
                        if (attemptFetchDirections()) {
                            clearInterval(authInterval);
                        }
                    }, 200);
                }
            }
        } catch (error) {
            console.error("Error processing stored teacher:", error);
        }
    }
});

const aboutBtn = document.getElementById('about-btn');
const aboutDisplay = document.getElementById('about-display');
if (aboutBtn && aboutDisplay) {
    aboutBtn.addEventListener('click', () => {
        if (aboutDisplay.style.display === 'none' || aboutDisplay.style.display === '') {
            aboutDisplay.style.display = 'block';
        } else {
            aboutDisplay.style.display = 'none';
        }
    });
}

// Keep this inside the if block
if (elements.getDirectionsButton && elements.directionsDisplay) {
    elements.getDirectionsButton.addEventListener('click', getDirections);
}

// Bug Report button handler
const bugReportBtn = document.getElementById('bug-report-btn');
if (bugReportBtn) {
    bugReportBtn.addEventListener('click', () => {
        window.open('https://forms.gle/eZ4DYbPMtEuXT2Qo6', '_blank');
    });
}


