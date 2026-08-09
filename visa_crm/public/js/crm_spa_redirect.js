/**
 * visa_crm/public/js/crm_spa_redirect.js
 *
 * Intercepts Vue Router (Frappe CRM SPA) navigation to the Leads list route
 * and redirects immediately to the custom Lead Management Desk Page (/app/lead-management).
 *
 * Scoping rules:
 *   - Matches list routes: /crm/leads, /crm/leads/view/list, /crm/leads/view/kanban, etc.
 *   - EXEMPTS individual lead detail URLs: /crm/leads/CRM-LEAD-2026-00126#activity
 *   - EXEMPTS all other CRM sections: /crm/contacts, /crm/deals, /crm/dashboard, /crm/notes, etc.
 *   - EXEMPTS Desk routes (/app/*)
 */
(function () {
    'use strict';

    var TARGET_URL = '/app/lead-management';

    function isLeadsListRoute(pathname) {
        if (!pathname) return false;

        // Normalize pathname: remove trailing slashes for comparison
        var path = pathname.replace(/\/+$/, '');

        // Must start with /crm
        if (path !== '/crm' && path.indexOf('/crm/') !== 0) return false;

        var relative = path.slice(4).replace(/^\//, ''); // strip /crm or /crm/

        // Bare /crm/leads or /crm/leads/view/*
        if (relative === 'leads') return true;

        if (relative.indexOf('leads/') === 0) {
            var sub = relative.slice(6); // strip "leads/"
            if (sub.indexOf('view/') === 0 || sub === 'view') {
                return true;
            }
            // Individual lead detail record names (e.g. CRM-LEAD-2026-00126) -> DO NOT REDIRECT
            return false;
        }

        return false;
    }

    function redirectIfMatching(urlOrPath) {
        try {
            var parsedPath = urlOrPath;
            if (urlOrPath && (urlOrPath.indexOf('http://') === 0 || urlOrPath.indexOf('https://') === 0 || urlOrPath.indexOf('/') === 0)) {
                var a = document.createElement('a');
                a.href = urlOrPath;
                parsedPath = a.pathname;
            }

            if (isLeadsListRoute(parsedPath)) {
                if (window.location.pathname !== TARGET_URL) {
                    window.location.href = TARGET_URL;
                }
            }
        } catch (e) {
            console.error('[visa_crm] Error checking CRM SPA redirect:', e);
        }
    }

    // 1. Initial page load check
    redirectIfMatching(window.location.pathname);

    // 2. Monkey-patch history.pushState (used by Vue Router during client-side navigation)
    var _pushState = history.pushState;
    if (_pushState && !_pushState._patched) {
        history.pushState = function (state, title, url) {
            var res = _pushState.apply(this, arguments);
            if (url) redirectIfMatching(url);
            return res;
        };
        history.pushState._patched = true;
    }

    // 3. Monkey-patch history.replaceState (used by Vue Router during route initialization)
    var _replaceState = history.replaceState;
    if (_replaceState && !_replaceState._patched) {
        history.replaceState = function (state, title, url) {
            var res = _replaceState.apply(this, arguments);
            if (url) redirectIfMatching(url);
            return res;
        };
        history.replaceState._patched = true;
    }

    // 4. Listen to popstate (browser back/forward in SPA)
    window.addEventListener('popstate', function () {
        redirectIfMatching(window.location.pathname);
    });

})();
